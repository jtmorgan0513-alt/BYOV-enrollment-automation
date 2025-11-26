import os
import uuid
import json
from pathlib import Path
import byov_app
import streamlit as st

print('Starting BYOV e2e test')

# Create test upload directory
record_id = str(uuid.uuid4())
base = Path('uploads') / f'test_{record_id}'
base.mkdir(parents=True, exist_ok=True)
(vehicle_dir := base / 'vehicle').mkdir(exist_ok=True)
(insurance_dir := base / 'insurance').mkdir(exist_ok=True)
(reg_dir := base / 'registration').mkdir(exist_ok=True)
Path('pdfs').mkdir(exist_ok=True)

# Create a small PDF signature file
sig_path = Path('pdfs') / f'sig_{record_id}.pdf'
from reportlab.pdfgen import canvas
c = canvas.Canvas(str(sig_path))
c.drawString(100, 750, 'Test Signature PDF')
c.save()
print('Created signature PDF:', sig_path)

# Create many dummy image files to force zipping (each ~1MB)
num_files = 25
vehicle_files = []
for i in range(num_files):
    p = vehicle_dir / f'photo_{i}.jpg'
    with open(p, 'wb') as f:
        f.write(os.urandom(1024 * 1024))
    vehicle_files.append(str(p))
print(f'Created {len(vehicle_files)} vehicle files ~1MB each')

# Create small insurance and registration files
ins_path = insurance_dir / 'ins_doc.txt'
ins_path.write_text('insurance doc')
reg_path = reg_dir / 'reg_doc.txt'
reg_path.write_text('registration doc')

# Build record
record = {
    'id': record_id,
    'tech_id': 'TEST123',
    'full_name': 'E2E Tester',
    'district': '99',
    'state': 'Test',
    'industries': ['Cook'],
    'vin': '1HGBH41JXMN109186',
    'year': '2020',
    'make': 'TestMake',
    'model': 'ModelX',
    'insurance_exp': '2026-01-01',
    'registration_exp': '2026-01-01',
    'comment': 'E2E test',
    'template_used': 'template_1.pdf',
    'signature_pdf_path': str(sig_path),
    'vehicle_photos_paths': vehicle_files,
    'insurance_docs_paths': [str(ins_path)],
    'registration_docs_paths': [str(reg_path)],
    'submission_date': '2025-11-21T12:00:00'
}

# Ensure st.secrets.email is present but empty to avoid sending real emails
try:
    st.secrets['email'] = st.secrets.get('email', {})
except Exception:
    # in some Streamlit installations st.secrets may be read-only mappingproxy; try attribute assign
    try:
        st.secrets = {'email': {}}
    except Exception:
        pass

print('Calling send_email_notification (this will attach/zip but may skip send if creds missing)')
ok = byov_app.send_email_notification(record)
print('send_email_notification returned:', ok)

# Save the record to enrollments.json (append)
records = byov_app.load_enrollments()
records.append(record)
byov_app.save_enrollments(records)
print('Saved test record to enrollments.json')

print('E2E test finished')
