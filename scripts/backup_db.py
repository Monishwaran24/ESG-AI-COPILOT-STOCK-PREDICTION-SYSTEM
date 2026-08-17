"""
Database Backup & Restore Script
=================================
Backs up both esg_stock.db and users.db with timestamped filenames,
automatic retention cleanup, and a restore helper.

Usage (manual):
    python scripts/backup_db.py              # Create a backup now
    python scripts/backup_db.py list         # List all backups
    python scripts/backup_db.py restore <path>  # Restore from a backup

Scheduled via APScheduler in app.py (configurable in .env):
    BACKUP_ENABLED=true
    BACKUP_INTERVAL_HOURS=6
    BACKUP_RETENTION_DAYS=7
"""

import os
import sys
import shutil
import glob
import json
from datetime import datetime, timedelta
from pathlib import Path

# Project root (one level up from scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = PROJECT_ROOT / 'backups'

# Database paths
DB_DIR = PROJECT_ROOT
MAIN_DB = DB_DIR / 'esg_stock.db'
USERS_DB = DB_DIR / 'users.db'

# Retention: keep backups for this many days (overridable via env)
RETENTION_DAYS = int(os.environ.get('BACKUP_RETENTION_DAYS', '7'))


def ensure_backup_dir():
    """Create the backup directory if it doesn't exist."""
    BACKUP_DIR.mkdir(exist_ok=True)
    # Create a .gitkeep so the directory is tracked
    gitkeep = BACKUP_DIR / '.gitkeep'
    if not gitkeep.exists():
        gitkeep.write_text('')


def get_timestamp():
    """Get a timestamp string for filenames."""
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def backup_database(source_path, prefix='esg_stock'):
    """
    Copy a single SQLite database to the backup directory with a timestamp.

    Returns the backup file path, or None on failure.
    """
    if not source_path.exists():
        print(f"  [SKIP] {source_path} does not exist.")
        return None

    timestamp = get_timestamp()
    backup_name = f"{prefix}_backup_{timestamp}.db"
    backup_path = BACKUP_DIR / backup_name

    try:
        shutil.copy2(str(source_path), str(backup_path))
        size_mb = backup_path.stat().st_size / (1024 * 1024)
        print(f"  [OK]   {backup_path.name} ({size_mb:.1f} MB)")
        return str(backup_path)
    except Exception as e:
        print(f"  [FAIL] {backup_name}: {e}")
        return None


def cleanup_old_backups(prefix=None):
    """
    Remove backups older than RETENTION_DAYS.

    If prefix is provided, only clean backups matching that prefix.
    """
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    pattern = f"{prefix}_backup_*.db" if prefix else "*_backup_*.db"
    removed = 0

    for backup_file in BACKUP_DIR.glob(pattern):
        # Parse timestamp from filename: prefix_backup_YYYYMMDD_HHMMSS.db
        try:
            parts = backup_file.stem.split('_')
            # Find the date part (after 'backup')
            if 'backup' in parts:
                idx = parts.index('backup')
                date_str = parts[idx + 1]
                file_time = datetime.strptime(date_str, '%Y%m%d')
                if file_time < cutoff:
                    backup_file.unlink()
                    removed += 1
                    print(f"  [DEL]  {backup_file.name}")
        except (ValueError, IndexError):
            continue

    if removed:
        print(f"  Cleaned up {removed} old backup(s) (retention: {RETENTION_DAYS} days)")
    return removed


def create_backup():
    """Backup both databases."""
    print("\n" + "=" * 55)
    print("  ESG STOCK DATABASE BACKUP")
    print("=" * 55)
    print(f"  Time:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Target: {BACKUP_DIR}")
    print("-" * 55)

    ensure_backup_dir()

    # Backup main database
    print("\n  [1/2] Backing up esg_stock.db...")
    main_result = backup_database(MAIN_DB, 'esg_stock')

    # Backup users database
    print("\n  [2/2] Backing up users.db...")
    users_result = backup_database(USERS_DB, 'users')

    print("-" * 55)
    if main_result or users_result:
        print("  [OK] Backup completed successfully")
    else:
        print("  [WARN] No databases were backed up")

    # Clean up old backups
    print(f"\n  Cleaning backups older than {RETENTION_DAYS} days...")
    cleanup_old_backups()

    print("=" * 55 + "\n")
    return {'main': main_result, 'users': users_result, 'timestamp': get_timestamp()}


def list_backups():
    """List all available backups."""
    ensure_backup_dir()
    backups = sorted(BACKUP_DIR.glob('*_backup_*.db'), reverse=True)

    print("\n" + "=" * 55)
    print("  DATABASE BACKUPS")
    print("=" * 55)

    if not backups:
        print("  No backups found.")
        print("=" * 55 + "\n")
        return

    print(f"  {'File':<40} {'Size':>10}")
    print("-" * 55)
    for b in backups:
        size = b.stat().st_size
        if size > 1024 * 1024:
            size_str = f"{size / (1024*1024):.1f} MB"
        elif size > 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size} B"
        print(f"  {b.name:<40} {size_str:>10}")

    print("-" * 55)
    print(f"  Total: {len(backups)} backup(s)")
    print("=" * 55 + "\n")


def restore_backup(backup_path):
    """
    Restore a database from a backup file.
    Usage: python scripts/backup_db.py restore /path/to/backup.db
    """
    backup_path = Path(backup_path)

    if not backup_path.exists():
        print(f"\n  ❌ Backup file not found: {backup_path}\n")
        return False

    # Determine which database to restore
    if 'esg_stock' in backup_path.name:
        target = MAIN_DB
    elif 'users' in backup_path.name:
        target = USERS_DB
    else:
        print(f"\n  ❌ Cannot determine target database from filename: {backup_path.name}")
        print("     Filename must contain 'esg_stock' or 'users'.\n")
        return False

    # Create a safety backup before restoring
    safety_backup = BACKUP_DIR / f"pre_restore_{target.stem}_{get_timestamp()}.db"
    if target.exists():
        shutil.copy2(str(target), str(safety_backup))
        print(f"\n  💾 Safety backup saved: {safety_backup.name}")

    # Restore
    try:
        shutil.copy2(str(backup_path), str(target))
        print(f"  ✅ Restored {target.name} from {backup_path.name}\n")
        return True
    except Exception as e:
        print(f"  ❌ Restore failed: {e}\n")
        return False


def run_scheduled_backup():
    """Called by APScheduler. Returns a summary dict for logging."""
    result = create_backup()
    return result


# ============================================================
# CLI Entry Point
# ============================================================
if __name__ == '__main__':
    if len(sys.argv) == 1:
        create_backup()
    elif sys.argv[1] == 'list':
        list_backups()
    elif sys.argv[1] == 'restore' and len(sys.argv) == 3:
        restore_backup(sys.argv[2])
    else:
        print("\n  Usage:")
        print("    python scripts/backup_db.py              Create a backup")
        print("    python scripts/backup_db.py list         List all backups")
        print("    python scripts/backup_db.py restore <path>  Restore from backup")
        print()
        sys.exit(1)
