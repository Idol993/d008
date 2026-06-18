import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import init_db, get_session, ReleaseRequest
from grayscale_manager import GrayscaleManager
from release_manager import ReleaseManager

init_db()

release_id = ReleaseManager.create_release(
    version='v3.0.0-graytest',
    title='灰度模块测试',
    description='测试灰度发布功能',
    risk_level='routine',
    insurance_types=['auto', 'life'],
    policy_types=['individual'],
    submitter='test_user'
)
print(f'创建发布: ID={release_id}')

session = get_session()
release = session.query(ReleaseRequest).filter_by(id=release_id).first()
release.status = 'approved'
release.precheck_passed = True
session.commit()
session.close()
print('设置状态: approved')

try:
    result = GrayscaleManager.start_grayscale(release_id)
    msg = result.get('message', '')
    print(f'灰度启动成功: {msg}')
    print(f'  险种: {result.get("insurance_type_name")}')
    print(f'  阶段: {result.get("stage")}')
    print(f'  比例: {result.get("percentage")*100}%')
except Exception as e:
    import traceback
    print(f'灰度启动失败: {e}')
    traceback.print_exc()

status = GrayscaleManager.get_grayscale_status(release_id)
print(f'\\n当前灰度状态:')
print(f'  整体状态: {status["overall_status"]}')
print(f'  当前险种: {status["current_insurance_type_name"]}')
print(f'  当前阶段: {status["current_stage"]}')

print(f'\\n灰度详情:')
for it, stages in status['grayscale_details'].items():
    print(f'  {it}:')
    for s in stages:
        print(f'    阶段{s["stage"]}: {s["percentage"]*100:.0f}% - {s["status"]}')

print('\n灰度模块测试完成!')
