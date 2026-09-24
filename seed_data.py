import os
from services.auth_service import create_user, admin_db, hash_password
from services.course_service import course_db
import datetime

def seed():
    print("Seeding initial data...")
    
    # Create Admin
    if not admin_db.find_one(email="admin@buildbyteacademy.com"):
        admin_data = {
            'full_name': "Admin User",
            'email': "admin@buildbyteacademy.com",
            'password_hash': hash_password("Admin123!"),
            'role': 'admin',
            'created_at': datetime.datetime.utcnow().isoformat(),
            'updated_at': datetime.datetime.utcnow().isoformat()
        }
        admin_db.create(admin_data, prefix="adm")
        print("Created admin: admin@buildbyteacademy.com / Admin123!")
    else:
        print("Admin already exists.")
    
    # Create Test Student
    # create_user("Test Student", "student@lms.com", "Student123!")
    # print("Created student: student@lms.com / Student123!")
    
        
    print("Seeding complete.")

if __name__ == '__main__':
    seed()
