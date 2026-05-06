from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from flask_caching import Cache
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, BackupJob, BackupFile, CostLog, SLAEvent, AuditLog
from backup_engine import BackupEngine
from cost_analyzer import CostAnalyzer
from sla_optimizer import SLAOptimizer
from ml_predictor import MLPredictor
from audit_logger import AuditLogger
from config import Config
import secrets, os, threading, logging
from datetime import datetime

# ---- Logging setup ----
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

# ---- App init ----
app = Flask(__name__)
app.config.from_object('config.Config')
db.init_app(app)

# ---- SocketIO ----
socketio = SocketIO(app, async_mode='threading', cors_allowed_origins="*")

# ---- Cache ----
cache = Cache(app)

# ---- Login manager ----
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---- Initialization ----
with app.app_context():
    db.create_all()
    for d in [Config.HOT_STORAGE, Config.WARM_STORAGE, Config.COLD_STORAGE]:
        os.makedirs(d, exist_ok=True)

    # Demo mode: create sample files if DEMO_MODE is enabled
    if Config.DEMO_MODE:
        demo_dir = Config.DEMO_SOURCE_FOLDER
        if not os.path.exists(demo_dir):
            os.makedirs(demo_dir, exist_ok=True)
            # Create sample directory structure with dummy files
            for folder in ['documents', 'images', 'config', 'logs']:
                fpath = os.path.join(demo_dir, folder)
                os.makedirs(fpath, exist_ok=True)
            sample_files = {
                'documents/report_2026.txt': 'Cloud Backup System - Annual Report 2026\n' + 'Data integrity verified.\n' * 50,
                'documents/meeting_notes.txt': 'Project Meeting Notes\n' + 'Action items discussed.\n' * 30,
                'documents/research_paper.txt': 'Cloud-Based Data Backup and Recovery System\n' + 'Abstract: This paper presents...\n' * 100,
                'images/architecture.svg': '<svg><rect width="100" height="100" fill="blue"/></svg>\n' * 10,
                'images/flowchart.svg': '<svg><circle cx="50" cy="50" r="40" fill="green"/></svg>\n' * 10,
                'config/backup_config.json': '{"schedule": "hourly", "retention": 30, "encryption": true}\n',
                'config/sla_policy.json': '{"rpo_minutes": 60, "rto_minutes": 30, "tier": "premium"}\n',
                'logs/system.log': 'INFO: System initialized\n' * 200,
                'logs/audit.log': 'AUDIT: User action logged\n' * 100,
                'readme.md': '# Demo Data\nThis folder contains sample files for backup testing.\n' * 5,
            }
            for fname, content in sample_files.items():
                fpath = os.path.join(demo_dir, fname)
                with open(fpath, 'w') as f:
                    f.write(content)
            logger.info(f"Demo mode: created sample files in {demo_dir}")

# ================= PAGE ROUTES =================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form.get('email')
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('User exists')
            return redirect(url_for('register'))
        salt = secrets.token_hex(16)
        hashed = generate_password_hash(password + salt)
        user = User(username=username, email=email, password_hash=hashed, encryption_salt=salt)
        # Auto-set demo folder if demo mode
        if Config.DEMO_MODE:
            user.backup_folder = Config.DEMO_SOURCE_FOLDER
        db.session.add(user)
        db.session.commit()
        flash('Registered successfully! Please login.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password + user.encryption_salt):
            login_user(user)
            AuditLogger.log(user.id, "LOGIN", "User logged in")
            return redirect(url_for('dashboard'))
        flash('Invalid credentials')
    return render_template('login.html', register=False)

@app.route('/logout')
@login_required
def logout():
    AuditLogger.log(current_user.id, "LOGOUT", "User logged out")
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    last_backup = BackupJob.query.filter_by(user_id=current_user.id, status='success')\
                  .order_by(BackupJob.completed_at.desc()).first()
    total_jobs = BackupJob.query.filter_by(user_id=current_user.id, status='success').count()
    total_files = BackupFile.query.join(BackupJob).filter(BackupJob.user_id == current_user.id).count()
    
    # Total storage used
    total_size = db.session.query(db.func.sum(BackupFile.size_bytes))\
                 .join(BackupJob).filter(BackupJob.user_id == current_user.id).scalar() or 0
    
    # Today's cost
    today_cost = CostLog.query.filter_by(user_id=current_user.id, date=datetime.utcnow().date()).first()
    
    return render_template('dashboard.html',
        last_backup=last_backup,
        total_jobs=total_jobs,
        total_files=total_files,
        total_size_mb=round(total_size / (1024*1024), 2),
        today_cost=round(today_cost.total_cost, 6) if today_cost else 0
    )

@app.route('/backups')
@login_required
def backups():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 15, type=int)
    jobs = BackupJob.query.filter_by(user_id=current_user.id)\
           .order_by(BackupJob.started_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template('backups.html', jobs=jobs)

@app.route('/restore')
@login_required
def restore():
    tree = BackupEngine.get_file_tree(current_user.id)
    return render_template('restore.html', tree=tree)

@app.route('/settings', methods=['GET','POST'])
@login_required
def settings():
    if request.method == 'POST':
        current_user.rpo_minutes = int(request.form['rpo'])
        current_user.rto_minutes = int(request.form['rto'])
        current_user.backup_folder = request.form['backup_folder']
        current_user.schedule_type = request.form.get('schedule_type', 'hourly')
        current_user.schedule_cron = request.form.get('schedule_cron', '')
        db.session.commit()
        flash('Settings saved successfully')
        return redirect(url_for('settings'))
    return render_template('settings.html', user=current_user)

@app.route('/monitoring')
@login_required
def monitoring():
    return render_template('monitoring.html')

@app.route('/drill')
@login_required
def drill():
    return render_template('drill.html')

@app.route('/reports')
@login_required
def reports():
    logs = CostLog.query.filter_by(user_id=current_user.id).order_by(CostLog.date).all()
    sla_events = SLAEvent.query.filter_by(user_id=current_user.id).order_by(SLAEvent.timestamp.desc()).all()
    
    # Calculate simulated savings
    actual_cost = sum(log.total_cost for log in logs)
    # Simulate legacy cost: 2.5x more expensive due to lack of tiering/incremental
    legacy_cost = actual_cost * 2.5
    
    savings = {
        'actual': actual_cost,
        'legacy': legacy_cost,
        'savings': legacy_cost - actual_cost
    }
    
    # Map SLA events to template expectations
    formatted_sla = []
    for e in sla_events:
        if not e.rpo_compliant or not e.rto_compliant:
            formatted_sla.append({
                'event_type': 'Violation',
                'severity': 'red',
                'timestamp': e.timestamp,
                'description': e.details or "RPO/RTO Violation detected"
            })
            
    return render_template('reports.html', costs=logs, sla_events=formatted_sla, savings=savings)


# ================= DATA APIs =================

@app.route('/api/chart-data')
@login_required
@cache.cached(timeout=60, query_string=True)
def api_chart_data():
    """Aggregated chart data for dashboard — cached 60s."""
    jobs = BackupJob.query.filter_by(user_id=current_user.id, status='success')\
           .order_by(BackupJob.started_at).all()
    
    storage_history = {
        'labels': [j.started_at.strftime('%m/%d %H:%M') for j in jobs[-15:]],
        'data': [round(j.size_bytes / (1024*1024), 2) for j in jobs[-15:]]
    }
    
    # Speed history (MB/s)
    speed_history = {
        'labels': [j.started_at.strftime('%m/%d %H:%M') for j in jobs[-15:]],
        'data': [round((j.size_bytes / (1024*1024)) / j.duration_seconds, 2) if j.duration_seconds > 0 else 0 for j in jobs[-15:]]
    }
    
    # Tier breakdown
    tier_stats = CostAnalyzer.get_tier_stats(current_user.id)
    tier_usage = {
        'labels': ['Hot', 'Warm', 'Cold'],
        'data': [
            round(tier_stats['hot']['size'] / (1024**2), 2),
            round(tier_stats['warm']['size'] / (1024**2), 2),
            round(tier_stats['cold']['size'] / (1024**2), 2)
        ],
        'counts': [tier_stats['hot']['count'], tier_stats['warm']['count'], tier_stats['cold']['count']]
    }
    
    # Cost trend
    cost_trend = CostAnalyzer.get_cost_trend(current_user.id, 30)
    
    # Cost breakdown
    cost_breakdown = {
        'labels': ['Hot', 'Warm', 'Cold'],
        'data': [
            round(tier_stats['hot']['size'] / (1024**3) * Config.HOT_COST_PER_GB_DAY, 6),
            round(tier_stats['warm']['size'] / (1024**3) * Config.WARM_COST_PER_GB_DAY, 6),
            round(tier_stats['cold']['size'] / (1024**3) * Config.COLD_COST_PER_GB_DAY, 6)
        ]
    }
    
    return jsonify({
        'storage_history': storage_history,
        'speed_history': speed_history,
        'tier_usage': tier_usage,
        'cost_trend': cost_trend,
        'cost_breakdown': cost_breakdown
    })

@app.route('/api/v1/history')
@login_required
def api_history():
    """Paginated backup history with filtering."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    backup_type = request.args.get('type', '')
    status = request.args.get('status', '')
    
    query = BackupJob.query.filter_by(user_id=current_user.id)
    if backup_type:
        query = query.filter_by(type=backup_type)
    if status:
        query = query.filter_by(status=status)
    
    paginated = query.order_by(BackupJob.started_at.desc())\
                .paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        'items': [{
            'id': j.id,
            'type': j.type,
            'status': j.status,
            'started_at': j.started_at.isoformat(),
            'completed_at': j.completed_at.isoformat() if j.completed_at else None,
            'size_bytes': j.size_bytes,
            'size_mb': round(j.size_bytes / (1024*1024), 2),
            'files_count': j.files_count,
            'duration': round(j.duration_seconds, 1) if j.duration_seconds else 0
        } for j in paginated.items],
        'page': paginated.page,
        'pages': paginated.pages,
        'total': paginated.total,
        'has_next': paginated.has_next,
        'has_prev': paginated.has_prev
    })

@app.route('/api/v1/job/<int:job_id>/files')
@login_required
def api_job_files(job_id):
    """Get files for a specific backup job (lazy loading for file tree)."""
    job = BackupJob.query.filter_by(id=job_id, user_id=current_user.id).first()
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    files = BackupFile.query.filter_by(job_id=job.id).all()
    return jsonify([{
        'id': f.id,
        'path': f.relative_path,
        'size_kb': round(f.size_bytes / 1024, 1),
        'tier': f.tier,
        'hash': f.file_hash[:12]
    } for f in files])

@app.route('/api/ml/prediction')
@login_required
def api_ml_prediction():
    """ML prediction summary with change rate and storage growth."""
    summary = MLPredictor.get_prediction_summary(current_user.id)
    change_rate = MLPredictor.get_change_rate_prediction(current_user.id)
    growth = MLPredictor.predict_storage_growth(current_user.id)
    
    return jsonify({
        'message': summary,
        'change_rate': change_rate,
        'growth': growth
    })

@app.route('/api/system/health')
@login_required
def api_system_health():
    """System health metrics."""
    total_jobs = BackupJob.query.filter_by(user_id=current_user.id).count()
    success_jobs = BackupJob.query.filter_by(user_id=current_user.id, status='success').count()
    failed_jobs = BackupJob.query.filter_by(user_id=current_user.id, status='failed').count()
    
    last_backup = BackupJob.query.filter_by(user_id=current_user.id, status='success')\
                  .order_by(BackupJob.completed_at.desc()).first()
    
    minutes_since = 0
    if last_backup and last_backup.completed_at:
        minutes_since = (datetime.utcnow() - last_backup.completed_at).total_seconds() / 60
    
    tier_stats = CostAnalyzer.get_tier_stats(current_user.id)
    total_storage = sum(t['size'] for t in tier_stats.values())
    
    # RPO compliance check
    rpo_ok = minutes_since <= current_user.rpo_minutes if last_backup else False
    rpo_pct = min(100, (current_user.rpo_minutes / max(minutes_since, 1)) * 100) if minutes_since > 0 else 100
    
    return jsonify({
        'total_jobs': total_jobs,
        'success_jobs': success_jobs,
        'failed_jobs': failed_jobs,
        'success_rate': round(success_jobs / max(total_jobs, 1) * 100, 1),
        'last_backup_minutes_ago': round(minutes_since, 1),
        'total_storage_mb': round(total_storage / (1024*1024), 2),
        'tier_stats': {k: {'count': v['count'], 'size_mb': round(v['size'] / (1024*1024), 2)} for k, v in tier_stats.items()},
        'rpo_compliant': rpo_ok,
        'rpo_percent': round(rpo_pct, 1),
        'rto_minutes': current_user.rto_minutes,
        'rpo_minutes': current_user.rpo_minutes
    })

@app.route('/api/backup/progress')
@login_required
def api_backup_progress():
    """Current backup progress for the logged-in user."""
    progress = BackupEngine.get_progress(current_user.id)
    if not progress:
        return jsonify({'active': False})
    return jsonify({
        'active': progress['status'] == 'running',
        'current': progress['current'],
        'total': progress['total'],
        'file': progress['file'],
        'speed_mbps': progress['speed_mbps'],
        'percent': round(progress['current'] / max(progress['total'], 1) * 100, 1),
        'status': progress['status']
    })


# ================= ACTION APIs =================

@app.route('/api/backup/run', methods=['POST'])
@login_required
def api_run_backup():
    """Trigger backup in a background thread for non-blocking UI."""
    if not current_user.backup_folder:
        return jsonify({'success': False, 'error': 'No backup folder set. Go to Settings first.'})
    
    user_id = current_user.id
    folder = current_user.backup_folder
    
    # Check if backup is already running
    progress = BackupEngine.get_progress(user_id)
    if progress and progress.get('status') == 'running':
        return jsonify({'success': False, 'error': 'A backup is already running'})
    
    def run_backup_thread():
        with app.app_context():
            success, msg = BackupEngine.perform_backup(user_id, folder, 'auto', socketio=socketio)
            if success:
                AuditLogger.log(user_id, "MANUAL_BACKUP", msg)
                CostAnalyzer.update_daily_cost(user_id)
            # Clear cache so dashboard refreshes
            cache.clear()
    
    thread = threading.Thread(target=run_backup_thread, daemon=True)
    thread.start()
    
    return jsonify({'success': True, 'message': 'Backup started in background. Watch the progress bar!'})

@app.route('/api/restore/file/<int:file_id>', methods=['POST'])
@login_required
def api_restore_file(file_id):
    dest = request.json.get('dest', os.path.expanduser('~/restored'))
    success, msg = BackupEngine.restore_file(file_id, dest)
    if success:
        AuditLogger.log(current_user.id, "RESTORE", msg)
    return jsonify({'success': success, 'message': msg})

@app.route('/api/restore/batch', methods=['POST'])
@login_required
def api_restore_batch():
    """Restore multiple files at once."""
    data = request.json
    file_ids = data.get('file_ids', [])
    dest = data.get('dest', os.path.expanduser('~/restored'))
    
    if not file_ids:
        return jsonify({'success': False, 'message': 'No files selected'})
    
    successes, failures, messages = BackupEngine.restore_multiple(file_ids, dest)
    AuditLogger.log(current_user.id, "BATCH_RESTORE", f"Restored {successes}/{successes+failures} files")
    
    return jsonify({
        'success': failures == 0,
        'message': f'Restored {successes} files, {failures} failed',
        'details': messages
    })

@app.route('/api/cost/stats')
@login_required
@cache.cached(timeout=300, query_string=True)
def api_cost_stats():
    """Cost statistics — cached 5 minutes."""
    trend = CostAnalyzer.get_cost_trend(current_user.id, 30)
    return jsonify(trend)

@app.route('/api/sla/compliance')
@login_required
def api_sla_compliance():
    events = SLAEvent.query.filter_by(user_id=current_user.id)\
             .order_by(SLAEvent.timestamp.desc()).limit(20).all()
    return jsonify([{
        'timestamp': e.timestamp.isoformat(),
        'rpo': e.rpo_compliant,
        'rto': e.rto_compliant,
        'details': e.details
    } for e in events])

@app.route('/api/audit')
@login_required
def api_audit():
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.filter_by(user_id=current_user.id)\
           .order_by(AuditLog.timestamp.desc()).limit(50).all()
    return jsonify([{
        'action': l.action,
        'details': l.details,
        'time': l.timestamp.isoformat(),
        'hash': l.hash_current[:16] if l.hash_current else '',
        'prev_hash': l.hash_prev[:16] if l.hash_prev else ''
    } for l in logs])

@app.route('/api/drill/run', methods=['POST'])
@login_required
def api_run_drill():
    """Simulate disaster recovery drill: restore a random file and measure RTO."""
    import time as _time
    drill_start = _time.time()
    
    file = BackupFile.query.join(BackupJob).filter(BackupJob.user_id == current_user.id).first()
    if not file:
        return jsonify({'success': False, 'message': 'No backup available for drill'})
    
    dest = os.path.join(Config.BASE_STORAGE, 'drill_restore')
    success, msg = BackupEngine.restore_file(file.id, dest)
    
    drill_duration = round(_time.time() - drill_start, 2)
    rto_ok = drill_duration < (current_user.rto_minutes * 60)
    
    if success:
        AuditLogger.log(current_user.id, "DISASTER_DRILL",
            f"Success in {drill_duration}s | RTO {'PASS' if rto_ok else 'FAIL'} | {msg}")
    
    return jsonify({
        'success': success,
        'message': msg,
        'duration_seconds': drill_duration,
        'rto_compliant': rto_ok,
        'rto_target_seconds': current_user.rto_minutes * 60
    })

@app.route('/api/tier/stats')
@login_required
def api_tier_stats():
    """Storage tier statistics."""
    stats = CostAnalyzer.get_tier_stats(current_user.id)
    return jsonify({k: {'count': v['count'], 'size_mb': round(v['size'] / (1024*1024), 2)} for k, v in stats.items()})


# ================= SocketIO Events =================
@socketio.on('connect')
def handle_connect():
    logger.info('Client connected via SocketIO')

@socketio.on('request_progress')
def handle_progress_request():
    """Client can request current backup progress."""
    if current_user.is_authenticated:
        progress = BackupEngine.get_progress(current_user.id)
        if progress:
            emit('backup_progress', {
                'current': progress['current'],
                'total': progress['total'],
                'file': progress['file'],
                'speed_mbps': progress['speed_mbps'],
                'percent': round(progress['current'] / max(progress['total'], 1) * 100, 1),
                'status': progress['status']
            })


# Start scheduler
from scheduler import start_scheduler
start_scheduler(app)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, use_reloader=False)
