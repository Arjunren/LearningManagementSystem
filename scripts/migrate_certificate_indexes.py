"""Backfill atomic unique certificate-ID index records for legacy enrollments."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.certificate_service import ensure_certificate_indexes

if __name__ == '__main__':
    ensure_certificate_indexes()
    print('Certificate ID migration completed.')
