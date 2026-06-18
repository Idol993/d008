import os
import sys
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import config
from models import init_db, get_session
from release_manager import ReleaseManager
from approval_manager import ApprovalManager
from grayscale_manager import GrayscaleManager
from monitor_rollback import MonitorManager, RollbackManager
from report_notification import ReportGenerator, NotificationManager
from rollback_drill import RollbackDrillManager
from weekly_report import WeeklyReportManager
from history_export import HistoryQuery, BatchExport
from audit_logger import AuditLogger


class InsuranceReleaseSystem:
    def __init__(self):
        init_db()
        self.scheduler = None
        self._init_stable_version()

    def _init_stable_version(self):
        session = get_session()
        try:
            from models import StableVersion
            count = session.query(StableVersion).count()
            if count == 0:
                sv = StableVersion(
                    version='v1.0.0-STABLE',
                    description='初始监管认可稳定版本',
                    regulatory_approved=True,
                    approval_date=datetime.now() - timedelta(days=30),
                    insurance_types=config.INSURANCE_TYPES,
                    is_active=True
                )
                session.add(sv)
                session.commit()
        finally:
            session.close()

    def start_scheduler(self):
        self.scheduler = BackgroundScheduler(timezone='Asia/Shanghai')

        self.scheduler.add_job(
            self._monitor_job,
            'interval',
            minutes=config.MONITOR_INTERVAL_MINUTES,
            id='monitor_job',
            replace_existing=True
        )

        self.scheduler.add_job(
            self._weekly_report_job,
            CronTrigger(
                day_of_week=config.WEEKLY_REPORT_DAY,
                hour=config.WEEKLY_REPORT_TIME.hour,
                minute=config.WEEKLY_REPORT_TIME.minute
            ),
            id='weekly_report_job',
            replace_existing=True
        )

        self.scheduler.add_job(
            self._grayscale_advance_job,
            'interval',
            minutes=30,
            id='grayscale_advance_job',
            replace_existing=True
        )

        self.scheduler.start()
        print(f'[系统] 调度器已启动')
        print(f'[系统] 监控任务: 每 {config.MONITOR_INTERVAL_MINUTES} 分钟执行')
        print(f'[系统] 周报任务: 每周一 {config.WEEKLY_REPORT_TIME.strftime("%H:%M")} 生成')
        print(f'[系统] 灰度推进检查: 每 30 分钟执行')

        return self.scheduler

    def stop_scheduler(self):
        if self.scheduler:
            self.scheduler.shutdown()
            print('[系统] 调度器已停止')

    def _monitor_job(self):
        print(f'[监控] {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} 开始执行监控任务...')
        session = get_session()
        try:
            from models import ReleaseRequest
            active_releases = session.query(ReleaseRequest).filter(
                ReleaseRequest.status.in_(['grayscaling', 'fully_released'])
            ).all()

            for release in active_releases:
                if release.rollback_triggered:
                    continue

                metrics = MonitorManager.collect_metrics(release.id)
                print(f'[监控] 发布 {release.id} ({release.version}): '
                      f'通过率={metrics["underwriting_pass_rate"]:.2%}, '
                      f'理赔延迟={metrics["claim_process_delay_seconds"]:.0f}s, '
                      f'异常率={metrics["claim_abnormal_rate"]:.2%}, '
                      f'泄露风险={metrics["info_leak_risk"]:.4%}, '
                      f'超阈值={"是" if metrics["threshold_exceeded"] else "否"}')

                if metrics['threshold_exceeded']:
                    print(f'[告警] 发布 {release.id} 指标超出阈值，触发合规回滚!')
                    self._trigger_auto_rollback(release.id, metrics)
        except Exception as e:
            print(f'[监控] 任务执行异常: {e}')
        finally:
            session.close()

    def _trigger_auto_rollback(self, release_id, metrics):
        try:
            threshold_details = metrics.get('threshold_details', {})
            exceeded_items = []
            for key, detail in threshold_details.items():
                if detail.get('exceeded'):
                    exceeded_items.append(f'{key}={detail["value"]}')
            reason = f'监控指标超出阈值: {"; ".join(exceeded_items)}'

            result = RollbackManager.trigger_rollback(release_id, reason, 'auto')

            ReportGenerator.generate_rollback_report(result['rollback_id'])

            NotificationManager.send_rollback_notifications(result['rollback_id'])

            RollbackManager.restart_monitoring_after_rollback(release_id)

            print(f'[回滚] 自动回滚完成: {result}')
        except Exception as e:
            print(f'[回滚] 自动回滚失败: {e}')

    def _weekly_report_job(self):
        print(f'[周报] {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} 开始生成周报...')
        try:
            result = WeeklyReportManager.generate_weekly_report()
            print(f'[周报] 生成完成: {result}')
        except Exception as e:
            print(f'[周报] 生成失败: {e}')

    def _grayscale_advance_job(self):
        session = get_session()
        try:
            from models import ReleaseRequest
            grayscaling = session.query(ReleaseRequest).filter_by(
                status='grayscaling'
            ).all()

            for release in grayscaling:
                if release.rollback_triggered:
                    continue
                result = GrayscaleManager.check_and_advance_if_ready(release.id)
                if result:
                    print(f'[灰度] 自动推进: {result.get("message", "")}')
        except Exception as e:
            print(f'[灰度] 推进检查异常: {e}')
        finally:
            session.close()

    def submit_release(self, version, title, description, risk_level,
                       insurance_types, policy_types, submitter):
        release_id = ReleaseManager.create_release(
            version=version, title=title, description=description,
            risk_level=risk_level, insurance_types=insurance_types,
            policy_types=policy_types, submitter=submitter
        )

        precheck_result = ReleaseManager.run_precheck(release_id)

        if precheck_result['all_passed']:
            ApprovalManager.initialize_approvals(release_id)

        return {
            'release_id': release_id,
            'precheck_result': precheck_result
        }

    def approve_release(self, release_id, role, approver, comment='', passed=True):
        result = ApprovalManager.approve(release_id, role, approver, comment, passed)

        if result.get('status') == 'approved':
            GrayscaleManager.start_grayscale(release_id)

        return result

    def trigger_manual_rollback(self, release_id, reason, operator):
        result = RollbackManager.trigger_rollback(release_id, reason, 'manual')

        ReportGenerator.generate_rollback_report(result['rollback_id'])

        NotificationManager.send_rollback_notifications(result['rollback_id'])

        RollbackManager.restart_monitoring_after_rollback(release_id)

        return result

    def create_drill(self, drill_name, drill_type, insurance_types,
                     policy_types, simulated_version, target_version, operator):
        drill_id = RollbackDrillManager.create_drill(
            drill_name=drill_name, drill_type=drill_type,
            insurance_types=insurance_types, policy_types=policy_types,
            simulated_version=simulated_version, target_version=target_version,
            operator=operator
        )

        RollbackDrillManager.generate_drill_plan(drill_id)

        return drill_id

    def execute_drill(self, drill_id):
        RollbackDrillManager.start_drill(drill_id)

        RollbackDrillManager.execute_policy_validation(drill_id)

        result = RollbackDrillManager.complete_drill(drill_id)

        return result

    def query_history(self, **kwargs):
        return HistoryQuery.query_releases(**kwargs)

    def batch_export(self, **kwargs):
        return BatchExport.export_releases(**kwargs)

    def generate_weekly_report_now(self):
        return WeeklyReportManager.generate_weekly_report()


def run_demo():
    print('=' * 70)
    print('  财产/人寿保险核保理赔系统 - 版本发布与合规回滚自动化管理系统')
    print('=' * 70)
    print()

    system = InsuranceReleaseSystem()
    system.start_scheduler()

    try:
        print('[演示] 1. 提交发布申请 - 常规规则迭代 (车险)')
        result1 = system.submit_release(
            version='v2.1.0',
            title='核保规则优化 - 车险风险评估模型升级',
            description='升级车险核保风险评估模型，提升核保准确率',
            risk_level='routine',
            insurance_types=['auto'],
            policy_types=['individual'],
            submitter='uw_engineer1'
        )
        print(f'  发布ID: {result1["release_id"]}')
        print(f'  前置检查结果: {"通过" if result1["precheck_result"]["all_passed"] else "未通过"}')
        for check in result1['precheck_result']['check_results']:
            status = '✓' if check['passed'] else '✗'
            print(f'    {status} {check["name"]}: {check["value"]:.4f} (阈值: {check["threshold"]})')
        print()

        print('[演示] 2. 自动审批通过所有环节')
        from approval_manager import ApprovalManager
        ApprovalManager.batch_auto_approve(result1['release_id'], 'demo_system')
        approval_status = ApprovalManager.get_approval_status(result1['release_id'])
        print(f'  当前状态: {approval_status["overall_status"]}')
        for appr in approval_status['approvals']:
            print(f'    - {appr["role_name"]}: {appr["status"]}')
        print()

        print('[演示] 3. 查看灰度发布状态')
        from grayscale_manager import GrayscaleManager
        gray_status = GrayscaleManager.get_grayscale_status(result1['release_id'])
        print(f'  整体状态: {gray_status["overall_status"]}')
        print(f'  当前险种: {gray_status["current_insurance_type_name"]}')
        print(f'  当前阶段: {gray_status["current_stage"]}')
        print()

        print('[演示] 4. 模拟多次监控数据采集')
        from monitor_rollback import MonitorManager
        for i in range(3):
            metrics = MonitorManager.collect_metrics(result1['release_id'])
            print(f'  第{i+1}次监控: 通过率={metrics["underwriting_pass_rate"]:.2%}, '
                  f'超阈值={"是" if metrics["threshold_exceeded"] else "否"}')
        print()

        print('[演示] 5. 创建回滚演练')
        drill_id = system.create_drill(
            drill_name='Q2合规回滚演练',
            drill_type='monthly',
            insurance_types=['auto', 'life'],
            policy_types=['individual', 'group'],
            simulated_version='v2.1.0',
            target_version='v1.0.0-STABLE',
            operator='compliance_officer1'
        )
        print(f'  演练ID: {drill_id}')
        drill_result = system.execute_drill(drill_id)
        print(f'  演练状态: {drill_result["status"]}')
        print(f'  归档路径: {drill_result["archive_path"]}')
        print()

        print('[演示] 6. 生成每周统计报表')
        weekly = system.generate_weekly_report_now()
        print(f'  周报ID: {weekly.get("report_id")}')
        print(f'  发布成功率: {weekly["release_success_rate"]*100:.2f}%')
        print(f'  回滚次数: {weekly["rollback_count"]}')
        print(f'  PDF报表: {weekly["pdf_path"]}')
        print(f'  Excel报表: {weekly["excel_path"]}')
        print()

        print('[演示] 7. 历史记录查询与导出')
        history = system.query_history(page=1, page_size=10)
        print(f'  共 {history["total"]} 条发布记录')
        for r in history['records'][:3]:
            print(f'    - {r["version"]}: {r["title"]} ({r["risk_level_name"]})')

        export_path = system.batch_export(export_format='excel')
        print(f'  导出文件: {export_path}')
        print()

        print('[演示] 8. 模拟手动触发回滚')
        rollback_result = system.trigger_manual_rollback(
            release_id=result1['release_id'],
            reason='演示用 - 手动触发回滚测试',
            operator='compliance_manager'
        )
        print(f'  回滚ID: {rollback_result["rollback_id"]}')
        print(f'  从版本: {rollback_result["from_version"]}')
        print(f'  回滚至: {rollback_result["to_version"]}')
        print(f'  影响保单: {rollback_result["affected_policies"]} 份')
        print()

        print('[演示] 9. 查询审计日志 (监管相关)')
        audit_logs = AuditLogger.query_logs(
            regulatory_related=True,
            page=1,
            page_size=5
        )
        print(f'  监管相关审计日志共 {audit_logs["total"]} 条')
        for log in audit_logs['logs']:
            print(f'    [{log["operation_time"]}] {log["operation_module"]} - '
                  f'{log["operation_type"]} by {log["operator"]}')
        print()

        print('=' * 70)
        print('  演示完成! 系统调度器继续后台运行中...')
        print('  (按 Ctrl+C 停止调度器并退出)')
        print('=' * 70)

        import time
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print('\n[系统] 正在停止...')
    finally:
        system.stop_scheduler()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='保险核保理赔系统 - 版本发布与合规回滚管理')
    parser.add_argument('--demo', action='store_true', help='运行演示程序')
    parser.add_argument('--start', action='store_true', help='启动系统服务')
    parser.add_argument('--init-db', action='store_true', help='初始化数据库')

    args = parser.parse_args()

    if args.init_db:
        init_db()
        print('数据库初始化完成')
        return

    if args.demo:
        run_demo()
        return

    if args.start:
        system = InsuranceReleaseSystem()
        system.start_scheduler()
        print('系统已启动，按 Ctrl+C 停止')
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            system.stop_scheduler()
        return

    parser.print_help()


if __name__ == '__main__':
    main()
