🌐 **Live Demo:** https://your-azure-app-url.azurewebsites.net

# Clone repository
git clone https://github.com/HARSHP-16/DBMS-project.git

# Navigate to project
cd hostel-management-system

# Create virtual environment
python -m venv venv

# Activate environment
venv\Scripts\activate   # Windows
source venv/bin/activate # Mac/Linux

# Install dependencies
pip install -r requirements.txt

# Setup environment variables (.env)
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=yourpassword
DB_NAME=hostel_db

# Initialize database
python init_db.py

# Run application
python app.py
