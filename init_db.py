import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def init_database():
    print("Connecting to database...")
    try:
        # Aiven specific connection settings
        conn = mysql.connector.connect(
            host=os.environ.get('DB_HOST'),
            port=int(os.environ.get('DB_PORT', 3306)),
            user=os.environ.get('DB_USER'),
            password=os.environ.get('DB_PASS'),
            database=os.environ.get('DB_NAME'),
            ssl_verify_identity=False,
            ssl_ca=''
        )
        cursor = conn.cursor()
        
        print("Connected! Reading schema.sql...")
        with open('schema.sql', 'r') as file:
            sql_script = file.read()
            
        # Split by semicolon and remove the CREATE DATABASE and USE commands as Aiven handles DB creation
        commands = sql_script.split(';')
        
        for command in commands:
            cmd = command.strip()
            # Skip empty commands and local DB creation commands
            if not cmd or cmd.upper().startswith("CREATE DATABASE") or cmd.upper().startswith("USE "):
                continue
                
            print(f"Executing: {cmd[:50]}...")
            cursor.execute(cmd)
            
        conn.commit()
        print("\n✅ All tables created successfully!")
        
    except mysql.connector.Error as err:
        print(f"\n❌ Database Error: {err}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn.is_connected():
            conn.close()

if __name__ == "__main__":
    init_database()
