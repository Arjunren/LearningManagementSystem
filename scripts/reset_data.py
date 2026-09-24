import os
import sys
import shutil
import json
import datetime
import argparse

# Add parent directory to path so we can import services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.user_service import user_db, create_user
from services.course_service import course_db, procedure_db, enrollment_db
from services.grade_service import grade_db
from services.certificate_db_service import cert_template_db

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
BACKUPS_DIR = os.path.join(BASE_DIR, 'backups')

def create_backup():
    if not os.path.exists(BACKUPS_DIR):
        os.makedirs(BACKUPS_DIR)
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_path = os.path.join(BACKUPS_DIR, f"backup_{timestamp}")
    
    if os.path.exists(DATA_DIR):
        shutil.copytree(DATA_DIR, backup_path)
        print(f"[+] Backup created at {backup_path}")
    else:
        print("[-] No data directory found to backup.")

def clear_directory(directory, exclude_files=None):
    if exclude_files is None:
        exclude_files = []
        
    if not os.path.exists(directory):
        return
        
    for filename in os.listdir(directory):
        if filename in exclude_files:
            continue
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)

def reset_student_data():
    print("[*] Removing student accounts...")
    users = user_db.get_all()
    for u in users:
        if u.get('role') == 'student':
            user_db.delete(u['id'])
    print("[+] Student data cleared.")

def reset_grades():
    print("[*] Clearing grades...")
    clear_directory(os.path.join(DATA_DIR, 'grades'))
    print("[+] Grades cleared.")

def reset_enrollments():
    print("[*] Clearing enrollments...")
    clear_directory(os.path.join(DATA_DIR, 'enrollments'))
    print("[+] Enrollments cleared.")

def reset_certificates():
    print("[*] Clearing certificate generation records...")
    # Certificates are stored inside enrollments as metadata, and PDF files in static/certificates.
    # We will just clear the PDF files and remove the cert fields from enrollments.
    certs_dir = os.path.join(BASE_DIR, 'static', 'certificates')
    clear_directory(certs_dir)
    
    enrollments = enrollment_db.get_all()
    for e in enrollments:
        if 'certificate_id' in e:
            e.pop('certificate_id', None)
            e.pop('certificate_filename', None)
            e.pop('cert_last_sent_at', None)
            enrollment_db.update(e['id'], e)
    print("[+] Certificates cleared.")

def reset_all_development_data():
    reset_student_data()
    reset_grades()
    reset_enrollments()
    reset_certificates()

def full_reset():
    print("[*] Performing full destructive reset (excluding settings/templates)...")
    clear_directory(os.path.join(DATA_DIR, 'users'))
    clear_directory(os.path.join(DATA_DIR, 'courses'))
    clear_directory(os.path.join(DATA_DIR, 'procedures'))
    clear_directory(os.path.join(DATA_DIR, 'enrollments'))
    clear_directory(os.path.join(DATA_DIR, 'grades'))
    clear_directory(os.path.join(DATA_DIR, 'otps'))
    clear_directory(os.path.join(DATA_DIR, 'teacher_assignments'))
    
    # We keep settings and certificate_templates as requested by prompt rules.
    print("[+] Full reset completed.")

def seed_data():
    print("[*] Seeding initial development data...")
    try:
        # Create Admin
        admin_id = create_user("Admin User", "admin@buildbyte.com", "admin123", "admin")
        # Create Teacher
        teacher_id = create_user("Arjunren Von", "teacher@buildbyte.com", "teacher123", "teacher")
        # Create Student
        student_id = create_user("Jarek Melgar", "student@buildbyte.com", "student123", "student")

        # Create Course
        course_data = {
            "title": "Advanced AWS Architecture",
            "description": "Learn to design scalable and resilient architectures on AWS.",
            "syllabus": "1. S3\n2. EC2\n3. VPC",
            "published": True
        }
        course_id = course_db.create(course_data, prefix="crs")

        # Create Procedure
        proc_data = {
            "course_id": course_id,
            "title": "Final Capstone Project",
            "order": 1,
            "graded": True,
            "required": True,
            "max_score": 100,
            "passing_score": 80
        }
        procedure_db.create(proc_data, prefix="proc")
        
        # Create Certificate Template
        cert_data = {
            "name": "Standard Completion",
            "course_id": course_id,
            "signature_name": "ARJUNREN VON",
            "signature_title": "CLOUD ENGINEER",
            "bg_image_url": "",
            "name_x": 50,
            "name_y": 40,
            "date_x": 20,
            "date_y": 80,
            "title_x": 50,
            "title_y": 60,
            "font_size": 5.7,
            "font_family": "Inter",
            "font_weight": 800
        }
        cert_template_db.create(cert_data, prefix="ctpl")

        print("[+] Seed data created successfully.")
    except Exception as e:
        print(f"[-] Error seeding data: {e}")

def main():
    parser = argparse.ArgumentParser(description="BuildByte Academy Data Reset Utility")
    parser.add_argument("--seed", action="store_true", help="Seed initial development data after reset.")
    args = parser.parse_args()

    if args.seed:
        print("Note: --seed flag detected. Data will be seeded after reset.")

    print("\n" + "="*40)
    print(" BuildByte Academy Data Reset")
    print("="*40)
    print("What do you want to reset?")
    print("1. Student Data")
    print("2. Grades")
    print("3. Enrollments")
    print("4. Certificates")
    print("5. All Development Data")
    print("6. Full Reset")
    print("7. Cancel\n")

    try:
        choice = input("Enter choice (1-7): ").strip()
    except KeyboardInterrupt:
        print("\nCancelled.")
        return

    if choice == '7' or not choice:
        print("Operation cancelled.")
        return

    options = {
        '1': "Student Data",
        '2': "Grades",
        '3': "Enrollments",
        '4': "Certificates",
        '5': "All Development Data",
        '6': "Full Reset"
    }

    if choice not in options:
        print("Invalid choice.")
        return

    print(f"\nWARNING: You are about to reset: {options[choice]}")
    print("Are you sure you want to continue?")
    print("Type: RESET to confirm.")
    
    try:
        confirm = input("> ").strip()
    except KeyboardInterrupt:
        print("\nCancelled.")
        return

    if confirm != "RESET":
        print("Confirmation failed. Operation cancelled.")
        return

    create_backup()

    if choice == '1':
        reset_student_data()
    elif choice == '2':
        reset_grades()
    elif choice == '3':
        reset_enrollments()
    elif choice == '4':
        reset_certificates()
    elif choice == '5':
        reset_all_development_data()
    elif choice == '6':
        full_reset()

    if args.seed:
        seed_data()

    print("\n[✓] Done.")

if __name__ == "__main__":
    main()
