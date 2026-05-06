from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from models import db, User
from backup_engine import BackupEngine
from cost_analyzer import CostAnalyzer
from sla_optimizer import SLAOptimizer
from ml_predictor import MLPredictor
from audit_logger import AuditLogger
import os, logging

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()

def dynamic_backup_job():
    """Scheduled job: checks SLA, runs ML predictions, triggers backups for all users."""
    with scheduler.app.app_context():
        users = User.query.all()
        for user in users:
            if not user.backup_folder or not os.path.exists(user.backup_folder):
                continue
            try:
                # Check SLA compliance
                SLAOptimizer.check_compliance(user.id)
                # ML prediction
                if user.id and MLPredictor.should_backup_early(user.id):
                    AuditLogger.log(user.id, "ML_TRIGGER", "Predictive backup triggered")
                    BackupEngine.perform_backup(user.id, user.backup_folder, 'incremental')
                else:
                    decision = SLAOptimizer.optimize_schedule(user.id)
                    if decision['should_backup']:
                        AuditLogger.log(user.id, "SCHEDULED_BACKUP", f"Type: {decision['backup_type']}")
                        BackupEngine.perform_backup(user.id, user.backup_folder, decision['backup_type'])
                CostAnalyzer.update_daily_cost(user.id)
            except Exception as e:
                logger.error(f"Scheduled backup error for user {user.id}: {e}")

def tier_migration_job():
    """Hourly job: migrates files between hot → warm → cold based on age."""
    with scheduler.app.app_context():
        try:
            migrated = BackupEngine.migrate_tiers()
            if migrated:
                logger.info(f"Tier migration: moved {migrated} files")
        except Exception as e:
            logger.error(f"Tier migration error: {e}")

def start_scheduler(app):
    scheduler.app = app
    scheduler.add_job(dynamic_backup_job, IntervalTrigger(minutes=15), id='dynamic_backup', replace_existing=True)
    scheduler.add_job(tier_migration_job, IntervalTrigger(hours=1), id='tier_migration', replace_existing=True)
    scheduler.start()
    logger.info("Scheduler started: dynamic_backup (15min), tier_migration (1hr)")

def shutdown_scheduler():
    scheduler.shutdown()
