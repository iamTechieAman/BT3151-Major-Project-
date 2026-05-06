from models import db, User, BackupFile, BackupJob, CostLog
from datetime import datetime, timedelta
from config import Config

class CostAnalyzer:
    # Simple in-memory cache for cost calculations
    _cache = {}   # {user_id: (timestamp, value)}
    _cache_ttl = 300  # 5 minutes

    @staticmethod
    def calculate_storage_cost(user_id):
        """Calculate current storage cost with 5-minute caching."""
        now = datetime.utcnow()
        cached = CostAnalyzer._cache.get(f'cost_{user_id}')
        if cached and (now - cached[0]).total_seconds() < CostAnalyzer._cache_ttl:
            return cached[1]

        files = BackupFile.query.join(BackupJob).filter(BackupJob.user_id == user_id).all()
        hot = sum(f.size_bytes for f in files if f.tier == 'hot') / (1024**3)
        warm = sum(f.size_bytes for f in files if f.tier == 'warm') / (1024**3)
        cold = sum(f.size_bytes for f in files if f.tier == 'cold') / (1024**3)
        cost = hot*Config.HOT_COST_PER_GB_DAY + warm*Config.WARM_COST_PER_GB_DAY + cold*Config.COLD_COST_PER_GB_DAY

        CostAnalyzer._cache[f'cost_{user_id}'] = (now, cost)
        return cost

    @staticmethod
    def update_daily_cost(user_id):
        today = datetime.utcnow().date()
        storage = CostAnalyzer.calculate_storage_cost(user_id)
        # Simplified transfer and operation costs
        transfer = 0.0
        operation = 0.0
        total = storage + transfer + operation
        existing = CostLog.query.filter_by(user_id=user_id, date=today).first()
        if existing:
            existing.storage_cost = storage
            existing.transfer_cost = transfer
            existing.operation_cost = operation
            existing.total_cost = total
        else:
            db.session.add(CostLog(user_id=user_id, date=today, storage_cost=storage, total_cost=total))
        db.session.commit()

    @staticmethod
    def get_cost_trend(user_id, days=30):
        """Return daily cost data for the last N days for chart rendering."""
        since = datetime.utcnow().date() - timedelta(days=days)
        logs = CostLog.query.filter(
            CostLog.user_id == user_id,
            CostLog.date >= since
        ).order_by(CostLog.date).all()
        return {
            'dates': [l.date.isoformat() for l in logs],
            'storage': [round(l.storage_cost, 6) for l in logs],
            'transfer': [round(l.transfer_cost, 6) for l in logs],
            'total': [round(l.total_cost, 6) for l in logs]
        }

    @staticmethod
    def get_tier_stats(user_id):
        """Return storage stats per tier."""
        files = BackupFile.query.join(BackupJob).filter(BackupJob.user_id == user_id).all()
        tiers = {'hot': {'count': 0, 'size': 0}, 'warm': {'count': 0, 'size': 0}, 'cold': {'count': 0, 'size': 0}}
        for f in files:
            t = f.tier if f.tier in tiers else 'hot'
            tiers[t]['count'] += 1
            tiers[t]['size'] += f.size_bytes
        return tiers
