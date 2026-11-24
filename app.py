
import os, sqlite3, secrets
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "academy.db")
UPLOAD_DIR = os.path.join(BASE, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE", "0") == "1"
ALLOWED = {"pdf"}

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con

def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
      password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','teacher')),
      active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS classes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS subjects(
      id INTEGER PRIMARY KEY AUTOINCREMENT, class_id INTEGER NOT NULL,
      name TEXT NOT NULL, FOREIGN KEY(class_id) REFERENCES classes(id) ON DELETE CASCADE,
      UNIQUE(class_id,name)
    );
    CREATE TABLE IF NOT EXISTS chapters(
      id INTEGER PRIMARY KEY AUTOINCREMENT, subject_id INTEGER NOT NULL,
      name TEXT NOT NULL, FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
      UNIQUE(subject_id,name)
    );
    CREATE TABLE IF NOT EXISTS books(
      id INTEGER PRIMARY KEY AUTOINCREMENT, chapter_id INTEGER NOT NULL,
      filename TEXT NOT NULL, original_name TEXT NOT NULL, uploaded_at TEXT NOT NULL,
      FOREIGN KEY(chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS questions(
      id INTEGER PRIMARY KEY AUTOINCREMENT, chapter_id INTEGER NOT NULL,
      qtype TEXT NOT NULL, source TEXT NOT NULL CHECK(source IN ('Theory','Exercise')),
      difficulty TEXT NOT NULL, question TEXT NOT NULL, answer TEXT DEFAULT '',
      marks INTEGER NOT NULL DEFAULT 1, created_by INTEGER,
      created_at TEXT NOT NULL,
      FOREIGN KEY(chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
      FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS papers(
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, class_name TEXT NOT NULL,
      subject_name TEXT NOT NULL, chapter_name TEXT NOT NULL, difficulty TEXT NOT NULL,
      total_marks INTEGER NOT NULL, duration INTEGER NOT NULL, created_by INTEGER,
      created_at TEXT NOT NULL,
      FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS paper_questions(
      paper_id INTEGER NOT NULL, question_id INTEGER NOT NULL, order_no INTEGER NOT NULL,
      FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE CASCADE,
      FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
    );
    """)
    # Exactly one administrator is bootstrapped. Public registration is not provided.
    if not con.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone():
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@academy.local").strip().lower()
        admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@12345")
        if len(admin_password) < 8:
            raise RuntimeError("ADMIN_PASSWORD must be at least 8 characters")
        con.execute("INSERT INTO users(name,email,password,role,active,created_at) VALUES(?,?,?,?,1,?)",
                    ("Main Admin", admin_email, generate_password_hash(admin_password), "admin", datetime.now().isoformat(timespec="minutes")))
    for cname in ["9th Class","10th Class","11th Class","12th Class"]:
        con.execute("INSERT OR IGNORE INTO classes(name) VALUES(?)",(cname,))
    con.commit()
    con.close()

init_db()

def current_user():
    if "uid" not in session: return None
    con=db(); u=con.execute("SELECT * FROM users WHERE id=? AND active=1",(session["uid"],)).fetchone(); con.close()
    return u

def login_required(fn):
    @wraps(fn)
    def wrapper(*a,**kw):
        if not current_user(): return redirect(url_for("login"))
        return fn(*a,**kw)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*a,**kw):
        u=current_user()
        if not u: return redirect(url_for("login"))
        if u["role"]!="admin": abort(403)
        return fn(*a,**kw)
    return wrapper

@app.context_processor
def inject_user():
    return {"me": current_user()}

@app.route("/service-worker.js")
def service_worker():
    response = send_from_directory(os.path.join(BASE, "static"), "sw.js", mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response

@app.route("/")
def home():
    if current_user(): return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        con=db(); u=con.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone(); con.close()
        if u and u["active"] and check_password_hash(u["password"],password):
            session.clear(); session["uid"]=u["id"]
            return redirect(url_for("dashboard"))
        flash("Email/password ghalat hai ya account inactive hai.","error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

@app.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        old = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        con = db()
        user = con.execute("SELECT * FROM users WHERE id=?", (session["uid"],)).fetchone()
        if not user or not check_password_hash(user["password"], old):
            flash("Current password ghalat hai.", "error")
        elif len(new) < 10:
            flash("Naya password kam az kam 10 characters ka rakhein.", "error")
        elif new != confirm:
            flash("New password aur confirmation match nahi karte.", "error")
        else:
            con.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(new), session["uid"]))
            con.commit()
            session.clear()
            con.close()
            flash("Password update ho gaya. Naye password se dobara login karein.", "success")
            return redirect(url_for("login"))
        con.close()
    return render_template("password.html")

@app.route("/dashboard")
@login_required
def dashboard():
    con=db()
    stats={
      "users":con.execute("SELECT COUNT(*) n FROM users WHERE role='teacher' AND active=1").fetchone()["n"],
      "classes":con.execute("SELECT COUNT(*) n FROM classes").fetchone()["n"],
      "questions":con.execute("SELECT COUNT(*) n FROM questions").fetchone()["n"],
      "papers":con.execute("SELECT COUNT(*) n FROM papers").fetchone()["n"]
    }
    recent=con.execute("""SELECT p.*,u.name creator FROM papers p LEFT JOIN users u ON p.created_by=u.id ORDER BY p.id DESC LIMIT 8""").fetchall()
    con.close()
    return render_template("dashboard.html",stats=stats,recent=recent)

@app.route("/users", methods=["GET","POST"])
@admin_required
def users():
    con=db()
    if request.method=="POST":
        name=request.form.get("name","").strip(); email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        if not name or not email or len(password)<8:
            flash("Name/email zaroori hain aur password kam az kam 8 characters ka ho.","error")
        else:
            try:
                con.execute("INSERT INTO users(name,email,password,role,active,created_at) VALUES(?,?,?,'teacher',1,?)",
                    (name,email,generate_password_hash(password),datetime.now().isoformat(timespec="minutes")))
                con.commit(); flash("Teacher account create ho gaya. Login details teacher ko securely share karein.","success")
            except sqlite3.IntegrityError: flash("Is email ka account pehle se mojood hai.","error")
    rows=con.execute("SELECT id,name,email,active,created_at FROM users WHERE role='teacher' ORDER BY id DESC").fetchall()
    con.close(); return render_template("users.html",users=rows)

@app.route("/users/<int:uid>/toggle",methods=["POST"])
@admin_required
def toggle_user(uid):
    con=db(); con.execute("UPDATE users SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=? AND role='teacher'",(uid,)); con.commit(); con.close()
    flash("Account status update ho gaya.","success"); return redirect(url_for("users"))

@app.route("/library",methods=["GET","POST"])
@login_required
def library():
    con=db()
    if request.method=="POST":
        action=request.form.get("action")
        try:
            if action=="class":
                con.execute("INSERT INTO classes(name) VALUES(?)",(request.form["name"].strip(),))
            elif action=="subject":
                con.execute("INSERT INTO subjects(class_id,name) VALUES(?,?)",(request.form["class_id"],request.form["name"].strip()))
            elif action=="chapter":
                con.execute("INSERT INTO chapters(subject_id,name) VALUES(?,?)",(request.form["subject_id"],request.form["name"].strip()))
            con.commit(); flash("Syllabus item add ho gaya.","success")
        except sqlite3.IntegrityError: flash("Ye item pehle se mojood hai.","error")
    classes=con.execute("SELECT * FROM classes ORDER BY name").fetchall()
    subjects=con.execute("SELECT s.*,c.name class_name FROM subjects s JOIN classes c ON c.id=s.class_id ORDER BY c.name,s.name").fetchall()
    chapters=con.execute("SELECT ch.*,s.name subject_name,c.name class_name FROM chapters ch JOIN subjects s ON s.id=ch.subject_id JOIN classes c ON c.id=s.class_id ORDER BY c.name,s.name,ch.name").fetchall()
    con.close(); return render_template("library.html",classes=classes,subjects=subjects,chapters=chapters)

@app.route("/books",methods=["GET","POST"])
@login_required
def books():
    con=db()
    if request.method=="POST":
        f=request.files.get("book"); cid=request.form.get("chapter_id")
        if not f or not f.filename:
            flash("PDF file select karein.","error")
        elif not f.filename.lower().endswith(".pdf"):
            flash("Sirf PDF files allowed hain.","error")
        else:
            safe=secure_filename(f.filename)
            stored=secrets.token_hex(8)+"_"+safe
            f.save(os.path.join(UPLOAD_DIR,stored))
            con.execute("INSERT INTO books(chapter_id,filename,original_name,uploaded_at) VALUES(?,?,?,?)",
                (cid,stored,f.filename,datetime.now().isoformat(timespec="minutes")))
            con.commit(); flash("Book PDF upload ho gayi. Abhi PDF storage ke liye hai; automatic AI extraction next integration stage hai.","success")
    rows=con.execute("""SELECT b.*,ch.name chapter_name,s.name subject_name,c.name class_name
      FROM books b JOIN chapters ch ON ch.id=b.chapter_id JOIN subjects s ON s.id=ch.subject_id
      JOIN classes c ON c.id=s.class_id ORDER BY b.id DESC""").fetchall()
    chapters=con.execute("""SELECT ch.id,ch.name,s.name subject_name,c.name class_name FROM chapters ch
      JOIN subjects s ON s.id=ch.subject_id JOIN classes c ON c.id=s.class_id ORDER BY c.name,s.name,ch.name""").fetchall()
    con.close(); return render_template("books.html",books=rows,chapters=chapters)

@app.route("/books/<int:bid>")
@login_required
def download_book(bid):
    con=db(); row=con.execute("SELECT * FROM books WHERE id=?",(bid,)).fetchone(); con.close()
    if not row: abort(404)
    return send_from_directory(UPLOAD_DIR,row["filename"],as_attachment=True,download_name=row["original_name"])

@app.route("/questions",methods=["GET","POST"])
@login_required
def questions():
    con=db()
    if request.method=="POST":
        q=request.form.get("question","").strip()
        if q:
            con.execute("""INSERT INTO questions(chapter_id,qtype,source,difficulty,question,answer,marks,created_by,created_at)
              VALUES(?,?,?,?,?,?,?,?,?)""",(request.form["chapter_id"],request.form["qtype"],request.form["source"],
              request.form["difficulty"],q,request.form.get("answer","").strip(),int(request.form.get("marks",1)),session["uid"],
              datetime.now().isoformat(timespec="minutes")))
            con.commit(); flash("Question bank mein question add ho gaya.","success")
    chapters=con.execute("""SELECT ch.id,ch.name chapter_name,s.name subject_name,c.name class_name FROM chapters ch
      JOIN subjects s ON s.id=ch.subject_id JOIN classes c ON c.id=s.class_id ORDER BY c.name,s.name,ch.name""").fetchall()
    rows=con.execute("""SELECT q.*,ch.name chapter_name,s.name subject_name,c.name class_name FROM questions q
      JOIN chapters ch ON ch.id=q.chapter_id JOIN subjects s ON s.id=ch.subject_id JOIN classes c ON c.id=s.class_id
      ORDER BY q.id DESC LIMIT 100""").fetchall()
    con.close(); return render_template("questions.html",chapters=chapters,questions=rows)

@app.route("/questions/<int:qid>/delete",methods=["POST"])
@login_required
def delete_question(qid):
    con=db(); con.execute("DELETE FROM questions WHERE id=?",(qid,)); con.commit(); con.close()
    flash("Question delete ho gaya.","success"); return redirect(url_for("questions"))

@app.route("/generate",methods=["GET","POST"])
@login_required
def generate():
    con=db()
    chapters=con.execute("""SELECT ch.id,ch.name chapter_name,s.name subject_name,c.name class_name FROM chapters ch
      JOIN subjects s ON s.id=ch.subject_id JOIN classes c ON c.id=s.class_id ORDER BY c.name,s.name,ch.name""").fetchall()
    paper=None; selected=[]
    if request.method=="POST":
        cid=int(request.form["chapter_id"]); difficulty=request.form.get("difficulty","Mixed")
        groups=[
          ("MCQ","mcq_theory","mcq_exercise"),
          ("Short","short_theory","short_exercise"),
          ("Long","long_theory","long_exercise"),
          ("Numerical","num_theory","num_exercise")]
        chosen=[]
        for qtype,tid,eid in groups:
            for source,field in [("Theory",tid),("Exercise",eid)]:
                qty=max(0,min(100,int(request.form.get(field,0) or 0)))
                if qty:
                    sql="SELECT * FROM questions WHERE chapter_id=? AND qtype=? AND source=?"
                    args=[cid,qtype,source]
                    if difficulty!="Mixed": sql+=" AND difficulty=?"; args.append(difficulty)
                    found=con.execute(sql+" ORDER BY RANDOM() LIMIT ?",(*args,qty)).fetchall()
                    if len(found)<qty:
                        flash(f"{qtype} ({source}) ke liye sirf {len(found)} questions available hain; {qty} required thay.","error")
                    chosen.extend(found)
        if chosen:
            ch=con.execute("""SELECT ch.name chapter_name,s.name subject_name,c.name class_name FROM chapters ch
              JOIN subjects s ON s.id=ch.subject_id JOIN classes c ON c.id=s.class_id WHERE ch.id=?""",(cid,)).fetchone()
            marks=sum(q["marks"] for q in chosen)
            title=request.form.get("title","").strip() or f"{ch['subject_name']} Chapter Test"
            cur=con.execute("""INSERT INTO papers(title,class_name,subject_name,chapter_name,difficulty,total_marks,duration,created_by,created_at)
              VALUES(?,?,?,?,?,?,?,?,?)""",(title,ch["class_name"],ch["subject_name"],ch["chapter_name"],difficulty,marks,
              int(request.form.get("duration",60)),session["uid"],datetime.now().isoformat(timespec="minutes")))
            pid=cur.lastrowid
            for i,q in enumerate(chosen,1): con.execute("INSERT INTO paper_questions VALUES(?,?,?)",(pid,q["id"],i))
            con.commit()
            return redirect(url_for("paper",pid=pid))
    con.close()
    return render_template("generate.html",chapters=chapters)

@app.route("/paper/<int:pid>")
@login_required
def paper(pid):
    con=db()
    p=con.execute("SELECT * FROM papers WHERE id=?",(pid,)).fetchone()
    if not p: abort(404)
    qs=con.execute("""SELECT q.* FROM paper_questions pq JOIN questions q ON q.id=pq.question_id
      WHERE pq.paper_id=? ORDER BY pq.order_no""",(pid,)).fetchall()
    con.close(); return render_template("paper.html",paper=p,questions=qs)

@app.route("/history")
@login_required
def history():
    con=db()
    rows=con.execute("""SELECT p.*,u.name creator FROM papers p LEFT JOIN users u ON u.id=p.created_by ORDER BY p.id DESC""").fetchall()
    con.close(); return render_template("history.html",papers=rows)

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
