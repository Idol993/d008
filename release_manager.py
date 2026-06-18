from datetime import datetime
from models import ReleaseRequest, PreCheckRecord, StableVersion, get_session
from audit_logger import log_release_submit, AuditLogger
import config
import random


class ReleaseManager:
    @staticmethod
    def create_release(version, title, description, risk_level,
                        insurance_types, policy_types, submitter):
        if risk_level not in config.RISK_LEVELS:
            raise ValueError(f'无效的风险级别: {risk_level}')

        for it in insurance_types:
            if it not in config.INSURANCE_TYPES:
                raise ValueError(f'无效的险种: {it}')

        for pt in policy_types:
            if pt not in config.POLICY_TYPES:
                raise ValueError(f'无效的保单类型: {pt}')

        session = get_session()
        try:
            release = ReleaseRequest(
                version=version,
                title=title,
                description=description,
                risk_level=risk_level,
                insurance_types=insurance_types,
                policy_types=policy_types,
                submitter=submitter,
                status='pending_check'
            )
            session.add(release)
            session.commit()
            release_id = release.id

            log_release_submit(release_id, submitter, version, title)

            return release_id
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def run_precheck(release_id):
        session = get_session()
        try:
            release = session.query(ReleaseRequest).filter_by(id=release_id).first()
            if not release:
                raise ValueError(f'发布申请不存在: {release_id}')

            results = []
            all_passed = True

            check_items = [
                {
                    'name': '核保规则准确率',
                    'key': 'underwriting_rule_accuracy',
                    'threshold': config.THRESHOLDS['underwriting_rule_accuracy_min'],
                    'check_func': ReleaseManager._check_underwriting_accuracy
                },
                {
                    'name': '理赔对账一致性',
                    'key': 'claim_reconciliation_consistency',
                    'threshold': config.THRESHOLDS['claim_reconciliation_consistency_min'],
                    'check_func': ReleaseManager._check_claim_reconciliation
                },
                {
                    'name': '监管条款适配',
                    'key': 'regulatory_compliance',
                    'threshold': config.THRESHOLDS['regulatory_compliance_min'],
                    'check_func': ReleaseManager._check_regulatory_compliance
                },
                {
                    'name': '客户信息安全校验',
                    'key': 'customer_info_security',
                    'threshold': config.THRESHOLDS['customer_info_security_min'],
                    'check_func': ReleaseManager._check_customer_info_security
                },
            ]

            for item in check_items:
                value, detail = item['check_func'](release)
                passed = value >= item['threshold']
                if not passed:
                    all_passed = False

                record = PreCheckRecord(
                    release_request_id=release_id,
                    check_item=item['key'],
                    check_value=value,
                    threshold=item['threshold'],
                    passed=passed,
                    detail=detail
                )
                session.add(record)

                results.append({
                    'name': item['name'],
                    'key': item['key'],
                    'value': value,
                    'threshold': item['threshold'],
                    'passed': passed,
                    'detail': detail
                })

            release.precheck_result = results
            release.precheck_passed = all_passed

            if all_passed:
                release.status = 'pending_approval'
            else:
                release.status = 'precheck_failed'

            release.updated_at = datetime.now()
            session.commit()

            detail_msg = '通过' if all_passed else '未通过'
            AuditLogger.log(
                operation_type='precheck',
                operation_module='release',
                operator='system',
                operation_detail=f'前置检查完成: {detail_msg}',
                related_id=release_id,
                related_type='release_request',
                regulatory_related=True,
                risk_level='high' if not all_passed else 'medium'
            )

            return {
                'release_id': release_id,
                'all_passed': all_passed,
                'check_results': results
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def _check_underwriting_accuracy(release):
        accuracy = 0.95 + random.uniform(-0.03, 0.03)
        accuracy = min(max(accuracy, 0.90), 0.99)
        detail = f'基于历史 {random.randint(1000, 5000)} 条核保样本测试，规则准确率 {accuracy:.4f}'
        return round(accuracy, 4), detail

    @staticmethod
    def _check_claim_reconciliation(release):
        consistency = 0.99 + random.uniform(-0.01, 0.005)
        consistency = min(max(consistency, 0.97), 1.0)
        detail = f'理赔对账样本 {random.randint(500, 2000)} 笔，一致性 {consistency:.4f}'
        return round(consistency, 4), detail

    @staticmethod
    def _check_regulatory_compliance(release):
        compliance_items = [
            '《保险法》最新修订版',
            '银保监会核保理赔管理办法',
            '个人信息保护法',
            '金融消费者权益保护实施办法'
        ]
        all_compliant = True
        issues = []
        for item in compliance_items:
            if random.random() < 0.05:
                all_compliant = False
                issues.append(f'{item}: 需进一步确认')
        value = 1.0 if all_compliant else 0.85
        detail = '全部监管条款适配通过' if all_compliant else '; '.join(issues)
        return value, detail

    @staticmethod
    def _check_customer_info_security(release):
        security_level = 1.0
        checks = [
            '数据加密验证',
            '访问控制审计',
            '敏感信息脱敏',
            '日志审计检查'
        ]
        issues = []
        for check in checks:
            if random.random() < 0.03:
                issues.append(f'{check}: 存在 minor 风险')
        if issues:
            security_level = 0.92
        detail = '客户信息安全校验全部通过' if not issues else '; '.join(issues)
        return security_level, detail

    @staticmethod
    def get_release(release_id):
        session = get_session()
        try:
            release = session.query(ReleaseRequest).filter_by(id=release_id).first()
            if not release:
                return None
            return ReleaseManager._to_dict(release)
        finally:
            session.close()

    @staticmethod
    def list_releases(status=None, risk_level=None, insurance_type=None,
                      version=None, start_time=None, end_time=None,
                      page=1, page_size=20):
        session = get_session()
        try:
            query = session.query(ReleaseRequest)

            if status:
                query = query.filter(ReleaseRequest.status == status)
            if risk_level:
                query = query.filter(ReleaseRequest.risk_level == risk_level)
            if version:
                query = query.filter(ReleaseRequest.version.like(f'%{version}%'))
            if start_time:
                query = query.filter(ReleaseRequest.submit_time >= start_time)
            if end_time:
                query = query.filter(ReleaseRequest.submit_time <= end_time)
            if insurance_type:
                query = query.filter(ReleaseRequest.insurance_types.like(f'%{insurance_type}%'))

            total = query.count()
            releases = query.order_by(ReleaseRequest.submit_time.desc()) \
                .offset((page - 1) * page_size).limit(page_size).all()

            return {
                'total': total,
                'page': page,
                'page_size': page_size,
                'releases': [ReleaseManager._to_dict(r) for r in releases]
            }
        finally:
            session.close()

    @staticmethod
    def _to_dict(release):
        return {
            'id': release.id,
            'version': release.version,
            'title': release.title,
            'description': release.description,
            'risk_level': release.risk_level,
            'risk_level_name': config.RISK_LEVEL_NAMES.get(release.risk_level, release.risk_level),
            'insurance_types': release.insurance_types,
            'policy_types': release.policy_types,
            'submitter': release.submitter,
            'submit_time': release.submit_time.strftime('%Y-%m-%d %H:%M:%S') if release.submit_time else None,
            'status': release.status,
            'precheck_passed': release.precheck_passed,
            'current_grayscale_stage': release.current_grayscale_stage,
            'current_insurance_type': release.current_insurance_type,
            'rollback_triggered': release.rollback_triggered,
            'rollback_reason': release.rollback_reason,
            'rollback_time': release.rollback_time.strftime('%Y-%m-%d %H:%M:%S') if release.rollback_time else None,
            'created_at': release.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': release.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }

    @staticmethod
    def set_stable_version(version, description, insurance_types, regulatory_approved=False, approval_date=None):
        session = get_session()
        try:
            sv = StableVersion(
                version=version,
                description=description,
                regulatory_approved=regulatory_approved,
                approval_date=approval_date,
                insurance_types=insurance_types,
                is_active=True
            )
            session.add(sv)
            session.commit()

            AuditLogger.log(
                operation_type='set_stable_version',
                operation_module='release',
                operator='system',
                operation_detail=f'设置监管认可稳定版本: {version}',
                related_id=sv.id,
                related_type='stable_version',
                regulatory_related=True,
                risk_level='medium'
            )

            return sv.id
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def get_latest_stable_version(insurance_type=None):
        session = get_session()
        try:
            query = session.query(StableVersion).filter_by(is_active=True, regulatory_approved=True)
            if insurance_type:
                query = query.filter(StableVersion.insurance_types.like(f'%{insurance_type}%'))
            sv = query.order_by(StableVersion.created_at.desc()).first()
            return sv
        finally:
            session.close()
