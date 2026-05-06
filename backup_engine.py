import os, hashlib, time, base64, shutil, logging
from datetime import datetime, timedelta
from cryptography.fernet import Fernet  # type: ignore
from models import db, BackupJob, BackupFile, User
from config import Config

logger = logging.getLogger(__name__)

class BackupEngine:
    # ---- Progress tracking (class-level, keyed by user_id) ----
    _progress = {}   # {user_id: {current: int, total: int, file: str, speed_mbps: float, started: float}}

    @classmethod
    def get_progress(cls, user_id):
        """Return current backup progress for a user, or None if idle."""
        return cls._progress.get(user_id)

    @classmethod
    def clear_progress(cls, user_id):
        cls._progress.pop(user_id, None)

    # ---- Encryption helpers ----
    @staticmethod
    def get_encryption_key(user):
        key_path = Config.ENCRYPTION_KEY_FILE
        if not os.path.exists(key_path):
            os.makedirs(Config.BASE_STORAGE, exist_ok=True)
            with open(key_path, 'wb') as f:
                f.write(Fernet.generate_key())
        with open(key_path, 'rb') as f:
            master_key = f.read()
        salt = user.encryption_salt.encode()
        combined = master_key + salt
        key = hashlib.sha256(combined).digest()
        return Fernet(base64.urlsafe_b64encode(key))

    @staticmethod
    def encrypt_data(data, fernet):
        return fernet.encrypt(data)

    @staticmethod
    def decrypt_data(encrypted_data, fernet):
        return fernet.decrypt(encrypted_data)

    @staticmethod
    def compute_hash(filepath):
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    # ---- Change rate heuristic ----
    @staticmethod
    def get_change_rate(user_id):
        recent = BackupJob.query.filter_by(user_id=user_id, status='success')\
                      .order_by(BackupJob.completed_at.desc()).limit(5).all()
        if len(recent) < 2:
            return 0.2
        # Compare file counts between last two backups for a heuristic
        if recent[0].files_count and recent[1].files_count and recent[1].files_count > 0:
            ratio = recent[0].files_count / recent[1].files_count
            return min(abs(ratio - 1.0), 1.0)
        return 0.2

    @staticmethod
    def should_use_full(user_id):
        return BackupEngine.get_change_rate(user_id) > 0.3

    # ---- Core backup with progress tracking ----
    @staticmethod
    def perform_backup(user_id, source_dir, backup_type='auto', socketio=None):
        """
        Perform a full or incremental backup.
        If socketio is provided, emits real-time progress events.
        """
        user = User.query.get(user_id)
        if not user or not os.path.exists(source_dir):
            return False, "Invalid source"

        if backup_type == 'auto':
            backup_type = 'full' if BackupEngine.should_use_full(user_id) else 'incremental'

        job = BackupJob(user_id=user_id, type=backup_type, status='running', started_at=datetime.utcnow())
        db.session.add(job)
        db.session.commit()
        start_time = time.time()

        # Gather previous hashes for incremental
        last_job = None
        if backup_type == 'incremental':
            last_job = BackupJob.query.filter_by(user_id=user_id, status='success')\
                       .order_by(BackupJob.completed_at.desc()).first()
        prev_hashes = {}
        if last_job:
            prev_files = BackupFile.query.filter_by(job_id=last_job.id).all()
            prev_hashes = {f.relative_path: f.file_hash for f in prev_files}

        fernet = BackupEngine.get_encryption_key(user)

        # Count total files first for progress tracking
        all_files = []
        for root, _, files in os.walk(source_dir):
            for file in files:
                all_files.append(os.path.join(root, file))

        total_files = len(all_files)
        total_size = 0
        backed_up = 0
        bytes_processed = 0

        # Initialize progress
        BackupEngine._progress[user_id] = {
            'current': 0, 'total': total_files, 'file': '',
            'speed_mbps': 0.0, 'started': start_time, 'status': 'running'
        }

        try:
            for idx, full_path in enumerate(all_files):
                rel_path = os.path.relpath(full_path, source_dir)
                file_hash = BackupEngine.compute_hash(full_path)

                # Skip unchanged files for incremental
                if backup_type == 'incremental' and rel_path in prev_hashes and prev_hashes[rel_path] == file_hash:
                    # Update progress even for skipped files
                    BackupEngine._progress[user_id]['current'] = idx + 1
                    BackupEngine._progress[user_id]['file'] = rel_path
                    continue

                with open(full_path, 'rb') as f:
                    plain = f.read()
                encrypted = BackupEngine.encrypt_data(plain, fernet)

                tier = 'hot'
                storage_dir = Config.HOT_STORAGE
                os.makedirs(storage_dir, exist_ok=True)
                unique = f"{job.id}_{hashlib.md5(rel_path.encode()).hexdigest()}.enc"
                storage_path = os.path.join(storage_dir, unique)
                with open(storage_path, 'wb') as f:
                    f.write(encrypted)

                file_size = os.path.getsize(full_path)
                total_size += file_size
                bytes_processed += file_size

                bf = BackupFile(job_id=job.id, relative_path=rel_path, file_hash=file_hash,
                                size_bytes=file_size, tier=tier, storage_path=storage_path)
                db.session.add(bf)
                backed_up += 1

                # Update progress
                elapsed = time.time() - start_time
                speed = (bytes_processed / (1024*1024)) / elapsed if elapsed > 0 else 0
                BackupEngine._progress[user_id] = {
                    'current': idx + 1, 'total': total_files, 'file': rel_path,
                    'speed_mbps': round(speed, 2), 'started': start_time, 'status': 'running'
                }

                # Emit SocketIO event if available
                if socketio:
                    socketio.emit('backup_progress', {
                        'user_id': user_id,
                        'current': idx + 1,
                        'total': total_files,
                        'file': rel_path,
                        'speed_mbps': round(speed, 2),
                        'percent': round((idx + 1) / total_files * 100, 1)
                    })

            job.status = 'success'
            job.size_bytes = total_size
            job.files_count = backed_up
            job.completed_at = datetime.utcnow()
            job.duration_seconds = time.time() - start_time
            db.session.commit()

            # Mark progress complete
            BackupEngine._progress[user_id] = {
                'current': total_files, 'total': total_files, 'file': 'Complete',
                'speed_mbps': 0, 'started': start_time, 'status': 'complete'
            }
            if socketio:
                socketio.emit('backup_complete', {
                    'user_id': user_id, 'job_id': job.id,
                    'files': backed_up, 'size_mb': round(total_size / (1024*1024), 2),
                    'duration': round(job.duration_seconds, 1)
                })

            return True, f"{backup_type} backup done: {backed_up} files"

        except Exception as e:
            job.status = 'failed'
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.session.commit()
            BackupEngine.clear_progress(user_id)
            logger.error(f"Backup failed for user {user_id}: {e}")
            return False, str(e)

    # ---- Restore single file ----
    @staticmethod
    def restore_file(file_id, dest_dir):
        bf = BackupFile.query.get(file_id)
        if not bf:
            return False, "File not found"
        user = User.query.get(bf.job.user_id)
        fernet = BackupEngine.get_encryption_key(user)
        try:
            os.makedirs(dest_dir, exist_ok=True)
            with open(bf.storage_path, 'rb') as f:
                encrypted = f.read()
            decrypted = BackupEngine.decrypt_data(encrypted, fernet)
            restore_path = os.path.join(dest_dir, bf.relative_path)
            os.makedirs(os.path.dirname(restore_path), exist_ok=True)
            with open(restore_path, 'wb') as f:
                f.write(decrypted)
            bf.last_accessed = datetime.utcnow()
            db.session.commit()
            return True, f"Restored to {restore_path}"
        except Exception as e:
            return False, str(e)

    # ---- Batch restore multiple files ----
    @staticmethod
    def restore_multiple(file_ids, dest_dir):
        """Restore multiple files at once. Returns (success_count, fail_count, messages)."""
        successes = 0
        failures = 0
        messages = []
        for fid in file_ids:
            ok, msg = BackupEngine.restore_file(fid, dest_dir)
            if ok:
                successes += 1
            else:
                failures += 1
            messages.append(msg)
        return successes, failures, messages

    # ---- File tree grouped by job ----
    @staticmethod
    def get_file_tree(user_id):
        """Return backup files grouped by job as a tree structure."""
        jobs = BackupJob.query.filter_by(user_id=user_id, status='success')\
                .order_by(BackupJob.completed_at.desc()).all()
        tree = []
        for job in jobs:
            files = BackupFile.query.filter_by(job_id=job.id).all()
            tree.append({
                'job_id': job.id,
                'type': job.type,
                'date': job.completed_at.isoformat() if job.completed_at else '',
                'files_count': job.files_count,
                'size_mb': round(job.size_bytes / (1024*1024), 2),
                'files': [{
                    'id': f.id,
                    'path': f.relative_path,
                    'size_kb': round(f.size_bytes / 1024, 1),
                    'tier': f.tier,
                    'hash': f.file_hash[:12]
                } for f in files]
            })
        return tree

    # ---- Tier migration (hot → warm → cold based on age) ----
    @staticmethod
    def migrate_tiers():
        """Move files between storage tiers based on age thresholds."""
        now = datetime.utcnow()
        warm_cutoff = now - timedelta(days=Config.WARM_THRESHOLD_DAYS)
        cold_cutoff = now - timedelta(days=Config.COLD_THRESHOLD_DAYS)
        migrated = 0

        # Hot → Warm
        hot_files = BackupFile.query.filter_by(tier='hot')\
                    .join(BackupJob).filter(BackupJob.completed_at < warm_cutoff).all()
        for f in hot_files:
            new_path = os.path.join(Config.WARM_STORAGE, os.path.basename(f.storage_path))
            try:
                os.makedirs(Config.WARM_STORAGE, exist_ok=True)
                if os.path.exists(f.storage_path):
                    shutil.move(f.storage_path, new_path)
                    f.storage_path = new_path
                    f.tier = 'warm'
                    migrated += 1
            except Exception as e:
                logger.warning(f"Tier migration failed for {f.id}: {e}")

        # Warm → Cold
        warm_files = BackupFile.query.filter_by(tier='warm')\
                     .join(BackupJob).filter(BackupJob.completed_at < cold_cutoff).all()
        for f in warm_files:
            new_path = os.path.join(Config.COLD_STORAGE, os.path.basename(f.storage_path))
            try:
                os.makedirs(Config.COLD_STORAGE, exist_ok=True)
                if os.path.exists(f.storage_path):
                    shutil.move(f.storage_path, new_path)
                    f.storage_path = new_path
                    f.tier = 'cold'
                    migrated += 1
            except Exception as e:
                logger.warning(f"Tier migration failed for {f.id}: {e}")

        if migrated:
            db.session.commit()
        return migrated
