import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print('Step 1: Import modules...')
from models import init_db, get_session, ReleaseRequest
from grayscale_manager import GrayscaleManager
from release_manager import ReleaseManager
from audit_logger import log_grayscale
print('  OK')

print('Step 2: Init DB...')
init_db()
print('  OK')

print('Step 3: Create release...')
release_id = ReleaseManager.create_release(
    version='v3.0.0-debug',
    title='debug test',
    description='test',
    risk_level='routine',
    insurance_types=['auto'],
    policy_types=['individual'],
    submitter='test'
)
print(f'  release_id={release_id}')

print('Step 4: Set status to approved...')
session = get_session()
release = session.query(ReleaseRequest).filter_by(id=release_id).first()
print(f'  before: status={release.status}')
release.status = 'approved'
release.precheck_passed = True
session.commit()
print(f'  after: status={release.status}')
session.close()
print('  OK')

print('Step 5: Call start_grayscale...')
try:
    result = GrayscaleManager.start_grayscale(release_id)
    print(f'  result={result}')
except Exception as e:
    import traceback
    print(f'  ERROR: {e}')
    traceback.print_exc()
print('  Done')

print('\\nAll steps completed!')
