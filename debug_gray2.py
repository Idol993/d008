import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import init_db, get_session, ReleaseRequest, GrayscaleRecord
from release_manager import ReleaseManager
import config

print('Init DB...')
init_db()

print('Create release...')
release_id = ReleaseManager.create_release(
    version='v4.0.0-debug',
    title='debug test',
    description='test',
    risk_level='routine',
    insurance_types=['auto'],
    policy_types=['individual'],
    submitter='test'
)
print(f'  release_id={release_id}')

print('Set status to approved...')
session = get_session()
release = session.query(ReleaseRequest).filter_by(id=release_id).first()
release.status = 'approved'
release.precheck_passed = True
session.commit()
print(f'  OK, status={release.status}')

print('Check insurance_types type...')
print(f'  type={type(release.insurance_types)}')
print(f'  value={release.insurance_types}')
print(f'  first={release.insurance_types[0]}')

first_insurance = release.insurance_types[0]
print(f'first_insurance={first_insurance}')

stages = config.GRAYSCALE_STRATEGY.get(first_insurance, [0.1, 0.5, 1.0])
print(f'stages={stages}')

print('Creating grayscale records...')
for idx, pct in enumerate(stages):
    record = GrayscaleRecord(
        release_request_id=release_id,
        insurance_type=first_insurance,
        stage=idx,
        percentage=pct,
        status='pending'
    )
    session.add(record)
    print(f'  added stage {idx}: {pct}')

print('Updating release...')
release.current_insurance_type = first_insurance
release.current_grayscale_stage = 0
release.status = 'grayscaling'
release.updated_at = __import__('datetime').datetime.now()
print('  flushing...')
session.flush()
print('  flushed OK')

print('Query record...')
record = session.query(GrayscaleRecord).filter_by(
    release_request_id=release.id,
    insurance_type=first_insurance,
    stage=0
).first()
print(f'  found: {record is not None}')
if record:
    print(f'  stage={record.stage}, pct={record.percentage}')

print('Testing log_grayscale...')
from audit_logger import log_grayscale
try:
    log_grayscale(release.id, first_insurance, 0, stages[0])
    print('  log_grayscale OK')
except Exception as e:
    print(f'  log_grayscale ERROR: {e}')
    import traceback
    traceback.print_exc()

print('Committing...')
session.commit()
print('  commit OK')

session.close()

print('\\nAll debug steps completed!')
