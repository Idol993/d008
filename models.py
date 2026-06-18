from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import config

Base = declarative_base()


class ReleaseRequest(Base):
    __tablename__ = 'release_requests'

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(50), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    risk_level = Column(String(30), nullable=False)
    insurance_types = Column(JSON, nullable=False)
    policy_types = Column(JSON, nullable=False)
    submitter = Column(String(100), nullable=False)
    submit_time = Column(DateTime, default=datetime.now)
    status = Column(String(30), default='pending_check')
    precheck_result = Column(JSON)
    precheck_passed = Column(Boolean)
    current_grayscale_stage = Column(Integer, default=0)
    current_insurance_type = Column(String(30))
    rollback_triggered = Column(Boolean, default=False)
    rollback_reason = Column(Text)
    rollback_time = Column(DateTime)
    stable_version_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    approvals = relationship('ApprovalRecord', back_populates='release_request')
    monitor_records = relationship('MonitorRecord', back_populates='release_request')
    grayscale_records = relationship('GrayscaleRecord', back_populates='release_request')


class ApprovalRecord(Base):
    __tablename__ = 'approval_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    release_request_id = Column(Integer, ForeignKey('release_requests.id'), nullable=False)
    role = Column(String(30), nullable=False)
    approver = Column(String(100), nullable=False)
    status = Column(String(30), default='pending')
    comment = Column(Text)
    approve_time = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    release_request = relationship('ReleaseRequest', back_populates='approvals')


class PreCheckRecord(Base):
    __tablename__ = 'precheck_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    release_request_id = Column(Integer, nullable=False, index=True)
    check_item = Column(String(50), nullable=False)
    check_value = Column(Float)
    threshold = Column(Float)
    passed = Column(Boolean)
    detail = Column(Text)
    check_time = Column(DateTime, default=datetime.now)


class GrayscaleRecord(Base):
    __tablename__ = 'grayscale_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    release_request_id = Column(Integer, ForeignKey('release_requests.id'), nullable=False)
    insurance_type = Column(String(30), nullable=False)
    stage = Column(Integer, nullable=False)
    percentage = Column(Float, nullable=False)
    status = Column(String(30), default='pending')
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    affected_policies_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)

    release_request = relationship('ReleaseRequest', back_populates='grayscale_records')


class MonitorRecord(Base):
    __tablename__ = 'monitor_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    release_request_id = Column(Integer, ForeignKey('release_requests.id'), nullable=False)
    insurance_type = Column(String(30), nullable=False)
    grayscale_stage = Column(Integer, nullable=False)
    underwriting_pass_rate = Column(Float)
    claim_process_delay_seconds = Column(Float)
    claim_abnormal_rate = Column(Float)
    info_leak_risk = Column(Float)
    threshold_exceeded = Column(Boolean, default=False)
    threshold_details = Column(JSON)
    monitor_time = Column(DateTime, default=datetime.now, index=True)

    release_request = relationship('ReleaseRequest', back_populates='monitor_records')


class RollbackRecord(Base):
    __tablename__ = 'rollback_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    release_request_id = Column(Integer, nullable=False, index=True)
    rollback_type = Column(String(30), nullable=False)
    trigger_reason = Column(Text, nullable=False)
    affected_policies_count = Column(Integer, default=0)
    affected_insurance_types = Column(JSON)
    rollback_from_version = Column(String(50))
    rollback_to_version = Column(String(50))
    claim_anomaly_details = Column(Text)
    regulatory_clause_explanation = Column(Text)
    status = Column(String(30), default='pending')
    start_time = Column(DateTime)
    complete_time = Column(DateTime)
    report_generated = Column(Boolean, default=False)
    report_path = Column(String(500))
    notifications_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)


class RollbackDrill(Base):
    __tablename__ = 'rollback_drills'

    id = Column(Integer, primary_key=True, autoincrement=True)
    drill_name = Column(String(200), nullable=False)
    drill_type = Column(String(50))
    insurance_types = Column(JSON)
    policy_types = Column(JSON)
    simulated_version = Column(String(50))
    target_version = Column(String(50))
    plan_details = Column(JSON)
    status = Column(String(30), default='planned')
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    policy_validation_result = Column(JSON)
    archive_path = Column(String(500))
    operator = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class WeeklyReport(Base):
    __tablename__ = 'weekly_reports'

    id = Column(Integer, primary_key=True, autoincrement=True)
    week_start = Column(DateTime, nullable=False)
    week_end = Column(DateTime, nullable=False)
    total_releases = Column(Integer, default=0)
    successful_releases = Column(Integer, default=0)
    release_success_rate = Column(Float)
    rollback_count = Column(Integer, default=0)
    avg_claim_process_duration = Column(Float)
    avg_underwriting_pass_rate = Column(Float)
    avg_claim_abnormal_rate = Column(Float)
    pdf_path = Column(String(500))
    excel_path = Column(String(500))
    generated_at = Column(DateTime, default=datetime.now)


class AuditLog(Base):
    __tablename__ = 'audit_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_type = Column(String(50), nullable=False, index=True)
    operation_module = Column(String(50), nullable=False)
    operator = Column(String(100), nullable=False)
    operation_detail = Column(Text)
    related_id = Column(Integer)
    related_type = Column(String(50))
    ip_address = Column(String(50))
    operation_time = Column(DateTime, default=datetime.now, index=True)
    regulatory_related = Column(Boolean, default=False)
    risk_level = Column(String(30), default='low')


class StableVersion(Base):
    __tablename__ = 'stable_versions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(50), nullable=False, unique=True)
    description = Column(Text)
    regulatory_approved = Column(Boolean, default=False)
    approval_date = Column(DateTime)
    insurance_types = Column(JSON)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)


def init_db():
    engine = create_engine(f'sqlite:///{config.DB_PATH}', echo=False)
    Base.metadata.create_all(engine)
    return engine


def get_session():
    engine = create_engine(f'sqlite:///{config.DB_PATH}', echo=False)
    Session = sessionmaker(bind=engine)
    return Session()
