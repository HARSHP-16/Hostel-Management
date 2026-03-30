from db import get_db_connection
import pymysql

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
