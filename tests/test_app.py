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


def test_admin_password_resets_from_env_vars():
    """The WSGI env vars are the admin password's source of truth: changing
    ADMIN_PASSWORD + Reload resets it (previously the env password was only
    read when the admin was first created, so a forgotten password could
    never be fixed from the WSGI file)."""
    c = make_client()
    assert b"Admin Dashboard" in login(c, "admin@test.com", "AdminPass123").data
    os.environ["ADMIN_EMAIL"] = "admin@test.com"
    os.environ["ADMIN_PASSWORD"] = "NewPass456"
    try:
        with appmod.app.app_context():
            assert appmod.ensure_admin_from_env() is True
            assert appmod.ensure_admin_from_env() is False  # already in sync
    finally:
        os.environ.pop("ADMIN_EMAIL", None)
        os.environ.pop("ADMIN_PASSWORD", None)
    fresh = appmod.app.test_client()
    assert b"Admin Dashboard" in login(fresh, "admin@test.com", "NewPass456").data
    assert b"Invalid email or password" in login(
        appmod.app.test_client(), "admin@test.com", "AdminPass123").data


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


def test_attempt_any_choice_total_and_pdf():
    """Choice: 8 Short questions in the paper, students attempt any 5 —
    total marks count only the 5 attempted, and the PDF says so."""
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="Physics", class_level_id=cl.id).first()
        data = {"title": "Choice Paper", "class_level_id": cl.id, "subject_id": subj.id,
                "scope": "full", "difficulty": "Mixed", "duration_minutes": 60,
                "paper_date": "2026-11-25", "variant": "A",
                "mcq_theory": 2, "mcq_exercise": 0, "short_theory": 4, "short_exercise": 4,
                "long_theory": 0, "long_exercise": 0, "num_theory": 0, "num_exercise": 0,
                "attempt_short": 5, "attempt_mcq": 0,
                "marks_mcq": 1, "marks_short": 2, "marks_long": 5, "marks_numerical": 4,
                "instructions": "Attempt all questions."}
        r = c.post("/generator", data=data, follow_redirects=True)
        assert b"Choice Paper" in r.data
        paper = appmod.Paper.query.filter_by(title="Choice Paper").first()
        assert paper is not None
        assert len(paper.questions) == 10  # all 8 Short + 2 MCQ are printed
        assert paper.attempts == {"Short": 5}
        # total marks: 5 Short x 2 + 2 MCQ x 1 = 12 (not 8x2+2)
        assert paper.total_marks == 12, paper.total_marks
        assert b"Attempt any 5 out of 8" in r.data
        pdf = c.get(f"/papers/{paper.id}/pdf")
        assert pdf.status_code == 200 and pdf.data[:4] == b"%PDF"
        # attempt more than the section has -> refused, no paper created
        data2 = dict(data, title="Bad Choice Paper", attempt_short=9)
        r2 = c.post("/generator", data=data2, follow_redirects=True)
        assert b"more than the 8 questions" in r2.data
        assert appmod.Paper.query.filter_by(title="Bad Choice Paper").first() is None


def test_custom_section_essay_with_choice_and_variant():
    """Add Section: an Essay section (3 Long Essay questions, attempt any 1)
    sits beside the normal MCQs; totals, view, PDF and variant all keep it."""
    c = make_client()
    login(c, "admin@test.com", "AdminPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="English", class_level_id=cl.id).first()
        ch = appmod.Chapter.query.filter_by(subject_id=subj.id).order_by(appmod.Chapter.number).first()
        for i, topic in enumerate(["My Best Friend", "A Visit to a Museum", "My Aim in Life"]):
            r = c.post("/questions/new", data={
                "class_level_id": cl.id, "subject_id": subj.id, "chapter_id": ch.id,
                "qtype": "Long", "source": "Theory", "format": "Essay",
                "text": f"Write an essay on {topic}.", "difficulty": "Medium",
                "marks": 10, "answer": f"Outline for {topic}."}, follow_redirects=True)
            assert b"Question added" in r.data
        # one more essay saved as Exercise — writing sections ignore Theory/Exercise
        r = c.post("/questions/new", data={
            "class_level_id": cl.id, "subject_id": subj.id, "chapter_id": ch.id,
            "qtype": "Long", "source": "Exercise", "format": "Essay",
            "text": "Write an essay on My School.", "difficulty": "Medium",
            "marks": 10, "answer": "Outline for My School."}, follow_redirects=True)
        assert b"Question added" in r.data
        assert appmod.Question.query.filter_by(format="Essay").count() == 4
    login(c, "teacher@test.com", "TeachPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="English", class_level_id=cl.id).first()
        data = {"title": "English Section Paper", "class_level_id": cl.id,
                "subject_id": subj.id, "scope": "full", "difficulty": "Mixed",
                "duration_minutes": 60, "paper_date": "2026-11-25", "variant": "A",
                "mcq_theory": 2, "mcq_exercise": 0, "short_theory": 0,
                "short_exercise": 0, "long_theory": 0, "long_exercise": 0,
                "num_theory": 0, "num_exercise": 0,
                "marks_mcq": 1, "marks_short": 2, "marks_long": 5, "marks_numerical": 4,
                "sec_title_0": "Essay", "sec_qtype_0": "Long", "sec_format_0": "Essay",
                "sec_qty_0": 3, "sec_marks_0": 10, "sec_choice_0": "1",
                "sec_attempt_0": 1, "sec_note_0": "Write an essay on any ONE topic.",
                "instructions": "Attempt all questions."}
        r = c.post("/generator", data=data, follow_redirects=True)
        assert b"English Section Paper" in r.data
        paper = appmod.Paper.query.filter_by(title="English Section Paper").first()
        assert paper is not None
        assert paper.sections == [{"title": "Essay", "qtype": "Long", "format": "Essay",
                                   "theory": 0, "exercise": 0, "qty": 3, "marks": 10,
                                   "attempt": 1, "chapters": [],
                                   "note": "Write an essay on any ONE topic.",
                                   "parts": None}]
        assert len(paper.questions) == 5  # 2 MCQ + 3 Essay topics
        # total: 2 MCQ x 1 + attempt 1 Essay x 10 = 12
        assert paper.total_marks == 12, paper.total_marks
        assert b"Attempt any 1 out of 3" in r.data
        pdf = c.get(f"/papers/{paper.id}/pdf")
        assert pdf.status_code == 200 and pdf.data[:4] == b"%PDF"
        # variant keeps the section and the total
        r2 = c.post(f"/generator/variant/{paper.id}", data={"variant": "B"},
                    follow_redirects=True)
        assert b"Paper B created" in r2.data
        var = appmod.Paper.query.filter_by(title="English Section Paper",
                                           variant="B").first()
        assert var is not None and var.sections == paper.sections
        assert var.total_marks == 12


def test_two_short_sections_from_different_chapters():
    """Two Short sections, each limited to its own chapter (full-book test
    with chapter-wise Short sections). Formats are subject-aware."""
    assert appmod.formats_for_subject("English") == [
        "General", "Essay", "Story", "Application", "Letter", "Translation",
        "Tenses", "Comprehension"]
    assert appmod.formats_for_subject("Urdu") == [
        "General", "Tashreeh", "Khulasa", "Mazmoon", "Darkhwast", "Tarjuma"]
    assert appmod.formats_for_subject("Physics") == ["General"]
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="Physics", class_level_id=cl.id).first()
        chs = appmod.Chapter.query.filter_by(subject_id=subj.id).order_by(
            appmod.Chapter.number).all()
        ch1, ch2 = chs[0], chs[1]
        data = {"title": "Chapterwise Short Paper", "class_level_id": cl.id,
                "subject_id": subj.id, "scope": "full", "difficulty": "Mixed",
                "duration_minutes": 60, "paper_date": "2026-11-25", "variant": "A",
                "mcq_theory": 0, "mcq_exercise": 0, "short_theory": 0,
                "short_exercise": 0, "long_theory": 0, "long_exercise": 0,
                "num_theory": 0, "num_exercise": 0,
                "marks_mcq": 1, "marks_short": 2, "marks_long": 5, "marks_numerical": 4,
                "sec_title_0": "Short Qs Ch 1", "sec_qtype_0": "Short",
                "sec_format_0": "General", "sec_theory_0": 1, "sec_exercise_0": 1,
                "sec_marks_0": 2, "sec_chapters_0": [str(ch1.id)],
                "sec_title_1": "Short Qs Ch 2", "sec_qtype_1": "Short",
                "sec_format_1": "General", "sec_theory_1": 1, "sec_exercise_1": 1,
                "sec_marks_1": 2, "sec_chapters_1": [str(ch2.id)],
                "instructions": "Attempt all questions."}
        r = c.post("/generator", data=data, follow_redirects=True)
        assert b"Chapterwise Short Paper" in r.data
        paper = appmod.Paper.query.filter_by(title="Chapterwise Short Paper").first()
        assert paper is not None
        assert [s["title"] for s in paper.sections] == ["Short Qs Ch 1", "Short Qs Ch 2"]
        sec1 = [q for q in paper.questions if q.get("section") == "Short Qs Ch 1"]
        sec2 = [q for q in paper.questions if q.get("section") == "Short Qs Ch 2"]
        assert len(sec1) == 2 and len(sec2) == 2
        assert all(q["chapter"] == ch1.name for q in sec1)
        assert all(q["chapter"] == ch2.name for q in sec2)
        assert paper.total_marks == 8  # 4 Short x 2, no choice
        assert b"Short Qs Ch 1" in r.data and b"Short Qs Ch 2" in r.data


def test_long_parts_section_a_and_b():
    """Long section split into part (a) Short + part (b) Numerical:
    one Long question prints as (a) and (b) with their own marks."""
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="Physics", class_level_id=cl.id).first()
        data = {"title": "Long Parts Paper", "class_level_id": cl.id,
                "subject_id": subj.id, "scope": "full", "difficulty": "Mixed",
                "duration_minutes": 60, "paper_date": "2026-11-25", "variant": "A",
                "mcq_theory": 0, "mcq_exercise": 0, "short_theory": 0,
                "short_exercise": 0, "long_theory": 0, "long_exercise": 0,
                "num_theory": 0, "num_exercise": 0,
                "marks_mcq": 1, "marks_short": 2, "marks_long": 5, "marks_numerical": 4,
                "sec_title_0": "Long Questions", "sec_qtype_0": "Long",
                "sec_format_0": "General", "sec_qty_0": 2, "sec_parts_0": "1",
                "sec_parta_type_0": "Short", "sec_parta_marks_0": 5,
                "sec_partb_type_0": "Numerical", "sec_partb_marks_0": 5,
                "instructions": "Attempt all questions."}
        r = c.post("/generator", data=data, follow_redirects=True)
        assert b"Long Parts Paper" in r.data
        paper = appmod.Paper.query.filter_by(title="Long Parts Paper").first()
        assert paper is not None
        assert len(paper.questions) == 2
        assert paper.total_marks == 20, paper.total_marks  # 2 x (5 + 5)
        for q in paper.questions:
            assert len(q["parts"]) == 2
            assert q["parts"][0]["qtype"] == "Short"
            assert q["parts"][1]["qtype"] == "Numerical"
        assert b"(a)" in r.data and b"(b)" in r.data
        pdf = c.get(f"/papers/{paper.id}/pdf")
        assert pdf.status_code == 200 and pdf.data[:4] == b"%PDF"
        # variant re-picks both parts and keeps the total
        c.post(f"/generator/variant/{paper.id}", data={"variant": "B"},
               follow_redirects=True)
        var = appmod.Paper.query.filter_by(title="Long Parts Paper",
                                           variant="B").first()
        assert var is not None and var.total_marks == 20
        assert all(len(q["parts"]) == 2 for q in var.questions)


def test_sections_have_no_limit_and_skipped_indices_count():
    """Sections are not limited and non-sequential indices all count
    (removing a middle section must not drop the ones after it)."""
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="Physics", class_level_id=cl.id).first()
        data = {"title": "Many Sections Paper", "class_level_id": cl.id,
                "subject_id": subj.id, "scope": "full", "difficulty": "Mixed",
                "duration_minutes": 60, "paper_date": "2026-11-25", "variant": "A",
                "mcq_theory": 0, "mcq_exercise": 0, "short_theory": 0,
                "short_exercise": 0, "long_theory": 0, "long_exercise": 0,
                "num_theory": 0, "num_exercise": 0,
                "marks_mcq": 1, "marks_short": 2, "marks_long": 5, "marks_numerical": 4,
                "sec_title_0": "S0", "sec_qtype_0": "Short", "sec_format_0": "General",
                "sec_theory_0": 1, "sec_exercise_0": 0, "sec_marks_0": 2,
                "sec_title_3": "S3", "sec_qtype_3": "Short", "sec_format_3": "General",
                "sec_theory_3": 1, "sec_exercise_3": 0, "sec_marks_3": 2,
                "sec_title_7": "S7", "sec_qtype_7": "Short", "sec_format_7": "General",
                "sec_theory_7": 1, "sec_exercise_7": 0, "sec_marks_7": 2,
                "instructions": "Attempt all questions."}
        r = c.post("/generator", data=data, follow_redirects=True)
        assert b"Many Sections Paper" in r.data
        paper = appmod.Paper.query.filter_by(title="Many Sections Paper").first()
        assert paper is not None
        assert [s["title"] for s in paper.sections] == ["S0", "S3", "S7"]
        assert len(paper.questions) == 3 and paper.total_marks == 6


def test_essay_topic_picker_picks_named_then_auto():
    """Essay section: tick two specific essay topics and the app uses those
    first (in ticked order), topping up the third itself."""
    c = make_client()
    login(c, "admin@test.com", "AdminPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="English", class_level_id=cl.id).first()
        ch = appmod.Chapter.query.filter_by(subject_id=subj.id).order_by(appmod.Chapter.number).first()
        for topic in ["My Best Friend", "A Visit to a Museum", "My Aim in Life", "My School"]:
            c.post("/questions/new", data={
                "class_level_id": cl.id, "subject_id": subj.id, "chapter_id": ch.id,
                "qtype": "Long", "source": "Theory", "format": "Essay",
                "text": f"Write an essay on {topic}.", "difficulty": "Medium",
                "marks": 10, "answer": f"Outline for {topic}."}, follow_redirects=True)
        essays = appmod.Question.query.filter_by(format="Essay").order_by(
            appmod.Question.id).all()
        assert len(essays) == 4
        picked = [essays[1], essays[3]]  # Museum, School — in this order
    login(c, "teacher@test.com", "TeachPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="English", class_level_id=cl.id).first()
        data = {"title": "Picked Essay Paper", "class_level_id": cl.id,
                "subject_id": subj.id, "scope": "full", "difficulty": "Mixed",
                "duration_minutes": 60, "paper_date": "2026-11-25", "variant": "A",
                "mcq_theory": 0, "mcq_exercise": 0, "short_theory": 0,
                "short_exercise": 0, "long_theory": 0, "long_exercise": 0,
                "num_theory": 0, "num_exercise": 0,
                "marks_mcq": 1, "marks_short": 2, "marks_long": 5, "marks_numerical": 4,
                "sec_title_0": "Essay", "sec_qtype_0": "Long", "sec_format_0": "Essay",
                "sec_qty_0": 3, "sec_marks_0": 10, "sec_choice_0": "1",
                "sec_attempt_0": 1,
                "sec_pick_0": [str(picked[0].id), str(picked[1].id)],
                "instructions": "Attempt all questions."}
        r = c.post("/generator", data=data, follow_redirects=True)
        assert b"Picked Essay Paper" in r.data
        paper = appmod.Paper.query.filter_by(title="Picked Essay Paper").first()
        assert paper is not None and len(paper.questions) == 3
        assert paper.questions[0]["id"] == picked[0].id
        assert paper.questions[1]["id"] == picked[1].id
        assert paper.questions[2]["id"] not in {picked[0].id, picked[1].id}
        # topic picker API lists only Essay questions of that subject
        bank = c.get(f"/api/bank/{subj.id}?format=Essay&qtype=Long")
        assert bank.status_code == 200
        texts = [row["text"] for row in bank.get_json()]
        assert len(texts) == 4 and all("essay on" in t for t in texts)
        assert c.get(f"/api/bank/{subj.id}?format=Story").get_json() == []


def test_english_paper_has_no_long_or_numerical():
    """English (and Urdu) papers have no Long or Numerical questions:
    even if Long/Numerical quantities are submitted, the paper contains
    only MCQ + Short. The generator page marks the cards per type."""
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    g = c.get("/generator")
    assert g.status_code == 200 and 'data-qtype="Long"' in g.data.decode()
    assert 'sec-writing-hint' in g.data.decode()
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="English", class_level_id=cl.id).first()
        data = {"title": "English Only Paper", "class_level_id": cl.id,
                "subject_id": subj.id, "scope": "full", "difficulty": "Mixed",
                "duration_minutes": 60, "paper_date": "2026-11-25", "variant": "A",
                "mcq_theory": 2, "mcq_exercise": 0, "short_theory": 1,
                "short_exercise": 0, "long_theory": 2, "long_exercise": 0,
                "num_theory": 2, "num_exercise": 0,
                "marks_mcq": 1, "marks_short": 2, "marks_long": 5, "marks_numerical": 4,
                "instructions": "Attempt all questions."}
        r = c.post("/generator", data=data, follow_redirects=True)
        assert b"English Only Paper" in r.data
        paper = appmod.Paper.query.filter_by(title="English Only Paper").first()
        assert paper is not None
        assert all(q["qtype"] in ("MCQ", "Short") for q in paper.questions)
        assert paper.total_marks == 4  # 2 MCQ x 1 + 1 Short x 2
        assert b"Long Questions" not in r.data


def test_excel_import_format_column():
    import io as _io
    from openpyxl import Workbook
    c = make_client()
    login(c, "admin@test.com", "AdminPass123")
    wb = Workbook(); ws = wb.active
    ws.append(["Class", "Subject", "Chapter", "Chapter No", "Type", "Source",
               "Format", "Difficulty", "Marks", "Question", "Option A", "Option B",
               "Option C", "Option D", "Correct Option", "Answer"])
    ws.append(["Class 9th", "English", "Reading", 1, "Long", "Theory", "Essay",
               "Medium", 10, "Write an essay on My School.", "", "", "", "", "",
               "Outline: intro, building, teachers, conclusion."])
    buf = _io.BytesIO(); wb.save(buf); buf.seek(0)
    r = c.post("/admin/questions/import", data={"file": (buf, "essay.xlsx")},
               content_type="multipart/form-data", follow_redirects=True)
    assert b"1 of 1 questions imported" in r.data
    with appmod.app.app_context():
        q = appmod.Question.query.filter_by(text="Write an essay on My School.").first()
        assert q is not None and q.format == "Essay"


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


def _gen_data(cl_id, subj_id, **over):
    data = {"title": "Phase 1 Test Paper", "class_level_id": cl_id,
            "subject_id": subj_id, "scope": "full", "difficulty": "Mixed",
            "duration_minutes": 60, "paper_date": "2026-11-26", "variant": "A",
            "mcq_theory": 0, "mcq_exercise": 0, "short_theory": 0,
            "short_exercise": 0, "long_theory": 0, "long_exercise": 0,
            "num_theory": 0, "num_exercise": 0,
            "marks_mcq": 1, "marks_short": 2, "marks_long": 5, "marks_numerical": 4,
            "instructions": "Attempt all questions."}
    data.update(over)
    return data


def test_generator_keeps_form_on_shortfall():
    """The audit's critical bug: a failed generation wiped the whole form.
    Now the class, subject, date, variant, quantities and the Essay section
    all come back exactly as the teacher filled them."""
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="English", class_level_id=cl.id).first()
        data = _gen_data(cl.id, subj.id, mcq_theory=2, short_theory=2, variant="B",
                         sec_title_0="Essay", sec_qtype_0="Long", sec_format_0="Essay",
                         sec_qty_0=1, sec_marks_0=10)
        r = c.post("/generator", data=data)
        assert r.status_code == 200
        body = r.data
        # Only the Essay (0 in the bank) is short — MCQ/Short were available.
        assert b"asked 1, only 0 available" in body
        assert b"asked 2, only" not in body
        # Everything the teacher typed is still there.
        assert f'<option value="{cl.id}" selected'.encode() in body
        assert f'"subject": "{subj.id}"'.encode() in body
        assert b'name="mcq_theory" value="2"' in body
        assert b'name="short_theory" value="2"' in body
        assert b'name="paper_date" value="2026-11-26"' in body
        assert b"<option selected>B</option>" in body
        # The section itself is built by JS from this JSON, so the preset
        # lives in the page as data — that is what the server must preserve.
        assert b'"title": "Essay"' in body
        assert b'"format": "Essay"' in body
        assert b'"qty": 1' in body
        # And no paper was created.
        assert appmod.Paper.query.filter_by(title="Phase 1 Test Paper").first() is None


def test_paper_preview_looks_like_a_real_exam_paper():
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="Physics", class_level_id=cl.id).first()
    r = c.post("/generator", data=_gen_data(cl.id, subj.id, mcq_theory=2, short_theory=2),
               follow_redirects=True)
    assert r.status_code == 200
    body = r.data
    assert b"26 November 2026" in body          # Pakistani date, not ISO
    assert b"[1 mark]" in body                  # not "[1 marks]"
    assert b"[2 marks]" in body
    assert b"(Theory" not in body               # no internal metadata on the student paper
    assert b"Name:" in body and b"Roll No:" in body
    assert b"(2 marks)" in body                 # MCQ section total: 2 x 1
    assert b"(4 marks)" in body                 # Short section total: 2 x 2
    assert b"<option>B</option>" in body and b"<option>C</option>" in body
    assert b"<option>A</option>" not in body    # current variant A is not offered
    assert b"/delete" in body


def _pdf_text(data):
    """Extract the literal text of a ReportLab PDF by decoding its streams
    (ReportLab wraps them in ASCII85 + Flate, so plain text never appears
    in the raw bytes)."""
    import re, zlib, base64
    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        raw = m.group(1).strip()
        for decoder in (lambda b: zlib.decompress(base64.a85decode(b, adobe=True)),
                        lambda b: zlib.decompress(b)):
            try:
                out.append(decoder(raw).decode("latin-1", "replace"))
                break
            except Exception:
                continue
    return "\n".join(out)


def test_paper_pdf_uses_pakistani_date_and_mark_grammar():
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="Physics", class_level_id=cl.id).first()
        teacher = appmod.User.query.filter_by(email="teacher@test.com").first()
        paper = appmod.Paper(title="PDF Check", teacher_id=teacher.id,
                             class_level_id=cl.id, subject_id=subj.id, variant="A",
                             total_marks=6, duration_minutes=60,
                             instructions="Attempt all questions.",
                             paper_date="2026-11-26",
                             questions_json=json.dumps([
                                 {"id": 1, "text": "What is 2+2?", "qtype": "MCQ",
                                  "source": "Theory", "marks": 1,
                                  "options": ["3", "4", "5", "6"], "correct_option": "B",
                                  "answer": "", "chapter": "Ch 1", "format": "General",
                                  "section": ""}]),
                             attempt_json="{}", sections_json="[]")
        appmod.db.session.add(paper)
        appmod.db.session.commit()
        pid = paper.id
    r = c.get(f"/papers/{pid}/pdf")
    assert r.status_code == 200
    assert "application/pdf" in r.content_type
    assert len(r.data) > 1000
    text = _pdf_text(r.data)
    assert "26 November 2026" in text
    assert "[1 mark]" in text
    assert "Name:" in text and "Roll No:" in text


def test_delete_paper():
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="Physics", class_level_id=cl.id).first()
    c.post("/generator", data=_gen_data(cl.id, subj.id, mcq_theory=2))
    with appmod.app.app_context():
        paper = appmod.Paper.query.filter_by(title="Phase 1 Test Paper").first()
        assert paper is not None
        pid = paper.id
    r = c.post(f"/papers/{pid}/delete", follow_redirects=True)
    assert r.status_code == 200
    assert b"deleted" in r.data
    with appmod.app.app_context():
        assert appmod.Paper.query.get(pid) is None


def test_teacher_cannot_delete_others_paper():
    c = make_client()
    login(c, "admin@test.com", "AdminPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="Physics", class_level_id=cl.id).first()
    c.post("/generator", data=_gen_data(cl.id, subj.id, mcq_theory=2))
    with appmod.app.app_context():
        pid = appmod.Paper.query.filter_by(title="Phase 1 Test Paper").first().id
    c.get("/logout", follow_redirects=True)
    login(c, "teacher@test.com", "TeachPass123")
    assert c.post(f"/papers/{pid}/delete").status_code == 403


def test_dashboard_greeting_not_duplicated():
    c = make_client()
    r = login(c, "admin@test.com", "AdminPass123")
    assert b"Welcome, Owner" in r.data
    assert b"(Owner / Admin)" not in r.data


def test_api_counts():
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="English", class_level_id=cl.id).first()
        ch1 = appmod.Chapter.query.filter_by(subject_id=subj.id, number=1).first()
        ch2 = appmod.Chapter.query.filter_by(subject_id=subj.id, number=2).first()
    r = c.get(f"/api/counts/{subj.id}")
    d = r.get_json()
    assert d["by_type"]["MCQ"] == {"Theory": 2, "Exercise": 1}
    assert d["by_type"]["Short"]["Theory"] == 3
    assert d["by_format"] == {"General": 7}
    r = c.get(f"/api/counts/{subj.id}?chapters={ch1.id}")
    d = r.get_json()
    assert d["by_type"]["MCQ"] == {"Theory": 1}
    assert d["by_type"]["Short"] == {"Theory": 1}
    # Comma-separated chapters narrow too (the JS sends ?chapters=1,2).
    r = c.get(f"/api/counts/{subj.id}?chapters={ch1.id},{ch2.id}")
    d = r.get_json()
    assert d["by_type"]["MCQ"] == {"Theory": 1}
    assert d["by_type"]["Short"] == {"Theory": 2}
    # No chapters ticked means zero available, not the full book.
    r = c.get(f"/api/counts/{subj.id}?chapters=")
    assert r.get_json() == {"by_type": {}, "by_format": {}}


def test_generator_shortfall_renders_subject_in_html():
    """The subject (and chapters) are server-rendered in the shortfall page,
    so the form is correct before any JS fetch runs — a slow network can no
    longer make it look reset."""
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="English", class_level_id=cl.id).first()
    data = _gen_data(cl.id, subj.id, mcq_theory=2, short_theory=2,
                     sec_title_0="Essay", sec_qtype_0="Long", sec_format_0="Essay",
                     sec_qty_0=1, sec_marks_0=10)
    r = c.post("/generator", data=data)
    assert r.status_code == 200
    assert f'<option value="{subj.id}" selected>English</option>'.encode() in r.data
    assert r.data.count(b'name="chapter_ids"') >= 9
    assert b'"subject_list"' in r.data and b'"chapter_list"' in r.data


def test_generator_shortfall_shows_anyway_totals():
    """The 'generate anyway' warning now says the exact shortfall in marks
    (6 of 16 marks, 4 of 5 questions) instead of just 'shorter'."""
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="English", class_level_id=cl.id).first()
    data = _gen_data(cl.id, subj.id, mcq_theory=2, short_theory=2,
                     sec_title_0="Essay", sec_qtype_0="Long", sec_format_0="Essay",
                     sec_qty_0=1, sec_marks_0=10)
    r = c.post("/generator", data=data)
    assert r.status_code == 200
    assert b"If you generate anyway" in r.data
    assert b"6 of 16 marks" in r.data
    assert b"4 of 5 questions" in r.data


def test_questions_bank_counts_search_pagination():
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="English", class_level_id=cl.id).first()
    r = c.get(f"/questions?class_level_id={cl.id}&subject_id={subj.id}")
    assert r.status_code == 200
    # Bank at a glance + the format breakdown, including the zero.
    assert "Class 9th · English — 7".encode() in r.data
    assert b"Essay 0" in r.data
    assert b"General 7" in r.data
    # Search narrows to matching text only.
    r = c.get("/questions?q=patriotism")
    assert b"Define patriotism." in r.data
    assert b"The Holy Prophet" not in r.data
    # Pagination: page 2 shows 51-100 of 194.
    r = c.get("/questions?page=2")
    assert b"51" in r.data and b"of 194" in r.data
    # Class 9th comes first, not Class 12th.
    r = c.get("/questions")
    assert r.data.index(b"Class 9th") < r.data.index(b"Class 12th")


def test_questions_answers_hidden_by_default():
    c = make_client()
    login(c, "teacher@test.com", "TeachPass123")
    r = c.get("/questions")
    assert b"Show answers" in r.data
    assert b'style="display:none"' in r.data
    assert b"Answer:" in r.data  # present in the page, just hidden


def test_history_subject_and_teacher_filters():
    c = make_client()
    login(c, "admin@test.com", "AdminPass123")
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        phys = appmod.Subject.query.filter_by(name="Physics", class_level_id=cl.id).first()
        engl = appmod.Subject.query.filter_by(name="English", class_level_id=cl.id).first()
        teacher = appmod.User.query.filter_by(email="teacher@test.com").first()
    c.post("/generator", data=_gen_data(cl.id, phys.id, title="Physics Paper", mcq_theory=2))
    c.get("/logout", follow_redirects=True)
    login(c, "teacher@test.com", "TeachPass123")
    c.post("/generator", data=_gen_data(cl.id, engl.id, title="English Paper", mcq_theory=2))
    c.get("/logout", follow_redirects=True)
    login(c, "admin@test.com", "AdminPass123")
    r = c.get(f"/history?subject_id={phys.id}")
    assert b"Physics Paper" in r.data and b"English Paper" not in r.data
    r = c.get(f"/history?teacher_id={teacher.id}")
    assert b"English Paper" in r.data and b"Physics Paper" not in r.data


def test_settings_academy_name():
    c = make_client()
    login(c, "admin@test.com", "AdminPass123")
    r = c.post("/admin/settings", data={"academy_name": "Sunrise Academy"},
               follow_redirects=True)
    assert r.status_code == 200
    assert b"Academy name saved" in r.data
    assert b"Sunrise Academy" in c.get("/admin/settings").data
    # The saved name appears on a paper preview.
    with appmod.app.app_context():
        cl = appmod.ClassLevel.query.filter_by(name="Class 9th").first()
        subj = appmod.Subject.query.filter_by(name="Physics", class_level_id=cl.id).first()
    c.post("/generator", data=_gen_data(cl.id, subj.id, mcq_theory=2),
           follow_redirects=True)
    with appmod.app.app_context():
        pid = appmod.Paper.query.filter_by(title="Phase 1 Test Paper").first().id
    assert b"Sunrise Academy" in c.get(f"/papers/{pid}").data
    # Empty goes back to the server default.
    c.post("/admin/settings", data={"academy_name": ""}, follow_redirects=True)
    assert b"My Academy" in c.get("/admin/settings").data
    # Teachers cannot change settings.
    c.get("/logout", follow_redirects=True)
    login(c, "teacher@test.com", "TeachPass123")
    assert c.post("/admin/settings", data={"academy_name": "Hack"}).status_code == 403


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            print("RUN", name)
            fn()
            print("PASS", name)
    print("ALL TESTS PASSED")
