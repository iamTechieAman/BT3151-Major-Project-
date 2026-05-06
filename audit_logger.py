import hashlib
from models import db, AuditLog
from datetime import datetime

class AuditLogger:
    @staticmethod
    def log(user_id, action, details):
        last = AuditLog.query.order_by(AuditLog.id.desc()).first()
        prev_hash = last.hash_current if last else "0"*64
        record_str = f"{user_id}|{action}|{details}|{datetime.utcnow()}|{prev_hash}"
        current_hash = hashlib.sha256(record_str.encode()).hexdigest()
        log = AuditLog(user_id=user_id, action=action, details=details,
                       hash_prev=prev_hash, hash_current=current_hash)
        db.session.add(log)
        db.session.commit()
        return current_hash
