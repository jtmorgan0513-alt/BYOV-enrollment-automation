# Data Persistence & Backup

## Database Location
The application uses SQLite database stored at `data/byov.db`.

## Database Persistence Guarantee ✅

**Your data is safe across restarts!** The SQLite database file (`data/byov.db`) persists on disk, so:
- ✅ **App restarts** - All enrollments remain intact
- ✅ **Code updates** - Database is never overwritten
- ✅ **Git operations** - Database stays local, not affected by pulls/pushes
- ✅ **Server reboots** - Data persists on the filesystem

### Where Your Data Lives
- **Local Development**: `C:\Users\tyler\Desktop\BYOV-enrollment-automation\BYOV-enrollment-automation\data\byov.db`
- **Streamlit Cloud**: Persistent storage (if configured) or ephemeral (resets on redeploy)

## Database is NOT Tracked by Git

The database file is intentionally excluded from Git:
- `data/byov.db` is in `.gitignore`
- Only `.gitkeep` and this README are tracked
- Enrollment data stays private and local

### Why this matters
✅ **Advantages:**
- No merge conflicts from database changes
- Sensitive data doesn't get pushed to GitHub
- Each environment has its own data
- Database can grow without bloating Git repository

⚠️ **Important:**
- Your local data is only on your machine
- Deleting the repo folder = losing all data
- Deploying to Streamlit Cloud requires separate data migration

## Backup Strategy

### Automated Backups with Script

Use the included `backup_database.py` script:

```powershell
# Create a timestamped backup
python backup_database.py backup

# List all backups
python backup_database.py list

# Restore from a specific backup
python backup_database.py restore byov_backup_20251126_120000.db
```

Backups are saved to `data/backups/` and can be tracked in Git (for off-site safety).

### Manual Backup

```powershell
# Quick backup with timestamp
copy data\byov.db "data\byov_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').db"

# Simple backup
copy data\byov.db data\byov.db.backup
```

### Regular Backup Schedule (Recommended)

For production use, set up automated backups:
- **Daily**: Before any major operations
- **Before deployment**: Always backup before pushing code changes
- **Weekly**: Regular scheduled backups to external storage

## Data Recovery

### Restore from Backup

```powershell
# Using the script (creates safety backup first)
python backup_database.py restore byov_backup_20251126_120000.db

# Manual restore
copy data\backups\byov_backup_20251126_120000.db data\byov.db
```

### Check Database Status

```python
import sqlite3
conn = sqlite3.connect('data/byov.db')
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM enrollments")
print(f"Total enrollments: {cursor.fetchone()[0]}")
conn.close()
```

## Clear Test Data

To start fresh (⚠️ removes all enrollments and files):
```powershell
python clear_database.py
```

## Deploying to Production

### Streamlit Cloud Deployment

⚠️ **Streamlit Cloud has ephemeral storage** - data resets on app restarts unless you use:

1. **Streamlit Cloud Persistent Storage** (if available in your plan)
2. **External Database** (PostgreSQL, MySQL, etc.)
3. **Cloud Storage** (AWS S3, Google Cloud Storage)

For critical production data, migrate to a managed database service.

### Manual Data Migration

```powershell
# Export current database
copy data\byov.db database_export.db

# On new system, restore it
copy database_export.db data\byov.db
```

## Directory Structure
```
data/
├── .gitkeep              # Tracked by Git (ensures folder exists)
├── README.md             # This file (tracked by Git)
├── byov.db               # NOT tracked (your actual data)
└── backups/              # Optional backup storage
    ├── byov_backup_20251126_120000.db
    └── byov_backup_20251126_150000.db
```

## Troubleshooting

**Q: My data disappeared after restarting!**
- Check if `data/byov.db` still exists
- Verify file permissions (should be readable/writable)
- Check Streamlit Cloud logs for storage issues

**Q: Can I sync data across multiple machines?**
- Not automatically (database is gitignored)
- Use backup/restore scripts to manually transfer
- Or use a cloud database for true sync

**Q: How do I know my data is really persisted?**
```powershell
# Check file exists and size
dir data\byov.db

# Count records
python -c "import sqlite3; conn=sqlite3.connect('data/byov.db'); print(f'Records: {conn.execute(\"SELECT COUNT(*) FROM enrollments\").fetchone()[0]}'); conn.close()"
```
