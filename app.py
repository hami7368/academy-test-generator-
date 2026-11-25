"""
Academy Test Generator — Flask app (Punjab Board, Pakistan).
Roles: admin (owner, one account) and teacher (admin-created only).
No public registration. All admin routes are server-enforced.
Run locally:  pip install -r requirements.txt && python app.py
Deploy: Render free web service + Neon free Postgres (see README.md).
"""
import os, json, random, io, secrets
from datetime import date, datetime
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for, flash,
                   send_file, send_from_directory, jsonify, abort, make_response)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user, logout_user,
                         login_required, current_user)
from flask_wtf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "instance", "uploads", "books")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# PWA icons are generated from code (see generate_icons.py) because the
# binary PNGs cannot be pushed through the text-only GitHub upload API.
try:
    from generate_icons import generate_icons
    generate_icons()
except Exception:
    pass

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
_db_url = os.environ.get("DATABASE_URL", "") or ""
if _db_url.startswith("postgres://"):
    _db_url = _db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = _db_url or "sqlite:///" + os.path.join(BASE_DIR, "instance", "academy.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB PDF limit
ACADEMY_NAME = os.environ.get("ACADEMY_NAME", "My Academy")

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in first."
csrf = CSRFProtect(app)

QTYPES = ["MCQ", "Short", "Long", "Numerical"]
SOURCES = ["Theory", "Exercise"]
# Question formats — what kind of question it is (Essay for English, Tashreeh
# for Urdu, ...). "General" is the default. Formats power the generator's
# custom "Add Section" blocks: a section can pick only Essay questions, etc.
FORMATS = ["General", "Essay", "Story", "Application", "Letter", "Translation",
           "Tenses", "Comprehension", "Tashreeh", "Khulasa", "Mazmoon",
           "Darkhwast", "Tarjuma"]
DIFFICULTIES = ["Easy", "Medium", "Hard"]
ALLOWED_EXT = {"pdf"}


# ---------------- Models ----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="teacher")  # admin|teacher
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    @property
    def is_admin(self):
        return self.role == "admin"


class ClassLevel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(60), nullable=False, unique=True)
    sort_order = db.Column(db.Integer, default=0)


class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    class_level_id = db.Column(db.Integer, db.ForeignKey("class_level.id"), nullable=False)
    class_level = db.relationship("ClassLevel", backref=db.backref("subjects", cascade="all, delete-orphan", lazy="dynamic"))


class Chapter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    number = db.Column(db.Integer, default=0)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    subject = db.relationship("Subject", backref=db.backref("chapters", cascade="all, delete-orphan", lazy="dynamic"))


class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    class_level_id = db.Column(db.Integer, db.ForeignKey("class_level.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    filename = db.Column(db.String(200))
    original_filename = db.Column(db.String(200))
    file_size = db.Column(db.Integer, default=0)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    class_level = db.relationship("ClassLevel")
    subject = db.relationship("Subject")


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_level_id = db.Column(db.Integer, db.ForeignKey("class_level.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    chapter_id = db.Column(db.Integer, db.ForeignKey("chapter.id"), nullable=False)
    qtype = db.Column(db.String(20), nullable=False)       # MCQ/Short/Long/Numerical
    source = db.Column(db.String(20), nullable=False)      # Theory/Exercise
    format = db.Column(db.String(30), default="General")   # Essay, Tashreeh, ...
    text = db.Column(db.Text, nullable=False)
    options_json = db.Column(db.Text)                       # JSON list of 4 options (MCQ)
    correct_option = db.Column(db.String(5))
    answer = db.Column(db.Text)
    difficulty = db.Column(db.String(20), default="Medium")
    marks = db.Column(db.Integer, default=1)
    image_filename = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    class_level = db.relationship("ClassLevel")
    subject = db.relationship("Subject")
    chapter = db.relationship("Chapter")

    @property
    def options(self):
        try:
            return json.loads(self.options_json) if self.options_json else []
        except Exception:
            return []


class Paper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    class_level_id = db.Column(db.Integer, db.ForeignKey("class_level.id"))
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"))
    variant = db.Column(db.String(5), default="A")
    total_marks = db.Column(db.Integer, default=0)
    duration_minutes = db.Column(db.Integer, default=60)
    instructions = db.Column(db.Text)
    paper_date = db.Column(db.String(20))
    questions_json = db.Column(db.Text, nullable=False, default="[]")  # snapshot [{id,text,qtype,source,marks,options,correct_option,answer,chapter}]
    attempt_json = db.Column(db.Text, default="{}")  # {"Short": 5} = attempt any 5 out of the Short questions
    sections_json = db.Column(db.Text, default="[]")  # custom sections [{title,qtype,format,theory,exercise,marks,attempt}]
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    teacher = db.relationship("User")
    class_level = db.relationship("ClassLevel")
    subject = db.relationship("Subject")

    @property
    def attempts(self):
        try:
            return json.loads(self.attempt_json or "{}")
        except Exception:
            return {}

    @property
    def sections(self):
        try:
            return json.loads(self.sections_json or "[]")
        except Exception:
            return []

    @property
    def questions(self):
        try:
            qs = json.loads(self.questions_json or "[]")
        except Exception:
            return []
        # Papers made before sections/formats existed have no such keys.
        for q in qs:
            q.setdefault("section", "")
            q.setdefault("format", "General")
        return qs


class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    action = db.Column(db.String(120), nullable=False)
    detail = db.Column(db.String(400))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User")


@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))


def log_activity(action, detail=""):
    try:
        db.session.add(ActivityLog(user_id=current_user.id if current_user.is_authenticated else None,
                                   action=action, detail=detail or ""))
        db.session.commit()
    except Exception:
        db.session.rollback()


# ---------------- Access control (server-enforced) ----------------
def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


@app.errorhandler(403)
def forbidden(e):
    return render_template("403.html"), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


def ensure_admin_from_env():
    """Create the single owner admin from env vars, if set and no admin exists."""
    email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    pw = os.environ.get("ADMIN_PASSWORD") or ""
    if not email or not pw:
        return False
    if User.query.filter_by(role="admin").first():
        return False
    if User.query.filter_by(email=email).first():
        return False
    u = User(name="Owner / Admin", email=email, role="admin", is_active=True)
    u.set_password(pw)
    db.session.add(u)
    db.session.commit()
    return True


def _ensure_column(table, column, ddl):
    """Add a column to an existing database if it is missing (databases
    created before the column existed). Fresh databases get it from create_all()."""
    try:
        from sqlalchemy import text as _text
        cols = [r[1] for r in db.session.execute(_text(f"PRAGMA table_info({table})"))]
        if column not in cols:
            db.session.execute(_text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
            db.session.commit()
    except Exception:
        db.session.rollback()
        try:
            from sqlalchemy import text as _text2
            db.session.execute(_text2(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {ddl}"))
            db.session.commit()
        except Exception:
            db.session.rollback()


def _ensure_columns():
    _ensure_column("paper", "attempt_json", "attempt_json TEXT DEFAULT '{}'")
    _ensure_column("paper", "sections_json", "sections_json TEXT DEFAULT '[]'")
    _ensure_column("question", "format", "format VARCHAR(30) DEFAULT 'General'")


def _total_with_attempts(questions, attempts):
    """Total marks counting only the questions a student must attempt:
    for each type, the first N questions where N = attempts[type] (or all)."""
    grouped = {}
    for q in questions:
        grouped.setdefault(q["qtype"], []).append(q)
    total = 0
    for qtype, items in grouped.items():
        n = (attempts or {}).get(qtype)
        n = len(items) if n is None else max(0, min(int(n), len(items)))
        total += sum(item["marks"] for item in items[:n])
    return total


def _paper_total(questions, attempts, sections):
    """Full paper total: fixed-type questions (attempt counts) plus each
    custom section (its own attempt count, or all its questions)."""
    total = _total_with_attempts([q for q in questions if not q.get("section")],
                                 attempts)
    for sec in (sections or []):
        items = [q for q in questions if q.get("section") == sec.get("title")]
        n = sec.get("attempt") or len(items)
        n = max(0, min(int(n), len(items)))
        total += sum(item["marks"] for item in items[:n])
    return total


def init_db():
    db.create_all()
    _ensure_columns()
    ensure_admin_from_env()
    try:
        from seed import seed_all
        seed_all(db, ClassLevel, Subject, Chapter, Question)
    except Exception as e:
        app.logger.warning("seed skipped: %s", e)


with app.app_context():
    init_db()


# ---------------- Public / auth ----------------
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/setup", methods=["GET", "POST"])
def setup():
    # One-time only: locked forever once an admin exists.
    if User.query.filter_by(role="admin").first():
        flash("Admin account already exists. Please log in.", "info")
        return redirect(url_for("login"))
    if request.method == "POST":
        name = request.form.get("name", "").strip() or "Owner / Admin"
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        pw2 = request.form.get("password2") or ""
        if "@" not in email or "." not in email:
            flash("Enter a valid email address.", "error")
        elif len(pw) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif pw != pw2:
            flash("Passwords do not match.", "error")
        else:
            u = User(name=name, email=email, role="admin", is_active=True)
            u.set_password(pw)
            db.session.add(u)
            db.session.commit()
            flash("Admin account created. Please log in.", "success")
            return redirect(url_for("login"))
    return render_template("setup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        u = User.query.filter_by(email=email).first()
        if u and u.check_password(pw):
            if not u.is_active:
                flash("Your account has been disabled. Contact the admin.", "error")
                return render_template("login.html")
            login_user(u)
            log_activity("login", u.email)
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        cur = request.form.get("current") or ""
        new = request.form.get("new") or ""
        new2 = request.form.get("new2") or ""
        if not current_user.check_password(cur):
            flash("Current password is wrong.", "error")
        elif len(new) < 8:
            flash("New password must be at least 8 characters.", "error")
        elif new != new2:
            flash("New passwords do not match.", "error")
        else:
            current_user.set_password(new)
            db.session.commit()
            log_activity("password_changed", current_user.email)
            flash("Password changed successfully.", "success")
            return redirect(url_for("dashboard"))
    return render_template("change_password.html")


# ---------------- Dashboards ----------------
@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.is_admin:
        stats = dict(teachers=User.query.filter_by(role="teacher").count(),
                     questions=Question.query.count(),
                     papers=Paper.query.count(),
                     books=Book.query.count(),
                     classes=ClassLevel.query.count())
        recent_papers = Paper.query.order_by(Paper.created_at.desc()).limit(8).all()
        recent_logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(10).all()
        return render_template("dashboard_admin.html", stats=stats,
                               recent_papers=recent_papers, recent_logs=recent_logs)
    my_papers = Paper.query.filter_by(teacher_id=current_user.id).order_by(Paper.created_at.desc()).all()
    stats = dict(papers=len(my_papers),
                 questions=Question.query.count(),
                 total_marks=sum(p.total_marks for p in my_papers))
    return render_template("dashboard_teacher.html", stats=stats, papers=my_papers[:8])


@app.route("/manifest.json")
def manifest():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "manifest.json",
                               mimetype="application/manifest+json")


@app.route("/sw.js")
def sw():
    return send_from_directory(os.path.join(BASE_DIR, "static"), "sw.js",
                               mimetype="application/javascript")


@app.route("/offline")
def offline():
    return render_template("offline.html")


# ---------------- Admin: teachers ----------------
@app.route("/admin/teachers")
@login_required
@admin_required
def admin_teachers():
    teachers = User.query.filter_by(role="teacher").order_by(User.created_at.desc()).all()
    return render_template("teachers.html", teachers=teachers)


@app.route("/admin/teachers/new", methods=["GET", "POST"])
@login_required
@admin_required
def admin_teacher_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = (request.form.get("email") or "").strip().lower()
        pw = request.form.get("password") or ""
        if not name or "@" not in email or len(pw) < 8:
            flash("Name, valid email and a password of 8+ characters are required.", "error")
        elif User.query.filter_by(email=email).first():
            flash("That email is already registered.", "error")
        else:
            u = User(name=name, email=email, role="teacher", is_active=True)
            u.set_password(pw)
            db.session.add(u)
            db.session.commit()
            log_activity("teacher_created", email)
            flash(f"Teacher {name} created. Share the login privately.", "success")
            return redirect(url_for("admin_teachers"))
    return render_template("teacher_form.html", teacher=None)


@app.route("/admin/teachers/<int:uid>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def admin_teacher_edit(uid):
    t = db.session.get(User, uid)
    if not t or t.role != "teacher":
        abort(404)
    if request.method == "POST":
        t.name = request.form.get("name", "").strip() or t.name
        new_email = (request.form.get("email") or "").strip().lower()
        if new_email and new_email != t.email:
            if User.query.filter_by(email=new_email).first():
                flash("That email is already in use.", "error")
                return render_template("teacher_form.html", teacher=t)
            t.email = new_email
        db.session.commit()
        log_activity("teacher_edited", t.email)
        flash("Teacher updated.", "success")
        return redirect(url_for("admin_teachers"))
    return render_template("teacher_form.html", teacher=t)


@app.route("/admin/teachers/<int:uid>/toggle", methods=["POST"])
@login_required
@admin_required
def admin_teacher_toggle(uid):
    t = db.session.get(User, uid)
    if not t or t.role != "teacher":
        abort(404)
    t.is_active = not t.is_active
    db.session.commit()
    log_activity("teacher_disabled" if not t.is_active else "teacher_enabled", t.email)
    flash(f"{t.name} {'disabled' if not t.is_active else 'enabled'}.", "success")
    return redirect(url_for("admin_teachers"))


@app.route("/admin/teachers/<int:uid>/reset-password", methods=["POST"])
@login_required
@admin_required
def admin_teacher_reset(uid):
    t = db.session.get(User, uid)
    if not t or t.role != "teacher":
        abort(404)
    pw = request.form.get("password") or ""
    if len(pw) < 8:
        flash("New password must be at least 8 characters.", "error")
    else:
        t.set_password(pw)
        db.session.commit()
        log_activity("teacher_password_reset", t.email)
        flash(f"Password reset for {t.name}. Share it privately.", "success")
    return redirect(url_for("admin_teachers"))


@app.route("/admin/teachers/<int:uid>/delete", methods=["POST"])
@login_required
@admin_required
def admin_teacher_delete(uid):
    t = db.session.get(User, uid)
    if not t or t.role != "teacher":
        abort(404)
    db.session.delete(t)
    db.session.commit()
    log_activity("teacher_deleted", t.email)
    flash("Teacher deleted.", "success")
    return redirect(url_for("admin_teachers"))


@app.route("/admin/activity")
@login_required
@admin_required
def admin_activity():
    logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(200).all()
    return render_template("activity.html", logs=logs)


@app.route("/admin/settings")
@login_required
@admin_required
def admin_settings():
    ai_configured = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY"))
    return render_template("settings.html", academy_name=ACADEMY_NAME,
                           ai_configured=ai_configured)


# ---------------- Admin: classes / subjects / chapters ----------------
@app.route("/admin/structure", methods=["GET", "POST"])
@login_required
@admin_required
def admin_structure():
    if request.method == "POST":
        kind = request.form.get("kind")
        if kind == "class":
            name = request.form.get("name", "").strip()
            if name and not ClassLevel.query.filter_by(name=name).first():
                db.session.add(ClassLevel(name=name, sort_order=ClassLevel.query.count() + 1))
                db.session.commit()
                flash("Class added.", "success")
        elif kind == "subject":
            name = request.form.get("name", "").strip()
            cid = request.form.get("class_level_id", type=int)
            if name and cid:
                db.session.add(Subject(name=name, class_level_id=cid))
                db.session.commit()
                flash("Subject added.", "success")
        elif kind == "chapter":
            name = request.form.get("name", "").strip()
            sid = request.form.get("subject_id", type=int)
            num = request.form.get("number", type=int) or 0
            if name and sid:
                db.session.add(Chapter(name=name, number=num, subject_id=sid))
                db.session.commit()
                flash("Chapter added.", "success")
        return redirect(url_for("admin_structure"))
    classes = ClassLevel.query.order_by(ClassLevel.sort_order).all()
    return render_template("structure.html", classes=classes)


@app.route("/admin/structure/delete/<kind>/<int:oid>", methods=["POST"])
@login_required
@admin_required
def admin_structure_delete(kind, oid):
    obj = None
    if kind == "class":
        obj = db.session.get(ClassLevel, oid)
    elif kind == "subject":
        obj = db.session.get(Subject, oid)
    elif kind == "chapter":
        obj = db.session.get(Chapter, oid)
    if not obj:
        abort(404)
    db.session.delete(obj)
    db.session.commit()
    flash("Deleted.", "success")
    return redirect(url_for("admin_structure"))


# ---------------- Admin: books ----------------
@app.route("/admin/books", methods=["GET", "POST"])
@login_required
@admin_required
def admin_books():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        cid = request.form.get("class_level_id", type=int)
        sid = request.form.get("subject_id", type=int)
        f = request.files.get("pdf")
        if not title or not cid or not sid:
            flash("Title, class and subject are required.", "error")
        elif not f or not f.filename.lower().endswith(".pdf"):
            flash("Please upload a PDF file.", "error")
        else:
            fname = secure_filename(f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{f.filename}")
            path = os.path.join(UPLOAD_DIR, fname)
            f.save(path)
            db.session.add(Book(title=title, class_level_id=cid, subject_id=sid,
                                filename=fname, original_filename=f.filename,
                                file_size=os.path.getsize(path)))
            db.session.commit()
            log_activity("book_uploaded", title)
            flash("Book uploaded.", "success")
        return redirect(url_for("admin_books"))
    books = Book.query.order_by(Book.uploaded_at.desc()).all()
    classes = ClassLevel.query.order_by(ClassLevel.sort_order).all()
    return render_template("books.html", books=books, classes=classes)


@app.route("/admin/books/<int:bid>/download")
@login_required
@admin_required
def admin_book_download(bid):
    b = db.session.get(Book, bid) or abort(404)
    return send_from_directory(UPLOAD_DIR, b.filename, as_attachment=True,
                               download_name=b.original_filename)


@app.route("/admin/books/<int:bid>/delete", methods=["POST"])
@login_required
@admin_required
def admin_book_delete(bid):
    b = db.session.get(Book, bid) or abort(404)
    try:
        os.remove(os.path.join(UPLOAD_DIR, b.filename))
    except OSError:
        pass
    db.session.delete(b)
    db.session.commit()
    flash("Book deleted. Note: on free hosting, uploaded files are not permanent — see README.", "info")
    return redirect(url_for("admin_books"))


# ---------------- Questions (admin manage; teachers read via generator) ----------------
@app.route("/questions")
@login_required
def list_questions():
    q = Question.query
    cid = request.args.get("class_level_id", type=int)
    sid = request.args.get("subject_id", type=int)
    chid = request.args.get("chapter_id", type=int)
    qt = request.args.get("qtype")
    src = request.args.get("source")
    fmt = request.args.get("format")
    if cid: q = q.filter_by(class_level_id=cid)
    if sid: q = q.filter_by(subject_id=sid)
    if chid: q = q.filter_by(chapter_id=chid)
    if qt in QTYPES: q = q.filter_by(qtype=qt)
    if src in SOURCES: q = q.filter_by(source=src)
    if fmt in FORMATS: q = q.filter_by(format=fmt)
    questions = q.order_by(Question.created_at.desc()).limit(300).all()
    classes = ClassLevel.query.order_by(ClassLevel.sort_order).all()
    subjects = Subject.query.all()
    chapters = Chapter.query.all()
    return render_template("questions.html", questions=questions, classes=classes,
                           subjects=subjects, chapters=chapters, formats=FORMATS,
                           sel=dict(cid=cid, sid=sid, chid=chid, qt=qt, src=src, fmt=fmt))


@app.route("/questions/new", methods=["GET", "POST"])
@login_required
@admin_required
def question_new():
    if request.method == "POST":
        err = _save_question(None, request.form)
        if err:
            flash(err, "error")
        else:
            flash("Question added.", "success")
            return redirect(url_for("list_questions"))
    classes = ClassLevel.query.order_by(ClassLevel.sort_order).all()
    return render_template("question_form.html", q=None, classes=classes,
                           subjects=Subject.query.all(), chapters=Chapter.query.all(),
                           formats=FORMATS)


@app.route("/questions/<int:qid>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def question_edit(qid):
    q = db.session.get(Question, qid) or abort(404)
    if request.method == "POST":
        err = _save_question(q, request.form)
        if err:
            flash(err, "error")
        else:
            flash("Question updated.", "success")
            return redirect(url_for("list_questions"))
    classes = ClassLevel.query.order_by(ClassLevel.sort_order).all()
    return render_template("question_form.html", q=q, classes=classes,
                           subjects=Subject.query.all(), chapters=Chapter.query.all(),
                           formats=FORMATS)


def _save_question(q, form):
    cid = form.get("class_level_id", type=int)
    sid = form.get("subject_id", type=int)
    chid = form.get("chapter_id", type=int)
    qtype = form.get("qtype")
    source = form.get("source")
    fmt = (form.get("format") or "General").strip()
    if fmt not in FORMATS:
        fmt = "General"
    text = (form.get("text") or "").strip()
    difficulty = form.get("difficulty") or "Medium"
    marks = form.get("marks", type=int) or 1
    if not (cid and sid and chid and text):
        return "Class, subject, chapter and question text are required."
    if qtype not in QTYPES or source not in SOURCES:
        return "Choose a valid question type and source (Theory / Exercise)."
    if q is None:
        q = Question()
        db.session.add(q)
    q.class_level_id, q.subject_id, q.chapter_id = cid, sid, chid
    q.qtype, q.source, q.text = qtype, source, text
    q.format = fmt
    q.difficulty, q.marks = difficulty, marks
    q.answer = (form.get("answer") or "").strip()
    if qtype == "MCQ":
        opts = [(form.get(f"opt{i}") or "").strip() for i in range(1, 5)]
        if any(not o for o in opts):
            return "MCQs need all 4 options (A–D)."
        q.options_json = json.dumps(opts)
        q.correct_option = form.get("correct_option") or "A"
    else:
        q.options_json, q.correct_option = None, None
    db.session.commit()
    return None


@app.route("/questions/<int:qid>/delete", methods=["POST"])
@login_required
@admin_required
def question_delete(qid):
    q = db.session.get(Question, qid) or abort(404)
    db.session.delete(q)
    db.session.commit()
    flash("Question deleted.", "success")
    return redirect(url_for("list_questions"))


# ---------------- Bulk import from Excel (.xlsx / .csv) ----------------
# The admin downloads a ready-made Excel template, fills one question per
# row, and uploads it. Columns (first row = headings):
# Class | Subject | Chapter | Chapter No | Type | Source | Difficulty |
# Marks | Question | Option A | Option B | Option C | Option D |
# Correct Option | Answer
# Type: MCQ / Short / Long / Numerical. Source: Theory / Exercise.
IMPORT_COLUMNS = ["Class", "Subject", "Chapter", "Chapter No", "Type", "Source",
                  "Format", "Difficulty", "Marks", "Question", "Option A", "Option B",
                  "Option C", "Option D", "Correct Option", "Answer"]
IMPORT_HEADER_ALIASES = {
    "class": "Class", "subject": "Subject", "chapter": "Chapter",
    "chapter no": "Chapter No", "chapter number": "Chapter No", "ch no": "Chapter No",
    "type": "Type", "question type": "Type", "source": "Source",
    "theory/exercise": "Source", "format": "Format", "question format": "Format",
    "difficulty": "Difficulty", "level": "Difficulty",
    "marks": "Marks", "mark": "Marks", "question": "Question",
    "question text": "Question", "option a": "Option A", "option b": "Option B",
    "option c": "Option C", "option d": "Option D",
    "correct option": "Correct Option", "correct answer": "Correct Option",
    "answer": "Answer", "solution": "Answer",
}


def _norm_header(value):
    return (str(value or "").strip().lower()
            .replace("_", " ").replace("-", " ").strip())


def _read_import_file(f):
    """Read an uploaded .xlsx or .csv into a list of dicts keyed by IMPORT_COLUMNS."""
    name = (f.filename or "").lower()
    if name.endswith(".csv"):
        import csv as _csv
        text = f.read().decode("utf-8-sig", errors="replace")
        reader = _csv.DictReader(text.splitlines())
        rows = []
        for raw in reader:
            row = {}
            for k, v in (raw or {}).items():
                col = IMPORT_HEADER_ALIASES.get(_norm_header(k))
                if col:
                    row[col] = v
            rows.append(row)
        return rows
    if not name.endswith((".xlsx", ".xlsm")):
        raise ValueError("Please upload an Excel (.xlsx) or CSV (.csv) file.")
    from openpyxl import load_workbook
    wb = load_workbook(filename=f, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [IMPORT_HEADER_ALIASES.get(_norm_header(h)) for h in rows[0]]
    out = []
    for values in rows[1:]:
        if all(v is None or str(v).strip() == "" for v in values):
            continue
        row = {}
        for col, v in zip(headers, values):
            if col:
                row[col] = v
        out.append(row)
    return out


def _import_question_rows(rows):
    """Validate and insert parsed rows. Returns (imported_count, [error strings])."""
    imported, errors = 0, []

    def _lookup(model, name, extra=None):
        if not name:
            return None
        q = model.query
        if extra:
            q = q.filter_by(**extra)
        name = str(name).strip()
        for obj in q.all():
            if obj.name.strip().lower() == name.lower():
                return obj
        return None

    for i, row in enumerate(rows, start=2):  # row 2 = first data row in the sheet
        def err(msg):
            errors.append(f"Row {i}: {msg}")

        cls_name = str(row.get("Class") or "").strip()
        subj_name = str(row.get("Subject") or "").strip()
        ch_name = str(row.get("Chapter") or "").strip()
        text = str(row.get("Question") or "").strip()
        qtype = str(row.get("Type") or "").strip()
        source = str(row.get("Source") or "").strip()
        if not (cls_name and subj_name and ch_name and text):
            err("Class, Subject, Chapter and Question are all required — row skipped.")
            continue
        if qtype not in QTYPES:
            err(f"Type must be one of {', '.join(QTYPES)} (got '{qtype}') — row skipped.")
            continue
        if source not in SOURCES:
            err(f"Source must be Theory or Exercise (got '{source}') — row skipped.")
            continue
        fmt_raw = str(row.get("Format") or "General").strip()
        fmt = next((f for f in FORMATS if f.lower() == fmt_raw.lower()), None)
        if fmt is None:
            err(f"Format must be one of {', '.join(FORMATS)} (got '{fmt_raw}') — row skipped.")
            continue
        cls = _lookup(ClassLevel, cls_name)
        if not cls:
            err(f"Class '{cls_name}' does not exist — add it under Classes & Subjects first.")
            continue
        subj = _lookup(Subject, subj_name, {"class_level_id": cls.id})
        if not subj:
            err(f"Subject '{subj_name}' does not exist for {cls_name} — add it first.")
            continue
        ch = _lookup(Chapter, ch_name, {"subject_id": subj.id})
        if not ch:
            try:
                ch_no = int(float(str(row.get("Chapter No") or 0) or 0))
            except (TypeError, ValueError):
                ch_no = 0
            if not ch_no:
                ch_no = (db.session.query(db.func.max(Chapter.number))
                         .filter_by(subject_id=subj.id).scalar() or 0) + 1
            ch = Chapter(name=ch_name, number=ch_no, subject_id=subj.id)
            db.session.add(ch)
            db.session.flush()
        difficulty = str(row.get("Difficulty") or "Medium").strip() or "Medium"
        if difficulty not in DIFFICULTIES:
            difficulty = "Medium"
        dup = Question.query.filter_by(class_level_id=cls.id, subject_id=subj.id,
                                       chapter_id=ch.id, qtype=qtype, source=source,
                                       text=text).first()
        if dup:
            err("This exact question is already in the bank — skipped.")
            continue
        try:
            marks = int(float(str(row.get("Marks") or 1) or 1))
        except (TypeError, ValueError):
            marks = 1
        q = Question(class_level_id=cls.id, subject_id=subj.id, chapter_id=ch.id,
                     qtype=qtype, source=source, text=text, format=fmt,
                     difficulty=difficulty, marks=max(marks, 0),
                     answer=str(row.get("Answer") or "").strip())
        if qtype == "MCQ":
            opts = [str(row.get(f"Option {L}") or "").strip() for L in "ABCD"]
            if any(not o for o in opts):
                err("MCQ needs all 4 options (A–D) — row skipped.")
                db.session.rollback()
                continue
            correct = str(row.get("Correct Option") or "A").strip().upper()[:1]
            if correct not in "ABCD":
                err("Correct Option must be A, B, C or D — row skipped.")
                db.session.rollback()
                continue
            q.options_json = json.dumps(opts)
            q.correct_option = correct
        db.session.add(q)
        try:
            db.session.commit()
            imported += 1
        except Exception as e:
            db.session.rollback()
            err(f"Could not save: {e}")
    return imported, errors


@app.route("/admin/questions/import", methods=["GET", "POST"])
@login_required
@admin_required
def question_import():
    if request.method == "POST":
        f = request.files.get("file")
        if not f or not f.filename:
            flash("Please choose an Excel (.xlsx) or CSV file to upload.", "error")
            return render_template("question_import.html", columns=IMPORT_COLUMNS)
        try:
            rows = _read_import_file(f)
        except Exception as e:
            flash(f"Could not read that file: {e}", "error")
            return render_template("question_import.html", columns=IMPORT_COLUMNS)
        if not rows:
            flash("No questions found in the file — did you keep the heading row?", "error")
            return render_template("question_import.html", columns=IMPORT_COLUMNS)
        imported, errors = _import_question_rows(rows)
        log_activity("questions_imported", f"{imported} questions from {f.filename}")
        return render_template("question_import.html", columns=IMPORT_COLUMNS,
                               imported=imported, total=len(rows), errors=errors)
    return render_template("question_import.html", columns=IMPORT_COLUMNS)


@app.route("/admin/questions/import/template")
@login_required
@admin_required
def question_import_template():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Questions"
    ws.append(IMPORT_COLUMNS)
    ws.append(["Class 9th", "Physics", "Physical Quantities and Measurement", 1,
               "MCQ", "Theory", "General", "Easy", 1,
               "What is the SI unit of force?",
               "Newton", "Joule", "Watt", "Pascal", "A",
               "Newton — named after Isaac Newton."])
    ws.append(["Class 9th", "Physics", "Physical Quantities and Measurement", 1,
               "Short", "Exercise", "General", "Medium", 2,
               "Define a physical quantity and give two examples.",
               "", "", "", "", "",
               "A quantity that can be measured, e.g. length and mass."])
    for col in range(1, len(IMPORT_COLUMNS) + 1):
        ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = 18
    ws.column_dimensions["I"].width = 55
    ws.column_dimensions["O"].width = 40
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     as_attachment=True, download_name="question-import-template.xlsx")


@app.route("/api/subjects/<int:cid>")
@login_required
def api_subjects(cid):
    return jsonify([{"id": s.id, "name": s.name}
                    for s in Subject.query.filter_by(class_level_id=cid).all()])


@app.route("/api/chapters/<int:sid>")
@login_required
def api_chapters(sid):
    return jsonify([{"id": c.id, "name": c.name, "number": c.number}
                    for c in Chapter.query.filter_by(subject_id=sid).order_by(Chapter.number).all()])


# ---------------- Paper generator ----------------
TYPE_MARKS_DEFAULT = {"MCQ": 1, "Short": 2, "Long": 5, "Numerical": 4}
TYPE_LABEL = {"MCQ": "MCQs", "Short": "Short Questions", "Long": "Long Questions",
              "Numerical": "Numericals"}
QTY_FIELDS = [("MCQ", "mcq_theory", "mcq_exercise"),
              ("Short", "short_theory", "short_exercise"),
              ("Long", "long_theory", "long_exercise"),
              ("Numerical", "num_theory", "num_exercise")]


def _chapter_ids_for_scope(scope, subject_id, chapter_ids):
    all_ch = Chapter.query.filter_by(subject_id=subject_id).order_by(Chapter.number).all()
    if scope == "full":
        return [c.id for c in all_ch]
    if scope == "half":
        half = (len(all_ch) + 1) // 2
        return [c.id for c in all_ch[:half]]
    if scope in ("one", "multiple", "custom"):
        return [int(x) for x in chapter_ids if str(x).isdigit()]
    return [c.id for c in all_ch]


def _pick_questions(chapter_ids, qtype, source, difficulty, n, exclude_ids, fmt=None):
    q = Question.query.filter(Question.chapter_id.in_(chapter_ids),
                              Question.qtype == qtype, Question.source == source)
    if fmt and fmt != "Any":
        q = q.filter(Question.format == fmt)
    if difficulty in ("Easy", "Medium", "Hard"):
        q = q.filter_by(difficulty=difficulty)
    if exclude_ids:
        q = q.filter(~Question.id.in_(exclude_ids))
    pool = q.all()
    random.shuffle(pool)
    return pool[:n], len(pool)


def _snapshot_question(qq, marks, section=""):
    ch = db.session.get(Chapter, qq.chapter_id)
    return {"id": qq.id, "text": qq.text, "qtype": qq.qtype,
            "source": qq.source, "marks": marks,
            "options": qq.options, "correct_option": qq.correct_option,
            "answer": qq.answer or "", "chapter": ch.name if ch else "",
            "format": qq.format or "General", "section": section}


@app.route("/generator", methods=["GET", "POST"])
@login_required
def generator():
    classes = ClassLevel.query.order_by(ClassLevel.sort_order).all()
    if request.method == "POST":
        cid = request.form.get("class_level_id", type=int)
        sid = request.form.get("subject_id", type=int)
        scope = request.form.get("scope", "full")
        chapter_ids = request.form.getlist("chapter_ids")
        difficulty = request.form.get("difficulty", "Mixed")
        title = (request.form.get("title") or "Test Paper").strip()
        duration = request.form.get("duration_minutes", type=int) or 60
        instructions = (request.form.get("instructions") or "").strip()
        paper_date = request.form.get("paper_date") or date.today().isoformat()
        variant = request.form.get("variant") or "A"
        allow_short = request.form.get("allow_short") == "1"
        if not (cid and sid):
            flash("Select a class and a subject.", "error")
            return render_template("generator.html", classes=classes)
        ch_ids = _chapter_ids_for_scope(scope, sid, chapter_ids)
        if not ch_ids:
            flash("Select at least one chapter.", "error")
            return render_template("generator.html", classes=classes)
        marks_per = {t: (request.form.get(f"marks_{t.lower()}", type=int)
                         or TYPE_MARKS_DEFAULT[t]) for t in QTYPES}
        selected, shortfalls = [], []
        used = set()
        for qtype, f_th, f_ex in QTY_FIELDS:
            for source, field in (("Theory", f_th), ("Exercise", f_ex)):
                n = request.form.get(field, type=int) or 0
                if n <= 0:
                    continue
                picked, avail = _pick_questions(ch_ids, qtype, source, difficulty, n, used)
                if len(picked) < n:
                    shortfalls.append(f"{TYPE_LABEL[qtype]} — {source}: asked {n}, only {avail} available")
                for qq in picked:
                    selected.append(_snapshot_question(qq, marks_per[qq.qtype]))
                    used.add(qq.id)
        # Custom "Add Section" blocks, e.g. Essay / Tashreeh / Translation.
        section_metas, preset_sections = [], []
        i = 0
        while f"sec_title_{i}" in request.form:
            sec_title = (request.form.get(f"sec_title_{i}") or "").strip()
            qtype = request.form.get(f"sec_qtype_{i}") or "Long"
            fmt = request.form.get(f"sec_format_{i}") or "Any"
            n_th = request.form.get(f"sec_theory_{i}", type=int) or 0
            n_ex = request.form.get(f"sec_exercise_{i}", type=int) or 0
            marks = request.form.get(f"sec_marks_{i}", type=int) or TYPE_MARKS_DEFAULT.get(qtype, 5)
            attempt = request.form.get(f"sec_attempt_{i}", type=int) or 0
            preset_sections.append({"title": sec_title, "qtype": qtype, "format": fmt,
                                    "theory": n_th, "exercise": n_ex,
                                    "marks": marks, "attempt": attempt})
            i += 1
            if not sec_title or qtype not in QTYPES:
                continue
            meta = {"title": sec_title, "qtype": qtype,
                    "format": fmt if fmt in FORMATS else "Any",
                    "theory": n_th, "exercise": n_ex, "marks": marks,
                    "attempt": attempt or None}
            section_metas.append(meta)
            for source, n in (("Theory", n_th), ("Exercise", n_ex)):
                if n <= 0:
                    continue
                picked, avail = _pick_questions(ch_ids, qtype, source, difficulty,
                                                n, used, meta["format"])
                if len(picked) < n:
                    shortfalls.append(f"{sec_title} — {source}: asked {n}, only {avail} available")
                for qq in picked:
                    selected.append(_snapshot_question(qq, marks, section=sec_title))
                    used.add(qq.id)
        if shortfalls and not allow_short:
            # Do NOT silently make a short paper: show the warning and ask to confirm.
            return render_template("generator.html", classes=classes, formats=FORMATS,
                                   shortfalls=shortfalls, form_data=request.form,
                                   preset_sections=preset_sections)
        # "Attempt any N out of M" choice, per question type (e.g. Short: any 5 of 8).
        attempts = {}
        for qtype in QTYPES:
            a = request.form.get(f"attempt_{qtype.lower()}", type=int) or 0
            if a:
                attempts[qtype] = a
        for qtype, n in attempts.items():
            have = sum(1 for q in selected if q["qtype"] == qtype and not q.get("section"))
            if n > have:
                flash(f"Attempt any {n} for {TYPE_LABEL[qtype]} is more than the {have} questions in that section — lower it or add more questions first.", "error")
                return render_template("generator.html", classes=classes, formats=FORMATS,
                                       form_data=request.form, preset_sections=preset_sections)
        for sec in section_metas:
            have = sum(1 for q in selected if q.get("section") == sec["title"])
            if sec["attempt"] and sec["attempt"] > have:
                flash(f"Section '{sec['title']}': attempt any {sec['attempt']} is more than the {have} questions in that section — lower it or add more questions first.", "error")
                return render_template("generator.html", classes=classes, formats=FORMATS,
                                       form_data=request.form, preset_sections=preset_sections)
        total = _paper_total(selected, attempts, section_metas)
        if not selected:
            flash("No questions selected — set at least one quantity above 0.", "error")
            return render_template("generator.html", classes=classes, formats=FORMATS)
        paper = Paper(title=title, teacher_id=current_user.id, class_level_id=cid,
                      subject_id=sid, variant=variant, total_marks=total,
                      duration_minutes=duration, instructions=instructions,
                      paper_date=paper_date, questions_json=json.dumps(selected),
                      attempt_json=json.dumps(attempts),
                      sections_json=json.dumps(section_metas))
        db.session.add(paper)
        db.session.commit()
        log_activity("paper_generated", f"{title} ({total} marks)")
        if shortfalls:
            flash("Paper generated with fewer questions than asked: " + "; ".join(shortfalls), "warning")
        else:
            flash("Paper generated successfully.", "success")
        return redirect(url_for("paper_view", pid=paper.id))
    return render_template("generator.html", classes=classes, formats=FORMATS,
                           preset_sections=[])


@app.route("/generator/variant/<int:pid>", methods=["POST"])
@login_required
def paper_variant(pid):
    orig = db.session.get(Paper, pid) or abort(404)
    if not current_user.is_admin and orig.teacher_id != current_user.id:
        abort(403)
    variant = request.form.get("variant") or "B"
    # Re-pick different questions from the same buckets, excluding the originals.
    orig_qs = orig.questions
    used_ids = {q["id"] for q in orig_qs}
    ch_ids = list({db.session.get(Question, q["id"]).chapter_id
                   for q in orig_qs if db.session.get(Question, q["id"])})
    new_qs, total = [], 0
    fixed_qs = [q for q in orig_qs if not q.get("section")]
    for qtype in QTYPES:
        for source in SOURCES:
            bucket = [q for q in fixed_qs if q["qtype"] == qtype and q["source"] == source]
            if not bucket:
                continue
            picked, _ = _pick_questions(ch_ids, qtype, source, "Mixed", len(bucket), used_ids)
            # fall back to originals if the bank has no spares
            chosen = picked if len(picked) == len(bucket) else bucket
            for qq in chosen:
                if isinstance(qq, Question):
                    new_qs.append(_snapshot_question(qq, bucket[0]["marks"]))
                else:
                    new_qs.append(qq)
    # Custom sections: re-pick within each section's own format/counts.
    for sec in orig.sections:
        for source, n in (("Theory", sec.get("theory") or 0),
                          ("Exercise", sec.get("exercise") or 0)):
            if n <= 0:
                continue
            bucket = [q for q in orig_qs if q.get("section") == sec["title"]
                      and q["source"] == source]
            picked, _ = _pick_questions(ch_ids, sec["qtype"], source, "Mixed",
                                        n, used_ids, sec.get("format") or "Any")
            chosen = picked if len(picked) == n else [q for q in bucket]
            for qq in chosen:
                if isinstance(qq, Question):
                    new_qs.append(_snapshot_question(qq, sec["marks"], section=sec["title"]))
                    used_ids.add(qq.id)
                else:
                    new_qs.append(qq)
    total = _paper_total(new_qs, orig.attempts, orig.sections)
    paper = Paper(title=orig.title, teacher_id=orig.teacher_id,
                  class_level_id=orig.class_level_id, subject_id=orig.subject_id,
                  variant=variant, total_marks=total,
                  duration_minutes=orig.duration_minutes,
                  instructions=orig.instructions, paper_date=orig.paper_date,
                  questions_json=json.dumps(new_qs),
                  attempt_json=json.dumps(orig.attempts),
                  sections_json=json.dumps(orig.sections))
    db.session.add(paper)
    db.session.commit()
    flash(f"Paper {variant} created with a different question selection.", "success")
    return redirect(url_for("paper_view", pid=paper.id))


# ---------------- Papers: view / edit / history ----------------
def _get_paper(pid):
    p = db.session.get(Paper, pid) or abort(404)
    if not current_user.is_admin and p.teacher_id != current_user.id:
        abort(403)
    return p


@app.route("/papers/<int:pid>")
@login_required
def paper_view(pid):
    p = _get_paper(pid)
    return render_template("paper_view.html", paper=p, academy_name=ACADEMY_NAME)


@app.route("/papers/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def paper_edit(pid):
    p = _get_paper(pid)
    if request.method == "POST":
        action = request.form.get("action")
        qs = p.questions
        if action == "save":
            p.title = request.form.get("title") or p.title
            p.instructions = request.form.get("instructions") or ""
            p.duration_minutes = request.form.get("duration_minutes", type=int) or p.duration_minutes
            new_qs, total = [], 0
            for i, q in enumerate(qs):
                q["text"] = request.form.get(f"text_{i}", q["text"])
                q["marks"] = request.form.get(f"marks_{i}", type=int) or q["marks"]
                new_qs.append(q)
            p.questions_json = json.dumps(new_qs)
            p.total_marks = _paper_total(new_qs, p.attempts, p.sections)
            db.session.commit()
            flash("Paper saved.", "success")
            return redirect(url_for("paper_view", pid=p.id))
        if action == "remove":
            idx = int(request.form.get("idx", -1))
            if 0 <= idx < len(qs):
                qs.pop(idx)
                p.questions_json = json.dumps(qs)
                p.total_marks = _paper_total(qs, p.attempts, p.sections)
                db.session.commit()
                flash("Question removed.", "success")
        elif action == "move":
            idx = int(request.form.get("idx", -1))
            direction = int(request.form.get("dir", 0))
            j = idx + direction
            if 0 <= idx < len(qs) and 0 <= j < len(qs):
                qs[idx], qs[j] = qs[j], qs[idx]
                p.questions_json = json.dumps(qs)
                db.session.commit()
        elif action == "replace":
            idx = int(request.form.get("idx", -1))
            if 0 <= idx < len(qs):
                old = qs[idx]
                ch_ids = [c.id for c in Chapter.query.filter_by(
                    subject_id=p.subject_id).all()]
                # find chapter id of the old question
                orig = db.session.get(Question, old["id"])
                pool_ids = [orig.chapter_id] if orig else ch_ids
                used = {q["id"] for q in qs}
                picked, _ = _pick_questions(pool_ids, old["qtype"], old["source"],
                                            "Mixed", 1, used, old.get("format") or "Any")
                if picked:
                    qq = picked[0]
                    qs[idx] = _snapshot_question(qq, old["marks"],
                                                 section=old.get("section", ""))
                    p.questions_json = json.dumps(qs)
                    db.session.commit()
                    flash("Question replaced.", "success")
                else:
                    flash("No unused question available in that bucket.", "error")
        return redirect(url_for("paper_edit", pid=p.id))
    return render_template("paper_edit.html", paper=p)


@app.route("/papers/<int:pid>/duplicate", methods=["POST"])
@login_required
def paper_duplicate(pid):
    p = _get_paper(pid)
    copy = Paper(title=p.title + " (Copy)", teacher_id=current_user.id,
                 class_level_id=p.class_level_id, subject_id=p.subject_id,
                 variant=p.variant, total_marks=p.total_marks,
                 duration_minutes=p.duration_minutes, instructions=p.instructions,
                 paper_date=p.paper_date, questions_json=p.questions_json,
                 attempt_json=json.dumps(p.attempts),
                 sections_json=json.dumps(p.sections))
    db.session.add(copy)
    db.session.commit()
    flash("Paper copied.", "success")
    return redirect(url_for("paper_view", pid=copy.id))


@app.route("/papers/<int:pid>/delete", methods=["POST"])
@login_required
def paper_delete(pid):
    p = _get_paper(pid)
    db.session.delete(p)
    db.session.commit()
    flash("Paper deleted.", "success")
    return redirect(url_for("history"))


@app.route("/history")
@login_required
def history():
    q = Paper.query
    if not current_user.is_admin:
        q = q.filter_by(teacher_id=current_user.id)
    title = request.args.get("q", "").strip()
    cid = request.args.get("class_level_id", type=int)
    sid = request.args.get("subject_id", type=int)
    d = request.args.get("date", "").strip()
    if title:
        q = q.filter(Paper.title.ilike(f"%{title}%"))
    if cid:
        q = q.filter_by(class_level_id=cid)
    if sid:
        q = q.filter_by(subject_id=sid)
    if d:
        q = q.filter_by(paper_date=d)
    papers = q.order_by(Paper.created_at.desc()).all()
    classes = ClassLevel.query.order_by(ClassLevel.sort_order).all()
    return render_template("history.html", papers=papers, classes=classes,
                           sel=dict(q=title, cid=cid, sid=sid, d=d))


# ---------------- PDF export ----------------
def _urdu_font_available():
    for cand in (os.path.join(BASE_DIR, "static", "fonts", "NotoNastaliqUrdu-Regular.ttf"),
                 "/usr/share/fonts/truetype/noto/NotoNastaliqUrdu-Regular.ttf"):
        if os.path.exists(cand):
            return cand
    return None


@app.route("/papers/<int:pid>/pdf")
@login_required
def paper_pdf(pid):
    return _paper_pdf(pid, answer_key=False)


@app.route("/papers/<int:pid>/answer-key")
@login_required
def paper_answer_key(pid):
    return _paper_pdf(pid, answer_key=True)


def _paper_pdf(pid, answer_key=False):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, PageBreak)
    from reportlab.lib import colors

    p = _get_paper(pid)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            title=f"{p.title} - {'Answer Key' if answer_key else 'Paper'}")
    h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=16, alignment=TA_CENTER)
    sub = ParagraphStyle("sub", fontName="Helvetica", fontSize=11, alignment=TA_CENTER)
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=11, leading=15)
    bold = ParagraphStyle("bold", fontName="Helvetica-Bold", fontSize=12, leading=16)
    story = []
    story.append(Paragraph(ACADEMY_NAME, h))
    story.append(Paragraph("Test Paper" + (" — Answer Key" if answer_key else ""), sub))
    story.append(Spacer(1, 4 * mm))
    meta = [[f"Class: {p.class_level.name if p.class_level else ''}",
             f"Subject: {p.subject.name if p.subject else ''}"],
            [f"Date: {p.paper_date or ''}", f"Time: {p.duration_minutes} minutes"],
            [f"Paper: {p.variant}", f"Total Marks: {p.total_marks}"]]
    t = Table(meta, colWidths=[85 * mm, 85 * mm])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.black),
                           ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
                           ("LEFTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(t)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"<b>{p.title}</b>", sub))
    if p.instructions and not answer_key:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(f"<b>Instructions:</b> {p.instructions}", body))
    story.append(Spacer(1, 4 * mm))
    grouped = {}
    for qq in p.questions:
        if not qq.get("section"):
            grouped.setdefault(qq["qtype"], []).append(qq)
    attempts = p.attempts
    n = 0
    for qtype in QTYPES:
        items = grouped.get(qtype, [])
        if not items:
            continue
        heading = f"Section: {TYPE_LABEL[qtype]}"
        if attempts.get(qtype):
            heading += f" — Attempt any {attempts[qtype]} out of {len(items)}"
        story.append(Paragraph(heading, bold))
        story.append(Spacer(1, 2 * mm))
        for qq in items:
            n += 1
            story.append(Paragraph(f"Q{n}. {qq['text']} &nbsp; <b>[{qq['marks']} marks]</b>", body))
            if qtype == "MCQ" and qq.get("options"):
                for letter, opt in zip("ABCD", qq["options"]):
                    story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;({letter}) {opt}", body))
                if answer_key:
                    story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;<b>Answer: ({qq.get('correct_option', '')})</b>", body))
            elif answer_key and qq.get("answer"):
                story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;<b>Answer:</b> {qq['answer']}", body))
            story.append(Spacer(1, 2 * mm))
        story.append(Spacer(1, 2 * mm))
    # Custom sections (Essay, Tashreeh, ...) in the order they were added.
    for sec in p.sections:
        items = [q for q in p.questions if q.get("section") == sec["title"]]
        if not items:
            continue
        heading = f"Section: {sec['title']}"
        if sec.get("attempt"):
            heading += f" — Attempt any {sec['attempt']} out of {len(items)}"
        story.append(Paragraph(heading, bold))
        story.append(Spacer(1, 2 * mm))
        for qq in items:
            n += 1
            story.append(Paragraph(f"Q{n}. {qq['text']} &nbsp; <b>[{qq['marks']} marks]</b>", body))
            if qq["qtype"] == "MCQ" and qq.get("options"):
                for letter, opt in zip("ABCD", qq["options"]):
                    story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;({letter}) {opt}", body))
                if answer_key:
                    story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;<b>Answer: ({qq.get('correct_option', '')})</b>", body))
            elif answer_key and qq.get("answer"):
                story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;<b>Answer:</b> {qq['answer']}", body))
            story.append(Spacer(1, 2 * mm))
        story.append(Spacer(1, 2 * mm))
    if not answer_key:
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph("Name: ______________________ &nbsp;&nbsp; Roll No: __________", body))

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        canvas.drawCentredString(A4[0] / 2, 12 * mm, f"Page {doc_.page}  |  {ACADEMY_NAME}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buf.seek(0)
    fname = f"{p.title.replace(' ', '_')}_{'answer-key' if answer_key else 'paper'}.pdf"
    return send_file(buf, mimetype="application/pdf", as_attachment=True,
                     download_name=secure_filename(fname) or "paper.pdf")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
