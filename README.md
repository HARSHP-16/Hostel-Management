# 🏨 Hostel Management System

🌐 **Live Demo:** https://hostel-management.azurewebsites.net/  
💻 **GitHub Repository:** https://github.com/HARSHP-16/DBMS-project.git

---

## 📌 Overview
A full-stack **Hostel Management System** built using **Python, Flask, and MySQL** to automate and streamline hostel operations.

The system provides **role-based dashboards** for **Students** and **Wardens**, enabling efficient management of rooms, complaints, fees, and services.

---

## ✨ Features

### 👨‍🎓 Student Portal
- 📊 Dashboard with complaints, fees, and laundry status  
- 🏠 View room allocation details  
- 📝 Apply for leave & track status  
- 🛠️ Raise maintenance complaints  
- 💳 Pay fees & download PDF receipts  
- 👕 Laundry request system  
- 🔔 Real-time notifications  

---

### 🧑‍💼 Warden Portal
- 📈 Dashboard with analytics & occupancy insights  
- 🏢 Manage hostel blocks and rooms  
- 🛏️ Allocate / deallocate rooms  
- ✅ Approve or reject leave requests  
- 🛠️ Track and resolve complaints  
- 💰 Issue and monitor fees  
- 👕 Manage laundry requests  

---

## 🛠️ Tech Stack

| Layer        | Technology |
|-------------|-----------|
| Backend     | Python, Flask |
| Database    | MySQL |
| Driver      | PyMySQL |
| Frontend    | HTML, CSS, JavaScript, Jinja2 |
| PDF         | FPDF2 |
| Deployment  | Microsoft Azure |

---

## 🧱 System Architecture

```
User (Browser)
      ↓
Frontend (HTML, CSS, JS)
      ↓
Flask Backend (Routing & Logic)
      ↓
MySQL Database
```

---

## ⚙️ Installation & Setup

### 1️⃣ Clone Repository
```bash
git clone https://github.com/your-username/your-repo.git
cd hostel-management-system
```

### 2️⃣ Create Virtual Environment
```bash
python -m venv venv
```

### 3️⃣ Activate Environment
```bash
# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 4️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

### 5️⃣ Configure Environment Variables

Create a `.env` file in root directory:

```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=yourpassword
DB_NAME=hostel_db
```

### 6️⃣ Initialize Database
```bash
python init_db.py
```

### 7️⃣ Run Application
```bash
python app.py
```

Open in browser:
👉 http://127.0.0.1:5000/

---

## 📊 Database Concepts Used
- SQL JOIN operations  
- GROUP BY & aggregate functions  
- Relational schema design  
- CRUD operations  

---

## 📸 Screenshots

> *(Add your project screenshots here)*

- Student Dashboard  
- Warden Dashboard  
- Fee Management  
- Complaint System  

---

## 🚀 Future Improvements
- 🔐 JWT Authentication & password hashing  
- 📱 Mobile-responsive UI  
- 📊 Advanced analytics dashboard  
- 🔔 Email/SMS notifications  
- 🐳 Docker containerization  

---

## 🧠 Learning Outcomes
- Built full-stack web application using Flask  
- Designed relational database schema  
- Implemented real-world DBMS concepts  
- Deployed application on Azure  

---

## 🏆 Project Context
Developed as part of a **Database Management System (DBMS)** academic project.

---

## 👨‍💻 Author
**Your Name**  
- LinkedIn: https://www.linkedin.com/in/harsh-palkrutwar 
- GitHub: https://github.com/HARSHP-16  

---

## ⭐ Support
If you like this project, give it a ⭐ on GitHub!
