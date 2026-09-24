"""Backfill student usernames/IDs and create persistent uniqueness indexes.

Run once during deployment: ``python scripts/migrate_identity_indexes.py``.
The operation is idempotent and retains valid unique values.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.auth_service import ensure_identity_indexes

if __name__ == '__main__':
    ensure_identity_indexes()
    print('Student identity migration completed.')
