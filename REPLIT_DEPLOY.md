Replit Deployment Guide

1) Requirements
- This repo includes `requirements.txt` listing Python dependencies. Replit will install these automatically.

2) Run command
- `.replit` is configured to run:

```
streamlit run byov_app.py --server.port $PORT --server.address 0.0.0.0
```

3) Secrets / Environment variables
Set the following secrets in the Replit Secrets pane (key/value):
- `REPLIT_DASHBOARD_URL` — url of your Replit dashboard API (e.g. https://byovdashboard.replit.app)
- `REPLIT_DASHBOARD_USERNAME` — dashboard API username
- `REPLIT_DASHBOARD_PASSWORD` — dashboard API password
- `GITHUB_TOKEN` (optional) — if you want the app to push backups to GitHub automatically
- `S3_BUCKET`, `S3_KEY`, `S3_SECRET` (optional) — if you want backups sent to S3

Note: Streamlit's `st.secrets` is specific to Streamlit Cloud; on Replit the app will read environment variables via `os.getenv()`. The app already falls back to environment variables if `st.secrets` is not configured.

4) Persistent storage notes
- Files created under your Repl project (e.g., `data/byov.db`, `data/backups/`, `uploads/`) are persistent across runs in the same Repl, but you should still keep backups off-instance for safety.

5) Backup strategy suggestions
- The app already creates timestamped backups in `data/backups/` on submission. Consider configuring automatic offsite backup (GitHub or S3) by providing a token/credentials in secrets and enabling the feature.

6) Starting the app on Replit
- Open the Repl, install packages if prompted, then click "Run". The Streamlit app will start and be visible in the Repl webview.

7) Troubleshooting
- If the DB appears empty after a redeploy: ensure you are running the same branch and that you didn't accidentally replace the `data/byov.db` file. Use `data/backups/` to restore.
- To restore a backup on Replit, upload the backup file to `data/backups/` and then run the restore command with the app's shell or via the `backup_database.py` script.
