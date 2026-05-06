# PROCESS.md — How the Cloud Backup & Recovery System Works

## 1. How a Backup Is Triggered

### Manual Trigger
1. User clicks **"Run Backup"** on the Dashboard
2. Frontend sends `POST /api/backup/run`
3. Server spawns a **background thread** (non-blocking)
4. SocketIO emits real-time `backup_progress` events to the UI
5. Progress bar updates live: "Backing up file 45/200 — 12.3 MB/s"

### Scheduled Trigger
1. APScheduler runs `dynamic_backup_job()` every **15 minutes**
2. For each user with a valid `backup_folder`:
   - Checks SLA compliance (RPO/RTO)
   - Queries ML predictor: should we backup early?
   - If ML says yes → triggers incremental backup
   - Otherwise → SLA optimizer decides based on RPO threshold

## 2. Full vs Incremental Decision

The system uses a **change rate heuristic**:

```
change_rate = files_in_latest_backup / files_in_previous_backup
if change_rate > 0.3 (30% change):
    → FULL backup (re-copy everything)
else:
    → INCREMENTAL (only changed files)
```

For incremental backups, each file's SHA-256 hash is compared against the previous backup's hash. Only files with changed hashes are re-encrypted and stored.

## 3. Encryption, Hashing, and Storage

### Encryption Flow
1. A **master key** is generated once and stored at `storage/master.key` (Fernet)
2. Each user has a unique `encryption_salt` (generated at registration)
3. Per-user key = `SHA-256(master_key + user_salt)` → base64 → Fernet key
4. Each file is encrypted with the user's derived Fernet key (AES-128-CBC)

### Hashing
- Every file gets a **SHA-256 hash** computed from its raw content
- Used for:
  - Incremental backup change detection
  - Data integrity verification during restore
  - Audit log hash chaining

### Tier Assignment
- New files → **Hot tier** (`storage/hot/`)
- Files older than 7 days → auto-migrate to **Warm** (`storage/warm/`)
- Files older than 30 days → auto-migrate to **Cold** (`storage/cold/`)
- Migration runs hourly via APScheduler `tier_migration_job()`

## 4. RPO-Based Schedule Adjustment

The SLA Optimizer checks:
```
minutes_since_last_backup = (now - last_backup_time) / 60

if minutes_since > RPO_minutes:
    → RPO VIOLATION (logged as SLAEvent)

if minutes_since > RPO_minutes * 0.75:
    → Trigger incremental backup proactively
```

This ensures backups happen **before** the RPO deadline, not after.

## 5. Selective Restore

### Single File Restore
1. User selects a file from the tree view
2. Server looks up `BackupFile` → finds `storage_path`
3. Reads encrypted file from tier storage
4. Decrypts with user's derived Fernet key
5. Writes plaintext to destination directory

### Batch Restore
1. User checks multiple files across jobs
2. Frontend sends `POST /api/restore/batch` with `file_ids[]`
3. Server iterates and restores each file independently
4. Returns success/failure count

### Key Feature: No full dataset recovery needed
Each file is stored independently with its own path and encryption. Restoring one file doesn't require downloading or decrypting the entire backup set.

## 6. Audit Log Hash Chaining (Blockchain-Inspired)

Every action creates an `AuditLog` entry:
```
record_string = f"{user_id}|{action}|{details}|{timestamp}|{previous_hash}"
current_hash = SHA-256(record_string)
```

- `hash_prev` points to the previous log entry's hash
- `hash_current` is the new entry's hash
- This creates an **immutable chain**: tampering with any entry breaks the chain
- The Monitoring page displays the hash chain visually

## 7. Disaster Recovery Drill

1. User clicks **"Execute Recovery Drill"**
2. System selects a random file from the user's backups
3. Starts an RTO timer
4. Restores the file to `storage/drill_restore/` (safe, isolated)
5. Measures total time
6. Compares against RTO target:
   - `duration < RTO_minutes * 60` → **PASS**
   - Otherwise → **FAIL**
7. Logs result to audit trail with timing details

## 8. ML Prediction Methodology

### Next Backup Prediction
- Uses **sklearn LinearRegression** on backup timestamps
- X = backup index (0, 1, 2, ...)
- Y = hours since first backup
- Predicts Y for next index → converts to datetime

### Storage Growth Forecast
- Fits linear regression on cumulative storage over time
- Predicts next 7 days of storage growth
- Reports growth rate in MB/day

### Change Rate Analysis
- Compares `files_count` between consecutive backups
- Calculates ratio and trend (increasing/stable/decreasing)
- Reports confidence based on sample size

## 9. Cost Optimization

### Multi-Tier Pricing
| Tier | Cost/GB/Day | When |
|------|------------|------|
| Hot  | $0.10      | Active data (< 7 days) |
| Warm | $0.03      | Aging data (7-30 days) |
| Cold | $0.01      | Archive (> 30 days) |

### Savings Calculation
- **Proposed System** = actual tiered cost
- **Legacy System** = proposed cost × 2.5 (simulates no tiering, no incremental)
- **Savings** = legacy - proposed

Cost logs are updated daily by the scheduler and displayed on the Reports page.
