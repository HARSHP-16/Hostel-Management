CREATE DATABASE IF NOT EXISTS hostel_management;
USE hostel_management;

-- 2. Hostel (created first because it's referenced by others)
CREATE TABLE IF NOT EXISTS Hostel (
    Hostel_ID INT AUTO_INCREMENT PRIMARY KEY,
    Hostel_Name VARCHAR(100) NOT NULL,
    Location VARCHAR(255),
    Type ENUM('Boys', 'Girls') NOT NULL
);

-- 6. Warden (needs Hostel_ID)
CREATE TABLE IF NOT EXISTS Warden (
    Warden_ID INT AUTO_INCREMENT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    Phone VARCHAR(15),
    Email VARCHAR(100) UNIQUE NOT NULL,
    Password VARCHAR(255) NOT NULL, -- Added for login
    Hostel_ID INT,
    FOREIGN KEY (Hostel_ID) REFERENCES Hostel(Hostel_ID) ON DELETE SET NULL
);

-- 3. Room (needs Hostel_ID)
CREATE TABLE IF NOT EXISTS Room (
    Room_ID INT AUTO_INCREMENT PRIMARY KEY,
    Room_Number VARCHAR(20) NOT NULL,
    Room_Type VARCHAR(50),
    Capacity INT NOT NULL,
    Hostel_ID INT NOT NULL,
    FOREIGN KEY (Hostel_ID) REFERENCES Hostel(Hostel_ID) ON DELETE CASCADE
);

-- 1. Student
CREATE TABLE IF NOT EXISTS Student (
    Student_ID INT AUTO_INCREMENT PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    Gender ENUM('Male', 'Female', 'Other'),
    Phone VARCHAR(15),
    Email VARCHAR(100) UNIQUE NOT NULL,
    Password VARCHAR(255) NOT NULL, -- Added for login
    Address TEXT,
    Course VARCHAR(100)
);

-- 4. Allocation (links Student and Room)
CREATE TABLE IF NOT EXISTS Allocation (
    Allocation_ID INT AUTO_INCREMENT PRIMARY KEY,
    Student_ID INT NOT NULL,
    Room_ID INT NOT NULL,
    Allotment_Date DATE DEFAULT (CURRENT_DATE),
    FOREIGN KEY (Student_ID) REFERENCES Student(Student_ID) ON DELETE CASCADE,
    FOREIGN KEY (Room_ID) REFERENCES Room(Room_ID) ON DELETE CASCADE
);

-- 5. Fees (links to Student)
CREATE TABLE IF NOT EXISTS Fees (
    Fee_ID INT AUTO_INCREMENT PRIMARY KEY,
    Student_ID INT NOT NULL,
    Amount DECIMAL(10, 2) NOT NULL,
    Payment_Date DATE,
    Payment_Status ENUM('Pending', 'Paid', 'Overdue') DEFAULT 'Pending',
    FOREIGN KEY (Student_ID) REFERENCES Student(Student_ID) ON DELETE CASCADE
);

-- 7. Leave (links to Student)
CREATE TABLE IF NOT EXISTS Student_Leave (
    Leave_ID INT AUTO_INCREMENT PRIMARY KEY,
    Student_ID INT NOT NULL,
    Leave_Date DATE NOT NULL,
    Return_Date DATE NOT NULL,
    Reason TEXT,
    Status ENUM('Pending', 'Approved', 'Rejected') DEFAULT 'Pending',
    FOREIGN KEY (Student_ID) REFERENCES Student(Student_ID) ON DELETE CASCADE
);

-- 8. Laundry (links to Student)
CREATE TABLE IF NOT EXISTS Laundry (
    Laundry_ID INT AUTO_INCREMENT PRIMARY KEY,
    Student_ID INT NOT NULL,
    Clothes_Count INT NOT NULL,
    Laundry_Date DATE DEFAULT (CURRENT_DATE),
    Charges DECIMAL(10, 2),
    Status ENUM('Pending', 'Completed') DEFAULT 'Pending',
    FOREIGN KEY (Student_ID) REFERENCES Student(Student_ID) ON DELETE CASCADE
);

-- 9. Complaint (links to Student and Room)
CREATE TABLE IF NOT EXISTS Complaint (
    Complaint_ID INT AUTO_INCREMENT PRIMARY KEY,
    Student_ID INT NOT NULL,
    Room_ID INT,
    Complaint_Date DATE DEFAULT (CURRENT_DATE),
    Complaint_Type VARCHAR(100),
    Description TEXT,
    Status ENUM('Open', 'In Progress', 'Closed') DEFAULT 'Open',
    FOREIGN KEY (Student_ID) REFERENCES Student(Student_ID) ON DELETE CASCADE,
    FOREIGN KEY (Room_ID) REFERENCES Room(Room_ID) ON DELETE SET NULL
);

-- 10. Maintenance (links to Complaint and Hostel)
CREATE TABLE IF NOT EXISTS Maintenance (
    Maintenance_ID INT AUTO_INCREMENT PRIMARY KEY,
    Complaint_ID INT,
    Hostel_ID INT NOT NULL,
    Maintenance_Date DATE DEFAULT (CURRENT_DATE),
    Work_Type VARCHAR(100),
    Cost DECIMAL(10, 2),
    Status ENUM('Pending', 'In Progress', 'Completed') DEFAULT 'Pending',
    FOREIGN KEY (Complaint_ID) REFERENCES Complaint(Complaint_ID) ON DELETE SET NULL,
    FOREIGN KEY (Hostel_ID) REFERENCES Hostel(Hostel_ID) ON DELETE CASCADE
);

use hostel_management;
select * from warden;
