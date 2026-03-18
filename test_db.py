import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

try:
    conn = mysql.connector.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASS', ''),
        database=os.environ.get('DB_NAME', 'hostel_management')
    )
    print("SUCCESS: Connected to database in test script!")
    conn.close()
except Exception as e:
    print(f"ERROR: {e}")
