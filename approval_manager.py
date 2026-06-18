from datetime import datetime
from models import ReleaseRequest, ApprovalRecord, get_session
from audit_logger import log_approval, AuditLogger
import config


class ApprovalManager:
    @staticmethod
    def generate_approval_workflow(risk_level):
        workflows = {
            'routine': ['underwriting', 'compliance'],
            'urgent_claim': ['claim', 'underwriting', 'compliance', 'legal'],
            'regulatory_update': ['compliance', 'legal', 'underwriting', 'claim']
        }
        return workflows.get(risk_level, ['underwriting', 'compliance'])

    @staticmethod
    def initialize_approvals(release_id):
        session = get_session()
        try:
            release = session.query(ReleaseRequest).filter_by(id=release_id).first()
            if not release:
                raise ValueError(f'发布申请不存在: {release_id}')

            workflow = ApprovalManager.generate_approval_workflow(release.risk_level)

            existing_count = session.query(ApprovalRecord).filter_by(
                release_request_id=release_id
            ).count()

            if existing_count > 0:
                return {'message': '审批流程已初始化'}

            for role in workflow:
                approver = config.APPROVERS.get(role, [f'{role}@insurance.com'])[0]
                record = ApprovalRecord(
                    release_request_id=release_id,
                    role=role,
                    approver=approver,
                    status='pending'
                )
                session.add(record)

            session.commit()

            AuditLogger.log(
                operation_type='init_approval',
                operation_module='compliance',
                operator='system',
                operation_detail=f'初始化审批流程: 风险级别{release.risk_level}, 审批环节{",".join(workflow)}',
                related_id=release_id,
                related_type='release_request',
                regulatory_related=True,
                risk_level='high'
            )

            return {
                'release_id': release_id,
                'risk_level': release.risk_level,
                'workflow': workflow,
                'message': '审批流程初始化成功'
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def approve(release_id, role, approver, comment='', passed=True):
        session = get_session()
        try:
            release = session.query(ReleaseRequest).filter_by(id=release_id).first()
            if not release:
                raise ValueError(f'发布申请不存在: {release_id}')

            approval = session.query(ApprovalRecord).filter_by(
                release_request_id=release_id,
                role=role,
                status='pending'
            ).first()

            if not approval:
                pending = session.query(ApprovalRecord).filter_by(
                    release_request_id=release_id,
                    role=role
                ).first()
                if pending:
                    raise ValueError(f'{role}审批已处理')
                else:
                    raise ValueError(f'{role}不在审批流程中')

            approval.status = 'approved' if passed else 'rejected'
            approval.comment = comment
            approval.approve_time = datetime.now()

            log_approval(release_id, role, approver, approval.status, comment)

            if not passed:
                release.status = 'rejected'
                release.updated_at = datetime.now()
                session.commit()
                return {
                    'release_id': release_id,
                    'status': 'rejected',
                    'rejected_by': role,
                    'message': '审批被驳回'
                }

            workflow = ApprovalManager.generate_approval_workflow(release.risk_level)
            current_index = workflow.index(role) if role in workflow else -1

            if current_index == len(workflow) - 1:
                release.status = 'approved'
                release.updated_at = datetime.now()
                session.commit()

                AuditLogger.log(
                    operation_type='all_approved',
                    operation_module='compliance',
                    operator='system',
                    operation_detail='所有审批通过，发布审批流程完成',
                    related_id=release_id,
                    related_type='release_request',
                    regulatory_related=True,
                    risk_level='high'
                )

                return {
                    'release_id': release_id,
                    'status': 'approved',
                    'message': '所有审批通过，可以开始灰度发布'
                }

            next_role = workflow[current_index + 1]
            next_approval = session.query(ApprovalRecord).filter_by(
                release_request_id=release_id,
                role=next_role
            ).first()

            if next_approval and next_approval.status == 'pending':
                pass

            release.updated_at = datetime.now()
            session.commit()

            return {
                'release_id': release_id,
                'status': 'approving',
                'current_approved_role': role,
                'next_role': next_role,
                'message': f'{role}审批通过，等待{next_role}审批'
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def get_approval_status(release_id):
        session = get_session()
        try:
            release = session.query(ReleaseRequest).filter_by(id=release_id).first()
            if not release:
                raise ValueError(f'发布申请不存在: {release_id}')

            approvals = session.query(ApprovalRecord).filter_by(
                release_request_id=release_id
            ).order_by(ApprovalRecord.created_at.asc()).all()

            workflow = ApprovalManager.generate_approval_workflow(release.risk_level)

            approval_list = []
            for role in workflow:
                approval = next((a for a in approvals if a.role == role), None)
                approval_list.append({
                    'role': role,
                    'role_name': config.APPROVAL_ROLE_NAMES.get(role, role),
                    'approver': approval.approver if approval else None,
                    'status': approval.status if approval else 'pending',
                    'comment': approval.comment if approval else None,
                    'approve_time': approval.approve_time.strftime('%Y-%m-%d %H:%M:%S') if approval and approval.approve_time else None
                })

            return {
                'release_id': release_id,
                'version': release.version,
                'risk_level': release.risk_level,
                'overall_status': release.status,
                'approvals': approval_list
            }
        finally:
            session.close()

    @staticmethod
    def get_pending_approvals(role=None, page=1, page_size=20):
        session = get_session()
        try:
            query = session.query(ApprovalRecord).filter_by(status='pending')

            if role:
                query = query.filter(ApprovalRecord.role == role)

            total = query.count()
            approvals = query.order_by(ApprovalRecord.created_at.desc()) \
                .offset((page - 1) * page_size).limit(page_size).all()

            result = []
            for approval in approvals:
                release = session.query(ReleaseRequest).filter_by(
                    id=approval.release_request_id
                ).first()
                result.append({
                    'approval_id': approval.id,
                    'release_id': approval.release_request_id,
                    'version': release.version if release else None,
                    'title': release.title if release else None,
                    'risk_level': release.risk_level if release else None,
                    'role': approval.role,
                    'role_name': config.APPROVAL_ROLE_NAMES.get(approval.role, approval.role),
                    'approver': approval.approver,
                    'created_at': approval.created_at.strftime('%Y-%m-%d %H:%M:%S')
                })

            return {
                'total': total,
                'page': page,
                'page_size': page_size,
                'approvals': result
            }
        finally:
            session.close()

    @staticmethod
    def batch_auto_approve(release_id, operator='system'):
        session = get_session()
        try:
            release = session.query(ReleaseRequest).filter_by(id=release_id).first()
            if not release:
                raise ValueError(f'发布申请不存在: {release_id}')

            workflow = ApprovalManager.generate_approval_workflow(release.risk_level)

            for role in workflow:
                approval = session.query(ApprovalRecord).filter_by(
                    release_request_id=release_id,
                    role=role,
                    status='pending'
                ).first()
                if approval:
                    approval.status = 'approved'
                    approval.approver = f'{operator}_auto'
                    approval.comment = '系统自动审批通过'
                    approval.approve_time = datetime.now()

            release.status = 'approved'
            release.updated_at = datetime.now()
            session.commit()

            AuditLogger.log(
                operation_type='auto_approve',
                operation_module='compliance',
                operator=operator,
                operation_detail=f'自动审批通过所有环节',
                related_id=release_id,
                related_type='release_request',
                regulatory_related=True,
                risk_level='high'
            )

            return {
                'release_id': release_id,
                'status': 'approved',
                'workflow': workflow,
                'message': '自动审批通过'
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
