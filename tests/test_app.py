"""Flask test-client checks for the Academy Test Generator.
Run:  python -m pytest tests/test_app.py -v   (or: python tests/test_app.py)
Uses a fresh temporary SQLite database; never touches production data.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.pop("ADMIN_EMAIL", None)
os.environ.pop("ADMIN_PASSWORD", None)

import app as appmod  # noqa: E402


def make_client():
    appmod.app.config["TESTING"] = True
    appmod.app.config["WTF_CSRF_ENABLED"] = False
    with appmod.app.app_context():
        appmod.db.drop_all()
        appmod.db.create_all()
        from seed import seed_all
        seed_all(appmod.db, appmod.ClassLevel, appmod.Subject, appmod.Chapter, appmod.Question)
        admin = appmod.User(name="Owner", email="admin@test.com", role="admin", is_active=True)
        admin.set_password("AdminPass123")
        teacher = appmod.User(name="Teacher One", email="teacher@test.com", role="teacher", is_active=True)
        teacher.set_password("TeachPass123")
        appmod.db.session.add_all([admin, teacher])
        appmod.db.session.commit()
    return appmod.app.test_client()


def login(c, email, pw):
    return c.post("/login", data={"email": email, "password": pw}, follow_redirects=True)


def test_no_registration_route():
    c = make_client()
    assert c.get("/register").status_code == 404
    assert c.get("/signup").status_code == 404
    assert c.post("/register", data={}).status_code in (404, 405)


def test_admin_login_and_teacher_login():
    c = make_client()
    assert b"Admin Dashboard" in login(c, "admin@test.com", "AdminPass123").data
    c2 = make_client()
    assert b"Teacher Dashboard" in login(c2, "teacher@test.com", "TeachPass123").data


def test_invalid_email_login_fails():
    c = make_client()
    r = login(c, "nobody@test.com", "whatever123")
    assert b"Invalid email or password" in r.data


def test_teacher_cannot_access_admin():
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    for url in ("/admin/teachers", "/admin/structure", "/admin/books",
                "/admin/activity", "/admin/settings", "/questions/new"):
        assert c.get(url).status_code == 403, url


def test_admin_can_add_teacher_and_disable_blocks_login():
    c = make_client()
    login(c, "admin@test.com", "AdminPass123")
    r = c.post("/admin/teachers/new", data={"name": "New Teacher", "email": "new@test.com",
                                            "password": "NewPass123"}, follow_redirects=True)
    assert b"New Teacher" in r.data
    with appmod.app.app_context():
        t = appmod.User.query.filter_by(email="new@test.com").first()
        assert t is not None
        c.post(f"/admin/teachers/{t.id}/toggle", follow_redirects=True)
    # fresh client, disabled teacher must fail to log in
    client2 = appmod.app.test_client()
    r = login(client2, "new@test.com", "NewPass123")
    assert b"disabled" in r.data.lower() or b"Invalid" in r.data


def test_password_change():
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    r = c.post("/change-password", data={"current": "TeachPass123", "new": "NewTeach123",
                                        "new2": "NewTeach123"}, follow_redirects=True)
    assert b"Password changed" in r.data
    c.get("/logout")
    assert b"Teacher Dashboard" in login(c, "teacher@test.com", "NewTeach123").data


def test_question_creation_and_theory_exercise_separation():
    c = make_client()
    login(c, "admin@test.com", "AdminPass123")
    with appmod.app.app_context():
        ch = appmod.Chapter.query.first()
        payload = {"class_level_id": ch.subject.class_level_id, "subject_id": ch.subject_id,
                   "chapter_id": ch.id, "qtype": "MCQ", "source": "Exercise",
                   "text": "Test MCQ from exercise?", "difficulty": "Easy", "marks": 1,
                   "opt1": "A1", "opt2": "A2", "opt3": "A3", "opt4": "A4", "correct_option": "B",
                   "answer": "A2 is correct."}
        r = c.post("/questions/new", data=payload, follow_redirects=True)
        assert b"Question added" in r.data
        assert appmod.Question.query.filter_by(source="Exercise", qtype="MCQ").count() >= 1
        assert appmod.Question.query.filter_by(source="Theory").count() >= 1


def test_paper_generation_marks_and_pdf_and_history():
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="Physics", class_level_id=cl.id).first()
        data = {"title": "Test Paper 1", "class_level_id": cl.id, "subject_id": subj.id,
                "scope": "full", "difficulty": "Mixed", "duration_minutes": 60,
                "paper_date": "2026-11-24", "variant": "A",
                "mcq_theory": 2, "mcq_exercise": 1, "short_theory": 1, "short_exercise": 0,
                "long_theory": 0, "long_exercise": 0, "num_theory": 0, "num_exercise": 0,
                "marks_mcq": 1, "marks_short": 2, "marks_long": 5, "marks_numerical": 4,
                "instructions": "Attempt all questions."}
        r = c.post("/generator", data=data, follow_redirects=True)
        assert b"Test Paper 1" in r.data
        paper = appmod.Paper.query.filter_by(title="Test Paper 1").first()
        assert paper is not None
        # marks: 3 MCQs x 1 + 1 short x 2 = 5
        assert paper.total_marks == 5, paper.total_marks
        qs = paper.questions
        assert sum(1 for q in qs if q["qtype"] == "MCQ" and q["source"] == "Theory") == 2
        assert sum(1 for q in qs if q["qtype"] == "MCQ" and q["source"] == "Exercise") == 1
        # PDF download returns a real PDF
        pdf = c.get(f"/papers/{paper.id}/pdf")
        assert pdf.status_code == 200
        assert pdf.data[:4] == b"%PDF"
        key = c.get(f"/papers/{paper.id}/answer-key")
        assert key.status_code == 200 and key.data[:4] == b"%PDF"
        # history lists it
        assert b"Test Paper 1" in c.get("/history").data
        # shortfall warning: ask for far more than exist
        data2 = dict(data, title="Impossible Paper", mcq_theory=99, mcq_exercise=99)
        r2 = c.post("/generator", data=data2, follow_redirects=True)
        assert b"Not enough questions" in r2.data
        assert appmod.Paper.query.filter_by(title="Impossible Paper").first() is None


def test_excel_import_template_and_upload():
    import io as _io
    from openpyxl import Workbook, load_workbook
    c = make_client()
    login(c, "admin@test.com", "AdminPass123")
    # template downloads as a real .xlsx with the right headings
    t = c.get("/admin/questions/import/template")
    assert t.status_code == 200
    assert "spreadsheetml" in t.headers.get("Content-Type", "")
    wb = load_workbook(filename=_io.BytesIO(t.data), read_only=True)
    assert list(next(wb.active.iter_rows(values_only=True)))[:3] == ["Class", "Subject", "Chapter"]
    # build an upload: 1 good MCQ, 1 good Short in a NEW chapter, 1 bad row
    wb2 = Workbook()
    ws = wb2.active
    ws.append(["Class", "Subject", "Chapter", "Chapter No", "Type", "Source",
               "Difficulty", "Marks", "Question", "Option A", "Option B",
               "Option C", "Option D", "Correct Option", "Answer"])
    ws.append(["Class 9th", "Physics", "Kinematics", 2, "MCQ", "Theory", "Easy", 1,
               "Import test MCQ?", "1", "2", "3", "4", "B", "2 it is."])
    ws.append(["Class 9th", "Physics", "Brand New Chapter", 99, "Short", "Exercise",
               "Medium", 2, "Import test short?", "", "", "", "", "", "Short answer."])
    ws.append(["Class 9th", "Physics", "Kinematics", 2, "Essay", "Theory", "Easy", 1,
               "Bad type row?", "", "", "", "", "", ""])
    buf = _io.BytesIO()
    wb2.save(buf)
    data_bytes = buf.getvalue()
    buf.seek(0)
    with appmod.app.app_context():
        before = appmod.Question.query.count()
    r = c.post("/admin/questions/import", data={"file": (buf, "questions.xlsx")},
               content_type="multipart/form-data", follow_redirects=True)
    assert b"2 of 3 questions imported" in r.data, r.data[:500]
    assert b"Row 4" in r.data  # bad row reported
    with appmod.app.app_context():
        assert appmod.Question.query.count() == before + 2
        assert appmod.Question.query.filter_by(text="Import test MCQ?").first() is not None
        assert appmod.Chapter.query.filter_by(name="Brand New Chapter").first() is not None
    # re-uploading the same file imports 0 new (duplicates skipped)
    buf2 = _io.BytesIO(data_bytes)
    r2 = c.post("/admin/questions/import", data={"file": (buf2, "questions.xlsx")},
                content_type="multipart/form-data", follow_redirects=True)
    assert b"0 of 3 questions imported" in r2.data


def test_teacher_cannot_import_questions():
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    assert c.get("/admin/questions/import").status_code == 403
    assert c.get("/admin/questions/import/template").status_code == 403


def test_setup_locks_after_admin_exists():
    c = make_client()
    r = c.get("/setup", follow_redirects=True)
    assert b"already exists" in r.data.lower() or b"Login" in r.data


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            print("RUN", name)
            fn()
            print("PASS", name)
    print("ALL TESTS PASSED")
