from datetime import datetime, timedelta
from models import ReleaseRequest, GrayscaleRecord, get_session
from audit_logger import log_grayscale, AuditLogger
import config
import random


class GrayscaleManager:
    @staticmethod
    def start_grayscale(release_id):
        session = get_session()
        try:
            release = session.query(ReleaseRequest).filter_by(id=release_id).first()
            if not release:
                raise ValueError(f'发布申请不存在: {release_id}')

            if release.status != 'approved':
                raise ValueError(f'发布状态异常: {release.status}, 需要状态为approved')

            insurance_types = release.insurance_types
            if not insurance_types:
                raise ValueError('未指定灰度发布的险种')

            first_insurance = insurance_types[0]
            stages = config.GRAYSCALE_STRATEGY.get(first_insurance, [0.1, 0.5, 1.0])
            first_stage = 0

            for idx, pct in enumerate(stages):
                record = GrayscaleRecord(
                    release_request_id=release_id,
                    insurance_type=first_insurance,
                    stage=idx,
                    percentage=pct,
                    status='pending'
                )
                session.add(record)

            release.current_insurance_type = first_insurance
            release.current_grayscale_stage = first_stage
            release.status = 'grayscaling'
            release.updated_at = datetime.now()
            session.flush()

            result = GrayscaleManager._advance_stage(session, release, first_insurance, first_stage)
            session.commit()

            return result
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def _advance_stage(session, release, insurance_type, stage):
        stages = config.GRAYSCALE_STRATEGY.get(insurance_type, [0.1, 0.5, 1.0])

        if stage >= len(stages):
            return GrayscaleManager._next_insurance_type(session, release)

        record = session.query(GrayscaleRecord).filter_by(
            release_request_id=release.id,
            insurance_type=insurance_type,
            stage=stage
        ).first()

        if not record:
            record = GrayscaleRecord(
                release_request_id=release.id,
                insurance_type=insurance_type,
                stage=stage,
                percentage=stages[stage],
                status='running'
            )
            session.add(record)

        record.status = 'running'
        record.start_time = datetime.now()
        record.affected_policies_count = GrayscaleManager._estimate_affected_policies(
            insurance_type, stages[stage]
        )

        release.current_insurance_type = insurance_type
        release.current_grayscale_stage = stage
        release.updated_at = datetime.now()

        log_grayscale(release.id, insurance_type, stage, stages[stage], session=session)

        return {
            'release_id': release.id,
            'insurance_type': insurance_type,
            'insurance_type_name': config.INSURANCE_TYPE_NAMES.get(insurance_type, insurance_type),
            'stage': stage,
            'percentage': stages[stage],
            'affected_policies': record.affected_policies_count,
            'status': 'running',
            'message': f'开始 {config.INSURANCE_TYPE_NAMES.get(insurance_type, insurance_type)} 第{stage}阶段灰度推送: {stages[stage]*100:.0f}%'
        }

    @staticmethod
    def _next_insurance_type(session, release):
        current_idx = release.insurance_types.index(release.current_insurance_type) if release.current_insurance_type in release.insurance_types else -1

        if current_idx >= len(release.insurance_types) - 1:
            release.status = 'fully_released'
            release.updated_at = datetime.now()

            AuditLogger.log(
                operation_type='full_release',
                operation_module='release',
                operator='system',
                operation_detail=f'灰度发布完成，版本{release.version}全量发布',
                related_id=release.id,
                related_type='release_request',
                regulatory_related=True,
                risk_level='high',
                session=session
            )

            return {
                'release_id': release.id,
                'status': 'fully_released',
                'message': '所有险种灰度发布完成，已全量发布'
            }

        next_insurance = release.insurance_types[current_idx + 1]
        stages = config.GRAYSCALE_STRATEGY.get(next_insurance, [0.1, 0.5, 1.0])

        for idx, pct in enumerate(stages):
            record = GrayscaleRecord(
                release_request_id=release.id,
                insurance_type=next_insurance,
                stage=idx,
                percentage=pct,
                status='pending'
            )
            session.add(record)

        return GrayscaleManager._advance_stage(session, release, next_insurance, 0)

    @staticmethod
    def complete_current_stage(release_id):
        session = get_session()
        try:
            release = session.query(ReleaseRequest).filter_by(id=release_id).first()
            if not release:
                raise ValueError(f'发布申请不存在: {release_id}')

            if release.status != 'grayscaling':
                raise ValueError(f'发布状态异常: {release.status}')

            current_insurance = release.current_insurance_type
            current_stage = release.current_grayscale_stage
            stages = config.GRAYSCALE_STRATEGY.get(current_insurance, [0.1, 0.5, 1.0])

            record = session.query(GrayscaleRecord).filter_by(
                release_request_id=release_id,
                insurance_type=current_insurance,
                stage=current_stage
            ).first()

            if record:
                record.status = 'completed'
                record.end_time = datetime.now()

            next_stage = current_stage + 1
            result = GrayscaleManager._advance_stage(session, release, current_insurance, next_stage)
            session.commit()

            return result
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def _estimate_affected_policies(insurance_type, percentage):
        base_counts = {
            'auto': 50000,
            'life': 30000,
            'critical_illness': 20000
        }
        base = base_counts.get(insurance_type, 10000)
        return int(base * percentage * random.uniform(0.95, 1.05))

    @staticmethod
    def get_grayscale_status(release_id):
        session = get_session()
        try:
            release = session.query(ReleaseRequest).filter_by(id=release_id).first()
            if not release:
                raise ValueError(f'发布申请不存在: {release_id}')

            records = session.query(GrayscaleRecord).filter_by(
                release_request_id=release_id
            ).order_by(GrayscaleRecord.created_at.asc()).all()

            grayscale_by_type = {}
            for record in records:
                it = record.insurance_type
                if it not in grayscale_by_type:
                    grayscale_by_type[it] = []
                grayscale_by_type[it].append({
                    'stage': record.stage,
                    'percentage': record.percentage,
                    'status': record.status,
                    'start_time': record.start_time.strftime('%Y-%m-%d %H:%M:%S') if record.start_time else None,
                    'end_time': record.end_time.strftime('%Y-%m-%d %H:%M:%S') if record.end_time else None,
                    'affected_policies_count': record.affected_policies_count
                })

            return {
                'release_id': release_id,
                'version': release.version,
                'overall_status': release.status,
                'current_insurance_type': release.current_insurance_type,
                'current_insurance_type_name': config.INSURANCE_TYPE_NAMES.get(
                    release.current_insurance_type, release.current_insurance_type
                ) if release.current_insurance_type else None,
                'current_stage': release.current_grayscale_stage,
                'grayscale_details': grayscale_by_type
            }
        finally:
            session.close()

    @staticmethod
    def get_grayscale_interval_hours(risk_level):
        return config.GRAYSCALE_INTERVAL_HOURS.get(risk_level, 4)

    @staticmethod
    def check_and_advance_if_ready(release_id):
        session = get_session()
        try:
            release = session.query(ReleaseRequest).filter_by(id=release_id).first()
            if not release or release.status != 'grayscaling':
                return None

            current_insurance = release.current_insurance_type
            current_stage = release.current_grayscale_stage

            record = session.query(GrayscaleRecord).filter_by(
                release_request_id=release_id,
                insurance_type=current_insurance,
                stage=current_stage
            ).first()

            if not record or not record.start_time:
                return None

            interval_hours = GrayscaleManager.get_grayscale_interval_hours(release.risk_level)
            if datetime.now() - record.start_time >= timedelta(hours=interval_hours):
                record.status = 'completed'
                record.end_time = datetime.now()

                stages = config.GRAYSCALE_STRATEGY.get(current_insurance, [0.1, 0.5, 1.0])
                next_stage = current_stage + 1

                result = GrayscaleManager._advance_stage(session, release, current_insurance, next_stage)
                session.commit()
                return result

            return None
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
