import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from models import init_db, get_session, ReleaseRequest, StableVersion
from release_manager import ReleaseManager
from approval_manager import ApprovalManager
from grayscale_manager import GrayscaleManager

print('Step 1: Check stable version...')
session = get_session()
sv = session.query(StableVersion).filter_by(version='v1.0.0-STABLE').first()
if sv:
    print('  exists')
else:
    print('  not found, creating...')
    sv = StableVersion(
        version='v1.0.0-STABLE',
        description='test stable',
        regulatory_approved=True,
        approval_date=datetime.now() - timedelta(days=30),
        insurance_types=['auto', 'life', 'critical_illness'],
        is_active=True
    )
    session.add(sv)
    session.commit()
    print('  created')
session.close()

print('Step 2: Create test release...')
import random
test_version = f'v2.0.0-rollback-test-{random.randint(1000, 9999)}'
release_id = ReleaseManager.create_release(
    version=test_version,
    title='rollback test',
    description='test',
    risk_level='routine',
    insurance_types=['auto'],
    policy_types=['individual'],
    submitter='test'
)
print(f'  release_id={release_id}')

print('Step 3: Approve & start grayscale...')
ApprovalManager.batch_auto_approve(release_id, 'test')
GrayscaleManager.start_grayscale(release_id)
print('  OK')

print('Step 4: Get stable version again (separate session)...')
try:
    sv = ReleaseManager.get_latest_stable_version()
    print(f'  OK: {sv.version}')
except Exception as e:
    print(f'  ERROR: {e}')
    import traceback
    traceback.print_exc()

print('Step 5: Import RollbackManager...')
try:
    from monitor_rollback import RollbackManager
    print('  OK')
except Exception as e:
    print(f'  ERROR: {e}')
    import traceback
    traceback.print_exc()

print('Step 6: Trigger rollback...')
try:
    result = RollbackManager.trigger_rollback(release_id, 'test reason', 'manual')
    print(f'  OK: rollback_id={result["rollback_id"]}')
except Exception as e:
    print(f'  ERROR: {e}')
    import traceback
    traceback.print_exc()

print('\\nAll done!')
