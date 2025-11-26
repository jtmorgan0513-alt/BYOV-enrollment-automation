import sys
import os

# Check parent directory
parent_dir = os.path.abspath('..')
sys.path.insert(0, parent_dir)
os.chdir(parent_dir)

import database

database.init_db()
enrollments = database.get_all_enrollments()

print(f'Checking directory: {os.getcwd()}')
print(f'Total enrollments: {len(enrollments)}')

jacob = [e for e in enrollments if 'clevidence' in e.get('full_name', '').lower()]
print(f'\nJacob Clevidence found: {len(jacob)}')

for e in jacob:
    print(f"\nID {e.get('id')}: {e.get('full_name')}")
    print(f"Tech ID: {e.get('tech_id')}")
    print(f"Submitted: {e.get('submission_date')}")
    print(f"All fields: {e}")
