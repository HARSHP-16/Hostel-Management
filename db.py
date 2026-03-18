import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv() # Load variables from .env file if present

def get_db_connection():
    config = {
        'host': os.environ.get('DB_HOST', 'localhost'),
        'user': os.environ.get('DB_USER', 'root'),
        'password': os.environ.get('DB_PASS', ''), # Default empty, update if needed
        'database': os.environ.get('DB_NAME', 'hostel_management'),
        'raise_on_warnings': True,
        'ssl_verify_identity': False,
        'ssl_ca': ''
    }
    
    return mysql.connector.connect(**config)
