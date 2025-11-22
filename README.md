# BYOV-enrollment-automation

Automated BYOV enrollment engine with VIN decoding, data collection, PDF generation, and an admin dashboard.

## Features
- Streamlit UI captures Tech ID, technician name, district, VIN, year, make, and model.
- VIN decode helper using the NHTSA public API.
- Signature pad that blocks submissions until signed; unsigned attempts are rejected.
-- Photo collection through the Streamlit form (uploads saved under `uploads/`).
- PDF generation with submitted details and embedded signature.
- Email notification with submission details, PDF, and photo attachments (configurable via SMTP environment variables).

## Getting started
1. Install dependencies (preferably in a virtual environment):
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Configure SMTP (optional, required for email delivery). The app uses Streamlit `secrets.toml` for email config.
   Create `secrets.toml` in the project root with the following structure:
   ```toml
   [email]
   sender = "you@example.com"
   app_password = "your-app-password"
   recipient = "recipient@example.com"
   ```

3. Run the Streamlit app:
   ```powershell
   streamlit run byov_app.py
   ```

4. (Optional) Start the photo upload API for POST-based uploads:
   ```bash
   uvicorn app:api --reload --host 0.0.0.0 --port 8000
   ```
   Upload photos with:
   ```bash
   curl -X POST -F "files=@/path/to/photo1.jpg" -F "files=@/path/to/photo2.jpg" http://localhost:8000/photos
   ```

Submitted PDFs are written to `pdfs/` and uploaded photos are stored in `uploads/`.
