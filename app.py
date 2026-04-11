import logging
import os
import re
import io
from datetime import timedelta

from flask import Flask, render_template, request, session, redirect, url_for, flash, send_file
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql
import pymysql.cursors
from fpdf import FPDF

from db import get_db_connection
from auth_utils import login_required, warden_required, student_required, admin_required

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ─── Application ──────────────────────────────────────────────────────────────
app = Flask(__name__)

_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    import warnings
    warnings.warn(
        "SECRET_KEY environment variable is not set. Using a random ephemeral key — "
        "sessions will be invalidated on every restart and will not work across "
        "multiple workers. Set SECRET_KEY in your environment for production.",
        RuntimeWarning,
        stacklevel=1,
    )
    _secret_key = os.urandom(24)

app.config.update(
    SECRET_KEY=_secret_key,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    WTF_CSRF_TIME_LIMIT=3600,
)

# ─── CSRF Protection ──────────────────────────────────────────────────────────
csrf = CSRFProtect(app)

# ─── Rate Limiting ────────────────────────────────────────────────────────────
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

# ─── Security Headers ─────────────────────────────────────────────────────────
@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    if app.config.get("SESSION_COOKIE_SECURE"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ─── Helpers ──────────────────────────────────────────────────────────────────
def add_notification(user_id, role, message):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO Notification (User_ID, Role, Message) VALUES (%s, %s, %s)",
            (user_id, role, message),
        )
        conn.commit()
    except pymysql.Error as err:
        logger.error("Error adding notification: %s", err)
    finally:
        cursor.close()
        conn.close()


@app.context_processor
def inject_notifications():
    if "user_id" in session and "role" in session:
        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        try:
            cursor.execute(
                "SELECT * FROM Notification WHERE User_ID = %s AND Role = %s "
                "ORDER BY Timestamp DESC LIMIT 5",
                (session["user_id"], session["role"]),
            )
            notifications = cursor.fetchall()
            cursor.execute(
                "SELECT COUNT(*) as count FROM Notification "
                "WHERE User_ID = %s AND Role = %s AND Is_Read = FALSE",
                (session["user_id"], session["role"]),
            )
            count_res = cursor.fetchone()
            unread_count = count_res["count"] if count_res else 0
            return dict(notifications=notifications, unread_notif_count=unread_count)
        except pymysql.Error as err:
            logger.error("Error fetching notifications: %s", err)
            return dict(notifications=[], unread_notif_count=0)
        finally:
            cursor.close()
            conn.close()
    return dict(notifications=[], unread_notif_count=0)


# ─── Notification endpoint — uses GET so that CSRF is not required ─────────────
@app.route("/notifications/read/<int:notif_id>", methods=["GET"])
@login_required
def mark_notification_read(notif_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE Notification SET Is_Read = TRUE "
            "WHERE Notification_ID = %s AND User_ID = %s AND Role = %s",
            (notif_id, session["user_id"], session["role"]),
        )
        conn.commit()
        return {"success": True}
    except pymysql.Error:
        return {"success": False}, 500
    finally:
        cursor.close()
        conn.close()


# ─── Public Routes ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if "user_id" in session:
        role = session.get("role")
        if role == "warden":
            return redirect(url_for("warden_dashboard"))
        elif role == "admin":
            return redirect(url_for("admin_dashboard"))
        return redirect(url_for("student_dashboard"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("15 per minute", methods=["POST"], error_message="Too many login attempts. Please wait a minute.")
def login():
    if request.method == "POST":
        role = request.form.get("role", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if role not in ("student", "warden", "admin"):
            flash("Invalid login role.", "error")
            return render_template("login.html")

        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)

        if role == "student":
            query = "SELECT * FROM Student WHERE Email = %s"
            id_field = "Student_ID"
        elif role == "warden":
            query = "SELECT * FROM Warden WHERE Email = %s"
            id_field = "Warden_ID"
        else:
            query = "SELECT * FROM Admin WHERE Email = %s"
            id_field = "Admin_ID"

        try:
            cursor.execute(query, (email,))
            user = cursor.fetchone()
        except pymysql.Error as err:
            logger.error("Login DB error: %s", err)
            user = None
        finally:
            cursor.close()
            conn.close()

        if user and check_password_hash(user["Password"], password):
            session.clear()
            session.permanent = True
            session["user_id"] = user[id_field]
            session["role"] = role
            session["name"] = user.get("Name", "Administrator")
            if role == "warden":
                session["hostel_id"] = user.get("Hostel_ID")
            flash(f"Welcome back, {session['name']}!", "success")
            if role == "admin":
                return redirect(url_for("admin_dashboard"))
            elif role == "warden":
                return redirect(url_for("warden_dashboard"))
            else:
                return redirect(url_for("student_dashboard"))
        else:
            flash("Invalid email or password.", "error")

    return render_template("login.html")


@app.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    # GET requests (e.g. direct navigation or old bookmarks) redirect without logging out.
    if request.method == "GET":
        return redirect(url_for("index"))
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# ─── Student Routes ───────────────────────────────────────────────────────────
@app.route("/student/dashboard")
@login_required
@student_required
def student_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    cursor.execute(
        """
        SELECT r.Room_Number, h.Hostel_Name
        FROM Allocation a
        JOIN Room r ON a.Room_ID = r.Room_ID
        JOIN Hostel h ON r.Hostel_ID = h.Hostel_ID
        WHERE a.Student_ID = %s
        """,
        (session["user_id"],),
    )
    allocation = cursor.fetchone()

    stats = {}
    cursor.execute(
        "SELECT COUNT(*) as count FROM Complaint WHERE Student_ID = %s AND Status != 'Closed'",
        (session["user_id"],),
    )
    stats["active_complaints"] = cursor.fetchone()["count"]

    cursor.execute(
        "SELECT SUM(Amount) as total FROM Fees WHERE Student_ID = %s AND Payment_Status = 'Pending'",
        (session["user_id"],),
    )
    res = cursor.fetchone()
    stats["pending_fees"] = res["total"] if res and res["total"] else 0.00

    cursor.execute(
        "SELECT COUNT(*) as count FROM Laundry WHERE Student_ID = %s AND Status = 'Pending'",
        (session["user_id"],),
    )
    stats["pending_laundry"] = cursor.fetchone()["count"]

    cursor.close()
    conn.close()
    return render_template("student_dashboard.html", allocation=allocation, stats=stats)


@app.route("/student/profile", methods=["GET", "POST"])
@login_required
@student_required
def student_profile():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        bio = request.form.get("bio", "").strip()
        emergency_contact = request.form.get("emergency_contact", "").strip()

        # Basic length validation
        if len(phone) > 15:
            flash("Phone number is too long.", "error")
            return redirect(url_for("student_profile"))
        if len(emergency_contact) > 15:
            flash("Emergency contact number is too long.", "error")
            return redirect(url_for("student_profile"))

        try:
            cursor.execute(
                "UPDATE Student SET Phone=%s, Address=%s, Bio=%s, Emergency_Contact=%s "
                "WHERE Student_ID=%s",
                (phone, address, bio, emergency_contact, session["user_id"]),
            )
            conn.commit()
            flash("Profile updated successfully!", "success")
            return redirect(url_for("student_profile"))
        except pymysql.Error as err:
            logger.error("Profile update error: %s", err)
            flash("An error occurred while updating your profile. Please try again.", "error")

    cursor.execute(
        "SELECT * FROM Student WHERE Student_ID = %s", (session["user_id"],)
    )
    student = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template("student_profile.html", student=student)


@app.route("/student/change_password", methods=["GET", "POST"])
@login_required
@student_required
def student_change_password():
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if len(new_pw) < 8:
            flash("New password must be at least 8 characters.", "error")
            return redirect(url_for("student_change_password"))
        if new_pw != confirm_pw:
            flash("New passwords do not match.", "error")
            return redirect(url_for("student_change_password"))

        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        try:
            cursor.execute(
                "SELECT Password FROM Student WHERE Student_ID = %s", (session["user_id"],)
            )
            student = cursor.fetchone()
            if not student or not check_password_hash(student["Password"], current_pw):
                flash("Current password is incorrect.", "error")
                return redirect(url_for("student_change_password"))
            cursor.execute(
                "UPDATE Student SET Password = %s WHERE Student_ID = %s",
                (generate_password_hash(new_pw), session["user_id"]),
            )
            conn.commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("student_dashboard"))
        except pymysql.Error as err:
            logger.error("Password change error: %s", err)
            flash("An error occurred. Please try again.", "error")
        finally:
            cursor.close()
            conn.close()

    return render_template("change_password.html", role="student")


@app.route("/student/apply_leave", methods=["GET", "POST"])
@login_required
@student_required
def apply_leave():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    if request.method == "POST":
        leave_date = request.form.get("leave_date", "").strip()
        return_date = request.form.get("return_date", "").strip()
        reason = request.form.get("reason", "").strip()

        # Validate date format and logic
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        if not date_pattern.match(leave_date) or not date_pattern.match(return_date):
            flash("Invalid date format.", "error")
            return redirect(url_for("apply_leave"))
        if return_date < leave_date:
            flash("Return date must be on or after the leave date.", "error")
            return redirect(url_for("apply_leave"))
        if not reason:
            flash("Please provide a reason for the leave.", "error")
            return redirect(url_for("apply_leave"))

        try:
            cursor.execute(
                "INSERT INTO Student_Leave (Student_ID, Leave_Date, Return_Date, Reason) "
                "VALUES (%s, %s, %s, %s)",
                (session["user_id"], leave_date, return_date, reason),
            )
            conn.commit()
            flash("Leave request submitted successfully!", "success")
            return redirect(url_for("apply_leave"))
        except pymysql.Error as err:
            logger.error("Leave application error: %s", err)
            flash("An error occurred while submitting your request. Please try again.", "error")

    cursor.execute(
        "SELECT * FROM Student_Leave WHERE Student_ID = %s ORDER BY Leave_Date DESC",
        (session["user_id"],),
    )
    leaves = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("apply_leave.html", leaves=leaves)


@app.route("/student/report_issue", methods=["GET", "POST"])
@login_required
@student_required
def report_issue():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    allowed_types = {"Electrical", "Plumbing", "Carpentry", "Cleanliness", "Internet", "Other"}

    if request.method == "POST":
        c_type = request.form.get("complaint_type", "").strip()
        desc = request.form.get("description", "").strip()

        if c_type not in allowed_types:
            flash("Invalid complaint type.", "error")
            return redirect(url_for("report_issue"))
        if not desc:
            flash("Please provide a description.", "error")
            return redirect(url_for("report_issue"))

        cursor.execute(
            "SELECT Room_ID FROM Allocation WHERE Student_ID = %s", (session["user_id"],)
        )
        allocation = cursor.fetchone()
        room_id = allocation["Room_ID"] if allocation else None

        try:
            cursor.execute(
                "INSERT INTO Complaint (Student_ID, Room_ID, Complaint_Type, Description) "
                "VALUES (%s, %s, %s, %s)",
                (session["user_id"], room_id, c_type, desc),
            )
            conn.commit()
            flash("Issue reported successfully. The warden has been notified.", "success")
            return redirect(url_for("report_issue"))
        except pymysql.Error as err:
            logger.error("Complaint submission error: %s", err)
            flash("An error occurred while submitting your complaint. Please try again.", "error")

    cursor.execute(
        "SELECT * FROM Complaint WHERE Student_ID = %s ORDER BY Complaint_Date DESC",
        (session["user_id"],),
    )
    complaints = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("report_issue.html", complaints=complaints)


@app.route("/student/fees")
@login_required
@student_required
def student_fees():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute(
        "SELECT * FROM Fees WHERE Student_ID = %s ORDER BY Payment_Date DESC",
        (session["user_id"],),
    )
    fees = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("student_fees.html", fees=fees)


@app.route("/student/pay_fees/confirm/<int:fee_id>", methods=["GET"])
@login_required
@student_required
def confirm_payment(fee_id):
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        cursor.execute(
            "SELECT f.*, s.Name FROM Fees f "
            "JOIN Student s ON f.Student_ID = s.Student_ID "
            "WHERE Fee_ID = %s AND f.Student_ID = %s",
            (fee_id, session["user_id"]),
        )
        fee = cursor.fetchone()
        if not fee:
            flash("Fee record not found.", "error")
            return redirect(url_for("student_fees"))
        if fee["Payment_Status"] == "Paid":
            flash("This fee is already paid.", "info")
            return redirect(url_for("student_fees"))
    except pymysql.Error as err:
        logger.error("Confirm payment error: %s", err)
        flash("An error occurred. Please try again.", "error")
        return redirect(url_for("student_fees"))
    finally:
        cursor.close()
        conn.close()
    return render_template("confirm_payment.html", fee=fee)


@app.route("/student/pay_fees/<int:fee_id>", methods=["POST"])
@login_required
@student_required
def pay_fees(fee_id):
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        # Re-validate that the fee is still unpaid before marking it paid
        cursor.execute(
            "SELECT Payment_Status FROM Fees WHERE Fee_ID = %s AND Student_ID = %s",
            (fee_id, session["user_id"]),
        )
        fee = cursor.fetchone()
        if not fee:
            flash("Fee record not found.", "error")
            return redirect(url_for("student_fees"))
        if fee["Payment_Status"] == "Paid":
            flash("This fee has already been paid.", "info")
            return redirect(url_for("student_fees"))

        cursor.execute(
            "UPDATE Fees SET Payment_Status = 'Paid' WHERE Fee_ID = %s AND Student_ID = %s",
            (fee_id, session["user_id"]),
        )
        conn.commit()
        flash("Payment successful! Your dues are cleared.", "success")
    except pymysql.Error as err:
        logger.error("Fee payment error: %s", err)
        flash("An error occurred while processing the payment. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("student_fees"))


@app.route("/student/download_receipt/<int:fee_id>")
@login_required
@student_required
def download_receipt(fee_id):
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        cursor.execute(
            "SELECT f.Fee_ID, f.Amount, f.Payment_Date, s.Name "
            "FROM Fees f JOIN Student s ON f.Student_ID = s.Student_ID "
            "WHERE Fee_ID = %s AND f.Student_ID = %s AND Payment_Status = 'Paid'",
            (fee_id, session["user_id"]),
        )
        fee = cursor.fetchone()
        if not fee:
            flash("Receipt not found or fee not paid.", "error")
            return redirect(url_for("student_fees"))

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, align="C", text="Hostel Management System", new_y="NEXT", new_x="LMARGIN")
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, align="C", text="Official Fee Receipt", new_y="NEXT", new_x="LMARGIN")
        pdf.ln(10)
        pdf.cell(0, 10, text=f"Receipt No: H-FEE-{fee['Fee_ID']}", new_y="NEXT", new_x="LMARGIN")
        pdf.cell(0, 10, text=f"Student Name: {fee['Name']}", new_y="NEXT", new_x="LMARGIN")
        pdf.cell(0, 10, text=f"Payment Date: {fee['Payment_Date']}", new_y="NEXT", new_x="LMARGIN")
        pdf.cell(0, 10, text=f"Amount Settled: ${fee['Amount']:.2f}", new_y="NEXT", new_x="LMARGIN")
        pdf.ln(20)
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 10, align="C", text="This is a computer generated receipt.", new_y="NEXT", new_x="LMARGIN")

        pdf_bytes = io.BytesIO(pdf.output())
        return send_file(
            pdf_bytes,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"receipt_H-FEE-{fee['Fee_ID']}.pdf",
        )
    except pymysql.Error as err:
        logger.error("Receipt download error: %s", err)
        flash("An error occurred while generating the receipt.", "error")
        return redirect(url_for("student_fees"))
    finally:
        cursor.close()
        conn.close()


@app.route("/student/laundry", methods=["GET", "POST"])
@login_required
@student_required
def student_laundry():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    if request.method == "POST":
        raw_count = request.form.get("clothes_count", "").strip()
        try:
            clothes_count = int(raw_count)
        except (ValueError, TypeError):
            flash("Please enter a valid number of clothes.", "error")
            return redirect(url_for("student_laundry"))

        if clothes_count < 1 or clothes_count > 200:
            flash("Clothes count must be between 1 and 200.", "error")
            return redirect(url_for("student_laundry"))

        charges = clothes_count * 20.00

        try:
            cursor.execute(
                "INSERT INTO Laundry (Student_ID, Clothes_Count, Charges, Status) "
                "VALUES (%s, %s, %s, 'Pending')",
                (session["user_id"], clothes_count, charges),
            )
            conn.commit()
            flash("Laundry request submitted successfully.", "success")
            return redirect(url_for("student_laundry"))
        except pymysql.Error as err:
            logger.error("Laundry submission error: %s", err)
            flash("An error occurred. Please try again.", "error")

    cursor.execute(
        "SELECT * FROM Laundry WHERE Student_ID = %s ORDER BY Laundry_Date DESC",
        (session["user_id"],),
    )
    laundry_records = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("student_laundry.html", laundry_records=laundry_records)


# ─── Warden Routes ────────────────────────────────────────────────────────────
@app.route("/warden/dashboard")
@login_required
@warden_required
def warden_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    hostel_id = session.get("hostel_id")
    stats = {}

    if not hostel_id:
        flash("You are not assigned to any hostel. Contact the administrator.", "warning")
        stats = {k: 0 for k in [
            "students", "rooms_total", "pending_leaves",
            "active_complaints", "pending_laundry", "active_maintenance", "pending_fees"
        ]}
        cursor.close()
        conn.close()
        return render_template("warden_dashboard.html", stats=stats)

    cursor.execute(
        """
        SELECT COUNT(DISTINCT s.Student_ID) as count
        FROM Student s
        JOIN Allocation a ON s.Student_ID = a.Student_ID
        JOIN Room r ON a.Room_ID = r.Room_ID
        WHERE r.Hostel_ID = %s
        """,
        (hostel_id,),
    )
    stats["students"] = cursor.fetchone()["count"]

    cursor.execute(
        "SELECT COUNT(*) as count FROM Room WHERE Hostel_ID = %s", (hostel_id,)
    )
    stats["rooms_total"] = cursor.fetchone()["count"]

    cursor.execute(
        """
        SELECT COUNT(*) as count
        FROM Student_Leave sl
        JOIN Allocation a ON sl.Student_ID = a.Student_ID
        JOIN Room r ON a.Room_ID = r.Room_ID
        WHERE sl.Status = 'Pending' AND r.Hostel_ID = %s
        """,
        (hostel_id,),
    )
    stats["pending_leaves"] = cursor.fetchone()["count"]

    cursor.execute(
        """
        SELECT COUNT(*) as count FROM Complaint
        WHERE Status != 'Closed'
          AND Room_ID IN (SELECT Room_ID FROM Room WHERE Hostel_ID = %s)
        """,
        (hostel_id,),
    )
    stats["active_complaints"] = cursor.fetchone()["count"]

    cursor.execute(
        """
        SELECT COUNT(*) as count
        FROM Laundry l
        JOIN Allocation a ON l.Student_ID = a.Student_ID
        JOIN Room r ON a.Room_ID = r.Room_ID
        WHERE l.Status = 'Pending' AND r.Hostel_ID = %s
        """,
        (hostel_id,),
    )
    stats["pending_laundry"] = cursor.fetchone()["count"]

    cursor.execute(
        "SELECT COUNT(*) as count FROM Maintenance "
        "WHERE Status != 'Completed' AND Hostel_ID = %s",
        (hostel_id,),
    )
    stats["active_maintenance"] = cursor.fetchone()["count"]

    cursor.execute(
        """
        SELECT SUM(f.Amount) as total
        FROM Fees f
        JOIN Allocation a ON f.Student_ID = a.Student_ID
        JOIN Room r ON a.Room_ID = r.Room_ID
        WHERE f.Payment_Status = 'Pending' AND r.Hostel_ID = %s
        """,
        (hostel_id,),
    )
    res = cursor.fetchone()
    stats["pending_fees"] = res["total"] if res and res["total"] else 0.00

    cursor.close()
    conn.close()
    return render_template("warden_dashboard.html", stats=stats)


@app.route("/warden/analytics")
@login_required
@warden_required
def warden_analytics():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    hostel_id = session.get("hostel_id")

    if not hostel_id:
        cursor.close()
        conn.close()
        return render_template(
            "warden_analytics.html",
            chart_occupancy={"occupied": 0, "vacant": 0},
            chart_complaints={},
            chart_fees={},
            maint_cost=0.00,
            laundry_rev=0.00,
            fees_paid=0.00,
        )

    cursor.execute(
        "SELECT COUNT(*) as occupied FROM Allocation a "
        "JOIN Room r ON a.Room_ID = r.Room_ID WHERE r.Hostel_ID = %s",
        (hostel_id,),
    )
    occupied = cursor.fetchone()["occupied"]

    cursor.execute(
        "SELECT SUM(Capacity) as total_capacity FROM Room WHERE Hostel_ID = %s", (hostel_id,)
    )
    row = cursor.fetchone()
    total_capacity = row["total_capacity"] if row and row["total_capacity"] else 0
    chart_occupancy = {"occupied": occupied, "vacant": max(total_capacity - occupied, 0)}

    cursor.execute(
        """
        SELECT Status, COUNT(*) as count FROM Complaint
        WHERE Room_ID IN (SELECT Room_ID FROM Room WHERE Hostel_ID = %s)
        GROUP BY Status
        """,
        (hostel_id,),
    )
    chart_complaints = {row["Status"]: row["count"] for row in cursor.fetchall()}

    cursor.execute(
        """
        SELECT f.Payment_Status, COUNT(*) as count FROM Fees f
        JOIN Allocation a ON f.Student_ID = a.Student_ID
        JOIN Room r ON a.Room_ID = r.Room_ID
        WHERE r.Hostel_ID = %s
        GROUP BY f.Payment_Status
        """,
        (hostel_id,),
    )
    chart_fees = {row["Payment_Status"]: row["count"] for row in cursor.fetchall()}

    cursor.execute(
        "SELECT SUM(Cost) as total FROM Maintenance "
        "WHERE Status = 'Completed' AND Hostel_ID = %s",
        (hostel_id,),
    )
    r1 = cursor.fetchone()
    maint_cost = (r1.get("total") or 0.00) if r1 else 0.00

    cursor.execute(
        """
        SELECT SUM(l.Charges) as total FROM Laundry l
        JOIN Allocation a ON l.Student_ID = a.Student_ID
        JOIN Room r ON a.Room_ID = r.Room_ID
        WHERE l.Status = 'Completed' AND r.Hostel_ID = %s
        """,
        (hostel_id,),
    )
    r2 = cursor.fetchone()
    laundry_rev = (r2.get("total") or 0.00) if r2 else 0.00

    cursor.execute(
        """
        SELECT SUM(f.Amount) as total FROM Fees f
        JOIN Allocation a ON f.Student_ID = a.Student_ID
        JOIN Room r ON a.Room_ID = r.Room_ID
        WHERE f.Payment_Status = 'Paid' AND r.Hostel_ID = %s
        """,
        (hostel_id,),
    )
    r3 = cursor.fetchone()
    fees_paid = (r3.get("total") or 0.00) if r3 else 0.00

    cursor.close()
    conn.close()
    return render_template(
        "warden_analytics.html",
        chart_occupancy=chart_occupancy,
        chart_complaints=chart_complaints,
        chart_fees=chart_fees,
        maint_cost=maint_cost,
        laundry_rev=laundry_rev,
        fees_paid=fees_paid,
    )


@app.route("/warden/students")
@login_required
@warden_required
def warden_students():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    hostel_id = session.get("hostel_id")

    if not hostel_id:
        cursor.close()
        conn.close()
        return render_template("warden_students.html", students=[])

    cursor.execute(
        """
        SELECT s.Student_ID, s.Name, s.Email, s.Phone, s.Course,
               r.Room_Number, h.Hostel_Name
        FROM Student s
        JOIN Allocation a ON s.Student_ID = a.Student_ID
        JOIN Room r ON a.Room_ID = r.Room_ID
        JOIN Hostel h ON r.Hostel_ID = h.Hostel_ID
        WHERE r.Hostel_ID = %s
        ORDER BY s.Name ASC
        """,
        (hostel_id,),
    )
    students = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("warden_students.html", students=students)


@app.route("/warden/add_student", methods=["GET", "POST"])
@login_required
@warden_required
def warden_add_student():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        gender = request.form.get("gender", "").strip()
        course = request.form.get("course", "").strip()
        address = request.form.get("address", "").strip()
        raw_password = request.form.get("password", "")

        if len(raw_password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("warden_add_student.html")

        if gender not in ("Male", "Female", "Other"):
            flash("Invalid gender value.", "error")
            return render_template("warden_add_student.html")

        password = generate_password_hash(raw_password)
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO Student (Name, Gender, Phone, Email, Password, Address, Course) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (name, gender, phone, email, password, address, course),
            )
            conn.commit()
            flash("Student securely registered. Inform them of their login details.", "success")
            return redirect(url_for("warden_students"))
        except pymysql.Error as err:
            if err.args[0] == 1062:
                flash("Email already registered for a student.", "error")
            else:
                logger.error("Add student error: %s", err)
                flash("An error occurred while registering the student. Please try again.", "error")
        finally:
            cursor.close()
            conn.close()

    return render_template("warden_add_student.html")


@app.route("/warden/delete_student/<int:student_id>", methods=["POST"])
@login_required
@warden_required
def delete_student(student_id):
    hostel_id = session.get("hostel_id")
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # IDOR check: ensure the student belongs to warden's hostel
    if hostel_id:
        cursor.execute(
            """
            SELECT 1 FROM Allocation a
            JOIN Room r ON a.Room_ID = r.Room_ID
            WHERE a.Student_ID = %s AND r.Hostel_ID = %s
            """,
            (student_id, hostel_id),
        )
        if not cursor.fetchone():
            flash("Access denied: student not in your hostel.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("warden_students"))

    try:
        cursor.execute(
            "DELETE FROM Notification WHERE User_ID = %s AND Role = 'student'", (student_id,)
        )
        cursor.execute("DELETE FROM Student WHERE Student_ID = %s", (student_id,))
        conn.commit()
        flash("Student record and all associated history deleted successfully.", "info")
    except pymysql.Error as err:
        logger.error("Delete student error: %s", err)
        flash("An error occurred while deleting the student record.", "error")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("warden_students"))


@app.route("/warden/room/<int:room_id>")
@login_required
@warden_required
def warden_room(room_id):
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    hostel_id = session.get("hostel_id")

    cursor.execute(
        "SELECT r.*, h.Hostel_Name FROM Room r "
        "JOIN Hostel h ON r.Hostel_ID = h.Hostel_ID WHERE Room_ID = %s",
        (room_id,),
    )
    room = cursor.fetchone()

    if not room:
        flash("Room not found.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("manage_rooms"))

    # IDOR check: ensure the room belongs to warden's hostel
    if hostel_id and room["Hostel_ID"] != hostel_id:
        flash("Access denied: room not in your hostel.", "error")
        cursor.close()
        conn.close()
        return redirect(url_for("manage_rooms"))

    cursor.execute(
        "SELECT s.Student_ID, s.Name, s.Email, s.Phone "
        "FROM Allocation a JOIN Student s ON a.Student_ID = s.Student_ID "
        "WHERE a.Room_ID = %s",
        (room_id,),
    )
    occupants = cursor.fetchall()

    cursor.execute(
        "SELECT * FROM Complaint WHERE Room_ID = %s ORDER BY Complaint_Date DESC LIMIT 10",
        (room_id,),
    )
    complaints = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template("warden_room.html", room=room, occupants=occupants, complaints=complaints)


@app.route("/warden/change_password", methods=["GET", "POST"])
@login_required
@warden_required
def warden_change_password():
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if len(new_pw) < 8:
            flash("New password must be at least 8 characters.", "error")
            return redirect(url_for("warden_change_password"))
        if new_pw != confirm_pw:
            flash("New passwords do not match.", "error")
            return redirect(url_for("warden_change_password"))

        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        try:
            cursor.execute(
                "SELECT Password FROM Warden WHERE Warden_ID = %s", (session["user_id"],)
            )
            warden = cursor.fetchone()
            if not warden or not check_password_hash(warden["Password"], current_pw):
                flash("Current password is incorrect.", "error")
                return redirect(url_for("warden_change_password"))
            cursor.execute(
                "UPDATE Warden SET Password = %s WHERE Warden_ID = %s",
                (generate_password_hash(new_pw), session["user_id"]),
            )
            conn.commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("warden_dashboard"))
        except pymysql.Error as err:
            logger.error("Warden password change error: %s", err)
            flash("An error occurred. Please try again.", "error")
        finally:
            cursor.close()
            conn.close()

    return render_template("change_password.html", role="warden")


@app.route("/warden/manage_leaves")
@login_required
@warden_required
def manage_leaves():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    hostel_id = session.get("hostel_id")

    if not hostel_id:
        cursor.close()
        conn.close()
        return render_template("manage_leaves.html", leaves=[])

    cursor.execute(
        """
        SELECT sl.*, s.Name as Student_Name, r.Room_Number
        FROM Student_Leave sl
        JOIN Student s ON sl.Student_ID = s.Student_ID
        JOIN Allocation a ON s.Student_ID = a.Student_ID
        JOIN Room r ON a.Room_ID = r.Room_ID
        WHERE r.Hostel_ID = %s
        ORDER BY sl.Leave_Date DESC
        """,
        (hostel_id,),
    )
    leaves = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("manage_leaves.html", leaves=leaves)


@app.route("/warden/update_leave/<int:leave_id>", methods=["POST"])
@login_required
@warden_required
def update_leave_status(leave_id):
    status = request.form.get("status", "")
    if status not in ("Approved", "Rejected"):
        flash("Invalid status update.", "error")
        return redirect(url_for("manage_leaves"))

    hostel_id = session.get("hostel_id")
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # IDOR check
    if hostel_id:
        cursor.execute(
            """
            SELECT sl.Leave_ID FROM Student_Leave sl
            JOIN Allocation a ON sl.Student_ID = a.Student_ID
            JOIN Room r ON a.Room_ID = r.Room_ID
            WHERE sl.Leave_ID = %s AND r.Hostel_ID = %s
            """,
            (leave_id, hostel_id),
        )
        if not cursor.fetchone():
            flash("Access denied.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("manage_leaves"))

    try:
        cursor.execute(
            "UPDATE Student_Leave SET Status = %s WHERE Leave_ID = %s", (status, leave_id)
        )
        cursor.execute(
            "SELECT Student_ID FROM Student_Leave WHERE Leave_ID = %s", (leave_id,)
        )
        res = cursor.fetchone()
        if res:
            add_notification(
                res["Student_ID"], "student",
                f"Your leave application has been {status.lower()}.",
            )
        conn.commit()
        flash(f"Leave application {status.lower()} applied successfully.", "success")
    except pymysql.Error as err:
        logger.error("Update leave error: %s", err)
        flash("An error occurred. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("manage_leaves"))


@app.route("/warden/rooms")
@login_required
@warden_required
def manage_rooms():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    hostel_id = session.get("hostel_id")

    if not hostel_id:
        cursor.close()
        conn.close()
        return render_template("manage_rooms.html", rooms=[])

    cursor.execute(
        """
        SELECT r.Room_ID, r.Room_Number, r.Room_Type, r.Capacity, h.Hostel_Name,
               COUNT(a.Allocation_ID) as Occupied_Count
        FROM Room r
        JOIN Hostel h ON r.Hostel_ID = h.Hostel_ID
        LEFT JOIN Allocation a ON r.Room_ID = a.Room_ID
        WHERE r.Hostel_ID = %s
        GROUP BY r.Room_ID, r.Room_Number, r.Room_Type, r.Capacity, h.Hostel_Name
        ORDER BY r.Room_Number
        """,
        (hostel_id,),
    )
    rooms = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("manage_rooms.html", rooms=rooms)


@app.route("/warden/add_room", methods=["GET", "POST"])
@login_required
@warden_required
def add_room():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    hostel_id = session.get("hostel_id")

    if request.method == "POST":
        submitted_hostel_id = request.form.get("hostel_id")
        room_number = request.form.get("room_number", "").strip()
        room_type = request.form.get("room_type", "").strip()
        raw_capacity = request.form.get("capacity", "").strip()

        # IDOR guard: warden can only add rooms to their own hostel
        if hostel_id and str(submitted_hostel_id) != str(hostel_id):
            flash("Access denied: you can only add rooms to your assigned hostel.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("add_room"))

        try:
            capacity = int(raw_capacity)
            if capacity < 1 or capacity > 20:
                raise ValueError("out of range")
        except (ValueError, TypeError):
            flash("Capacity must be a number between 1 and 20.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("add_room"))

        try:
            cursor.execute(
                "INSERT INTO Room (Room_Number, Room_Type, Capacity, Hostel_ID) "
                "VALUES (%s, %s, %s, %s)",
                (room_number, room_type, capacity, submitted_hostel_id),
            )
            conn.commit()
            flash("Room added successfully!", "success")
            return redirect(url_for("manage_rooms"))
        except pymysql.Error as err:
            logger.error("Add room error: %s", err)
            flash("An error occurred while adding the room. Please try again.", "error")

    # Restrict hostel dropdown to warden's own hostel
    if hostel_id:
        cursor.execute("SELECT * FROM Hostel WHERE Hostel_ID = %s", (hostel_id,))
    else:
        cursor.execute("SELECT * FROM Hostel")
    hostels = cursor.fetchall()
    cursor.close()
    conn.close()

    if not hostels:
        flash("You must be assigned to a hostel before adding rooms.", "warning")
        return redirect(url_for("warden_dashboard"))

    return render_template("add_room.html", hostels=hostels)


@app.route("/warden/allocations")
@login_required
@warden_required
def allocations():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    hostel_id = session.get("hostel_id")

    if not hostel_id:
        cursor.close()
        conn.close()
        return render_template("allocations.html", allocations=[])

    cursor.execute(
        """
        SELECT a.Allocation_ID, a.Allotment_Date,
               s.Name as Student_Name, s.Email, s.Course,
               r.Room_Number, h.Hostel_Name
        FROM Allocation a
        JOIN Student s ON a.Student_ID = s.Student_ID
        JOIN Room r ON a.Room_ID = r.Room_ID
        JOIN Hostel h ON r.Hostel_ID = h.Hostel_ID
        WHERE r.Hostel_ID = %s
        ORDER BY a.Allotment_Date DESC
        """,
        (hostel_id,),
    )
    all_allocations = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("allocations.html", allocations=all_allocations)


@app.route("/warden/allocate_room", methods=["GET", "POST"])
@login_required
@warden_required
def allocate_room():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    hostel_id = session.get("hostel_id")

    if request.method == "POST":
        student_id = request.form.get("student_id")
        room_id = request.form.get("room_id")

        # IDOR guard: verify the room belongs to warden's hostel
        if hostel_id:
            cursor.execute(
                "SELECT 1 FROM Room WHERE Room_ID = %s AND Hostel_ID = %s",
                (room_id, hostel_id),
            )
            if not cursor.fetchone():
                flash("Access denied: room not in your hostel.", "error")
                cursor.close()
                conn.close()
                return redirect(url_for("allocate_room"))

        try:
            cursor.execute(
                "INSERT INTO Allocation (Student_ID, Room_ID) VALUES (%s, %s)",
                (student_id, room_id),
            )
            conn.commit()
            flash("Student successfully allocated to room!", "success")
            return redirect(url_for("allocations"))
        except pymysql.Error as err:
            logger.error("Allocate room error: %s", err)
            flash("An error occurred during allocation. Please try again.", "error")

    # Unallocated students (any hostel — they have no hostel yet)
    cursor.execute(
        "SELECT Student_ID, Name, Course FROM Student "
        "WHERE Student_ID NOT IN (SELECT Student_ID FROM Allocation)"
    )
    unallocated_students = cursor.fetchall()

    # Available rooms scoped to warden's hostel
    if hostel_id:
        cursor.execute(
            """
            SELECT r.Room_ID, r.Room_Number, r.Capacity, h.Hostel_Name,
                   COUNT(a.Allocation_ID) as Occupied_Count
            FROM Room r
            JOIN Hostel h ON r.Hostel_ID = h.Hostel_ID
            LEFT JOIN Allocation a ON r.Room_ID = a.Room_ID
            WHERE r.Hostel_ID = %s
            GROUP BY r.Room_ID, r.Room_Number, r.Capacity, h.Hostel_Name
            HAVING Occupied_Count < r.Capacity
            """,
            (hostel_id,),
        )
    else:
        cursor.execute(
            """
            SELECT r.Room_ID, r.Room_Number, r.Capacity, h.Hostel_Name,
                   COUNT(a.Allocation_ID) as Occupied_Count
            FROM Room r
            JOIN Hostel h ON r.Hostel_ID = h.Hostel_ID
            LEFT JOIN Allocation a ON r.Room_ID = a.Room_ID
            GROUP BY r.Room_ID, r.Room_Number, r.Capacity, h.Hostel_Name
            HAVING Occupied_Count < r.Capacity
            """
        )
    available_rooms = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template(
        "allocate_room.html",
        unallocated_students=unallocated_students,
        available_rooms=available_rooms,
    )


@app.route("/warden/deallocate/<int:allocation_id>", methods=["POST"])
@login_required
@warden_required
def deallocate_room(allocation_id):
    hostel_id = session.get("hostel_id")
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # IDOR check
    if hostel_id:
        cursor.execute(
            """
            SELECT 1 FROM Allocation a
            JOIN Room r ON a.Room_ID = r.Room_ID
            WHERE a.Allocation_ID = %s AND r.Hostel_ID = %s
            """,
            (allocation_id, hostel_id),
        )
        if not cursor.fetchone():
            flash("Access denied.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("allocations"))

    try:
        cursor.execute(
            "DELETE FROM Allocation WHERE Allocation_ID = %s", (allocation_id,)
        )
        conn.commit()
        flash("Student deallocated successfully.", "success")
    except pymysql.Error as err:
        logger.error("Deallocate error: %s", err)
        flash("An error occurred. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("allocations"))


@app.route("/warden/complaints")
@login_required
@warden_required
def manage_complaints():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    hostel_id = session.get("hostel_id")

    if not hostel_id:
        cursor.close()
        conn.close()
        return render_template("manage_complaints.html", complaints=[])

    cursor.execute(
        """
        SELECT c.*, s.Name as Student_Name, r.Room_Number
        FROM Complaint c
        JOIN Student s ON c.Student_ID = s.Student_ID
        LEFT JOIN Room r ON c.Room_ID = r.Room_ID
        WHERE c.Room_ID IN (SELECT Room_ID FROM Room WHERE Hostel_ID = %s)
        ORDER BY
            CASE c.Status WHEN 'Open' THEN 1 WHEN 'In Progress' THEN 2 WHEN 'Closed' THEN 3 END,
            c.Complaint_Date DESC
        """,
        (hostel_id,),
    )
    complaints = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("manage_complaints.html", complaints=complaints)


@app.route("/warden/update_complaint/<int:complaint_id>", methods=["POST"])
@login_required
@warden_required
def update_complaint(complaint_id):
    status = request.form.get("status", "")
    if status not in ("Open", "In Progress", "Closed"):
        flash("Invalid status.", "error")
        return redirect(url_for("manage_complaints"))

    hostel_id = session.get("hostel_id")
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # IDOR check
    if hostel_id:
        cursor.execute(
            """
            SELECT 1 FROM Complaint c
            JOIN Room r ON c.Room_ID = r.Room_ID
            WHERE c.Complaint_ID = %s AND r.Hostel_ID = %s
            """,
            (complaint_id, hostel_id),
        )
        if not cursor.fetchone():
            flash("Access denied.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("manage_complaints"))

    try:
        cursor.execute(
            "UPDATE Complaint SET Status = %s WHERE Complaint_ID = %s", (status, complaint_id)
        )
        cursor.execute(
            "SELECT Student_ID FROM Complaint WHERE Complaint_ID = %s", (complaint_id,)
        )
        res = cursor.fetchone()
        if res:
            add_notification(
                res["Student_ID"], "student", f"Your complaint status is now: {status}."
            )
        conn.commit()
        flash("Complaint status updated successfully.", "success")
    except pymysql.Error as err:
        logger.error("Update complaint error: %s", err)
        flash("An error occurred. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("manage_complaints"))


@app.route("/warden/fees")
@login_required
@warden_required
def manage_fees():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    hostel_id = session.get("hostel_id")

    if not hostel_id:
        cursor.close()
        conn.close()
        return render_template("warden_fees.html", fees=[])

    cursor.execute(
        """
        SELECT f.*, s.Name as Student_Name, s.Email, s.Course
        FROM Fees f
        JOIN Student s ON f.Student_ID = s.Student_ID
        JOIN Allocation a ON s.Student_ID = a.Student_ID
        JOIN Room r ON a.Room_ID = r.Room_ID
        WHERE r.Hostel_ID = %s
        ORDER BY f.Payment_Status ASC, f.Payment_Date DESC
        """,
        (hostel_id,),
    )
    fees = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("warden_fees.html", fees=fees)


@app.route("/warden/issue_bill", methods=["GET", "POST"])
@login_required
@warden_required
def issue_bill():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    hostel_id = session.get("hostel_id")

    if request.method == "POST":
        student_id = request.form.get("student_id", "").strip()
        raw_amount = request.form.get("amount", "").strip()
        due_date = request.form.get("due_date", "").strip()

        # Validate amount
        try:
            amount = float(raw_amount)
            if amount <= 0 or amount > 1_000_000:
                raise ValueError("out of range")
        except (ValueError, TypeError):
            flash("Amount must be a positive number.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("issue_bill"))

        # Validate due_date format
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", due_date):
            flash("Invalid due date format.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("issue_bill"))

        # IDOR guard: verify student belongs to warden's hostel
        if hostel_id:
            cursor.execute(
                """
                SELECT 1 FROM Allocation a
                JOIN Room r ON a.Room_ID = r.Room_ID
                WHERE a.Student_ID = %s AND r.Hostel_ID = %s
                """,
                (student_id, hostel_id),
            )
            if not cursor.fetchone():
                flash("Access denied: student not in your hostel.", "error")
                cursor.close()
                conn.close()
                return redirect(url_for("issue_bill"))

        try:
            cursor.execute(
                "INSERT INTO Fees (Student_ID, Amount, Payment_Date, Payment_Status) "
                "VALUES (%s, %s, %s, 'Pending')",
                (student_id, amount, due_date),
            )
            add_notification(
                student_id, "student",
                f"A new fee bill of ${amount:.2f} has been issued. Due: {due_date}.",
            )
            conn.commit()
            flash("Bill issued successfully!", "success")
            return redirect(url_for("manage_fees"))
        except pymysql.Error as err:
            logger.error("Issue bill error: %s", err)
            flash("An error occurred while issuing the bill. Please try again.", "error")

    # Scope student list to warden's hostel
    if hostel_id:
        cursor.execute(
            """
            SELECT s.Student_ID, s.Name, s.Course FROM Student s
            JOIN Allocation a ON s.Student_ID = a.Student_ID
            JOIN Room r ON a.Room_ID = r.Room_ID
            WHERE r.Hostel_ID = %s ORDER BY s.Name
            """,
            (hostel_id,),
        )
    else:
        cursor.execute("SELECT Student_ID, Name, Course FROM Student ORDER BY Name")
    students = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("issue_bill.html", students=students)


@app.route("/warden/laundry")
@login_required
@warden_required
def manage_laundry():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    hostel_id = session.get("hostel_id")

    if not hostel_id:
        cursor.close()
        conn.close()
        return render_template("warden_laundry.html", requests=[])

    cursor.execute(
        """
        SELECT l.*, s.Name as Student_Name, r.Room_Number
        FROM Laundry l
        JOIN Student s ON l.Student_ID = s.Student_ID
        JOIN Allocation a ON s.Student_ID = a.Student_ID
        JOIN Room r ON a.Room_ID = r.Room_ID
        WHERE r.Hostel_ID = %s
        ORDER BY l.Status ASC, l.Laundry_Date DESC
        """,
        (hostel_id,),
    )
    laundry_requests = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("warden_laundry.html", requests=laundry_requests)


@app.route("/warden/update_laundry/<int:laundry_id>", methods=["POST"])
@login_required
@warden_required
def update_laundry(laundry_id):
    status = request.form.get("status", "")
    if status not in ("Pending", "Completed"):
        flash("Invalid status.", "error")
        return redirect(url_for("manage_laundry"))

    hostel_id = session.get("hostel_id")
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # IDOR check
    if hostel_id:
        cursor.execute(
            """
            SELECT 1 FROM Laundry l
            JOIN Allocation a ON l.Student_ID = a.Student_ID
            JOIN Room r ON a.Room_ID = r.Room_ID
            WHERE l.Laundry_ID = %s AND r.Hostel_ID = %s
            """,
            (laundry_id, hostel_id),
        )
        if not cursor.fetchone():
            flash("Access denied.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("manage_laundry"))

    try:
        cursor.execute(
            "UPDATE Laundry SET Status = %s WHERE Laundry_ID = %s", (status, laundry_id)
        )
        cursor.execute(
            "SELECT Student_ID FROM Laundry WHERE Laundry_ID = %s", (laundry_id,)
        )
        res = cursor.fetchone()
        if res:
            add_notification(
                res["Student_ID"], "student", f"Your laundry request is now: {status}."
            )
        conn.commit()
        flash("Laundry status updated.", "success")
    except pymysql.Error as err:
        logger.error("Update laundry error: %s", err)
        flash("An error occurred. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("manage_laundry"))


@app.route("/warden/maintenance", methods=["GET", "POST"])
@login_required
@warden_required
def manage_maintenance():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    hostel_id = session.get("hostel_id")

    if request.method == "POST":
        complaint_id = request.form.get("complaint_id") or None
        submitted_hostel_id = request.form.get("hostel_id")
        work_type = request.form.get("work_type", "").strip()
        raw_cost = request.form.get("cost", "").strip()

        # IDOR guard on hostel
        if hostel_id and str(submitted_hostel_id) != str(hostel_id):
            flash("Access denied: you can only log maintenance for your hostel.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("manage_maintenance"))

        try:
            cost = float(raw_cost) if raw_cost else None
            if cost is not None and (cost < 0 or cost > 10_000_000):
                raise ValueError("out of range")
        except (ValueError, TypeError):
            flash("Cost must be a valid positive number.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("manage_maintenance"))

        try:
            cursor.execute(
                "INSERT INTO Maintenance (Complaint_ID, Hostel_ID, Work_Type, Cost) "
                "VALUES (%s, %s, %s, %s)",
                (complaint_id, submitted_hostel_id, work_type, cost),
            )
            conn.commit()
            flash("Maintenance task logged successfully.", "success")
            return redirect(url_for("manage_maintenance"))
        except pymysql.Error as err:
            logger.error("Add maintenance error: %s", err)
            flash("An error occurred. Please try again.", "error")

    # Scope dropdowns to warden's hostel
    if hostel_id:
        cursor.execute(
            """
            SELECT c.Complaint_ID, c.Complaint_Type, c.Room_ID FROM Complaint c
            JOIN Room r ON c.Room_ID = r.Room_ID
            WHERE c.Status != 'Closed' AND r.Hostel_ID = %s
            """,
            (hostel_id,),
        )
        active_complaints = cursor.fetchall()
        cursor.execute(
            "SELECT Hostel_ID, Hostel_Name FROM Hostel WHERE Hostel_ID = %s", (hostel_id,)
        )
        hostels = cursor.fetchall()
    else:
        cursor.execute(
            "SELECT Complaint_ID, Complaint_Type, Room_ID FROM Complaint WHERE Status != 'Closed'"
        )
        active_complaints = cursor.fetchall()
        cursor.execute("SELECT Hostel_ID, Hostel_Name FROM Hostel")
        hostels = cursor.fetchall()

    # Maintenance records scoped to warden's hostel
    if hostel_id:
        cursor.execute(
            """
            SELECT m.*, h.Hostel_Name, c.Complaint_Type, r.Room_Number
            FROM Maintenance m
            JOIN Hostel h ON m.Hostel_ID = h.Hostel_ID
            LEFT JOIN Complaint c ON m.Complaint_ID = c.Complaint_ID
            LEFT JOIN Room r ON c.Room_ID = r.Room_ID
            WHERE m.Hostel_ID = %s
            ORDER BY
                CASE m.Status WHEN 'Pending' THEN 1 WHEN 'In Progress' THEN 2 WHEN 'Completed' THEN 3 END,
                m.Maintenance_Date DESC
            """,
            (hostel_id,),
        )
    else:
        cursor.execute(
            """
            SELECT m.*, h.Hostel_Name, c.Complaint_Type, r.Room_Number
            FROM Maintenance m
            JOIN Hostel h ON m.Hostel_ID = h.Hostel_ID
            LEFT JOIN Complaint c ON m.Complaint_ID = c.Complaint_ID
            LEFT JOIN Room r ON c.Room_ID = r.Room_ID
            ORDER BY
                CASE m.Status WHEN 'Pending' THEN 1 WHEN 'In Progress' THEN 2 WHEN 'Completed' THEN 3 END,
                m.Maintenance_Date DESC
            """
        )
    maintenance_tasks = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template(
        "manage_maintenance.html",
        tasks=maintenance_tasks,
        complaints=active_complaints,
        hostels=hostels,
    )


@app.route("/warden/update_maintenance/<int:maintenance_id>", methods=["POST"])
@login_required
@warden_required
def update_maintenance(maintenance_id):
    status = request.form.get("status", "")
    if status not in ("Pending", "In Progress", "Completed"):
        flash("Invalid status.", "error")
        return redirect(url_for("manage_maintenance"))

    hostel_id = session.get("hostel_id")
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    # IDOR check
    if hostel_id:
        cursor.execute(
            "SELECT 1 FROM Maintenance WHERE Maintenance_ID = %s AND Hostel_ID = %s",
            (maintenance_id, hostel_id),
        )
        if not cursor.fetchone():
            flash("Access denied.", "error")
            cursor.close()
            conn.close()
            return redirect(url_for("manage_maintenance"))

    try:
        cursor.execute(
            "UPDATE Maintenance SET Status = %s WHERE Maintenance_ID = %s",
            (status, maintenance_id),
        )
        conn.commit()
        flash("Maintenance status updated.", "success")
    except pymysql.Error as err:
        logger.error("Update maintenance error: %s", err)
        flash("An error occurred. Please try again.", "error")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("manage_maintenance"))


# ─── Admin Routes ─────────────────────────────────────────────────────────────
@app.route("/admin/dashboard")
@login_required
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    stats = {}
    cursor.execute("SELECT COUNT(*) as count FROM Warden")
    stats["wardens"] = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM Hostel")
    stats["hostels"] = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM Room")
    stats["rooms_total"] = cursor.fetchone()["count"]

    cursor.execute(
        "SELECT w.*, h.Hostel_Name FROM Warden w "
        "LEFT JOIN Hostel h ON w.Hostel_ID = h.Hostel_ID ORDER BY w.Name ASC"
    )
    wardens = cursor.fetchall()

    cursor.execute(
        "SELECT h.Hostel_ID, h.Hostel_Name, h.Location, h.Type, "
        "(SELECT COUNT(*) FROM Room WHERE Hostel_ID = h.Hostel_ID) as Room_Count "
        "FROM Hostel h ORDER BY h.Hostel_Name"
    )
    hostels = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template("admin_dashboard.html", stats=stats, wardens=wardens, hostels=hostels)


@app.route("/admin/add_warden", methods=["GET", "POST"])
@login_required
@admin_required
def admin_add_warden():
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        hostel_id = request.form.get("hostel_id") or None
        raw_password = request.form.get("password", "")

        if len(raw_password) < 8:
            flash("Password must be at least 8 characters.", "error")
            cursor.execute("SELECT * FROM Hostel")
            hostels = cursor.fetchall()
            cursor.close()
            conn.close()
            return render_template("admin_add_warden.html", hostels=hostels)

        password = generate_password_hash(raw_password)
        try:
            cursor.execute(
                "INSERT INTO Warden (Name, Phone, Email, Password, Hostel_ID) "
                "VALUES (%s, %s, %s, %s, %s)",
                (name, phone, email, password, hostel_id),
            )
            conn.commit()
            flash("Warden account created successfully!", "success")
            return redirect(url_for("admin_dashboard"))
        except pymysql.Error as err:
            if err.args[0] == 1062:
                flash("Email already registered for a warden.", "error")
            else:
                logger.error("Add warden error: %s", err)
                flash("An error occurred while creating the warden account. Please try again.", "error")

    cursor.execute("SELECT * FROM Hostel")
    hostels = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("admin_add_warden.html", hostels=hostels)


@app.route("/admin/add_hostel", methods=["GET", "POST"])
@login_required
@admin_required
def add_hostel():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        location = request.form.get("location", "").strip()
        h_type = request.form.get("type", "").strip()

        if h_type not in ("Boys", "Girls"):
            flash("Invalid hostel type.", "error")
            return render_template("add_hostel.html")

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO Hostel (Hostel_Name, Location, Type) VALUES (%s, %s, %s)",
                (name, location, h_type),
            )
            conn.commit()
            flash("Hostel block added successfully!", "success")
            return redirect(url_for("admin_dashboard"))
        except pymysql.Error as err:
            logger.error("Add hostel error: %s", err)
            flash("An error occurred while adding the hostel. Please try again.", "error")
        finally:
            cursor.close()
            conn.close()

    return render_template("add_hostel.html")


@app.route("/admin/change_password", methods=["GET", "POST"])
@login_required
@admin_required
def admin_change_password():
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if len(new_pw) < 8:
            flash("New password must be at least 8 characters.", "error")
            return redirect(url_for("admin_change_password"))
        if new_pw != confirm_pw:
            flash("New passwords do not match.", "error")
            return redirect(url_for("admin_change_password"))

        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        try:
            cursor.execute(
                "SELECT Password FROM Admin WHERE Admin_ID = %s", (session["user_id"],)
            )
            admin = cursor.fetchone()
            if not admin or not check_password_hash(admin["Password"], current_pw):
                flash("Current password is incorrect.", "error")
                return redirect(url_for("admin_change_password"))
            cursor.execute(
                "UPDATE Admin SET Password = %s WHERE Admin_ID = %s",
                (generate_password_hash(new_pw), session["user_id"]),
            )
            conn.commit()
            flash("Password changed successfully.", "success")
            return redirect(url_for("admin_dashboard"))
        except pymysql.Error as err:
            logger.error("Admin password change error: %s", err)
            flash("An error occurred. Please try again.", "error")
        finally:
            cursor.close()
            conn.close()

    return render_template("change_password.html", role="admin")


# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
