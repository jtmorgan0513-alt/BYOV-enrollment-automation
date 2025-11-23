import json
import os
from datetime import datetime

DATA_FILE = "enrollments.json"


def load_enrollments():
    """Return list of enrollment records from DATA_FILE."""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return []


def save_enrollments(records):
    """Write list of enrollment records to DATA_FILE."""
    with open(DATA_FILE, 'w') as f:
        json.dump(records, f, indent=2, default=str)
