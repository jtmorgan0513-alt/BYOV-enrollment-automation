# BYOV-enrollment-automation

Automated BYOV enrollment engine with VIN decoding, data collection, PDF generation, and an admin control center. **Successfully collects enrollment data and transmits to Replit dashboard with each new enrollment via an approve button in the admin dashboard.**

## Features
- Streamlit UI wizard for technician enrollment (Tech Info, Vehicle & Docs, Policy & Signature, Review & Submit)
- VIN decode helper using the NHTSA public API
- Signature pad (submission blocked until signed)
- Photo/document uploads (vehicle, insurance, registration)
- PDF generation with embedded signature
- Email notification with submission details, PDF, and attachments (configurable via SMTP)
- **Admin Control Center**: Comprehensive dashboard for managing enrollments and transmitting to external systems
    - **One-Click Approval**: Approve button creates technician records on Replit dashboard with photos in a single API call
    - Overview metrics (enrollments, rules, emails sent, storage mode)
    - Enrollments tab: search, pagination, photo viewer, PDF download
    - View Photos modal: organized tabs for vehicle, insurance, registration, and signed PDF documents
    - Test enrollment creator: Generate complete test data with sample photos for workflow validation
    - Real-time dashboard sync status tracking with detailed error reporting
    - No password required (as of latest update)
- SQLite database (with JSON fallback for environments without sqlite3)
- **External Dashboard Integration**: Automatic transmission of enrollment data to Replit dashboard via REST API

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

### Optional: Dashboard Integration

The application now **automatically transmits enrollment data to a Replit dashboard** using a modern REST API integration.

#### Configuration

Set these secrets in Streamlit Cloud or in `.streamlit/secrets.toml`:

```toml
[replit]
REPLIT_DASHBOARD_URL = "https://your-replit-dashboard.replit.app"
REPLIT_DASHBOARD_USERNAME = "admin"
REPLIT_DASHBOARD_PASSWORD = "your-secure-password"
```

Or use environment variables:

```powershell
set REPLIT_DASHBOARD_URL=https://your-replit-dashboard.replit.app
set REPLIT_DASHBOARD_USERNAME=admin
set REPLIT_DASHBOARD_PASSWORD=your-secure-password
```

#### Workflow

1. **Enrollment Collection**: Users submit enrollments through the wizard (Tech Info → Vehicle & Docs → Policy & Signature → Review & Submit)
2. **Admin Review**: Admins review enrollments in the Admin Control Center → Enrollments tab
3. **One-Click Approval**: Click the **✅ Approve** button on any enrollment
4. **Automatic Transmission**: The system:
   - Authenticates with the Replit dashboard API
   - Encodes all photos as base64 (max 10MB per photo)
   - Sends technician data + photos in a single POST request to `/api/external/technicians`
   - Handles success (201), partial success (207), or errors (400/500)
   - Marks the enrollment as approved locally
   - Displays detailed results and any failed photo uploads

#### API Endpoint

The integration uses the external technician creation endpoint:

**POST** `/api/external/technicians`

**Payload includes:**
- Technician details (name, techId, region, district, enrollmentStatus, etc.)
- Vehicle information (vinNumber, make, model, year)
- Contact details (mobilePhoneNumber, techEmail)
- Expiration dates (insuranceExpiration, registrationExpiration)
- Photos array with base64-encoded images (vehicle, insurance, registration categories)

**Response codes:**
- `201` - Success: technician and all photos created
- `207` - Partial success: technician created, some photos failed
- `400` - Validation error
- `500` - Server error

#### Testing

Use the built-in **Test Enrollment Creator** in the Admin Control Center:
1. Navigate to Admin Control Center → Enrollments → Diagnostics & Maintenance
2. Fill in test data (or use defaults)
3. Upload sample photos
4. Click **✅ Create Test Enrollment**
5. Find the test enrollment in the list and click **✅ Approve**
6. Verify the technician appears on your Replit dashboard with photos attached

### Optional: SendGrid Email Delivery
You can switch email notifications (submission + rules) to SendGrid instead of raw SMTP.

Set secrets or environment variables:

```powershell
set SENDGRID_API_KEY=SG.xxxxxx
set SENDGRID_FROM_EMAIL=byov@yourdomain.com
```

Or in `secrets.toml`:
```toml
[email]
sendgrid_api_key = "SG.xxxxxx"
sendgrid_from_email = "byov@yourdomain.com"
sender = "fallback@gmail.com"         # kept for SMTP fallback
app_password = "gmail-app-password"   # fallback
recipient = "recipient@example.com"
```

Behavior:
- If SendGrid vars present, attempts API send first.
- Falls back to Gmail SMTP if SendGrid fails.
- Large attachment handling unchanged (zipping >20MB aggregate).

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

_Last updated: November 2025 — Integrated Replit dashboard transmission with one-click approval workflow. All enrollment data and photos are automatically transmitted via REST API on admin approval._
