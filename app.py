from flask import Flask, render_template, request, session, redirect, url_for, flash
import os
from db import get_db_connection
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from auth_utils import login_required, warden_required, student_required

app = Flask(__name__)
app.secret_key = os.urandom(24)

@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'warden':
            return redirect(url_for('warden_dashboard'))
        return redirect(url_for('student_dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        role = request.form.get('role')
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        
        hashed_password = generate_password_hash(password)
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        try:
            if role == 'student':
                gender = request.form.get('gender')
                course = request.form.get('course')
                address = request.form.get('address')
                
                cursor.execute(
                    "INSERT INTO Student (Name, Gender, Phone, Email, Password, Address, Course) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (name, gender, phone, email, hashed_password, address, course)
                )
            else:
                # For warden, we insert without a Hostel_ID initially, the admin can assign this later
                cursor.execute(
                    "INSERT INTO Warden (Name, Phone, Email, Password) VALUES (%s, %s, %s, %s)",
                    (name, phone, email, hashed_password)
                )
            
            conn.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except mysql.connector.Error as err:
            flash(f"Error: {err}", 'error')
        finally:
            cursor.close()
            conn.close()
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form.get('role')
        email = request.form.get('email')
        password = request.form.get('password')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM Student WHERE Email = %s" if role == 'student' else "SELECT * FROM Warden WHERE Email = %s"
        cursor.execute(query, (email,))
        user = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if user and check_password_hash(user['Password'], password):
            session['user_id'] = user['Student_ID'] if role == 'student' else user['Warden_ID']
            session['role'] = role
            session['name'] = user['Name']
            flash(f"Welcome back, {user['Name']}!", 'success')
            
            if role == 'student':
                return redirect(url_for('student_dashboard'))
            else:
                return redirect(url_for('warden_dashboard'))
        else:
            flash('Invalid email or password.', 'error')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/student/dashboard')
@login_required
@student_required
def student_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get student room details
    cursor.execute("""
        SELECT r.Room_Number, h.Hostel_Name 
        FROM Allocation a 
        JOIN Room r ON a.Room_ID = r.Room_ID 
        JOIN Hostel h ON r.Hostel_ID = h.Hostel_ID
        WHERE a.Student_ID = %s
    """, (session['user_id'],))
    allocation = cursor.fetchone()
    
    # Get stats
    stats = {}
    cursor.execute("SELECT COUNT(*) as count FROM Complaint WHERE Student_ID = %s AND Status != 'Closed'", (session['user_id'],))
    stats['active_complaints'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT SUM(Amount) as total FROM Fees WHERE Student_ID = %s AND Payment_Status = 'Pending'", (session['user_id'],))
    res = cursor.fetchone()
    stats['pending_fees'] = res['total'] if res['total'] else 0.00
    
    cursor.execute("SELECT COUNT(*) as count FROM Laundry WHERE Student_ID = %s AND Status = 'Pending'", (session['user_id'],))
    stats['pending_laundry'] = cursor.fetchone()['count']
    
    cursor.close()
    conn.close()
    
    return render_template('student_dashboard.html', allocation=allocation, stats=stats)

@app.route('/warden/dashboard')
@login_required
@warden_required
def warden_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get high-level stats for warden
    stats = {}
    cursor.execute("SELECT COUNT(*) as count FROM Student")
    stats['students'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM Room")
    stats['rooms_total'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM Student_Leave WHERE Status = 'Pending'")
    stats['pending_leaves'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM Complaint WHERE Status != 'Closed'")
    stats['active_complaints'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM Laundry WHERE Status = 'Pending'")
    stats['pending_laundry'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM Maintenance WHERE Status != 'Completed'")
    stats['active_maintenance'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT SUM(Amount) as total FROM Fees WHERE Payment_Status = 'Pending'")
    res = cursor.fetchone()
    stats['pending_fees'] = res['total'] if res['total'] else 0.00
    
    cursor.close()
    conn.close()
    return render_template('warden_dashboard.html', stats=stats)

@app.route('/student/apply_leave', methods=['GET', 'POST'])
@login_required
@student_required
def apply_leave():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        leave_date = request.form.get('leave_date')
        return_date = request.form.get('return_date')
        reason = request.form.get('reason')
        
        try:
            cursor.execute(
                "INSERT INTO Student_Leave (Student_ID, Leave_Date, Return_Date, Reason) VALUES (%s, %s, %s, %s)",
                (session['user_id'], leave_date, return_date, reason)
            )
            conn.commit()
            flash('Leave request submitted successfully!', 'success')
            return redirect(url_for('apply_leave'))
        except mysql.connector.Error as err:
            flash(f"Database Error: {err}", 'error')
            
    # Fetch historical leaves
    cursor.execute("SELECT * FROM Student_Leave WHERE Student_ID = %s ORDER BY Leave_Date DESC", (session['user_id'],))
    leaves = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('apply_leave.html', leaves=leaves)

@app.route('/warden/manage_leaves')
@login_required
@warden_required
def manage_leaves():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # View capturing student info along with leave info, utilizing multiple joins (as expected in a DBMS project)
    query = """
        SELECT sl.*, s.Name as Student_Name, r.Room_Number
        FROM Student_Leave sl
        JOIN Student s ON sl.Student_ID = s.Student_ID
        LEFT JOIN Allocation a ON s.Student_ID = a.Student_ID
        LEFT JOIN Room r ON a.Room_ID = r.Room_ID
        ORDER BY sl.Leave_Date DESC
    """
    cursor.execute(query)
    leaves = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('manage_leaves.html', leaves=leaves)

@app.route('/warden/update_leave/<int:leave_id>', methods=['POST'])
@login_required
@warden_required
def update_leave_status(leave_id):
    status = request.form.get('status')
    
    if status not in ['Approved', 'Rejected']:
        flash('Invalid status update.', 'error')
        return redirect(url_for('manage_leaves'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("UPDATE Student_Leave SET Status = %s WHERE Leave_ID = %s", (status, leave_id))
        conn.commit()
        flash(f'Leave application {status.lower()} applied successfully.', 'success')
    except mysql.connector.Error as err:
        flash(f"Error: {err}", 'error')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('manage_leaves'))

@app.route('/warden/add_hostel', methods=['GET', 'POST'])
@login_required
@warden_required
def add_hostel():
    if request.method == 'POST':
        name = request.form.get('name')
        location = request.form.get('location')
        h_type = request.form.get('type')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO Hostel (Hostel_Name, Location, Type) VALUES (%s, %s, %s)", (name, location, h_type))
            conn.commit()
            flash('Hostel block added successfully!', 'success')
            return redirect(url_for('add_room'))
        except mysql.connector.Error as err:
            flash(f"Database Error: {err}", 'error')
        finally:
            cursor.close()
            conn.close()
            
    return render_template('add_hostel.html')

@app.route('/warden/rooms')
@login_required
@warden_required
def manage_rooms():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Complex query to get rooms alongside their current occupancy count via the Allocation table
    query = """
        SELECT r.Room_ID, r.Room_Number, r.Room_Type, r.Capacity, h.Hostel_Name,
               COUNT(a.Allocation_ID) as Occupied_Count
        FROM Room r
        JOIN Hostel h ON r.Hostel_ID = h.Hostel_ID
        LEFT JOIN Allocation a ON r.Room_ID = a.Room_ID
        GROUP BY r.Room_ID, r.Room_Number, r.Room_Type, r.Capacity, h.Hostel_Name
        ORDER BY h.Hostel_Name, r.Room_Number
    """
    cursor.execute(query)
    rooms = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('manage_rooms.html', rooms=rooms)

@app.route('/warden/add_room', methods=['GET', 'POST'])
@login_required
@warden_required
def add_room():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        hostel_id = request.form.get('hostel_id')
        room_number = request.form.get('room_number')
        room_type = request.form.get('room_type')
        capacity = request.form.get('capacity')
        
        try:
            cursor.execute(
                "INSERT INTO Room (Room_Number, Room_Type, Capacity, Hostel_ID) VALUES (%s, %s, %s, %s)",
                (room_number, room_type, capacity, hostel_id)
            )
            conn.commit()
            flash('Room added successfully!', 'success')
            return redirect(url_for('manage_rooms'))
        except mysql.connector.Error as err:
            flash(f"Database Error: {err}", 'error')
            
    cursor.execute("SELECT * FROM Hostel")
    hostels = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    if not hostels:
        flash('You must create a Hostel block first before adding rooms.', 'warning')
        return redirect(url_for('add_hostel'))
        
    return render_template('add_room.html', hostels=hostels)

@app.route('/warden/allocations')
@login_required
@warden_required
def allocations():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = """
        SELECT a.Allocation_ID, a.Allotment_Date,
               s.Name as Student_Name, s.Email, s.Course,
               r.Room_Number, h.Hostel_Name
        FROM Allocation a
        JOIN Student s ON a.Student_ID = s.Student_ID
        JOIN Room r ON a.Room_ID = r.Room_ID
        JOIN Hostel h ON r.Hostel_ID = h.Hostel_ID
        ORDER BY a.Allotment_Date DESC
    """
    cursor.execute(query)
    all_allocations = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('allocations.html', allocations=all_allocations)

@app.route('/warden/allocate_room', methods=['GET', 'POST'])
@login_required
@warden_required
def allocate_room():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        room_id = request.form.get('room_id')
        
        try:
            cursor.execute("INSERT INTO Allocation (Student_ID, Room_ID) VALUES (%s, %s)", (student_id, room_id))
            conn.commit()
            flash('Student successfully allocated to room!', 'success')
            return redirect(url_for('allocations'))
        except mysql.connector.Error as err:
            flash(f"Database Error: {err}", 'error')
            
    # Complex query #1: Find students who do NOT have an active allocation
    cursor.execute("""
        SELECT Student_ID, Name, Course 
        FROM Student 
        WHERE Student_ID NOT IN (SELECT Student_ID FROM Allocation)
    """)
    unallocated_students = cursor.fetchall()
    
    # Complex query #2: Find rooms that are NOT fully occupied
    cursor.execute("""
        SELECT r.Room_ID, r.Room_Number, r.Capacity, h.Hostel_Name,
               COUNT(a.Allocation_ID) as Occupied_Count
        FROM Room r
        JOIN Hostel h ON r.Hostel_ID = h.Hostel_ID
        LEFT JOIN Allocation a ON r.Room_ID = a.Room_ID
        GROUP BY r.Room_ID, r.Room_Number, r.Capacity, h.Hostel_Name
        HAVING Occupied_Count < r.Capacity
    """)
    available_rooms = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('allocate_room.html', unallocated_students=unallocated_students, available_rooms=available_rooms)

@app.route('/warden/deallocate/<int:allocation_id>', methods=['POST'])
@login_required
@warden_required
def deallocate_room(allocation_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM Allocation WHERE Allocation_ID = %s", (allocation_id,))
        conn.commit()
        flash('Student deallocated successfully.', 'success')
    except mysql.connector.Error as err:
        flash(f"Error: {err}", 'error')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('allocations'))

@app.route('/student/report_issue', methods=['GET', 'POST'])
@login_required
@student_required
def report_issue():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        c_type = request.form.get('complaint_type')
        desc = request.form.get('description')
        
        # We need the student's room_id to associate the complaint correctly
        cursor.execute("SELECT Room_ID FROM Allocation WHERE Student_ID = %s", (session['user_id'],))
        allocation = cursor.fetchone()
        room_id = allocation['Room_ID'] if allocation else None
        
        try:
            cursor.execute(
                "INSERT INTO Complaint (Student_ID, Room_ID, Complaint_Type, Description) VALUES (%s, %s, %s, %s)",
                (session['user_id'], room_id, c_type, desc)
            )
            conn.commit()
            flash('Issue reported successfully. The warden has been notified.', 'success')
            return redirect(url_for('report_issue'))
        except mysql.connector.Error as err:
            flash(f"Database Error: {err}", 'error')
            
    cursor.execute("SELECT * FROM Complaint WHERE Student_ID = %s ORDER BY Complaint_Date DESC", (session['user_id'],))
    complaints = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('report_issue.html', complaints=complaints)

@app.route('/warden/complaints')
@login_required
@warden_required
def manage_complaints():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = """
        SELECT c.*, s.Name as Student_Name, r.Room_Number 
        FROM Complaint c
        JOIN Student s ON c.Student_ID = s.Student_ID
        LEFT JOIN Room r ON c.Room_ID = r.Room_ID
        ORDER BY 
            CASE c.Status 
                WHEN 'Open' THEN 1 
                WHEN 'In Progress' THEN 2 
                WHEN 'Closed' THEN 3 
            END,
            c.Complaint_Date DESC
    """
    cursor.execute(query)
    complaints = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('manage_complaints.html', complaints=complaints)

@app.route('/warden/update_complaint/<int:complaint_id>', methods=['POST'])
@login_required
@warden_required
def update_complaint(complaint_id):
    status = request.form.get('status')
    if status not in ['Open', 'In Progress', 'Closed']:
        flash('Invalid status.', 'error')
        return redirect(url_for('manage_complaints'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE Complaint SET Status = %s WHERE Complaint_ID = %s", (status, complaint_id))
        conn.commit()
        flash('Complaint status updated successfully.', 'success')
    except mysql.connector.Error as err:
        flash(f"Error: {err}", 'error')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('manage_complaints'))

@app.route('/student/fees')
@login_required
@student_required
def student_fees():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT * FROM Fees WHERE Student_ID = %s ORDER BY Payment_Date DESC", (session['user_id'],))
    fees = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('student_fees.html', fees=fees)

@app.route('/student/pay_fees/<int:fee_id>', methods=['POST'])
@login_required
@student_required
def pay_fees(fee_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE Fees SET Payment_Status = 'Paid' WHERE Fee_ID = %s AND Student_ID = %s", (fee_id, session['user_id']))
        conn.commit()
        flash('Payment successful! Your dues are cleared.', 'success')
    except mysql.connector.Error as err:
        flash(f"Error processing payment: {err}", 'error')
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('student_fees'))

@app.route('/warden/fees')
@login_required
@warden_required
def manage_fees():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = """
        SELECT f.*, s.Name as Student_Name, s.Email, s.Course
        FROM Fees f
        JOIN Student s ON f.Student_ID = s.Student_ID
        ORDER BY f.Payment_Status ASC, f.Payment_Date DESC
    """
    cursor.execute(query)
    fees = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('warden_fees.html', fees=fees)

@app.route('/warden/issue_bill', methods=['GET', 'POST'])
@login_required
@warden_required
def issue_bill():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        amount = request.form.get('amount')
        due_date = request.form.get('due_date')
        
        try:
            cursor.execute(
                "INSERT INTO Fees (Student_ID, Amount, Payment_Date, Payment_Status) VALUES (%s, %s, %s, 'Pending')",
                (student_id, amount, due_date)
            )
            conn.commit()
            flash('Bill issued successfully!', 'success')
            return redirect(url_for('manage_fees'))
        except mysql.connector.Error as err:
            flash(f"Database Error: {err}", 'error')
            
    cursor.execute("SELECT Student_ID, Name, Course FROM Student ORDER BY Name")
    students = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('issue_bill.html', students=students)

@app.route('/student/laundry', methods=['GET', 'POST'])
@login_required
@student_required
def student_laundry():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        clothes_count = request.form.get('clothes_count')
        # Typical logic: calc charges, let's say 20 per cloth
        charges = int(clothes_count) * 20.00
        
        try:
            cursor.execute(
                "INSERT INTO Laundry (Student_ID, Clothes_Count, Charges, Status) VALUES (%s, %s, %s, 'Pending')",
                (session['user_id'], clothes_count, charges)
            )
            conn.commit()
            flash('Laundry request submitted successfully.', 'success')
            return redirect(url_for('student_laundry'))
        except mysql.connector.Error as err:
            flash(f"Database Error: {err}", 'error')
            
    cursor.execute("SELECT * FROM Laundry WHERE Student_ID = %s ORDER BY Laundry_Date DESC", (session['user_id'],))
    laundry_records = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('student_laundry.html', laundry_records=laundry_records)

@app.route('/warden/laundry')
@login_required
@warden_required
def manage_laundry():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    query = """
        SELECT l.*, s.Name as Student_Name, r.Room_Number
        FROM Laundry l
        JOIN Student s ON l.Student_ID = s.Student_ID
        LEFT JOIN Allocation a ON s.Student_ID = a.Student_ID
        LEFT JOIN Room r ON a.Room_ID = r.Room_ID
        ORDER BY l.Status ASC, l.Laundry_Date DESC
    """
    cursor.execute(query)
    laundry_requests = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('warden_laundry.html', requests=laundry_requests)

@app.route('/warden/update_laundry/<int:laundry_id>', methods=['POST'])
@login_required
@warden_required
def update_laundry(laundry_id):
    status = request.form.get('status')
    if status not in ['Pending', 'Completed']:
        flash('Invalid status.', 'error')
        return redirect(url_for('manage_laundry'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE Laundry SET Status = %s WHERE Laundry_ID = %s", (status, laundry_id))
        conn.commit()
        flash('Laundry status updated.', 'success')
    except mysql.connector.Error as err:
        flash(f"Error: {err}", 'error')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('manage_laundry'))

@app.route('/warden/maintenance', methods=['GET', 'POST'])
@login_required
@warden_required
def manage_maintenance():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        complaint_id = request.form.get('complaint_id')
        hostel_id = request.form.get('hostel_id')
        work_type = request.form.get('work_type')
        cost = request.form.get('cost')
        
        # Complaint_ID can be optional in some cases, let's allow it to be empty string -> None
        comp_id_val = complaint_id if complaint_id else None
        
        try:
            cursor.execute(
                "INSERT INTO Maintenance (Complaint_ID, Hostel_ID, Work_Type, Cost) VALUES (%s, %s, %s, %s)",
                (comp_id_val, hostel_id, work_type, cost)
            )
            conn.commit()
            flash('Maintenance task logged successfully.', 'success')
            return redirect(url_for('manage_maintenance'))
        except mysql.connector.Error as err:
            flash(f"Database Error: {err}", 'error')
            
    # Get lists for the dropdowns
    cursor.execute("SELECT Complaint_ID, Complaint_Type, Room_ID FROM Complaint WHERE Status != 'Closed'")
    active_complaints = cursor.fetchall()
    
    cursor.execute("SELECT Hostel_ID, Hostel_Name FROM Hostel")
    hostels = cursor.fetchall()
    
    # Get all maintenance records
    query = """
        SELECT m.*, h.Hostel_Name, c.Complaint_Type, r.Room_Number
        FROM Maintenance m
        JOIN Hostel h ON m.Hostel_ID = h.Hostel_ID
        LEFT JOIN Complaint c ON m.Complaint_ID = c.Complaint_ID
        LEFT JOIN Room r ON c.Room_ID = r.Room_ID
        ORDER BY 
            CASE m.Status 
                WHEN 'Pending' THEN 1 
                WHEN 'In Progress' THEN 2 
                WHEN 'Completed' THEN 3 
            END,
            m.Maintenance_Date DESC
    """
    cursor.execute(query)
    maintenance_tasks = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('manage_maintenance.html', tasks=maintenance_tasks, complaints=active_complaints, hostels=hostels)

@app.route('/warden/update_maintenance/<int:maintenance_id>', methods=['POST'])
@login_required
@warden_required
def update_maintenance(maintenance_id):
    status = request.form.get('status')
    if status not in ['Pending', 'In Progress', 'Completed']:
        flash('Invalid status.', 'error')
        return redirect(url_for('manage_maintenance'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE Maintenance SET Status = %s WHERE Maintenance_ID = %s", (status, maintenance_id))
        conn.commit()
        flash('Maintenance status updated.', 'success')
    except mysql.connector.Error as err:
        flash(f"Error: {err}", 'error')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('manage_maintenance'))

if __name__ == '__main__':
    app.run(debug=True)
