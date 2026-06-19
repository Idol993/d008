import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta

print('=' * 70)
print('  保险核保理赔系统 - 功能验证测试')
print('=' * 70)
print()

all_passed = True

print('[1/11] 测试数据库初始化...')
try:
    from models import init_db, get_session
    init_db()
    session = get_session()
    session.close()
    print('  ✓ 数据库初始化成功')
except Exception as e:
    print(f'  ✗ 失败: {e}')
    all_passed = False
print()

print('[2/11] 测试审计日志模块...')
try:
    from audit_logger import AuditLogger
    log_id = AuditLogger.log(
        operation_type='test',
        operation_module='test_module',
        operator='test_user',
        operation_detail='测试日志记录',
        regulatory_related=True,
        risk_level='low'
    )
    logs = AuditLogger.query_logs(operation_type='test', page_size=1)
    assert logs['total'] >= 1
    print(f'  ✓ 审计日志正常 (日志ID: {log_id})')
except Exception as e:
    print(f'  ✗ 失败: {e}')
    all_passed = False
print()

print('[3/11] 测试发布管理模块...')
try:
    from release_manager import ReleaseManager
    release_id = ReleaseManager.create_release(
        version='v2.0.0-test',
        title='测试发布 - 核保规则优化',
        description='测试用发布申请',
        risk_level='routine',
        insurance_types=['auto', 'life'],
        policy_types=['individual'],
        submitter='test_user'
    )
    precheck = ReleaseManager.run_precheck(release_id)
    print(f'  ✓ 发布创建成功 (ID: {release_id})')
    print(f'  ✓ 前置检查完成: {"通过" if precheck["all_passed"] else "未通过"}')
    for check in precheck['check_results']:
        status = '✓' if check['passed'] else '✗'
        print(f'    {status} {check["name"]}: {check["value"]:.4f}')
except Exception as e:
    print(f'  ✗ 失败: {e}')
    all_passed = False
    import traceback
    traceback.print_exc()
print()

print('[4/11] 测试审批流程模块...')
try:
    from approval_manager import ApprovalManager
    workflow = ApprovalManager.generate_approval_workflow('routine')
    init_result = ApprovalManager.initialize_approvals(release_id)
    print(f'  ✓ 审批流程初始化成功: {", ".join(workflow)}')

    ApprovalManager.approve(release_id, 'underwriting', 'uw_manager', '同意', True)
    status = ApprovalManager.get_approval_status(release_id)
    print(f'  ✓ 核保审批通过，当前状态: {status["overall_status"]}')

    ApprovalManager.batch_auto_approve(release_id, 'test_system')
    status = ApprovalManager.get_approval_status(release_id)
    print(f'  ✓ 自动审批完成，最终状态: {status["overall_status"]}')
except Exception as e:
    print(f'  ✗ 失败: {e}')
    all_passed = False
    import traceback
    traceback.print_exc()
print()

print('[5/11] 测试灰度发布模块...')
try:
    from grayscale_manager import GrayscaleManager
    from models import get_session, ReleaseRequest
    session = get_session()
    try:
        rel = session.query(ReleaseRequest).filter_by(id=release_id).first()
        current_status = rel.status
    finally:
        session.close()

    if current_status in ('grayscaling', 'fully_released'):
        print(f'  ✓ 灰度发布已在审批通过时自动启动 (当前状态: {current_status})')
    else:
        result = GrayscaleManager.start_grayscale(release_id)
        print(f'  ✓ 灰度发布启动: {result["message"]}')

    status = GrayscaleManager.get_grayscale_status(release_id)
    print(f'  ✓ 当前灰度状态: {status["overall_status"]}')
    print(f'    险种: {status["current_insurance_type_name"]}')
    print(f'    阶段: {status["current_stage"]}')
    if status.get('grayscale_details'):
        for it, stages in status['grayscale_details'].items():
            import config
            it_name = config.INSURANCE_TYPE_NAMES.get(it, it)
            running = [s for s in stages if s['status'] == 'running']
            if running:
                s = running[0]
                print(f'    {it_name} 第{s["stage"]}阶段: {s["percentage"]*100:.0f}% (影响{s["affected_policies_count"]}份)')
except Exception as e:
    print(f'  ✗ 失败: {e}')
    all_passed = False
    import traceback
    traceback.print_exc()
print()

print('[6/11] 测试监控模块...')
try:
    from monitor_rollback import MonitorManager
    metrics = MonitorManager.collect_metrics(release_id)
    print(f'  ✓ 监控指标采集完成')
    print(f'    核保通过率: {metrics["underwriting_pass_rate"]:.2%}')
    print(f'    理赔处理延迟: {metrics["claim_process_delay_seconds"]:.0f}秒')
    print(f'    赔付异常率: {metrics["claim_abnormal_rate"]:.2%}')
    print(f'    信息泄露风险: {metrics["info_leak_risk"]:.4%}')
    print(f'    超阈值: {"是" if metrics["threshold_exceeded"] else "否"}')
except Exception as e:
    print(f'  ✗ 失败: {e}')
    all_passed = False
    import traceback
    traceback.print_exc()
print()

print('[6.5/11] 初始化稳定版本...')
try:
    from release_manager import ReleaseManager
    ReleaseManager.set_stable_version(
        version='v1.0.0-STABLE',
        description='监管认可稳定版本',
        insurance_types=['auto', 'life', 'critical_illness'],
        regulatory_approved=True,
        approval_date=datetime.now() - timedelta(days=30)
    )
    print('  ✓ 稳定版本创建成功')
except Exception as e:
    print(f'  ✗ 失败: {e}')
    all_passed = False
print()

print('[7/11] 测试回滚模块...')
try:
    from monitor_rollback import RollbackManager
    rollback_result = RollbackManager.trigger_rollback(
        release_id, '测试回滚 - 功能验证', 'manual'
    )
    print(f'  ✓ 回滚执行完成 (ID: {rollback_result["rollback_id"]})')
    print(f'    从版本: {rollback_result["from_version"]}')
    print(f'    回滚至: {rollback_result["to_version"]}')
    print(f'    影响保单: {rollback_result["affected_policies"]}份')

    restart_result = RollbackManager.restart_monitoring_after_rollback(release_id)
    print(f'  ✓ 监控重启: {restart_result["status"]}')
except Exception as e:
    print(f'  ✗ 失败: {e}')
    all_passed = False
    import traceback
    traceback.print_exc()
print()

print('[8/11] 测试报告与通知模块...')
try:
    from report_notification import ReportGenerator, NotificationManager
    report_result = ReportGenerator.generate_rollback_report(rollback_result['rollback_id'])
    print(f'  ✓ 回滚报告生成: {report_result["report_filename"]}')

    notif_result = NotificationManager.send_rollback_notifications(rollback_result['rollback_id'])
    print(f'  ✓ 通知已发送 (收件人: {notif_result["sent_count"]}人)')
except Exception as e:
    print(f'  ✗ 失败: {e}')
    all_passed = False
    import traceback
    traceback.print_exc()
print()

print('[9/11] 测试回滚演练模块...')
try:
    from rollback_drill import RollbackDrillManager
    drill_id = RollbackDrillManager.create_drill(
        drill_name='功能验证演练',
        drill_type='test',
        insurance_types=['auto', 'critical_illness'],
        policy_types=['individual', 'group'],
        simulated_version='v2.0.0-test',
        target_version='v1.0.0-STABLE',
        operator='test_user'
    )

    plan = RollbackDrillManager.generate_drill_plan(drill_id)
    print(f'  ✓ 演练创建成功 (ID: {drill_id})')
    print(f'  ✓ 演练计划生成: {len(plan["phases"])}个阶段')

    RollbackDrillManager.start_drill(drill_id)
    validation = RollbackDrillManager.execute_policy_validation(drill_id)
    print(f'  ✓ 保单校验完成: 抽检{validation["total_policies_checked"]}份')
    print(f'    通过率: {validation["overall_pass_rate"]:.2%}')

    complete_result = RollbackDrillManager.complete_drill(drill_id)
    print(f'  ✓ 演练完成并归档: {complete_result["archive_path"]}')
except Exception as e:
    print(f'  ✗ 失败: {e}')
    all_passed = False
    import traceback
    traceback.print_exc()
print()

print('[10/11] 测试周报生成模块...')
try:
    from weekly_report import WeeklyReportManager
    week_end = datetime.now()
    week_start = week_end - timedelta(days=7)
    report = WeeklyReportManager.generate_weekly_report(week_start, week_end)
    print(f'  ✓ 周报生成 (ID: {report["report_id"]})')
    print(f'    总发布次数: {report["total_releases"]}')
    print(f'    发布成功率: {report["release_success_rate"]*100:.2f}%')
    print(f'    回滚次数: {report["rollback_count"]}')
    print(f'    PDF: {os.path.basename(report["pdf_path"])}')
    print(f'    Excel: {os.path.basename(report["excel_path"])}')
except Exception as e:
    print(f'  ✗ 失败: {e}')
    all_passed = False
    import traceback
    traceback.print_exc()
print()

print('[11/11] 测试历史查询与导出模块...')
try:
    from history_export import HistoryQuery, BatchExport
    history = HistoryQuery.query_releases(page=1, page_size=10)
    print(f'  ✓ 历史记录查询: 共{history["total"]}条记录')

    excel_path = BatchExport.export_releases(export_format='excel')
    print(f'  ✓ Excel导出: {excel_path}')

    csv_path = BatchExport.export_rollbacks(export_format='csv')
    print(f'  ✓ CSV导出: {csv_path}')
except Exception as e:
    print(f'  ✗ 失败: {e}')
    all_passed = False
    import traceback
    traceback.print_exc()
print()

print('=' * 70)
if all_passed:
    print('  ✓ 所有模块测试通过!')
else:
    print('  ✗ 部分模块测试失败，请检查错误信息')
print('=' * 70)
print()
print('生成的文件:')
for root, dirs, files in os.walk(os.path.join(os.path.dirname(__file__), 'reports')):
    for f in files:
        print(f'  - reports/{f}')
print()
print('数据库文件: data/insurance_underwriting.db')
