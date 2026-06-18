import os
from datetime import datetime
from models import RollbackRecord, ReleaseRequest, get_session
from audit_logger import AuditLogger
import config


class ReportGenerator:
    @staticmethod
    def generate_rollback_report(rollback_id):
        session = get_session()
        try:
            rollback = session.query(RollbackRecord).filter_by(id=rollback_id).first()
            if not rollback:
                raise ValueError(f'回滚记录不存在: {rollback_id}')

            release = session.query(ReleaseRequest).filter_by(
                id=rollback.release_request_id
            ).first()

            report_content = ReportGenerator._build_rollback_report_content(rollback, release)

            report_filename = f'rollback_report_{rollback_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
            report_path = os.path.join(config.REPORT_DIR, report_filename)

            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report_content)

            rollback.report_generated = True
            rollback.report_path = report_path
            session.commit()

            AuditLogger.log(
                operation_type='generate_report',
                operation_module='report',
                operator='system',
                operation_detail=f'生成回滚报告: {report_filename}',
                related_id=rollback_id,
                related_type='rollback_record',
                regulatory_related=True,
                risk_level='high'
            )

            return {
                'rollback_id': rollback_id,
                'report_path': report_path,
                'report_filename': report_filename
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def _build_rollback_report_content(rollback, release):
        insurance_type_names = [
            config.INSURANCE_TYPE_NAMES.get(it, it)
            for it in (rollback.affected_insurance_types or [])
        ]

        content = []
        content.append('=' * 70)
        content.append('            保险核保理赔系统 - 合规回滚报告')
        content.append('=' * 70)
        content.append('')

        content.append('一、回滚基本信息')
        content.append('-' * 50)
        content.append(f'回滚ID: {rollback.id}')
        content.append(f'回滚类型: {rollback.rollback_type}')
        content.append(f'触发原因: {rollback.trigger_reason}')
        content.append(f'回滚状态: {rollback.status}')
        content.append(f'回滚开始时间: {rollback.start_time.strftime("%Y-%m-%d %H:%M:%S") if rollback.start_time else "-"}')
        content.append(f'回滚完成时间: {rollback.complete_time.strftime("%Y-%m-%d %H:%M:%S") if rollback.complete_time else "-"}')
        content.append('')

        content.append('二、版本信息')
        content.append('-' * 50)
        content.append(f'回滚前版本: {rollback.rollback_from_version}')
        content.append(f'回滚后版本: {rollback.rollback_to_version}')
        if release:
            content.append(f'发布标题: {release.title}')
            content.append(f'风险级别: {config.RISK_LEVEL_NAMES.get(release.risk_level, release.risk_level)}')
        content.append('')

        content.append('三、保单影响范围')
        content.append('-' * 50)
        content.append(f'影响保单总数: {rollback.affected_policies_count} 份')
        content.append(f'涉及险种: {", ".join(insurance_type_names) if insurance_type_names else "-"}')
        content.append('')

        content.append('四、理赔异常原因分析')
        content.append('-' * 50)
        content.append(rollback.claim_anomaly_details or '无')
        content.append('')

        content.append('五、监管条款说明')
        content.append('-' * 50)
        content.append(rollback.regulatory_clause_explanation or '无')
        content.append('')

        content.append('六、受影响干系人')
        content.append('-' * 50)
        stakeholders = []
        for role, emails in config.STAKEHOLDERS.items():
            stakeholders.append(f'{role}: {", ".join(emails)}')
        content.append('\n'.join(stakeholders))
        content.append('')

        content.append('七、后续行动')
        content.append('-' * 50)
        content.append('1. 已恢复上一监管认可稳定版本')
        content.append('2. 已重启核生理赔监控')
        content.append('3. 已通知所有相关干系人')
        content.append('4. 问题根因分析待进行')
        content.append('5. 修复验证完成后可重新申请发布')
        content.append('')

        content.append('=' * 70)
        content.append(f'报告生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        content.append('本报告由系统自动生成，仅供内部及监管审计使用')
        content.append('=' * 70)

        return '\n'.join(content)


class NotificationManager:
    @staticmethod
    def send_rollback_notifications(rollback_id):
        session = get_session()
        try:
            rollback = session.query(RollbackRecord).filter_by(id=rollback_id).first()
            if not rollback:
                raise ValueError(f'回滚记录不存在: {rollback_id}')

            release = session.query(ReleaseRequest).filter_by(
                id=rollback.release_request_id
            ).first()

            all_emails = set()
            for role_emails in config.STAKEHOLDERS.values():
                all_emails.update(role_emails)

            subject = f'【重要】合规回滚通知 - 版本{rollback.rollback_from_version}'
            body = NotificationManager._build_notification_body(rollback, release)

            sent_emails = []
            for email in all_emails:
                try:
                    NotificationManager._send_email(email, subject, body)
                    sent_emails.append(email)
                except Exception as e:
                    print(f'发送邮件失败 {email}: {e}')

            rollback.notifications_sent = True
            session.commit()

            AuditLogger.log(
                operation_type='send_notification',
                operation_module='notification',
                operator='system',
                operation_detail=f'发送回滚通知给 {len(sent_emails)} 位干系人',
                related_id=rollback_id,
                related_type='rollback_record',
                regulatory_related=True,
                risk_level='high'
            )

            return {
                'rollback_id': rollback_id,
                'sent_count': len(sent_emails),
                'recipients': sent_emails
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def _build_notification_body(rollback, release):
        body = []
        body.append('尊敬的干系人：')
        body.append('')
        body.append(f'保险核保理赔系统已执行合规回滚操作，详情如下：')
        body.append('')
        body.append(f'【回滚版本】{rollback.rollback_from_version}')
        body.append(f'【回滚至】{rollback.rollback_to_version}')
        body.append(f'【触发原因】{rollback.trigger_reason}')
        body.append(f'【影响保单】{rollback.affected_policies_count} 份')
        body.append(f'【回滚状态】{rollback.status}')
        body.append('')
        body.append('请各部门关注业务影响，做好客户沟通和理赔处理工作。')
        body.append('')
        body.append('详细报告请见附件或系统内回滚记录。')
        body.append('')
        body.append('此致')
        body.append('保险核保理赔系统')
        body.append(datetime.now().strftime('%Y年%m月%d日 %H:%M'))
        return '\n'.join(body)

    @staticmethod
    def _send_email(to_email, subject, body):
        print(f'[模拟发送邮件] 至: {to_email}')
        print(f'  主题: {subject}')
        print(f'  内容摘要: {body[:80]}...')
        return True

    @staticmethod
    def send_approval_notification(role, release_version, release_title):
        approvers = config.APPROVERS.get(role, [])
        subject = f'【审批通知】{role}审批待处理 - {release_version}'
        body = f'请处理以下发布申请的{role}审批：\n版本: {release_version}\n标题: {release_title}'

        for email in approvers:
            NotificationManager._send_email(email, subject, body)

        return approvers

    @staticmethod
    def send_monitor_alert(release_id, alert_details):
        emails = config.STAKEHOLDERS.get('compliance', []) + \
                 config.STAKEHOLDERS.get('underwriting', [])
        subject = f'【监控告警】发布{release_id} 指标异常'
        body = f'监控检测到指标异常：\n{alert_details}'

        for email in emails:
            NotificationManager._send_email(email, subject, body)

        return emails
