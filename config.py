import os

class Config:
    SECRET_KEY = 'your-secret-key-2026'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///backup_system.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    BASE_STORAGE = os.path.join(os.getcwd(), 'storage')
    HOT_STORAGE = os.path.join(BASE_STORAGE, 'hot')
    WARM_STORAGE = os.path.join(BASE_STORAGE, 'warm')
    COLD_STORAGE = os.path.join(BASE_STORAGE, 'cold')

    # Cost (USD)
    HOT_COST_PER_GB_DAY = 0.10
    WARM_COST_PER_GB_DAY = 0.03
    COLD_COST_PER_GB_DAY = 0.01
    TRANSFER_COST_PER_GB = 0.02
    OPERATION_COST_PER_JOB = 0.01

    ENCRYPTION_KEY_FILE = os.path.join(BASE_STORAGE, 'master.key')

    # ML settings
    ML_ENABLED = True   # enable predictive scheduling

    # Flask-Caching
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 300  # 5 minutes

    # Demo mode — auto-creates sample files for testing
    DEMO_MODE = True
    DEMO_SOURCE_FOLDER = os.path.join(os.getcwd(), 'staging', 'demo_data')

    # Tier migration thresholds (days)
    WARM_THRESHOLD_DAYS = 7
    COLD_THRESHOLD_DAYS = 30
