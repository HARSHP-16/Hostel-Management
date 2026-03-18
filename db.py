import mysql.connector
import os

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),  # ✅ FIXED
        database=os.getenv("DB_NAME"),
        ssl_disabled=False  # ✅ REQUIRED for Aiven
    )