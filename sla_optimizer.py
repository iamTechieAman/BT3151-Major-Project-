from models import db, User, BackupJob, SLAEvent
from datetime import datetime

class SLAOptimizer:
    @staticmethod
    def get_last_backup_time(user_id):
        last = BackupJob.query.filter_by(user_id=user_id, status='success')\
                .order_by(BackupJob.completed_at.desc()).first()
        return last.completed_at if last else None

    @staticmethod
    def check_compliance(user_id):
        user = User.query.get(user_id)
        last = SLAOptimizer.get_last_backup_time(user_id)
        now = datetime.utcnow()
        rpo_ok = True
        if last:
            minutes_since = (now - last).total_seconds() / 60
            if minutes_since > user.rpo_minutes:
                rpo_ok = False
        else:
            rpo_ok = False
        event = SLAEvent(user_id=user_id, rpo_compliant=rpo_ok, rto_compliant=True)
        db.session.add(event)
        db.session.commit()
        return rpo_ok, "Compliant" if rpo_ok else "RPO violation"

    @staticmethod
    def optimize_schedule(user_id):
        user = User.query.get(user_id)
        last = SLAOptimizer.get_last_backup_time(user_id)
        if not last:
            return {'should_backup': True, 'backup_type': 'full'}
        minutes_since = (datetime.utcnow() - last).total_seconds() / 60
        if minutes_since > user.rpo_minutes * 0.75:
            return {'should_backup': True, 'backup_type': 'incremental'}
        return {'should_backup': False, 'backup_type': 'none'}
