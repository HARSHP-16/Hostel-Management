import os
import pymysql
import pymysql.cursors
from urllib.parse import urlparse

def get_db_connection():
    db_url = os.getenv("MYSQL_URL")
    if not db_url:
        # Fallback for local development if MYSQL_URL is not set
        return pymysql.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "hostel_management"),
            ssl={"ssl": {}} if os.getenv("DB_SSL") == "true" else None,
            cursorclass=pymysql.cursors.DictCursor
        )
        
    url = urlparse(db_url)
    return pymysql.connect(
        host=url.hostname,
        user=url.username,
        password=url.password,
        database=url.path[1:],
        port=url.port,
        ssl={"ssl": {}},  # ✅ REQUIRED FOR AIVEN/AZURE
        cursorclass=pymysql.cursors.DictCursor
    )