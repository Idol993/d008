import os
from datetime import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
REPORT_DIR = os.path.join(BASE_DIR, 'reports')

for d in [DATA_DIR, LOG_DIR, REPORT_DIR]:
    os.makedirs(d, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, 'insurance_underwriting.db')

MONITOR_INTERVAL_MINUTES = 3

THRESHOLDS = {
    'underwriting_pass_rate_min': 0.85,
    'underwriting_pass_rate_max': 0.98,
    'claim_process_delay_max_seconds': 3600,
    'claim_abnormal_rate_max': 0.05,
    'info_leak_risk_max': 0.01,
    'underwriting_rule_accuracy_min': 0.95,
    'claim_reconciliation_consistency_min': 0.99,
    'regulatory_compliance_min': 1.0,
    'customer_info_security_min': 1.0,
}

INSURANCE_TYPES = ['auto', 'life', 'critical_illness']
INSURANCE_TYPE_NAMES = {
    'auto': '车险',
    'life': '寿险',
    'critical_illness': '重疾险'
}

POLICY_TYPES = ['individual', 'group']
POLICY_TYPE_NAMES = {
    'individual': '个人险',
    'group': '团体险'
}

RISK_LEVELS = ['routine', 'urgent_claim', 'regulatory_update']
RISK_LEVEL_NAMES = {
    'routine': '常规规则迭代',
    'urgent_claim': '紧急理赔故障',
    'regulatory_update': '监管条款更新'
}

APPROVAL_ROLES = ['underwriting', 'claim', 'compliance', 'legal']
APPROVAL_ROLE_NAMES = {
    'underwriting': '核保',
    'claim': '理赔',
    'compliance': '合规',
    'legal': '法务'
}

GRAYSCALE_STRATEGY = {
    'auto': [0.1, 0.3, 0.5, 0.7, 1.0],
    'life': [0.05, 0.2, 0.4, 0.6, 0.8, 1.0],
    'critical_illness': [0.05, 0.15, 0.3, 0.5, 0.7, 1.0],
}

GRAYSCALE_INTERVAL_HOURS = {
    'routine': 4,
    'urgent_claim': 1,
    'regulatory_update': 6,
}

APPROVERS = {
    'underwriting': ['uw_manager1@insurance.com', 'uw_manager2@insurance.com'],
    'claim': ['claim_manager1@insurance.com', 'claim_manager2@insurance.com'],
    'compliance': ['compliance_officer1@insurance.com', 'compliance_officer2@insurance.com'],
    'legal': ['legal_counsel1@insurance.com', 'legal_counsel2@insurance.com'],
}

STAKEHOLDERS = {
    'underwriting': ['uw_team@insurance.com'],
    'claim': ['claim_team@insurance.com'],
    'customer_service': ['cs_team@insurance.com'],
    'compliance': ['compliance_team@insurance.com'],
}

WEEKLY_REPORT_DAY = 0
WEEKLY_REPORT_TIME = time(9, 0, 0)

AUDIT_LOG_RETENTION_DAYS = 365 * 7

SMTP_CONFIG = {
    'host': 'smtp.insurance.com',
    'port': 587,
    'username': 'system@insurance.com',
    'password': 'your_password',
    'use_tls': True,
    'sender': '保险核保理赔系统 <system@insurance.com>'
}
