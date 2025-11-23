# BYOV-enrollment-automation

Automated BYOV enrollment engine with VIN decoding, data collection, PDF generation, and an admin control center.

## Features
- Streamlit UI wizard for technician enrollment (Tech Info, Vehicle & Docs, Policy & Signature, Review & Submit)
- VIN decode helper using the NHTSA public API
- Signature pad (submission blocked until signed)
- Photo/document uploads (vehicle, insurance, registration)
- PDF generation with embedded signature
- Email notification with submission details, PDF, and attachments (configurable via SMTP)
- **Admin Control Center**: Tabbed dashboard for managing enrollments, notification rules, and logs
    - Overview metrics (enrollments, rules, emails sent, storage mode)
    - Enrollments tab: search, pagination, record selection
    - Rules tab: create/edit/delete/toggle/run notification rules
    - Notifications Log tab: view sent notifications
    - No password required (as of latest update)
- SQLite database (with JSON fallback for environments without sqlite3)

## Requirements
- Python 3.12+
- Streamlit
- Pillow, ReportLab, PyPDF2, pandas
- SMTP credentials for email notifications (optional)

## Setup
1. **Install dependencies** (preferably in a virtual environment):
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure SMTP** (optional, for email delivery):
   Create `secrets.toml` in the project root:
   ```toml
   [email]
   sender = "you@example.com"
   app_password = "your-app-password"
   recipient = "recipient@example.com"
   ```

3. **Run the app:**
   ```powershell
   streamlit run byov_app.py
   ```

4. **Access the Admin Control Center:**
   - Use the sidebar to select "Admin Control Center"
   - No password required
   - Tabs: Overview, Enrollments, Rules, Notifications Log

5. **Deployment:**
   - Push your code to GitHub
   - Deploy on Streamlit Cloud or other platforms that support Streamlit
   - Streamlit Cloud will auto-update from your GitHub repo

## File Structure
- `byov_app.py` — Main app and wizard
- `admin_dashboard.py` — Admin Control Center UI
- `database.py` — Data layer (SQLite/JSON)
- `notifications.py` — Email logic
- `requirements.txt` — Python dependencies
- `secrets.toml` — Email credentials (not included in repo)
- `uploads/`, `pdfs/`, `data/` — Storage folders

## License
Business Source License 1.1 (BSL-1.1)

## Notes
- For production, update SMTP credentials and secrets.
- If sqlite3 is unavailable, app will use JSON fallback for data storage.
- For support, open an issue on GitHub or contact the author.

---

_Last updated: November 2025 — Admin Control Center UI overhaul, password removed, improved metrics and rule management._
