from datetime import datetime
from models import ReleaseRequest, ApprovalRecord, get_session
from audit_logger import log_approval, AuditLogger
import config


def _start_grayscale_for_approved_release(release_id):
    try:
        from grayscale_manager import GrayscaleManager
        return GrayscaleManager.start_grayscale(release_id)
    except Exception as e:
        return {'error': str(e), 'message': f'灰度启动失败: {e}'}


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

            release.status = 'pending_approval'
            release.updated_at = datetime.now()
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

            workflow = ApprovalManager.generate_approval_workflow(release.risk_level)

            if role not in workflow:
                return {
                    'release_id': release_id,
                    'status': 'blocked',
                    'blocked_reason': f'审批失败: {config.APPROVAL_ROLE_NAMES.get(role, role)}不在审批流程中',
                    'workflow': [config.APPROVAL_ROLE_NAMES.get(r, r) for r in workflow],
                    'message': f'审批被拦截: {role}不在审批流程中'
                }

            current_role_index = workflow.index(role)
            for i in range(current_role_index):
                prev_role = workflow[i]
                prev_approval = session.query(ApprovalRecord).filter_by(
                    release_request_id=release_id,
                    role=prev_role
                ).first()
                if not prev_approval or prev_approval.status != 'approved':
                    prev_role_name = config.APPROVAL_ROLE_NAMES.get(prev_role, prev_role)
                    cur_role_name = config.APPROVAL_ROLE_NAMES.get(role, role)
                    return {
                        'release_id': release_id,
                        'status': 'blocked',
                        'blocked_reason': f'审批顺序异常: {prev_role_name}尚未通过, 不能执行{cur_role_name}审批',
                        'expected_next_role': prev_role_name,
                        'attempted_role': cur_role_name,
                        'workflow_status': ApprovalManager._get_workflow_status(session, release_id, workflow),
                        'message': f'审批被拦截: 请先完成{prev_role_name}审批'
                    }

            approval = session.query(ApprovalRecord).filter_by(
                release_request_id=release_id,
                role=role,
                status='pending'
            ).first()

            if not approval:
                existing = session.query(ApprovalRecord).filter_by(
                    release_request_id=release_id,
                    role=role
                ).first()
                if existing:
                    role_name = config.APPROVAL_ROLE_NAMES.get(role, role)
                    return {
                        'release_id': release_id,
                        'status': 'blocked',
                        'blocked_reason': f'{role_name}审批已处理, 状态={existing.status}',
                        'message': f'审批被拦截: {role_name}已处理过'
                    }
                else:
                    role_name = config.APPROVAL_ROLE_NAMES.get(role, role)
                    return {
                        'release_id': release_id,
                        'status': 'blocked',
                        'blocked_reason': f'{role_name}审批记录不存在',
                        'message': f'审批被拦截: {role_name}记录不存在'
                    }

            approval.status = 'approved' if passed else 'rejected'
            approval.comment = comment
            approval.approve_time = datetime.now()

            log_approval(release_id, role, approver, approval.status, comment, session=session)

            if not passed:
                release.status = 'rejected'
                release.updated_at = datetime.now()
                session.commit()
                role_name = config.APPROVAL_ROLE_NAMES.get(role, role)
                return {
                    'release_id': release_id,
                    'status': 'rejected',
                    'rejected_by': role,
                    'rejected_by_name': role_name,
                    'message': f'{role_name}审批被驳回'
                }

            if current_role_index == len(workflow) - 1:
                release.status = 'approved'
                release.updated_at = datetime.now()

                AuditLogger.log(
                    operation_type='all_approved',
                    operation_module='compliance',
                    operator='system',
                    operation_detail='所有审批通过，发布审批流程完成',
                    related_id=release_id,
                    related_type='release_request',
                    regulatory_related=True,
                    risk_level='high',
                    session=session
                )

                session.commit()

                grayscale_result = _start_grayscale_for_approved_release(release_id)

                return {
                    'release_id': release_id,
                    'status': 'approved',
                    'grayscale_started': 'error' not in grayscale_result,
                    'grayscale_result': grayscale_result,
                    'message': '所有审批通过，已自动启动灰度发布'
                }

            next_role = workflow[current_role_index + 1]
            next_role_name = config.APPROVAL_ROLE_NAMES.get(next_role, next_role)
            cur_role_name = config.APPROVAL_ROLE_NAMES.get(role, role)

            release.updated_at = datetime.now()
            session.commit()

            return {
                'release_id': release_id,
                'status': 'approving',
                'current_approved_role': role,
                'current_approved_role_name': cur_role_name,
                'next_role': next_role,
                'next_role_name': next_role_name,
                'workflow_status': ApprovalManager._get_workflow_status(session, release_id, workflow),
                'message': f'{cur_role_name}审批通过，等待{next_role_name}审批'
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def _get_workflow_status(session, release_id, workflow):
        result = []
        for role in workflow:
            approval = session.query(ApprovalRecord).filter_by(
                release_request_id=release_id,
                role=role
            ).first()
            result.append({
                'role': role,
                'role_name': config.APPROVAL_ROLE_NAMES.get(role, role),
                'status': approval.status if approval else 'not_initialized',
                'approver': approval.approver if approval else None
            })
        return result

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

            for idx, role in enumerate(workflow):
                for prev_idx in range(idx):
                    prev_role = workflow[prev_idx]
                    prev_approval = session.query(ApprovalRecord).filter_by(
                        release_request_id=release_id,
                        role=prev_role
                    ).first()
                    if prev_approval:
                        prev_approval.status = 'approved'
                        prev_approval.approver = f'{operator}_auto'
                        prev_approval.comment = '系统自动审批通过'
                        prev_approval.approve_time = datetime.now()

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

                    log_approval(release_id, role, f'{operator}_auto', 'approved',
                                 '系统自动审批通过', session=session)

            release.status = 'approved'
            release.updated_at = datetime.now()

            AuditLogger.log(
                operation_type='auto_approve',
                operation_module='compliance',
                operator=operator,
                operation_detail=f'自动审批通过所有环节: {",".join(workflow)}',
                related_id=release_id,
                related_type='release_request',
                regulatory_related=True,
                risk_level='high',
                session=session
            )

            AuditLogger.log(
                operation_type='all_approved',
                operation_module='compliance',
                operator=operator,
                operation_detail='所有审批通过(自动)，发布审批流程完成',
                related_id=release_id,
                related_type='release_request',
                regulatory_related=True,
                risk_level='high',
                session=session
            )

            session.commit()

            grayscale_result = _start_grayscale_for_approved_release(release_id)

            return {
                'release_id': release_id,
                'status': 'approved',
                'workflow': workflow,
                'grayscale_started': 'error' not in grayscale_result,
                'grayscale_result': grayscale_result,
                'message': '自动审批通过，已自动启动灰度发布'
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
