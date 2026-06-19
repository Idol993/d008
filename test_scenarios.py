import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from models import init_db, get_session, ReleaseRequest, StableVersion
import config

SCENARIO_PASS = 0
SCENARIO_FAIL = 0

def _print_banner(title, idx, total):
    global SCENARIO_PASS, SCENARIO_FAIL
    print()
    print('=' * 72)
    print(f'  场景 {idx}/{total}：{title}')
    print('=' * 72)
    SCENARIO_PASS = 0
    SCENARIO_FAIL = 0

def _step(desc, cond, detail=''):
    global SCENARIO_PASS, SCENARIO_FAIL
    if cond:
        SCENARIO_PASS += 1
        print(f'  [✓ 成功] {desc}')
        if detail:
            print(f'         {detail}')
    else:
        SCENARIO_FAIL += 1
        print(f'  [✗ 失败] {desc}')
        if detail:
            print(f'         {detail}')

def _summary():
    print()
    if SCENARIO_FAIL == 0:
        print(f'  场景结果：全部通过 ({SCENARIO_PASS}/{SCENARIO_PASS + SCENARIO_FAIL})')
        return True
    else:
        print(f'  场景结果：{SCENARIO_FAIL} 项失败 ({SCENARIO_PASS}/{SCENARIO_PASS + SCENARIO_FAIL})')
        return False

def _ensure_stable_version():
    session = get_session()
    try:
        sv = session.query(StableVersion).filter_by(version='v1.0.0-SCENARIO').first()
        if not sv:
            sv = StableVersion(
                version='v1.0.0-SCENARIO',
                description='场景测试用稳定版本',
                regulatory_approved=True,
                approval_date=datetime.now() - timedelta(days=30),
                insurance_types=config.INSURANCE_TYPES,
                is_active=True
            )
            session.add(sv)
            session.commit()
        return sv.id
    finally:
        session.close()


def scenario_1_order_control():
    """
    场景 1：审批顺序控制（先跳过前置审批的失败拦截）
    目标：
      - 审批顺序必须按 workflow 顺序推进
      - 前一个环节未通过，后一个环节必须返回明确失败原因
      - 审批不在流程中必须被拦截
    """
    _print_banner('审批顺序控制 - 前序环节未通过时后续审批必须被拦截', 1, 3)

    from release_manager import ReleaseManager
    from approval_manager import ApprovalManager

    release_id = ReleaseManager.create_release(
        version=f'v9.1.0-order-{int(datetime.now().timestamp())}',
        title='[场景1] 审批顺序控制测试',
        description='routine 风险级别，流程为 underwriting -> compliance',
        risk_level='routine',
        insurance_types=['auto'],
        policy_types=['individual'],
        submitter='scenario_tester'
    )
    _step(f'创建 routine 风险发布: ID={release_id}', release_id > 0)

    ReleaseManager.run_precheck(release_id)
    init_result = ApprovalManager.initialize_approvals(release_id)
    _step(f'初始化审批流程: workflow={init_result.get("workflow")}',
          init_result.get('workflow') == ['underwriting', 'compliance'])

    status_before = ApprovalManager.get_approval_status(release_id)
    _step(f'初始状态: overall_status={status_before["overall_status"]}',
          status_before['overall_status'] in ('pending_check', 'pending_approval'))

    # Step A: 直接尝试 compliance (跳过 underwriting)，必须被拦截
    r1 = ApprovalManager.approve(release_id, 'compliance', 'compliance_1', '跳过核保直接合规')
    _step('跳过核保，直接执行合规审批',
          r1.get('status') == 'blocked',
          f'status={r1.get("status")}, reason={r1.get("blocked_reason")}')

    has_expected = '尚未通过' in (r1.get('blocked_reason') or '') or '顺序异常' in (r1.get('blocked_reason') or '')
    _step('失败原因包含“前序未通过/顺序异常”语义', has_expected,
          f'blocked_reason="{r1.get("blocked_reason")}"')

    expected_next = r1.get('expected_next_role')
    _step('返回值中指定正确的 expected_next_role=核保',
          expected_next == '核保', f'expected_next_role={expected_next}')

    attempted = r1.get('attempted_role')
    _step('返回值中包含 attempted_role=合规',
          attempted == '合规', f'attempted_role={attempted}')

    # Step B: 尝试一个完全不在流程里的角色，必须被拦截
    r2 = ApprovalManager.approve(release_id, 'legal', 'legal_1', '法务审批不在流程里')
    _step('不在审批流程中的角色(legal/routine)被拦截',
          r2.get('status') == 'blocked',
          f'status={r2.get("status")}, reason={r2.get("blocked_reason")}')

    # Step C: 先通过 underwriting，再通过 compliance (正确顺序)
    r3 = ApprovalManager.approve(release_id, 'underwriting', 'uw_1', '核保审批通过')
    _step('先执行核保审批(正确的第一步)',
          r3.get('status') == 'approving',
          f'status={r3.get("status")}, next_role_name={r3.get("next_role_name")}')

    _step('核保通过后，next_role_name=合规',
          r3.get('next_role_name') == '合规',
          f'next_role={r3.get("next_role")}, next_role_name={r3.get("next_role_name")}')

    # Step D: 再次尝试 underwriting (已处理过)，必须被拦截
    r4 = ApprovalManager.approve(release_id, 'underwriting', 'uw_2', '重复核保审批')
    _step('已通过的环节再次审批被拦截',
          r4.get('status') == 'blocked',
          f'status={r4.get("status")}, reason={r4.get("blocked_reason")}')

    # Step E: 通过 compliance，观察灰度自动启动
    r5 = ApprovalManager.approve(release_id, 'compliance', 'comp_1', '合规审批通过')
    _step('第二步合规审批通过，status=approved',
          r5.get('status') == 'approved',
          f'status={r5.get("status")}, grayscale_started={r5.get("grayscale_started")}')

    _step('审批通过后灰度启动标志 grayscale_started=True',
          r5.get('grayscale_started') is True,
          f'grayscale_started={r5.get("grayscale_started")}')

    gr = r5.get('grayscale_result') or {}
    _step('灰度返回中包含 insurance_type_name=车险',
          gr.get('insurance_type_name') == '车险',
          f'insurance_type_name={gr.get("insurance_type_name")}')

    _step(f'灰度返回中包含 stage=0, percentage=10%',
          gr.get('stage') == 0 and gr.get('percentage') == 0.1,
          f'stage={gr.get("stage")}, percentage={gr.get("percentage")}')

    _step('灰度返回中包含 affected_policies 数值',
          isinstance(gr.get('affected_policies'), int) and gr.get('affected_policies', 0) > 0,
          f'affected_policies={gr.get("affected_policies")}')

    # 验证整体状态
    status_final = ApprovalManager.get_approval_status(release_id)
    _step('最终发布状态: overall_status in (grayscaling, approved)',
          status_final['overall_status'] in ('grayscaling', 'approved'),
          f'overall_status={status_final["overall_status"]}')

    all_appr_ok = all(a['status'] == 'approved' for a in status_final['approvals'])
    _step('所有环节状态均为 approved', all_appr_ok,
          f'approvals={[(a["role_name"], a["status"]) for a in status_final["approvals"]]}')

    # 验证灰度状态接口能看到明细
    from grayscale_manager import GrayscaleManager
    gs = GrayscaleManager.get_grayscale_status(release_id)
    _step('get_grayscale_status 返回 overall_status=grayscaling',
          gs['overall_status'] == 'grayscaling',
          f'overall_status={gs["overall_status"]}')

    _step(f'get_grayscale_status 返回 current_insurance_type_name=车险',
          gs['current_insurance_type_name'] == '车险',
          f'current_insurance_type_name={gs["current_insurance_type_name"]}')

    _step(f'get_grayscale_status 返回 current_stage=0',
          gs['current_stage'] == 0,
          f'current_stage={gs["current_stage"]}')

    details = gs.get('grayscale_details', {}).get('auto', [])
    running_stage = next((s for s in details if s['status'] == 'running'), None)
    _step('灰度明细中存在 running 阶段=10%',
          running_stage is not None and running_stage['percentage'] == 0.1,
          f'running_stage={running_stage}')

    return _summary()


def scenario_2_manual_vs_auto_consistency():
    """
    场景 2：手动审批 vs 自动审批 - 结果一致性 + 灰度启动
    目标：
      - 手动审批走完所有环节 -> 灰度启动
      - 批量自动审批 -> 灰度启动
      - 两条路径最终状态一致（grayscaling，险种/阶段/比例字段齐全）
    """
    _print_banner('手动审批 vs 批量自动审批一致性 + 灰度启动确认', 2, 3)

    from release_manager import ReleaseManager
    from approval_manager import ApprovalManager
    from grayscale_manager import GrayscaleManager

    # ----- Part A: 手动审批全流程 -----
    rid_manual = ReleaseManager.create_release(
        version=f'v9.2.0-manual-{int(datetime.now().timestamp())}',
        title='[场景2A] 手动审批全流程测试',
        description='urgent_claim 风险级别: claim -> underwriting -> compliance -> legal',
        risk_level='urgent_claim',
        insurance_types=['life', 'critical_illness'],
        policy_types=['individual', 'group'],
        submitter='scenario_tester'
    )
    ReleaseManager.run_precheck(rid_manual)
    ApprovalManager.initialize_approvals(rid_manual)
    _step(f'A. 创建 urgent_claim 发布 ID={rid_manual} (4个审批环节)', rid_manual > 0)

    r = ApprovalManager.approve(rid_manual, 'claim', 'c1', '理赔通过')
    _step('A1. 第一步 claim 审批通过 -> status=approving',
          r.get('status') == 'approving', f'next={r.get("next_role_name")}')

    r = ApprovalManager.approve(rid_manual, 'underwriting', 'uw1', '核保通过')
    _step('A2. 第二步 underwriting 审批通过 -> status=approving',
          r.get('status') == 'approving', f'next={r.get("next_role_name")}')

    r = ApprovalManager.approve(rid_manual, 'compliance', 'cmp1', '合规通过')
    _step('A3. 第三步 compliance 审批通过 -> status=approving',
          r.get('status') == 'approving', f'next={r.get("next_role_name")}')

    r = ApprovalManager.approve(rid_manual, 'legal', 'lgl1', '法务通过')
    _step('A4. 第四步 legal 审批通过 -> status=approved, grayscale_started=True',
          r.get('status') == 'approved' and r.get('grayscale_started') is True,
          f'status={r.get("status")}, grayscale_started={r.get("grayscale_started")}')

    gr_manual = r.get('grayscale_result', {})
    _step('A5. 手动审批末环节返回灰度明细(寿险/第0阶段/5%)',
          gr_manual.get('insurance_type_name') == '寿险'
          and gr_manual.get('stage') == 0
          and gr_manual.get('percentage') == 0.05,
          f'insurance_type_name={gr_manual.get("insurance_type_name")}, '
          f'stage={gr_manual.get("stage")}, percentage={gr_manual.get("percentage")}')

    gs_manual = GrayscaleManager.get_grayscale_status(rid_manual)
    _step('A6. get_grayscale_status 整体=grayscaling, 险种=寿险, 阶段=0',
          gs_manual['overall_status'] == 'grayscaling'
          and gs_manual['current_insurance_type_name'] == '寿险'
          and gs_manual['current_stage'] == 0,
          f'overall={gs_manual["overall_status"]}, '
          f'insurance={gs_manual["current_insurance_type_name"]}, '
          f'stage={gs_manual["current_stage"]}')

    # ----- Part B: 批量自动审批流程 -----
    rid_auto = ReleaseManager.create_release(
        version=f'v9.2.0-auto-{int(datetime.now().timestamp())}',
        title='[场景2B] 批量自动审批测试',
        description='regulatory_update 风险级别: compliance -> legal -> underwriting -> claim',
        risk_level='regulatory_update',
        insurance_types=['auto', 'life'],
        policy_types=['individual'],
        submitter='scenario_tester'
    )
    ReleaseManager.run_precheck(rid_auto)
    ApprovalManager.initialize_approvals(rid_auto)
    _step(f'B. 创建 regulatory_update 发布 ID={rid_auto}', rid_auto > 0)

    auto = ApprovalManager.batch_auto_approve(rid_auto, 'scenario_batch')
    _step('B1. batch_auto_approve 返回 status=approved',
          auto.get('status') == 'approved',
          f'status={auto.get("status")}')

    _step('B2. batch_auto_approve 返回 grayscale_started=True',
          auto.get('grayscale_started') is True,
          f'grayscale_started={auto.get("grayscale_started")}')

    gr_auto = auto.get('grayscale_result', {})
    _step('B3. 批量审批末环节返回灰度明细(合规/第0阶段/5%)',
          gr_auto.get('insurance_type_name') == '车险'
          and gr_auto.get('stage') == 0
          and gr_auto.get('percentage') == 0.1,
          f'insurance_type_name={gr_auto.get("insurance_type_name")}, '
          f'stage={gr_auto.get("stage")}, percentage={gr_auto.get("percentage")}')

    gs_auto = GrayscaleManager.get_grayscale_status(rid_auto)
    _step('B4. get_grayscale_status 整体=grayscaling, 险种=车险, 阶段=0',
          gs_auto['overall_status'] == 'grayscaling'
          and gs_auto['current_insurance_type_name'] == '车险'
          and gs_auto['current_stage'] == 0,
          f'overall={gs_auto["overall_status"]}, '
          f'insurance={gs_auto["current_insurance_type_name"]}, '
          f'stage={gs_auto["current_stage"]}')

    # 验证两个路径最终状态一致
    status_consistent = (
        gs_manual['overall_status'] == gs_auto['overall_status'] == 'grayscaling'
        and gs_manual['current_stage'] == gs_auto['current_stage'] == 0
    )
    _step('B5. 手动审批路径 与 批量自动审批路径 最终状态一致 (grayscaling + stage=0)',
          status_consistent,
          f'手动: overall={gs_manual["overall_status"]}, stage={gs_manual["current_stage"]}; '
          f'自动: overall={gs_auto["overall_status"]}, stage={gs_auto["current_stage"]}')

    session = get_session()
    try:
        rm = session.query(ReleaseRequest).filter(ReleaseRequest.id.in_([rid_manual, rid_auto])).all()
        all_grayscale = all(r.status == 'grayscaling' for r in rm)
        _step('B6. 数据库层面两条发布 status=grayscaling',
              all_grayscale,
              f'statuses={[(r.id, r.status) for r in rm]}')
    finally:
        session.close()

    return _summary()


def scenario_3_rollback_then_monitor():
    """
    场景 3：回滚后继续稳定版监控
    目标：
      - 触发 rollback 后，发布状态变为 rolled_back
      - 再次 collect_metrics 能产生稳定版监控记录
      - 监控记录显示 is_rolled_back_monitoring=True，version_label 含 STABLE
      - 即使指标波动，稳定版监控不触发二次回滚
      - 历史查询可区分普通监控与回滚后稳定版监控 (grayscale_stage=-1)
    """
    _print_banner('回滚后继续稳定版监控 + 二次监控不触发回滚', 3, 3)

    from release_manager import ReleaseManager
    from approval_manager import ApprovalManager
    from monitor_rollback import MonitorManager, RollbackManager

    _ensure_stable_version()

    rid = ReleaseManager.create_release(
        version=f'v9.3.0-rollback-{int(datetime.now().timestamp())}',
        title='[场景3] 回滚后稳定版监控测试',
        risk_level='routine',
        insurance_types=['auto'],
        policy_types=['individual'],
        description='测试回滚后是否继续产生稳定版监控记录',
        submitter='scenario_tester'
    )
    ReleaseManager.run_precheck(rid)
    ApprovalManager.initialize_approvals(rid)
    ApprovalManager.batch_auto_approve(rid, 'scenario_3')
    _step(f'创建发布+审批通过: ID={rid}', rid > 0)

    # 采集 2 次正常监控
    m1 = MonitorManager.collect_metrics(rid)
    m2 = MonitorManager.collect_metrics(rid)
    _step('回滚前采集 2 次正常监控',
          not m1.get('is_rolled_back_monitoring') and not m2.get('is_rolled_back_monitoring'),
          f'm1.stage={m1.get("stage")}, m2.stage={m2.get("stage")}, '
          f'm1.rolled_back={m1.get("is_rolled_back_monitoring")}')

    # 触发手动回滚
    rb = RollbackManager.trigger_rollback(rid, '场景3 触发回滚', 'manual')
    _step(f'触发回滚 rollback_id={rb["rollback_id"]}',
          rb.get('status') == 'completed',
          f'from={rb.get("from_version")}, to={rb.get("to_version")}')

    session = get_session()
    try:
        rel = session.query(ReleaseRequest).filter_by(id=rid).first()
        _step('数据库层面 release.status=rolled_back',
              rel.status == 'rolled_back',
              f'status={rel.status}')
    finally:
        session.close()

    RollbackManager.restart_monitoring_after_rollback(rid)

    # 采集 5 次稳定版监控
    stable_metrics = []
    for i in range(5):
        m = MonitorManager.collect_metrics(rid)
        stable_metrics.append(m)

    all_stable = all(m.get('is_rolled_back_monitoring') for m in stable_metrics)
    _step('回滚后 5 次监控 is_rolled_back_monitoring 全部=True',
          all_stable,
          f'is_rolled_back_flags={[m.get("is_rolled_back_monitoring") for m in stable_metrics]}')

    all_label_ok = all('STABLE' in (m.get('version_label') or '') for m in stable_metrics)
    _step('回滚后监控 version_label 均含 STABLE 前缀',
          all_label_ok,
          f'version_labels={[m.get("version_label") for m in stable_metrics]}')

    all_stage_neg1 = all(m.get('stage') == -1 for m in stable_metrics)
    _step('回滚后监控 stage 字段均为 -1 (稳定版标识)',
          all_stage_neg1,
          f'stages={[m.get("stage") for m in stable_metrics]}')

    # 验证 4 项指标在合理范围内
    pass_rates = [m['underwriting_pass_rate'] for m in stable_metrics]
    delays = [m['claim_process_delay_seconds'] for m in stable_metrics]
    abnormals = [m['claim_abnormal_rate'] for m in stable_metrics]
    leaks = [m['info_leak_risk'] for m in stable_metrics]

    _step(f'稳定版核保通过率均在 [82%, 97%] 内: {[f"{r*100:.1f}%" for r in pass_rates]}',
          all(0.82 <= r <= 0.97 for r in pass_rates))

    _step(f'稳定版理赔延迟均在 [900s, 3200s] 内: {[f"{d:.0f}s" for d in delays]}',
          all(900 <= d <= 3200 for d in delays))

    _step(f'稳定版赔付异常率均在 [0.1%, 4%] 内: {[f"{r*100:.2f}%" for r in abnormals]}',
          all(0.001 <= r <= 0.04 for r in abnormals))

    _step(f'稳定版信息泄露风险均在 [0.01%, 0.8%] 内: {[f"{r*100:.4f}%" for r in leaks]}',
          all(0.0001 <= r <= 0.008 for r in leaks))

    # 验证不触发二次回滚
    threshold_flags = [m.get('threshold_exceeded', False) for m in stable_metrics]
    trigger_record = MonitorManager.get_latest_monitor(rid)
    no_auto_rollback = True
    session = get_session()
    try:
        rel = session.query(ReleaseRequest).filter_by(id=rid).first()
        no_auto_rollback = (rel.status == 'rolled_back')
    finally:
        session.close()
    _step('稳定版监控期间即使超阈值也不触发二次自动回滚（状态保持 rolled_back）',
          no_auto_rollback,
          f'threshold_flags={threshold_flags}, 最终status=rolled_back')

    # 用 history 区分
    history = MonitorManager.get_monitor_history(rid, limit=100)
    normal_cnt = sum(1 for m in history if m.get('grayscale_stage') != -1)
    stable_cnt = sum(1 for m in history if m.get('grayscale_stage') == -1)
    _step(f'历史监控记录 普通:{normal_cnt}条, 稳定版:{stable_cnt}条 (共{len(history)}条)',
          normal_cnt >= 2 and stable_cnt >= 5,
          f'normal={normal_cnt}, stable={stable_cnt}, total={len(history)}')

    return _summary()


def main():
    print('╔' + '═' * 70 + '╗')
    print('║' + '  保险核保理赔系统 - 三大核心场景自动化测试脚本'.center(70) + '║')
    print('╚' + '═' * 70 + '╝')
    print()
    print('  覆盖场景：')
    print('    1. 审批顺序控制 - 先跳过前置审批的失败拦截')
    print('    2. 手动审批 vs 批量自动审批结果一致性 + 灰度启动确认')
    print('    3. 回滚后再次监控 - 稳定版监控持续 + 不触发二次回滚')
    print()

    try:
        import shutil
        db_path = os.path.join(os.path.dirname(__file__), 'data', 'insurance_underwriting.db')
        if os.path.exists(db_path):
            backup = db_path + '.bak_' + datetime.now().strftime('%Y%m%d%H%M%S')
            shutil.copy(db_path, backup)
            os.remove(db_path)
    except Exception as e:
        pass
    init_db()

    results = []
    results.append(('场景1 - 审批顺序控制', scenario_1_order_control()))
    results.append(('场景2 - 手动/自动审批一致性+灰度启动', scenario_2_manual_vs_auto_consistency()))
    results.append(('场景3 - 回滚后稳定版监控', scenario_3_rollback_then_monitor()))

    print()
    print('╔' + '═' * 70 + '╗')
    print('║' + '  总 结 汇 总'.center(70) + '║')
    print('╠' + '═' * 70 + '╣')
    all_ok = True
    for name, ok in results:
        tag = '✓ PASS' if ok else '✗ FAIL'
        print(f'║  {tag}  {name}'.ljust(70) + '║')
        if not ok:
            all_ok = False
    print('╠' + '═' * 70 + '╣')
    if all_ok:
        print('║  🏆 所有场景全部通过！系统行为符合预期  '.ljust(70) + '║')
    else:
        print('║  ⚠️  存在失败场景，请检查上方失败步骤  '.ljust(70) + '║')
    print('╚' + '═' * 70 + '╝')
    print()
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
