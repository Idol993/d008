from datetime import datetime, timedelta
from models import AuditLog, get_session
import config


class AuditLogger:
    @staticmethod
    def log(operation_type, operation_module, operator, operation_detail,
            related_id=None, related_type=None, ip_address=None,
            regulatory_related=False, risk_level='low', session=None):
        if session is not None:
            log = AuditLog(
                operation_type=operation_type,
                operation_module=operation_module,
                operator=operator,
                operation_detail=operation_detail,
                related_id=related_id,
                related_type=related_type,
                ip_address=ip_address,
                regulatory_related=regulatory_related,
                risk_level=risk_level
            )
            session.add(log)
            session.flush()
            return log.id

        session = get_session()
        try:
            log = AuditLog(
                operation_type=operation_type,
                operation_module=operation_module,
                operator=operator,
                operation_detail=operation_detail,
                related_id=related_id,
                related_type=related_type,
                ip_address=ip_address,
                regulatory_related=regulatory_related,
                risk_level=risk_level
            )
            session.add(log)
            session.commit()
            return log.id
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def query_logs(start_time=None, end_time=None, operation_type=None,
                   operation_module=None, operator=None, regulatory_related=None,
                   risk_level=None, related_id=None, related_type=None,
                   page=1, page_size=100):
        session = get_session()
        try:
            query = session.query(AuditLog)

            if start_time:
                query = query.filter(AuditLog.operation_time >= start_time)
            if end_time:
                query = query.filter(AuditLog.operation_time <= end_time)
            if operation_type:
                query = query.filter(AuditLog.operation_type == operation_type)
            if operation_module:
                query = query.filter(AuditLog.operation_module == operation_module)
            if operator:
                query = query.filter(AuditLog.operator == operator)
            if regulatory_related is not None:
                query = query.filter(AuditLog.regulatory_related == regulatory_related)
            if risk_level:
                query = query.filter(AuditLog.risk_level == risk_level)
            if related_id:
                query = query.filter(AuditLog.related_id == related_id)
            if related_type:
                query = query.filter(AuditLog.related_type == related_type)

            total = query.count()
            logs = query.order_by(AuditLog.operation_time.desc()) \
                .offset((page - 1) * page_size).limit(page_size).all()

            return {
                'total': total,
                'page': page,
                'page_size': page_size,
                'logs': [AuditLogger._to_dict(log) for log in logs]
            }
        finally:
            session.close()

    @staticmethod
    def _to_dict(log):
        return {
            'id': log.id,
            'operation_type': log.operation_type,
            'operation_module': log.operation_module,
            'operator': log.operator,
            'operation_detail': log.operation_detail,
            'related_id': log.related_id,
            'related_type': log.related_type,
            'ip_address': log.ip_address,
            'operation_time': log.operation_time.strftime('%Y-%m-%d %H:%M:%S'),
            'regulatory_related': log.regulatory_related,
            'risk_level': log.risk_level
        }

    @staticmethod
    def cleanup_old_logs(days=None):
        if days is None:
            days = config.AUDIT_LOG_RETENTION_DAYS
        session = get_session()
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            deleted = session.query(AuditLog).filter(
                AuditLog.operation_time < cutoff_date
            ).delete()
            session.commit()
            return deleted
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def export_for_regulatory(start_time, end_time, file_path):
        import csv
        result = AuditLogger.query_logs(
            start_time=start_time,
            end_time=end_time,
            regulatory_related=True,
            page_size=10000
        )

        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                '日志ID', '操作类型', '操作模块', '操作人', '操作详情',
                '关联ID', '关联类型', 'IP地址', '操作时间',
                '是否监管相关', '风险级别'
            ])
            for log in result['logs']:
                writer.writerow([
                    log['id'],
                    log['operation_type'],
                    log['operation_module'],
                    log['operator'],
                    log['operation_detail'],
                    log['related_id'],
                    log['related_type'],
                    log['ip_address'],
                    log['operation_time'],
                    '是' if log['regulatory_related'] else '否',
                    log['risk_level']
                ])
        return file_path


def log_release_submit(release_id, operator, version, title, session=None):
    AuditLogger.log(
        operation_type='submit',
        operation_module='release',
        operator=operator,
        operation_detail=f'提交发布申请: 版本{version}, 标题: {title}',
        related_id=release_id,
        related_type='release_request',
        regulatory_related=True,
        risk_level='medium',
        session=session
    )


def log_approval(release_id, role, approver, status, comment, session=None):
    AuditLogger.log(
        operation_type='approval',
        operation_module='compliance',
        operator=approver,
        operation_detail=f'{role}审批: {status}, 意见: {comment}',
        related_id=release_id,
        related_type='release_request',
        regulatory_related=True,
        risk_level='high',
        session=session
    )


def log_rollback(rollback_id, operator, reason, version_from, version_to, session=None):
    AuditLogger.log(
        operation_type='rollback',
        operation_module='rollback',
        operator=operator,
        operation_detail=f'合规回滚: 原因{reason}, 从版本{version_from}回滚到{version_to}',
        related_id=rollback_id,
        related_type='rollback_record',
        regulatory_related=True,
        risk_level='high',
        session=session
    )


def log_grayscale(release_id, insurance_type, stage, percentage, session=None):
    AuditLogger.log(
        operation_type='grayscale_push',
        operation_module='release',
        operator='system',
        operation_detail=f'灰度推送: {insurance_type} 第{stage}阶段 {percentage*100}%',
        related_id=release_id,
        related_type='release_request',
        regulatory_related=True,
        risk_level='medium',
        session=session
    )


def log_monitor_alert(release_id, alert_type, detail, session=None):
    AuditLogger.log(
        operation_type='monitor_alert',
        operation_module='monitor',
        operator='system',
        operation_detail=f'监控告警: {alert_type}, 详情: {detail}',
        related_id=release_id,
        related_type='release_request',
        regulatory_related=True,
        risk_level='high',
        session=session
    )


def log_drill(drill_id, operator, drill_name, status, session=None):
    AuditLogger.log(
        operation_type='drill',
        operation_module='rollback_drill',
        operator=operator,
        operation_detail=f'回滚演练: {drill_name}, 状态: {status}',
        related_id=drill_id,
        related_type='rollback_drill',
        regulatory_related=True,
        risk_level='low',
        session=session
    )
