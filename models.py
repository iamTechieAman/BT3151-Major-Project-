from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True) # Added email
    password_hash = db.Column(db.String(200), nullable=False)
    encryption_salt = db.Column(db.String(64), nullable=False)
    rpo_minutes = db.Column(db.Integer, default=60)
    rto_minutes = db.Column(db.Integer, default=30)
    backup_folder = db.Column(db.String(500), default='')
    multi_cloud = db.Column(db.Boolean, default=False)   # NEW: multi-cloud simulation
    schedule_type = db.Column(db.String(20), default='hourly')   # hourly / daily / custom
    schedule_cron = db.Column(db.String(100), default='')        # custom cron expression
    
    backups = db.relationship('BackupJob', backref='user', lazy=True)

class BackupJob(db.Model):
    __table_args__ = (
        db.Index('idx_job_user_status', 'user_id', 'status'),
        db.Index('idx_job_started', 'started_at'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    type = db.Column(db.String(20))
    status = db.Column(db.String(20))
    started_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    size_bytes = db.Column(db.Integer, default=0)
    files_count = db.Column(db.Integer, default=0)
    duration_seconds = db.Column(db.Float, default=0.0)
    storage_tier = db.Column(db.String(10), default='hot')
    error_message = db.Column(db.Text, nullable=True)
    predicted = db.Column(db.Boolean, default=False)   # ML flag
    
    files = db.relationship('BackupFile', backref='job', lazy=True)

class BackupFile(db.Model):
    __table_args__ = (
        db.Index('idx_file_job', 'job_id'),
        db.Index('idx_file_tier', 'tier'),
    )
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('backup_job.id'), nullable=False, index=True)
    relative_path = db.Column(db.String(500), nullable=False)
    file_hash = db.Column(db.String(64), nullable=False)
    size_bytes = db.Column(db.Integer, default=0)
    tier = db.Column(db.String(10), default='hot')
    storage_path = db.Column(db.String(500), nullable=False)
    last_accessed = db.Column(db.DateTime, default=datetime.utcnow)

class CostLog(db.Model):
    __table_args__ = (
        db.Index('idx_cost_user_date', 'user_id', 'date'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    date = db.Column(db.Date, default=datetime.utcnow().date)
    storage_cost = db.Column(db.Float, default=0.0)
    transfer_cost = db.Column(db.Float, default=0.0)
    operation_cost = db.Column(db.Float, default=0.0)
    total_cost = db.Column(db.Float, default=0.0)

class SLAEvent(db.Model):
    __table_args__ = (
        db.Index('idx_sla_user_ts', 'user_id', 'timestamp'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    rpo_compliant = db.Column(db.Boolean, default=True)
    rto_compliant = db.Column(db.Boolean, default=True)
    details = db.Column(db.Text, nullable=True)

class AuditLog(db.Model):          # NEW: blockchain‑inspired audit
    __table_args__ = (
        db.Index('idx_audit_user_ts', 'user_id', 'timestamp'),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    action = db.Column(db.String(50))
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    hash_prev = db.Column(db.String(64), nullable=True)
    hash_current = db.Column(db.String(64), unique=True)
