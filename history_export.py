import os
from datetime import datetime
from models import (ReleaseRequest, RollbackRecord, MonitorRecord,
                     GrayscaleRecord, ApprovalRecord, get_session)
import config
import csv


class HistoryQuery:
    @staticmethod
    def query_releases(start_time=None, end_time=None, insurance_type=None,
                       policy_type=None, version=None, risk_level=None,
                       status=None, page=1, page_size=50):
        session = get_session()
        try:
            query = session.query(ReleaseRequest)

            if start_time:
                query = query.filter(ReleaseRequest.submit_time >= start_time)
            if end_time:
                query = query.filter(ReleaseRequest.submit_time <= end_time)
            if version:
                query = query.filter(ReleaseRequest.version.like(f'%{version}%'))
            if risk_level:
                query = query.filter(ReleaseRequest.risk_level == risk_level)
            if status:
                query = query.filter(ReleaseRequest.status == status)
            if insurance_type:
                query = query.filter(ReleaseRequest.insurance_types.like(f'%{insurance_type}%'))
            if policy_type:
                query = query.filter(ReleaseRequest.policy_types.like(f'%{policy_type}%'))

            total = query.count()
            releases = query.order_by(ReleaseRequest.submit_time.desc()) \
                .offset((page - 1) * page_size).limit(page_size).all()

            return {
                'total': total,
                'page': page,
                'page_size': page_size,
                'records': [HistoryQuery._release_to_dict(r) for r in releases]
            }
        finally:
            session.close()

    @staticmethod
    def _release_to_dict(release):
        return {
            'id': release.id,
            'version': release.version,
            'title': release.title,
            'description': release.description,
            'risk_level': release.risk_level,
            'risk_level_name': config.RISK_LEVEL_NAMES.get(release.risk_level, release.risk_level),
            'insurance_types': release.insurance_types,
            'insurance_type_names': [config.INSURANCE_TYPE_NAMES.get(it, it) for it in release.insurance_types],
            'policy_types': release.policy_types,
            'policy_type_names': [config.POLICY_TYPE_NAMES.get(pt, pt) for pt in release.policy_types],
            'submitter': release.submitter,
            'submit_time': release.submit_time.strftime('%Y-%m-%d %H:%M:%S') if release.submit_time else None,
            'status': release.status,
            'precheck_passed': release.precheck_passed,
            'rollback_triggered': release.rollback_triggered,
            'rollback_reason': release.rollback_reason,
            'rollback_time': release.rollback_time.strftime('%Y-%m-%d %H:%M:%S') if release.rollback_time else None
        }

    @staticmethod
    def query_rollbacks(start_time=None, end_time=None, rollback_type=None,
                        release_id=None, status=None, page=1, page_size=50):
        session = get_session()
        try:
            query = session.query(RollbackRecord)

            if start_time:
                query = query.filter(RollbackRecord.start_time >= start_time)
            if end_time:
                query = query.filter(RollbackRecord.start_time <= end_time)
            if rollback_type:
                query = query.filter(RollbackRecord.rollback_type == rollback_type)
            if release_id:
                query = query.filter(RollbackRecord.release_request_id == release_id)
            if status:
                query = query.filter(RollbackRecord.status == status)

            total = query.count()
            rollbacks = query.order_by(RollbackRecord.created_at.desc()) \
                .offset((page - 1) * page_size).limit(page_size).all()

            return {
                'total': total,
                'page': page,
                'page_size': page_size,
                'records': [HistoryQuery._rollback_to_dict(r) for r in rollbacks]
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
            'status': rollback.status,
            'start_time': rollback.start_time.strftime('%Y-%m-%d %H:%M:%S') if rollback.start_time else None,
            'complete_time': rollback.complete_time.strftime('%Y-%m-%d %H:%M:%S') if rollback.complete_time else None
        }

    @staticmethod
    def query_monitor_records(release_id=None, insurance_type=None,
                              start_time=None, end_time=None,
                              threshold_exceeded=None, page=1, page_size=100):
        session = get_session()
        try:
            query = session.query(MonitorRecord)

            if release_id:
                query = query.filter(MonitorRecord.release_request_id == release_id)
            if insurance_type:
                query = query.filter(MonitorRecord.insurance_type == insurance_type)
            if start_time:
                query = query.filter(MonitorRecord.monitor_time >= start_time)
            if end_time:
                query = query.filter(MonitorRecord.monitor_time <= end_time)
            if threshold_exceeded is not None:
                query = query.filter(MonitorRecord.threshold_exceeded == threshold_exceeded)

            total = query.count()
            records = query.order_by(MonitorRecord.monitor_time.desc()) \
                .offset((page - 1) * page_size).limit(page_size).all()

            return {
                'total': total,
                'page': page,
                'page_size': page_size,
                'records': [HistoryQuery._monitor_to_dict(r) for r in records]
            }
        finally:
            session.close()

    @staticmethod
    def _monitor_to_dict(record):
        return {
            'id': record.id,
            'release_id': record.release_request_id,
            'insurance_type': record.insurance_type,
            'insurance_type_name': config.INSURANCE_TYPE_NAMES.get(record.insurance_type, record.insurance_type),
            'grayscale_stage': record.grayscale_stage,
            'underwriting_pass_rate': record.underwriting_pass_rate,
            'claim_process_delay_seconds': record.claim_process_delay_seconds,
            'claim_abnormal_rate': record.claim_abnormal_rate,
            'info_leak_risk': record.info_leak_risk,
            'threshold_exceeded': record.threshold_exceeded,
            'monitor_time': record.monitor_time.strftime('%Y-%m-%d %H:%M:%S')
        }


class BatchExport:
    @staticmethod
    def export_releases(start_time=None, end_time=None, insurance_type=None,
                        policy_type=None, version=None, risk_level=None,
                        status=None, export_format='excel'):
        result = HistoryQuery.query_releases(
            start_time=start_time, end_time=end_time,
            insurance_type=insurance_type, policy_type=policy_type,
            version=version, risk_level=risk_level, status=status,
            page=1, page_size=10000
        )

        records = result['records']

        if export_format == 'csv':
            return BatchExport._export_releases_csv(records)
        else:
            return BatchExport._export_releases_excel(records)

    @staticmethod
    def _export_releases_csv(records):
        import tempfile
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'release_history_{timestamp}.csv'
        filepath = os.path.join(config.REPORT_DIR, filename)

        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                'ID', '版本号', '标题', '风险级别', '涉及险种', '保单类型',
                '提交人', '提交时间', '状态', '前置检查是否通过',
                '是否回滚', '回滚原因', '回滚时间'
            ])
            for r in records:
                writer.writerow([
                    r['id'], r['version'], r['title'], r['risk_level_name'],
                    ','.join(r['insurance_type_names']),
                    ','.join(r['policy_type_names']),
                    r['submitter'], r['submit_time'], r['status'],
                    '是' if r['precheck_passed'] else '否',
                    '是' if r['rollback_triggered'] else '否',
                    r['rollback_reason'] or '',
                    r['rollback_time'] or ''
                ])
        return filepath

    @staticmethod
    def _export_releases_excel(records):
        import pandas as pd
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'release_history_{timestamp}.xlsx'
        filepath = os.path.join(config.REPORT_DIR, filename)

        data = []
        for r in records:
            data.append({
                'ID': r['id'],
                '版本号': r['version'],
                '标题': r['title'],
                '风险级别': r['risk_level_name'],
                '涉及险种': ','.join(r['insurance_type_names']),
                '保单类型': ','.join(r['policy_type_names']),
                '提交人': r['submitter'],
                '提交时间': r['submit_time'],
                '状态': r['status'],
                '前置检查是否通过': '是' if r['precheck_passed'] else '否',
                '是否回滚': '是' if r['rollback_triggered'] else '否',
                '回滚原因': r['rollback_reason'] or '',
                '回滚时间': r['rollback_time'] or ''
            })

        df = pd.DataFrame(data)
        df.to_excel(filepath, index=False, engine='openpyxl')
        return filepath

    @staticmethod
    def export_rollbacks(start_time=None, end_time=None, rollback_type=None,
                         status=None, export_format='excel'):
        result = HistoryQuery.query_rollbacks(
            start_time=start_time, end_time=end_time,
            rollback_type=rollback_type, status=status,
            page=1, page_size=10000
        )
        records = result['records']

        if export_format == 'csv':
            return BatchExport._export_rollbacks_csv(records)
        else:
            return BatchExport._export_rollbacks_excel(records)

    @staticmethod
    def _export_rollbacks_csv(records):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'rollback_history_{timestamp}.csv'
        filepath = os.path.join(config.REPORT_DIR, filename)

        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow([
                '回滚ID', '关联发布ID', '回滚类型', '触发原因',
                '影响保单数', '从版本', '回滚至', '状态',
                '开始时间', '完成时间'
            ])
            for r in records:
                writer.writerow([
                    r['id'], r['release_id'], r['rollback_type'],
                    r['trigger_reason'], r['affected_policies_count'],
                    r['rollback_from_version'], r['rollback_to_version'],
                    r['status'], r['start_time'], r['complete_time']
                ])
        return filepath

    @staticmethod
    def _export_rollbacks_excel(records):
        import pandas as pd
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'rollback_history_{timestamp}.xlsx'
        filepath = os.path.join(config.REPORT_DIR, filename)

        data = []
        for r in records:
            data.append({
                '回滚ID': r['id'],
                '关联发布ID': r['release_id'],
                '回滚类型': r['rollback_type'],
                '触发原因': r['trigger_reason'],
                '影响保单数': r['affected_policies_count'],
                '从版本': r['rollback_from_version'],
                '回滚至': r['rollback_to_version'],
                '状态': r['status'],
                '开始时间': r['start_time'],
                '完成时间': r['complete_time']
            })

        df = pd.DataFrame(data)
        df.to_excel(filepath, index=False, engine='openpyxl')
        return filepath

    @staticmethod
    def export_full_report(release_ids, export_format='excel'):
        import pandas as pd
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'full_report_{timestamp}.xlsx'
        filepath = os.path.join(config.REPORT_DIR, filename)

        session = get_session()
        try:
            releases = session.query(ReleaseRequest).filter(
                ReleaseRequest.id.in_(release_ids)
            ).all()

            rollbacks = session.query(RollbackRecord).filter(
                RollbackRecord.release_request_id.in_(release_ids)
            ).all()

            approvals = session.query(ApprovalRecord).filter(
                ApprovalRecord.release_request_id.in_(release_ids)
            ).all()

            grayscales = session.query(GrayscaleRecord).filter(
                GrayscaleRecord.release_request_id.in_(release_ids)
            ).all()

            monitors = session.query(MonitorRecord).filter(
                MonitorRecord.release_request_id.in_(release_ids)
            ).all()

            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                pd.DataFrame([HistoryQuery._release_to_dict(r) for r in releases]).to_excel(
                    writer, sheet_name='发布记录', index=False)
                pd.DataFrame([HistoryQuery._rollback_to_dict(r) for r in rollbacks]).to_excel(
                    writer, sheet_name='回滚记录', index=False)
                pd.DataFrame([{
                    'ID': a.id, '发布ID': a.release_request_id,
                    '角色': config.APPROVAL_ROLE_NAMES.get(a.role, a.role),
                    '审批人': a.approver, '状态': a.status,
                    '意见': a.comment, '审批时间': a.approve_time
                } for a in approvals]).to_excel(writer, sheet_name='审批记录', index=False)
                pd.DataFrame([{
                    'ID': g.id, '发布ID': g.release_request_id,
                    '险种': config.INSURANCE_TYPE_NAMES.get(g.insurance_type, g.insurance_type),
                    '阶段': g.stage, '推送比例': f'{g.percentage*100:.0f}%',
                    '状态': g.status, '开始时间': g.start_time, '结束时间': g.end_time,
                    '影响保单数': g.affected_policies_count
                } for g in grayscales]).to_excel(writer, sheet_name='灰度记录', index=False)
                pd.DataFrame([HistoryQuery._monitor_to_dict(m) for m in monitors]).to_excel(
                    writer, sheet_name='监控记录', index=False)

            return filepath
        finally:
            session.close()
