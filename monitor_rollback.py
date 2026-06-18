from datetime import datetime, timedelta
from models import (ReleaseRequest, MonitorRecord, RollbackRecord,
                     GrayscaleRecord, get_session, StableVersion)
from audit_logger import log_monitor_alert, log_rollback, AuditLogger
from release_manager import ReleaseManager
import config
import random


class MonitorManager:
    @staticmethod
    def collect_metrics(release_id):
        session = get_session()
        try:
            release = session.query(ReleaseRequest).filter_by(id=release_id).first()
            if not release:
                raise ValueError(f'发布申请不存在: {release_id}')

            insurance_type = release.current_insurance_type or release.insurance_types[0]
            stage = release.current_grayscale_stage or 0

            underwriting_pass_rate = MonitorManager._simulate_underwriting_pass_rate(release, insurance_type)
            claim_process_delay = MonitorManager._simulate_claim_delay(release, insurance_type)
            claim_abnormal_rate = MonitorManager._simulate_claim_abnormal_rate(release, insurance_type)
            info_leak_risk = MonitorManager._simulate_info_leak_risk(release, insurance_type)

            threshold_details = MonitorManager._check_thresholds(
                underwriting_pass_rate, claim_process_delay,
                claim_abnormal_rate, info_leak_risk
            )
            threshold_exceeded = any(
                detail['exceeded'] for detail in threshold_details.values()
            )

            record = MonitorRecord(
                release_request_id=release_id,
                insurance_type=insurance_type,
                grayscale_stage=stage,
                underwriting_pass_rate=underwriting_pass_rate,
                claim_process_delay_seconds=claim_process_delay,
                claim_abnormal_rate=claim_abnormal_rate,
                info_leak_risk=info_leak_risk,
                threshold_exceeded=threshold_exceeded,
                threshold_details=threshold_details
            )
            session.add(record)
            session.commit()
            record_id = record.id

            if threshold_exceeded:
                log_monitor_alert(release_id, 'threshold_exceeded',
                                  f'{insurance_type} 阶段{stage} 指标超出阈值')

            return {
                'record_id': record_id,
                'release_id': release_id,
                'insurance_type': insurance_type,
                'stage': stage,
                'underwriting_pass_rate': underwriting_pass_rate,
                'claim_process_delay_seconds': claim_process_delay,
                'claim_abnormal_rate': claim_abnormal_rate,
                'info_leak_risk': info_leak_risk,
                'threshold_exceeded': threshold_exceeded,
                'threshold_details': threshold_details
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def _simulate_underwriting_pass_rate(release, insurance_type):
        base_rate = {
            'auto': 0.92,
            'life': 0.88,
            'critical_illness': 0.85
        }
        base = base_rate.get(insurance_type, 0.90)
        variance = random.uniform(-0.08, 0.03)
        if release.status == 'grayscaling' and release.current_grayscale_stage < 2:
            variance += random.uniform(-0.02, 0.01)
        return round(max(0.70, min(0.99, base + variance)), 4)

    @staticmethod
    def _simulate_claim_delay(release, insurance_type):
        base_delay = {
            'auto': 1800,
            'life': 2400,
            'critical_illness': 3000
        }
        base = base_delay.get(insurance_type, 2000)
        variance = random.uniform(-300, 800)
        if release.status == 'grayscaling':
            variance += random.uniform(0, 500)
        return round(max(600, base + variance), 0)

    @staticmethod
    def _simulate_claim_abnormal_rate(release, insurance_type):
        base_rate = {
            'auto': 0.02,
            'life': 0.015,
            'critical_illness': 0.025
        }
        base = base_rate.get(insurance_type, 0.02)
        variance = random.uniform(-0.01, 0.03)
        if release.status == 'grayscaling' and release.current_grayscale_stage < 1:
            variance += random.uniform(0, 0.02)
        return round(max(0.001, min(0.10, base + variance)), 4)

    @staticmethod
    def _simulate_info_leak_risk(release, insurance_type):
        base_risk = 0.002
        variance = random.uniform(-0.001, 0.005)
        if release.status == 'grayscaling' and release.current_grayscale_stage == 0:
            variance += random.uniform(0, 0.003)
        return round(max(0.0001, min(0.02, base_risk + variance)), 5)

    @staticmethod
    def _check_thresholds(pass_rate, delay, abnormal_rate, leak_risk):
        return {
            'underwriting_pass_rate': {
                'value': pass_rate,
                'min_threshold': config.THRESHOLDS['underwriting_pass_rate_min'],
                'max_threshold': config.THRESHOLDS['underwriting_pass_rate_max'],
                'exceeded': (pass_rate < config.THRESHOLDS['underwriting_pass_rate_min'] or
                           pass_rate > config.THRESHOLDS['underwriting_pass_rate_max']),
                'direction': 'too_low' if pass_rate < config.THRESHOLDS['underwriting_pass_rate_min'] else 'too_high' if pass_rate > config.THRESHOLDS['underwriting_pass_rate_max'] else 'normal'
            },
            'claim_process_delay': {
                'value': delay,
                'max_threshold': config.THRESHOLDS['claim_process_delay_max_seconds'],
                'exceeded': delay > config.THRESHOLDS['claim_process_delay_max_seconds'],
                'direction': 'too_high'
            },
            'claim_abnormal_rate': {
                'value': abnormal_rate,
                'max_threshold': config.THRESHOLDS['claim_abnormal_rate_max'],
                'exceeded': abnormal_rate > config.THRESHOLDS['claim_abnormal_rate_max'],
                'direction': 'too_high'
            },
            'info_leak_risk': {
                'value': leak_risk,
                'max_threshold': config.THRESHOLDS['info_leak_risk_max'],
                'exceeded': leak_risk > config.THRESHOLDS['info_leak_risk_max'],
                'direction': 'too_high'
            }
        }

    @staticmethod
    def get_latest_monitor(release_id):
        session = get_session()
        try:
            record = session.query(MonitorRecord).filter_by(
                release_request_id=release_id
            ).order_by(MonitorRecord.monitor_time.desc()).first()
            if not record:
                return None
            return MonitorManager._to_dict(record)
        finally:
            session.close()

    @staticmethod
    def get_monitor_history(release_id, limit=100):
        session = get_session()
        try:
            records = session.query(MonitorRecord).filter_by(
                release_request_id=release_id
            ).order_by(MonitorRecord.monitor_time.desc()).limit(limit).all()
            return [MonitorManager._to_dict(r) for r in records]
        finally:
            session.close()

    @staticmethod
    def _to_dict(record):
        return {
            'id': record.id,
            'release_id': record.release_request_id,
            'insurance_type': record.insurance_type,
            'insurance_type_name': config.INSURANCE_TYPE_NAMES.get(
                record.insurance_type, record.insurance_type
            ),
            'grayscale_stage': record.grayscale_stage,
            'underwriting_pass_rate': record.underwriting_pass_rate,
            'claim_process_delay_seconds': record.claim_process_delay_seconds,
            'claim_abnormal_rate': record.claim_abnormal_rate,
            'info_leak_risk': record.info_leak_risk,
            'threshold_exceeded': record.threshold_exceeded,
            'threshold_details': record.threshold_details,
            'monitor_time': record.monitor_time.strftime('%Y-%m-%d %H:%M:%S')
        }


class RollbackManager:
    @staticmethod
    def trigger_rollback(release_id, reason, rollback_type='auto'):
        session = get_session()
        try:
            release = session.query(ReleaseRequest).filter_by(id=release_id).first()
            if not release:
                raise ValueError(f'发布申请不存在: {release_id}')

            if release.rollback_triggered:
                return {
                    'release_id': release_id,
                    'status': 'already_rolled_back',
                    'message': '已触发过回滚'
                }

            from models import StableVersion
            stable_version = session.query(StableVersion).filter_by(
                is_active=True, regulatory_approved=True
            ).order_by(StableVersion.created_at.desc()).first()
            if not stable_version:
                raise ValueError('没有找到监管认可的稳定版本，无法回滚')

            affected_count = RollbackManager._calculate_affected_policies(session, release)
            claim_anomaly = RollbackManager._analyze_claim_anomalies(release)
            regulatory_explanation = RollbackManager._generate_regulatory_explanation(release)

            rollback = RollbackRecord(
                release_request_id=release_id,
                rollback_type=rollback_type,
                trigger_reason=reason,
                affected_policies_count=affected_count,
                affected_insurance_types=release.insurance_types,
                rollback_from_version=release.version,
                rollback_to_version=stable_version.version,
                claim_anomaly_details=claim_anomaly,
                regulatory_clause_explanation=regulatory_explanation,
                status='in_progress',
                start_time=datetime.now()
            )
            session.add(rollback)
            session.flush()
            rollback_id = rollback.id

            release.rollback_triggered = True
            release.rollback_reason = reason
            release.rollback_time = datetime.now()
            release.status = 'rolling_back'
            release.stable_version_id = stable_version.id
            release.updated_at = datetime.now()

            RollbackManager._perform_rollback(session, release, stable_version)

            rollback.status = 'completed'
            rollback.complete_time = datetime.now()

            AuditLogger.log(
                operation_type='rollback_complete',
                operation_module='rollback',
                operator='system',
                operation_detail=f'回滚完成: 从{release.version}到{stable_version.version}, 影响保单{affected_count}份',
                related_id=rollback_id,
                related_type='rollback_record',
                regulatory_related=True,
                risk_level='high',
                session=session
            )

            session.commit()

            return {
                'rollback_id': rollback_id,
                'release_id': release_id,
                'rollback_type': rollback_type,
                'from_version': release.version,
                'to_version': stable_version.version,
                'affected_policies': affected_count,
                'trigger_reason': reason,
                'status': 'completed'
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def _calculate_affected_policies(session, release):
        total = 0
        records = session.query(GrayscaleRecord).filter_by(
            release_request_id=release.id,
            status='running'
        ).all()
        for r in records:
            total += r.affected_policies_count

        if total == 0:
            for it in release.insurance_types:
                base = {'auto': 50000, 'life': 30000, 'critical_illness': 20000}.get(it, 10000)
                total += int(base * 0.3)

        return total

    @staticmethod
    def _analyze_claim_anomalies(release):
        anomalies = [
            '核保规则变更导致部分保单理赔条件判断异常',
            '新规则下部分重疾险理赔申请延迟增加',
            '车险快速理赔通道数据同步异常'
        ]
        selected = random.sample(anomalies, k=random.randint(1, 2))
        return '; '.join(selected)

    @staticmethod
    def _generate_regulatory_explanation(release):
        clauses = [
            '符合《保险法》第134条关于保险条款和费率审批的规定',
            '符合银保监会《财产保险公司保险条款和保险费率管理办法》',
            '符合《人身保险业务基本服务规定》相关要求',
            '符合《保险消费者权益保护管理办法》'
        ]
        return '; '.join(random.sample(clauses, k=2))

    @staticmethod
    def _perform_rollback(session, release, stable_version):
        grayscale_records = session.query(GrayscaleRecord).filter_by(
            release_request_id=release.id,
            status='running'
        ).all()
        for record in grayscale_records:
            record.status = 'rolled_back'
            record.end_time = datetime.now()

        release.status = 'rolled_back'
        release.updated_at = datetime.now()

    @staticmethod
    def restart_monitoring_after_rollback(release_id):
        session = get_session()
        try:
            release = session.query(ReleaseRequest).filter_by(id=release_id).first()
            if not release or release.status != 'rolled_back':
                raise ValueError('状态异常，无法重启监控')

            stable_version = session.query(StableVersion).filter_by(
                id=release.stable_version_id
            ).first() if release.stable_version_id else None

            AuditLogger.log(
                operation_type='restart_monitoring',
                operation_module='monitor',
                operator='system',
                operation_detail=f'回滚后重启核生理赔监控，当前稳定版本: {stable_version.version if stable_version else "unknown"}',
                related_id=release_id,
                related_type='release_request',
                regulatory_related=True,
                risk_level='medium'
            )

            return {
                'release_id': release_id,
                'stable_version': stable_version.version if stable_version else None,
                'status': 'monitoring_restarted',
                'message': '核生理赔监控已重启'
            }
        finally:
            session.close()

    @staticmethod
    def get_rollback_record(rollback_id):
        session = get_session()
        try:
            rollback = session.query(RollbackRecord).filter_by(id=rollback_id).first()
            if not rollback:
                return None
            return RollbackManager._rollback_to_dict(rollback)
        finally:
            session.close()

    @staticmethod
    def list_rollbacks(release_id=None, rollback_type=None, status=None,
                       start_time=None, end_time=None, page=1, page_size=20):
        session = get_session()
        try:
            query = session.query(RollbackRecord)

            if release_id:
                query = query.filter(RollbackRecord.release_request_id == release_id)
            if rollback_type:
                query = query.filter(RollbackRecord.rollback_type == rollback_type)
            if status:
                query = query.filter(RollbackRecord.status == status)
            if start_time:
                query = query.filter(RollbackRecord.start_time >= start_time)
            if end_time:
                query = query.filter(RollbackRecord.start_time <= end_time)

            total = query.count()
            rollbacks = query.order_by(RollbackRecord.created_at.desc()) \
                .offset((page - 1) * page_size).limit(page_size).all()

            return {
                'total': total,
                'page': page,
                'page_size': page_size,
                'rollbacks': [RollbackManager._rollback_to_dict(r) for r in rollbacks]
            }
        finally:
            session.close()

    @staticmethod
    def _rollback_to_dict(rollback):
        return {
            'id': rollback.id,
            'release_id': rollback.release_request_id,
            'rollback_type': rollback.rollback_type,
            'trigger_reason': rollback.trigger_reason,
            'affected_policies_count': rollback.affected_policies_count,
            'affected_insurance_types': rollback.affected_insurance_types,
            'rollback_from_version': rollback.rollback_from_version,
            'rollback_to_version': rollback.rollback_to_version,
            'claim_anomaly_details': rollback.claim_anomaly_details,
            'regulatory_clause_explanation': rollback.regulatory_clause_explanation,
            'status': rollback.status,
            'start_time': rollback.start_time.strftime('%Y-%m-%d %H:%M:%S') if rollback.start_time else None,
            'complete_time': rollback.complete_time.strftime('%Y-%m-%d %H:%M:%S') if rollback.complete_time else None,
            'report_generated': rollback.report_generated,
            'report_path': rollback.report_path,
            'notifications_sent': rollback.notifications_sent,
            'created_at': rollback.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }
