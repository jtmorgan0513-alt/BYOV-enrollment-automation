# BYOV Enrollment Automation

## Overview

This is a **BYOV (Bring Your Own Vehicle) Enrollment Automation System** for Sears Home Services technicians. The application streamlines the vehicle enrollment process through a multi-step wizard interface and provides an admin control center for managing approvals and syncing data with external dashboards.

**Core Purpose:** Automate technician vehicle enrollment by collecting vehicle information, documents, signatures, and photos, then transmitting approved enrollments to a central dashboard system.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Framework:** Streamlit-based web application (`byov_app.py`)
- **UI Pattern:** Multi-step wizard workflow (Tech Info → Vehicle & Docs → Policy & Signature → Review & Submit)
- **Key Features:**
  - VIN decoding via NHTSA public API
  - Digital signature pad (blocks submission until signed)
  - Photo/document upload interface
  - Admin Control Center with approval dashboard

### Backend Architecture

#### Database Layer
- **Primary:** PostgreSQL (when `DATABASE_URL` environment variable is set)
- **Fallback:** SQLite with JSON fallback for environments without sqlite3
- **Design Pattern:** Database abstraction layer (`database.py`) that delegates to `database_pg.py` or SQLite implementation
- **Connection Management:** Context managers with retry logic and connection pooling for PostgreSQL
- **Schema:** Enrollments, documents, notification rules, and notifications_sent tables

#### File Storage System
- **Dual-mode storage:** Local filesystem or Replit Object Storage
- **Detection:** Uses `PRIVATE_OBJECT_DIR` environment variable to determine storage mode
- **API:** Unified interface in `file_storage.py` that abstracts storage location
- **Replit Integration:** Uses sidecar endpoint (`http://127.0.0.1:1106`) for presigned URL generation

#### Document Generation
- **PDF Creation:** ReportLab for generating enrollment PDFs
- **Template System:** State-based template selection (different templates for CA/WA/IL vs other states)
- **Signature Embedding:** PyPDF2 for merging signature canvas into final PDF
- **Page 6 Element Placement** (coordinates for signature page):
  - Signature: x=73, y=442, width=160, height=28
  - Employee Name: x=257, y=545
  - Tech ID: x=257, y=531
  - Date: x=316, y=442

#### Notification System
- **Email Delivery:** SendGrid API (primary) with SMTP fallback via `secrets.toml` or environment variables
- **Templates:** Branded HTML email templates with Sears styling
- **Logo:** Sears logo embedded as inline CID image (requires `static/sears_logo.png` to be present)
- **Notification Rules:** Database-driven rule engine for triggered notifications

### Data Flow Architecture

1. **Enrollment Submission:**
   - Technician completes wizard → Data validated → Photos uploaded → Signature captured
   - Record saved to database → PDF generated → Backup created → Optional email sent

2. **Admin Approval Workflow:**
   - Admin reviews enrollments in two-pane control center:
     - **Top Pane:** AgGrid spreadsheet with all enrollment fields, column visibility controls (by group), and single-row selection
     - **Bottom Pane:** Tabbed action panel (Overview | Checklist | Documents)
   - **Overview Tab:** Summary card, Approve & Sync button, Send PDF to HR button, Send Notification button, Delete
   - **Checklist Tab:** Task tracking with 6 required tasks per enrollment:
     - Approved Enrollment & Synced to Dashboard
     - Signed Policy Form Sent to HSHRpaperwork
     - Mileage form created in Segno
     - Supplies Notified for Magnets
     - Fleet & Inventory Notified
     - 30 Day survey completed
     - Simple checkbox interface (no email function)
     - Progress bar shows completion status
   - **Documents Tab:** Inline PDF preview via iframe, photo thumbnails by category (Vehicle, Registration, Insurance)
   - **Global Approval Notifications Tab** (top-level tab next to Email Config):
     - Field selector checkboxes (choose which data fields to include in email)
     - Document selector checkboxes (choose which photos/PDFs to attach)
     - Recipients and subject template configuration
     - Live email preview showing exactly what will be sent
     - Settings apply to all enrollments when approved
   - Approval triggers dashboard sync via REST API + custom email notification
   - `send_custom_notification` function generates emails using only selected fields and attaches only selected documents
   - Record status updated with approval metadata
   - Photos and documents transmitted to external dashboard

3. **Dashboard Integration:**
   - REST API calls to Replit dashboard (`REPLIT_DASHBOARD_URL`)
   - Automatic retry logic with exponential backoff
   - Error tracking and status reporting in UI

### Backup & Recovery Strategy
- **Automatic Timestamped Backups:** JSON exports created on submission
- **Location:** `data/backups/` directory
- **Format:** JSON with full enrollment data and documents
- **PostgreSQL Support:** Exports both enrollments and notification rules
- **Restoration:** `restore_db.py` script can rebuild database from uploads directory

## External Dependencies

### Third-Party APIs
- **NHTSA VIN Decoder API:** `vpic.nhtsa.dot.gov` - Public API for vehicle information lookup
- **Replit Dashboard API:** External REST API for technician record management (configured via `REPLIT_DASHBOARD_URL`)

### Database Services
- **PostgreSQL:** Cloud-hosted database (via `DATABASE_URL` environment variable)
- **SQLite:** Local fallback database stored in `data/byov.db`

### Cloud Storage
- **Replit Object Storage:** Private object storage accessed via sidecar API
- **Local Filesystem:** Fallback storage in `uploads/` and `pdfs/` directories

### Email Services
- **SMTP:** Configurable email delivery (Gmail or custom SMTP server)
- **Configuration:** Via Streamlit secrets or environment variables

### Python Dependencies
- **streamlit:** Web application framework
- **psycopg2-binary:** PostgreSQL database adapter
- **Pillow:** Image processing
- **reportlab, PyPDF2:** PDF generation and manipulation
- **streamlit-drawable-canvas:** Signature capture
- **st_aggrid:** Data grid component for admin dashboard
- **requests:** HTTP client for API calls

### Node.js Workflow API (Optional Component)
- **Location:** `workflow-api/` directory
- **Purpose:** Separate admin approval workflow server (can be deployed independently)
- **Framework:** Express.js with TypeScript
- **Features:** Admin review endpoints, email notifications via SendGrid/SMTP, dashboard integration
- **Database:** MongoDB (separate from main app)
- **Note:** This is an optional secondary application that provides similar functionality to the Streamlit admin dashboard

### Environment Configuration Requirements
- `DATABASE_URL` - PostgreSQL connection string (optional, falls back to SQLite)
- `REPLIT_DASHBOARD_URL` - External dashboard API endpoint
- `REPLIT_DASHBOARD_USERNAME` - Dashboard API authentication
- `REPLIT_DASHBOARD_PASSWORD` - Dashboard API authentication
- `PRIVATE_OBJECT_DIR` - Replit Object Storage bucket path (optional)
- Email credentials in `secrets.toml` or environment variables (optional)