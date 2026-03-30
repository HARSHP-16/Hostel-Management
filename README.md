# 🏨 Hostel Management System

A comprehensive web-based hostel management system built with Python Flask and MySQL, designed to streamline hostel operations including student registration, room allocation, and hostel management.

## 🌐 Live Demo
https://hostel-management.azurewebsites.net/

## ✨ Features
- 👥 Student registration and management
- 🛏️ Room allocation and tracking
- 👔 Hostel staff management
- 💰 Fee collection and billing
- 📢 Complaint management system
- 📊 Real-time occupancy tracking
- 📈 Hostel analytics and reports

## 📋 Prerequisites
- Python 3.8 or higher
- MySQL 5.7 or higher
- pip (Python package manager)
- Git

## 🚀 Getting Started

### 1. Clone the Repository
```bash
git clone https://github.com/HARSHP-16/DBMS-project.git
cd hostel-management-system

2. Create Virtual Environment
bash
python -m venv venv
3. Activate Virtual Environment
Windows:

bash
venv\Scripts\activate
Mac/Linux:

bash
source venv/bin/activate
4. Install Dependencies
bash
pip install -r requirements.txt
5. Configure Environment Variables
Create a .env file in the project root directory:

env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=yourpassword
DB_NAME=hostel_db
6. Initialize Database
bash
python init_db.py
7. Run the Application
bash
python app.py
The application will be available at http://localhost:5000

📁 Project Structure
Code
hostel-management-system/
├── app.py                 # Main application file
├── init_db.py            # Database initialization script
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables (create this)
├── .gitignore           # Git ignore file
├── templates/           # HTML templates
├── static/              # Static files (CSS, JS, images)
│   ├── css/
│   ├── js/
│   └── images/
└── README.md           # This file
🛠️ Technologies Used
Backend Framework: Python Flask
Database: MySQL
Frontend: HTML5, CSS3, JavaScript
Deployment: Microsoft Azure App Services
Version Control: Git & GitHub
🔐 Security Notes
Never commit .env file to the repository
Use strong database passwords in production
Implement user authentication and authorization
Validate all user inputs
📞 Support & Contact
For issues and questions, please open a GitHub issue or contact the author.

📝 License
This project is licensed under the MIT License - see the LICENSE file for details.

👨‍💻 Author
HARSHP-16

🤝 Contributing
Contributions are welcome! To contribute:

Fork the repository
Create a feature branch (git checkout -b feature/AmazingFeature)
Commit your changes (git commit -m 'Add some AmazingFeature')
Push to the branch (git push origin feature/AmazingFeature)
Open a Pull Request
