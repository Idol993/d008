import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from models import init_db, get_session, ReleaseRequest, StableVersion
from release_manager import ReleaseManager
from approval_manager import ApprovalManager
from grayscale_manager import GrayscaleManager

print('Init DB...')
init_db()

print('Create stable version...')
ReleaseManager.set_stable_version(
    version='v1.0.0-STABLE',
    description='test stable',
    insurance_types=['auto', 'life', 'critical_illness'],
    regulatory_approved=True,
    approval_date=datetime.now() - timedelta(days=30)
)
print('  OK')

print('Create release...')
release_id = ReleaseManager.create_release(
    version='v2.0.0-rollback-test',
    title='rollback test',
    description='test',
    risk_level='routine',
    insurance_types=['auto'],
    policy_types=['individual'],
    submitter='test'
)
print(f'  release_id={release_id}')

print('Set approved & start grayscale...')
session = get_session()
release = session.query(ReleaseRequest).filter_by(id=release_id).first()
release.status = 'approved'
release.precheck_passed = True
session.commit()
session.close()

GrayscaleManager.start_grayscale(release_id)
print('  OK')

print('Step 1: test get_latest_stable_version...')
try:
    sv = ReleaseManager.get_latest_stable_version()
    print(f'  OK: version={sv.version}')
except Exception as e:
    print(f'  ERROR: {e}')
    import traceback
    traceback.print_exc()

print('Step 2: import RollbackManager...')
try:
    from monitor_rollback import RollbackManager
    print('  OK')
except Exception as e:
    print(f'  ERROR: {e}')
    import traceback
    traceback.print_exc()

print('Step 3: test trigger_rollback...')
try:
    result = RollbackManager.trigger_rollback(release_id, 'test reason', 'manual')
    print(f'  OK: rollback_id={result["rollback_id"]}')
except Exception as e:
    print(f'  ERROR: {e}')
    import traceback
    traceback.print_exc()

print('\\nAll done!')
