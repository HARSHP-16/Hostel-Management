import logging

logger = logging.getLogger(__name__)

from db import get_db_connection
import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

def run_migrations():
    print("Connecting to database...")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        print("Adding Bio to Student table if not exists...")
        try:
            cursor.execute("ALTER TABLE Student ADD COLUMN Bio TEXT")
            print("Bio column added.")
        except pymysql.err.OperationalError as e:
            if "Duplicate column" in str(e):
                print("Bio column already exists.")
            else:
                print(f"Error: {e}")
                
        print("Adding Emergency_Contact to Student table if not exists...")
        try:
            cursor.execute("ALTER TABLE Student ADD COLUMN Emergency_Contact VARCHAR(15)")
            print("Emergency_Contact column added.")
        except pymysql.err.OperationalError as e:
            if "Duplicate column" in str(e):
                print("Emergency_Contact column already exists.")
            else:
                print(f"Error: {e}")

        print("Creating Notification table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Notification (
                Notification_ID INT AUTO_INCREMENT PRIMARY KEY,
                User_ID INT NOT NULL,
                Role ENUM('student', 'warden') NOT NULL,
                Message TEXT NOT NULL,
                Timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                Is_Read BOOLEAN DEFAULT FALSE
            )
        """)
        print("Notification table ready.")
        
        print("Creating Admin table & seeding...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Admin (
                Admin_ID INT AUTO_INCREMENT PRIMARY KEY,
                Email VARCHAR(100) UNIQUE NOT NULL,
                Password VARCHAR(255) NOT NULL
            )
        """)

        # Seed default admin from environment variables only — never from hardcoded values.
        admin_email = os.environ.get("ADMIN_EMAIL")
        admin_password = os.environ.get("ADMIN_PASSWORD")
        if admin_email and admin_password:
            cursor.execute("SELECT * FROM Admin WHERE Email = %s", (admin_email,))
            if not cursor.fetchone():
                from werkzeug.security import generate_password_hash
                hashed_pwd = generate_password_hash(admin_password)
                cursor.execute(
                    "INSERT INTO Admin (Email, Password) VALUES (%s, %s)",
                    (admin_email, hashed_pwd),
                )
                print("Default admin seeded from environment variables.")
            else:
                print("Admin already exists.")
        else:
            print("ADMIN_EMAIL / ADMIN_PASSWORD not set — skipping admin seed.")
            print("Set both environment variables and re-run migrate_db.py to create the admin account.")
            
        conn.commit()
        print("Migrations ran successfully.")
        
    except pymysql.Error as e:
        print(f"Global error running migrations: {e}")
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    run_migrations()
