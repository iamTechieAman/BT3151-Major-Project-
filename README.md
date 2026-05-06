# Cloud-Based Data Backup & Recovery System (Pro Edition)

A production-ready, lag-free backup system featuring intelligent scheduling, real-time visualizations, ML predictions, immutable audit logs, and disaster recovery simulation.

## 🚀 Key Features

- **Intelligent Backups**: Automatic Full vs. Incremental detection based on change rate analysis
- **SLA-Aware Scheduling**: Dynamic RPO/RTO monitoring with automated enforcement
- **Multi-Tier Storage**: Cost-optimized Hot/Warm/Cold placement with automatic migration
- **AES-256 Encryption**: User-specific derived keys for data-at-rest protection
- **Real-Time Dashboard**: Live progress bars, backup speed charts, tier usage, cost trends, SLA gauges
- **ML Predictor**: Linear regression for backup scheduling and storage growth forecasting
- **Blockchain Audit**: Cryptographically chained logs for immutable action tracking
- **DR Drills**: One-click disaster recovery simulation with RTO measurement
- **WebSocket Updates**: Real-time backup progress via Flask-SocketIO
- **Demo Mode**: Auto-creates sample data for immediate testing

## 🛠 Setup Instructions

### 1. Environment Setup
```bash
cd MajorProject
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Application
```bash
python3 run.py
```
Access the dashboard at `http://localhost:5000`

### 3. Demo Mode
Demo mode is enabled by default (`DEMO_MODE = True` in `config.py`). On first run:
- Creates `staging/demo_data/` with sample files (documents, configs, logs)
- Auto-sets the backup folder for new users
- Ready to test immediately after registration

## 🧪 Testing Features

1. **Register & Login** → Creates account with demo folder pre-configured
2. **Run Backup** → Watch live progress bar on Dashboard
3. **View History** → Paginated table with filter/expand per job
4. **Restore Files** → Tree view with multi-select and batch restore
5. **Monitoring** → Real-time audit chain + ML predictions
6. **DR Drill** → Execute with RTO timer
7. **Reports** → Cost savings analysis + SLA violations

## 📊 Architecture

```
app.py              → Flask + SocketIO routes, API endpoints
backup_engine.py    → Backup/restore logic, encryption, tier migration
scheduler.py        → APScheduler: dynamic backup + tier migration jobs
cost_analyzer.py    → Multi-tier cost calculation with caching
sla_optimizer.py    → RPO/RTO compliance checking
ml_predictor.py     → sklearn LinearRegression predictions
audit_logger.py     → Blockchain-style hash-chained audit log
models.py           → SQLAlchemy models with indexed columns
config.py           → Configuration (costs, paths, thresholds)
```

## 📁 Storage Structure
- `storage/hot/` — Active encrypted backups (< 7 days)
- `storage/warm/` — Aging data (7-30 days, auto-migrated)
- `storage/cold/` — Archive (> 30 days, auto-migrated)
- `storage/master.key` — Encryption root key
- `storage/drill_restore/` — DR drill destination

## 🔧 Scalability Notes

- **Multiple Users**: Already supports multi-user with isolated encryption keys
- **Real Cloud Storage**: Replace `storage/` paths with S3 buckets (hot→Standard, warm→IA, cold→Glacier)
- **Database**: Migrate from SQLite to PostgreSQL for production
- **Task Queue**: Replace threading with Celery + Redis for distributed backup processing
- **Horizontal Scaling**: Stateless Flask app can run behind a load balancer
# BT3151-Major-Project-
