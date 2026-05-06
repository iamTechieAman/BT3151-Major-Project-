import numpy as np
from models import BackupJob, BackupFile, User
from datetime import datetime, timedelta

class MLPredictor:
    @staticmethod
    def predict_next_backup(user_id):
        """Linear regression prediction of next backup time based on historical intervals."""
        jobs = BackupJob.query.filter_by(user_id=user_id, status='success')\
                .order_by(BackupJob.completed_at).all()
        if len(jobs) < 3:
            return None

        # Convert to numeric times (hours since first backup)
        base = jobs[0].completed_at
        times = [(j.completed_at - base).total_seconds() / 3600 for j in jobs]

        # Use sklearn linear regression if available, otherwise fallback
        try:
            from sklearn.linear_model import LinearRegression
            X = np.arange(len(times)).reshape(-1, 1)
            y = np.array(times)
            model = LinearRegression()
            model.fit(X, y)
            next_hours = model.predict([[len(times)]])[0]
        except ImportError:
            # Fallback: average of last intervals
            intervals = [times[i] - times[i-1] for i in range(1, len(times))]
            avg_interval = np.mean(intervals[-3:])
            next_hours = times[-1] + avg_interval

        predicted_time = base + timedelta(hours=next_hours)
        return predicted_time

    @staticmethod
    def should_backup_early(user_id):
        pred = MLPredictor.predict_next_backup(user_id)
        if not pred:
            return False
        now = datetime.utcnow()
        # If predicted time is within next 2 hours, suggest backup
        return (pred - now).total_seconds() < 7200

    @staticmethod
    def predict_storage_growth(user_id, days=7):
        """Predict storage growth for the next N days using linear regression."""
        jobs = BackupJob.query.filter_by(user_id=user_id, status='success')\
                .order_by(BackupJob.completed_at).all()
        if len(jobs) < 2:
            return None

        # Cumulative size over time
        base = jobs[0].completed_at
        x_days = [(j.completed_at - base).total_seconds() / 86400 for j in jobs]
        cumulative = []
        total = 0
        for j in jobs:
            total += j.size_bytes
            cumulative.append(total / (1024**2))  # MB

        try:
            from sklearn.linear_model import LinearRegression
            X = np.array(x_days).reshape(-1, 1)
            y = np.array(cumulative)
            model = LinearRegression()
            model.fit(X, y)

            last_day = x_days[-1]
            future_days = [last_day + i for i in range(1, days + 1)]
            predictions = model.predict(np.array(future_days).reshape(-1, 1))
            return {
                'current_mb': round(cumulative[-1], 2),
                'predicted_mb': [round(float(p), 2) for p in predictions],
                'days_ahead': days,
                'growth_rate_mb_day': round(float(model.coef_[0]), 2)
            }
        except ImportError:
            return None

    @staticmethod
    def get_change_rate_prediction(user_id):
        """Predict the data change rate based on historical backup patterns."""
        jobs = BackupJob.query.filter_by(user_id=user_id, status='success')\
                .order_by(BackupJob.completed_at).limit(10).all()
        if len(jobs) < 2:
            return {'rate': 0.0, 'trend': 'stable', 'confidence': 'low'}

        rates = []
        for i in range(1, len(jobs)):
            if jobs[i-1].files_count and jobs[i-1].files_count > 0:
                rate = jobs[i].files_count / jobs[i-1].files_count
                rates.append(rate)

        if not rates:
            return {'rate': 0.0, 'trend': 'stable', 'confidence': 'low'}

        avg_rate = float(np.mean(rates))
        trend = 'increasing' if avg_rate > 1.1 else ('decreasing' if avg_rate < 0.9 else 'stable')
        confidence = 'high' if len(rates) >= 5 else ('medium' if len(rates) >= 3 else 'low')

        return {
            'rate': round(avg_rate, 3),
            'trend': trend,
            'confidence': confidence,
            'samples': len(rates)
        }

    @staticmethod
    def get_prediction_summary(user_id):
        """Return a human-readable ML prediction summary."""
        pred_time = MLPredictor.predict_next_backup(user_id)
        change_rate = MLPredictor.get_change_rate_prediction(user_id)
        growth = MLPredictor.predict_storage_growth(user_id)

        parts = []
        if pred_time:
            delta = pred_time - datetime.utcnow()
            if delta.total_seconds() > 0:
                hours = delta.total_seconds() / 3600
                parts.append(f"Next backup predicted in {hours:.1f} hours ({pred_time.strftime('%H:%M %b %d')})")
            else:
                parts.append("A backup is overdue based on your pattern")

        parts.append(f"Change rate trend: {change_rate['trend']} ({change_rate['confidence']} confidence)")

        if growth:
            parts.append(f"Storage growth: ~{growth['growth_rate_mb_day']} MB/day")

        return ' | '.join(parts) if parts else 'Need at least 3 backups for predictions'
