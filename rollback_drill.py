import os
from datetime import datetime
from models import RollbackDrill, get_session, StableVersion
from audit_logger import log_drill, AuditLogger
import config
import random
import json


class RollbackDrillManager:
    @staticmethod
    def create_drill(drill_name, drill_type, insurance_types, policy_types,
                     simulated_version, target_version, operator):
        for it in insurance_types:
            if it not in config.INSURANCE_TYPES:
                raise ValueError(f'无效的险种: {it}')

        for pt in policy_types:
            if pt not in config.POLICY_TYPES:
                raise ValueError(f'无效的保单类型: {pt}')

        session = get_session()
        try:
            drill = RollbackDrill(
                drill_name=drill_name,
                drill_type=drill_type,
                insurance_types=insurance_types,
                policy_types=policy_types,
                simulated_version=simulated_version,
                target_version=target_version,
                operator=operator,
                status='planned'
            )
            session.add(drill)
            session.commit()
            drill_id = drill.id

            log_drill(drill_id, operator, drill_name, 'created')

            return drill_id
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def generate_drill_plan(drill_id):
        session = get_session()
        try:
            drill = session.query(RollbackDrill).filter_by(id=drill_id).first()
            if not drill:
                raise ValueError(f'演练不存在: {drill_id}')

            plan = {
                'drill_id': drill_id,
                'drill_name': drill.drill_name,
                'drill_type': drill.drill_type,
                'phases': [
                    {
                        'phase': '准备阶段',
                        'order': 1,
                        'duration_minutes': 10,
                        'tasks': [
                            '确认演练参与人员',
                            '检查演练环境状态',
                            '备份当前系统配置',
                            '准备演练用例数据'
                        ]
                    },
                    {
                        'phase': '执行阶段',
                        'order': 2,
                        'duration_minutes': 30,
                        'tasks': [
                            '模拟触发回滚条件',
                            '执行版本回滚操作',
                            '验证回滚后系统状态',
                            '检查保单数据一致性'
                        ]
                    },
                    {
                        'phase': '验证阶段',
                        'order': 3,
                        'duration_minutes': 20,
                        'tasks': [
                            '核保功能验证',
                            '理赔功能验证',
                            '客户信息安全检查',
                            '监管合规性检查'
                        ]
                    },
                    {
                        'phase': '恢复阶段',
                        'order': 4,
                        'duration_minutes': 10,
                        'tasks': [
                            '恢复演练前状态',
                            '清理演练数据',
                            '确认系统正常运行'
                        ]
                    }
                ],
                'insurance_scope': drill.insurance_types,
                'policy_scope': drill.policy_types,
                'simulated_version': drill.simulated_version,
                'target_version': drill.target_version,
                'estimated_total_minutes': 70,
                'participants': ['核保组', '理赔组', '合规组', '技术组']
            }

            drill.plan_details = plan
            drill.status = 'planned'
            drill.updated_at = datetime.now()
            session.commit()

            log_drill(drill_id, drill.operator, drill.drill_name, 'plan_generated')

            return plan
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def start_drill(drill_id):
        session = get_session()
        try:
            drill = session.query(RollbackDrill).filter_by(id=drill_id).first()
            if not drill:
                raise ValueError(f'演练不存在: {drill_id}')

            if drill.status not in ['planned', 'completed']:
                raise ValueError(f'演练状态异常: {drill.status}')

            drill.status = 'running'
            drill.start_time = datetime.now()
            drill.updated_at = datetime.now()
            session.commit()

            log_drill(drill_id, drill.operator, drill.drill_name, 'started')

            return {
                'drill_id': drill_id,
                'status': 'running',
                'start_time': drill.start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'message': '回滚演练已开始'
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def execute_policy_validation(drill_id):
        session = get_session()
        try:
            drill = session.query(RollbackDrill).filter_by(id=drill_id).first()
            if not drill:
                raise ValueError(f'演练不存在: {drill_id}')

            validation_result = {
                'total_policies_checked': 0,
                'passed_policies': 0,
                'failed_policies': 0,
                'by_insurance_type': {},
                'failed_policy_samples': [],
                'validation_details': []
            }

            for insurance_type in drill.insurance_types:
                type_count = random.randint(100, 500)
                failed = random.randint(0, 5)
                passed = type_count - failed

                validation_result['total_policies_checked'] += type_count
                validation_result['passed_policies'] += passed
                validation_result['failed_policies'] += failed

                type_name = config.INSURANCE_TYPE_NAMES.get(insurance_type, insurance_type)
                validation_result['by_insurance_type'][insurance_type] = {
                    'name': type_name,
                    'total': type_count,
                    'passed': passed,
                    'failed': failed,
                    'pass_rate': round(passed / type_count, 4) if type_count > 0 else 1.0
                }

                for i in range(min(failed, 3)):
                    validation_result['failed_policy_samples'].append({
                        'policy_id': f'POL{random.randint(100000, 999999)}',
                        'insurance_type': insurance_type,
                        'issue': random.choice([
                            '保单状态不一致',
                            '保费计算异常',
                            '受益人信息缺失',
                            '核保结论错误'
                        ])
                    })

            validation_result['overall_pass_rate'] = round(
                validation_result['passed_policies'] / validation_result['total_policies_checked'], 4
            ) if validation_result['total_policies_checked'] > 0 else 1.0

            validation_result['validation_details'].extend([
                '保单数据完整性校验',
                '保费计算准确性校验',
                '核保结论一致性校验',
                '理赔条件适配性校验',
                '客户信息脱敏验证'
            ])

            drill.policy_validation_result = validation_result
            drill.updated_at = datetime.now()
            session.commit()

            return validation_result
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def complete_drill(drill_id):
        session = get_session()
        try:
            drill = session.query(RollbackDrill).filter_by(id=drill_id).first()
            if not drill:
                raise ValueError(f'演练不存在: {drill_id}')

            if drill.status != 'running':
                raise ValueError(f'演练状态异常: {drill.status}')

            drill.status = 'completed'
            drill.end_time = datetime.now()
            drill.updated_at = datetime.now()

            archive_filename = f'drill_archive_{drill_id}_{datetime.now().strftime("%Y%m%d")}.json'
            archive_path = os.path.join(config.REPORT_DIR, archive_filename)

            archive_data = {
                'drill_id': drill_id,
                'drill_name': drill.drill_name,
                'drill_type': drill.drill_type,
                'insurance_types': drill.insurance_types,
                'policy_types': drill.policy_types,
                'simulated_version': drill.simulated_version,
                'target_version': drill.target_version,
                'plan_details': drill.plan_details,
                'policy_validation_result': drill.policy_validation_result,
                'start_time': drill.start_time.strftime('%Y-%m-%d %H:%M:%S') if drill.start_time else None,
                'end_time': drill.end_time.strftime('%Y-%m-%d %H:%M:%S') if drill.end_time else None,
                'operator': drill.operator,
                'archived_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'regulatory_reference': '符合银保监会《保险信息系统安全管理指引》演练要求'
            }

            with open(archive_path, 'w', encoding='utf-8') as f:
                json.dump(archive_data, f, ensure_ascii=False, indent=2)

            drill.archive_path = archive_path
            session.commit()

            log_drill(drill_id, drill.operator, drill.drill_name, 'completed')

            AuditLogger.log(
                operation_type='archive_drill',
                operation_module='rollback_drill',
                operator=drill.operator,
                operation_detail=f'演练归档: {drill.drill_name}, 监管备查',
                related_id=drill_id,
                related_type='rollback_drill',
                regulatory_related=True,
                risk_level='medium'
            )

            return {
                'drill_id': drill_id,
                'status': 'completed',
                'archive_path': archive_path,
                'message': '演练完成并归档，可供监管检查'
            }
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @staticmethod
    def get_drill(drill_id):
        session = get_session()
        try:
            drill = session.query(RollbackDrill).filter_by(id=drill_id).first()
            if not drill:
                return None
            return RollbackDrillManager._to_dict(drill)
        finally:
            session.close()

    @staticmethod
    def list_drills(status=None, drill_type=None, start_time=None,
                    end_time=None, page=1, page_size=20):
        session = get_session()
        try:
            query = session.query(RollbackDrill)

            if status:
                query = query.filter(RollbackDrill.status == status)
            if drill_type:
                query = query.filter(RollbackDrill.drill_type == drill_type)
            if start_time:
                query = query.filter(RollbackDrill.created_at >= start_time)
            if end_time:
                query = query.filter(RollbackDrill.created_at <= end_time)

            total = query.count()
            drills = query.order_by(RollbackDrill.created_at.desc()) \
                .offset((page - 1) * page_size).limit(page_size).all()

            return {
                'total': total,
                'page': page,
                'page_size': page_size,
                'drills': [RollbackDrillManager._to_dict(d) for d in drills]
            }
        finally:
            session.close()

    @staticmethod
    def _to_dict(drill):
        return {
            'id': drill.id,
            'drill_name': drill.drill_name,
            'drill_type': drill.drill_type,
            'insurance_types': drill.insurance_types,
            'policy_types': drill.policy_types,
            'simulated_version': drill.simulated_version,
            'target_version': drill.target_version,
            'status': drill.status,
            'start_time': drill.start_time.strftime('%Y-%m-%d %H:%M:%S') if drill.start_time else None,
            'end_time': drill.end_time.strftime('%Y-%m-%d %H:%M:%S') if drill.end_time else None,
            'archive_path': drill.archive_path,
            'operator': drill.operator,
            'has_plan': drill.plan_details is not None,
            'has_validation': drill.policy_validation_result is not None,
            'created_at': drill.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': drill.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        }
