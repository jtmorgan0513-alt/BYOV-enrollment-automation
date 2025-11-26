# Data Persistence

## Database Location
The application uses SQLite database stored at `data/byov.db`.

## Important Notes

### Database is NOT tracked by Git
- The `data/` folder (except `.gitkeep`) is ignored by Git
- Your enrollment data, uploaded files, and PDFs are stored locally only
- When you commit code changes, the database stays on your local machine

### Why this matters
✅ **Advantages:**
- No conflicts when multiple people work on the code
- Sensitive enrollment data doesn't get pushed to GitHub
- Database can grow without bloating the Git repository

⚠️ **Important:**
- Your enrollment data is only on your local machine
- If you delete the repository folder, you'll lose all enrollments
- Code updates won't overwrite your existing data

### Backup Your Data

To backup your database:
```powershell
# Create a backup
copy data\byov.db data\byov.db.backup

# Or backup with timestamp
copy data\byov.db data\byov_backup_2025-11-23.db
```

### Clear Test Data

To start fresh (removes all enrollments and files):
```powershell
python clear_database.py
```

### If You Need to Share Data

If you're deploying to a server or sharing with others:
1. Export the database separately (not through Git)
2. Copy `data/byov.db` directly to the target system
3. Or use database backup/restore tools

## Directory Structure
```
data/
├── .gitkeep          # Tracked by Git (ensures folder exists)
└── byov.db           # NOT tracked by Git (your actual data)
```
