import database

database.init_db()
enrollments = database.get_all_enrollments()

jacob = [e for e in enrollments if 'clevidence' in e.get('full_name', '').lower()]

print(f'Found {len(jacob)} matching enrollments:')
for e in jacob:
    print(f"ID {e.get('id')}: {e.get('full_name')} - Tech ID: {e.get('tech_id')} - Submitted: {e.get('submission_date')}")

print(f"\nTotal enrollments in database: {len(enrollments)}")
if enrollments:
    print(f"\nAll enrollment IDs: {[e.get('id') for e in enrollments]}")
