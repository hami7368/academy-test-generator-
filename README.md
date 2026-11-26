# Academy Test Generator

A complete, private, invitation-only test-paper generator for a Punjab Board academy in Pakistan.
Teachers generate papers from a question bank (Theory / Exercise kept separate), edit them,
and download clean PDF papers and answer keys. Installable as a mobile app (PWA).

## What is built

- **Roles (server-enforced):** Admin (owner, one account) and Teacher (admin-created only).
  No public registration page exists at all. Teachers hitting any `/admin/*` route get a 403.
- **Admin:** create / edit / disable / enable / delete teachers, reset teacher passwords,
  manage classes, subjects, chapters, textbook PDFs, questions, view all papers and activity.
- **Teachers:** log in only with an admin-created email, change own password, generate papers,
  edit / remove / replace / reorder questions, create Paper A / B / C variants, download
  PDF paper + separate answer key, view own paper history (search + filter + copy).
- **Question bank:** class, subject, chapter, type (MCQ / Short / Long / Numerical),
  **source (Theory / Exercise — always separate)**, difficulty, marks, answer/solution.
  Seeded with classes 9th–12th, 7 subjects per class, real Punjab Board chapter names,
  and **194 sample questions**.
- **Paper generator:** one / multiple / half-book / full-book chapter scope, difficulty
  (Easy / Medium / Hard / Mixed), **separate Theory and Exercise quantities for every
  question type**, marks per type, live total-marks calculation (also checked server-side).
  If the bank has too few questions, the app shows a clear shortfall warning and does
  **not** silently make a short paper — you must tick "generate anyway" to proceed.
- **PWA:** manifest, service worker (offline fallback page), 192px + 512px icons,
  standalone display. On Android Chrome: menu → "Add to Home Screen" / "Install app".
  (Icons are generated from code by `generate_icons.py` at startup/build time,
  so the PWA works even though no binary PNG is stored in the repo.)
- **PDF:** ReportLab, clean academy layout (name, class, subject, date, time, total marks,
  sections by type, marks in brackets, page numbers). Urdu renders correctly in the
  web preview; **PDF Urdu needs a font** — see "Urdu in PDFs" below.

## Tech stack

Python 3.12, Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF (CSRF on all POST forms),
Werkzeug password hashing, ReportLab, Gunicorn. Database: PostgreSQL via `DATABASE_URL`
(Neon free tier recommended) with SQLite fallback for local testing. Secrets only in
environment variables — no passwords are hardcoded anywhere.

## Run locally (for testing on your own laptop)

1. Install Python 3.12 from python.org (tick "Add Python to PATH").
2. Download this project (ZIP from GitHub, or `git clone <your-repo-url>`).
3. In a terminal in the project folder:
   ```
   python -m venv .venv
   .venv\Scripts\activate        (Windows)
   source .venv/bin/activate     (Mac/Linux)
   pip install -r requirements.txt
   python app.py
   ```
4. Open http://127.0.0.1:5000 — first visit **/setup** to create the one admin account
   (page locks forever once an admin exists). Or set `ADMIN_EMAIL` / `ADMIN_PASSWORD`
   in a `.env` file (copy `.env.example` to `.env` first) before starting.

## Deploy free: Render + Neon (recommended)

**Why this pair:** Render's free web service runs the app; Neon gives a *permanent* free
PostgreSQL database (1 GB, 100 CU-hours/month, scales to zero after 5 min idle).
Do **not** use Render's free PostgreSQL — it expires after 30 days.

1. **Neon database (free, permanent):** go to neon.tech → sign up (GitHub login works) →
   New Project → copy the connection string, e.g.
   `postgresql://user:password@ep-xxx.aws.neon.tech/neondb?sslmode=require`
2. **GitHub:** create a repo and upload this whole project folder (see "Upload to GitHub" below).
3. **Render:** go to render.com → sign up (GitHub login) → New → Web Service →
   pick your repo → Runtime: Python → Build command: `pip install -r requirements.txt` →
   Start command: `gunicorn app:app --bind 0.0.0.0:$PORT` (a `render.yaml` is included,
   so Render can also do this automatically with "Blueprint").
4. In Render → your service → **Environment**, add:
   - `DATABASE_URL` = your Neon connection string
   - `ADMIN_EMAIL` = your private admin email
   - `ADMIN_PASSWORD` = a strong password (12+ characters, never share it)
   - `SECRET_KEY` = a long random string (Render can generate one)
   - `ACADEMY_NAME` = your academy name (optional)
   - `SESSION_COOKIE_SECURE` = `1` (Render serves HTTPS)
5. Deploy. When it says "Live", open the Render URL (`https://your-app.onrender.com`).
   The admin account is created automatically from `ADMIN_EMAIL`/`ADMIN_PASSWORD`.
   Log in, then add teachers in **Teachers → Add Teacher**.
6. Later you can add a custom domain in Render → Settings → Custom Domain, no rebuild needed.

**Note (2026-11-24):** Render now asks new accounts for a credit card at deploy time
(a temporary $1 authorization, free plan stays $0). If you do not want to add a card,
use the PythonAnywhere deploy below instead.

## Deploy free, no card: PythonAnywhere (SQLite)

**Why this pair:** PythonAnywhere's free Beginner account needs **no credit card**,
the app does not sleep, and the SQLite database file lives on PythonAnywhere's disk
so it persists. Trade-off: free PythonAnywhere accounts **cannot connect to an
external Postgres database (Neon)** — only HTTP(S) to whitelisted sites is allowed —
so the database here is SQLite, not Neon. Your Neon project stays ready for a later
move back to Render; teachers/papers made on PythonAnywhere will not auto-transfer.

1. **Sign up:** pythonanywhere.com → **Pricing → Beginner (free)** → create account.
   No card needed. Your site will be `https://YOUR-USERNAME.pythonanywhere.com`.
2. **Get the code:** open a **Bash console** (Consoles tab) and run:
   ```
   git clone https://github.com/hami7368/academy-test-generator-.git
   cd academy-test-generator-
   mkvirtualenv --python=python3.12 academy-test-generator
   pip install -r requirements.txt
   ```
3. **Create the web app:** Web tab → **Add a new web app** → **Manual configuration**
   → Python 3.12 → pick your new virtualenv (`academy-test-generator`).
4. **WSGI file:** on the Web tab, open the **WSGI configuration file** link, delete its
   contents and paste in `pythonanywhere_wsgi.py` from this repo — replacing `USERNAME`
   (3 places) with your PythonAnywhere username, and the placeholder values with your
   own `SECRET_KEY` (long random string), `ADMIN_EMAIL`, `ADMIN_PASSWORD` (12+ chars,
   never share it) and `ACADEMY_NAME`. Do **not** add `DATABASE_URL`.
5. **Static files:** on the Web tab, under **Static Files**, add:
   URL `/static/` → Directory `/home/USERNAME/academy-test-generator-/static/`
   (again with your real username).
6. Click the green **Reload** button. Open `https://YOUR-USERNAME.pythonanywhere.com`
   and log in with your `ADMIN_EMAIL` / `ADMIN_PASSWORD`. The admin account and the
   194 seed questions are created automatically on first start.
7. **Renewal:** free web apps expire after ~3 months of inactivity — PythonAnywhere
   emails you a reminder; click the button on the Web tab to extend, no rebuild needed.

## Honest free-tier limits

- **Render free web service sleeps after 15 minutes idle** — the first visit after a pause
  takes 30–60 seconds to wake up. This is normal on the free plan.
- **Render free PostgreSQL expires in 30 days** — that is why this guide uses **Neon**
  (permanent free tier) instead.
- **Uploaded textbook PDFs are NOT permanent on Render free** — there is no persistent
  disk, so uploads are lost when the service restarts/redeploys. Keep your own copies
  and re-upload when needed. For permanent storage later: Render paid disk, or cloud
  storage (e.g. Cloudinary / S3). The question bank and papers live in Neon Postgres
  and **are** permanent.
- **PythonAnywhere free uses SQLite, not Neon Postgres** — free accounts cannot
  reach an external Postgres server, so question bank and papers live in a SQLite
  file on PythonAnywhere's disk. It persists across restarts, but it is one file:
  download a backup copy from the Files tab from time to time. Free web apps also
  need a one-click renewal every ~3 months of inactivity (email reminder sent).
- **AI PDF extraction is NOT implemented yet.** The Settings page says so plainly.
  Questions are added manually today. When extraction is added, the key will come from
  the `GEMINI_API_KEY` / `OPENAI_API_KEY` environment variable — never paste a key
  into the app or the database.

## Urdu in PDFs

English PDFs work perfectly. Urdu text in PDFs needs the Noto Nastaliq font file
(`NotoNastaliqUrdu-Regular.ttf`) placed in `app/static/fonts/` — it is not bundled
because of its size. Download it from Google Fonts (Noto Nastaliq Urdu) and drop the
file there; the PDF code picks it up automatically. Without it, Urdu in the PDF falls
back to the standard font; Urdu in the on-screen preview always renders correctly.

## Upload to GitHub (beginner, no Git commands needed)

The GitHub website upload page sometimes shows HTTP ERROR 400 for large uploads.
Easier method — **GitHub Desktop** (free, no commands):

1. Install GitHub Desktop from desktop.github.com and sign in.
2. File → New Repository → name `academy-test-generator` → Local path: pick an empty folder → Create.
3. Copy **all files from this project folder** into that folder (including `render.yaml`,
   `Procfile`, `requirements.txt`, `.env.example` — but **never** a real `.env` file
   or the `instance/` folder).
4. In GitHub Desktop you will see the files listed on the left → write a summary
   ("First version") → **Commit to main** → **Publish repository** (make it Private).
5. Your repo URL will be `https://github.com/<your-username>/academy-test-generator`.
   That is the repo you connect to Render in the deploy steps above.

If you prefer the website: repo → **Add file → Upload files** → drag the files in
small batches (a few at a time, not the whole ZIP at once).

## First admin account (do this first)

- **Option A (recommended for deployment):** set `ADMIN_EMAIL` and `ADMIN_PASSWORD`
  in Render's Environment tab before the first deploy. The account is created on startup.
- **Option B (local / first run):** open `/setup` in the browser, enter your name, email
  and a password of 8+ characters, and submit. The page locks forever afterwards.
- There are **no default credentials** (no admin/admin). Never share the admin password.

## Forgot the admin password?

The WSGI file is the source of truth: change `ADMIN_PASSWORD` in the
WSGI file (`/var/www/testgeneratorhamid_pythonanywhere_com_wsgi.py`) to a
new password, then run `bash update.sh` and click **Reload** on the Web
tab. The new password works immediately — the app syncs the admin account
from the env vars on every start. (Teachers' passwords are reset from the
Admin Panel → Teachers, not this way.)

## Import questions from Excel (bulk add)

Typing questions one by one is slow. Instead, fill an Excel sheet and upload it:

1. Log in as admin → **Question Bank → Import from Excel**.
2. Click **Download Excel template** — it has the right headings and 2 example rows.
3. Fill one question per row: **Class** (e.g. `Class 9th`), **Subject** (`Physics`),
   **Chapter**, **Chapter No**, **Type** (`MCQ` / `Short` / `Long` / `Numerical`),
   **Source** (`Theory` or `Exercise`), **Difficulty** (`Easy` / `Medium` / `Hard`),
   **Marks**, **Question**, **Option A–D** (MCQ only), **Correct Option** (A–D, MCQ only),
   **Answer**. Keep the heading row exactly as in the template.
4. Upload the file. The page tells you how many questions were imported and lists
   any skipped rows with the reason (e.g. unknown class/subject, MCQ missing an
   option). Good rows are imported even if some rows fail.
5. Notes: Class and Subject must already exist (add them under Classes & Subjects
   first). A chapter that does not exist yet is created automatically. Uploading
   the same file again is safe — questions already in the bank are skipped, not
   duplicated. A `.csv` file with the same columns works too.

After a code update on PythonAnywhere, run in the Bash console
`git pull` and `pip install -r requirements.txt` (only needed when
`requirements.txt` changed), then click **Reload** on the Web tab.
From the next update on, one command does the same thing:

```bash
bash academy-test-generator-/update.sh
```

## Choice in a paper ("Attempt any N out of M")

On the Generate Paper page, under each type (MCQ / Short / Long / Numerical)
there is an **Attempt any** box. Leave it blank and students attempt all
questions; enter e.g. **5** for Short and the paper prints all 8 Short
questions with the heading **"Attempt any 5 out of 8"** — and the total marks
count only the 5 attempted (5 × 2 = 10, not 8 × 2). The choice is shown on the
web preview and in the PDF, and is kept when you make a variant (A/B/C) or a
copy. Attempt can never be more than the questions in that section.

## Formats and custom sections ("Add Section")

Some questions do not fit MCQ / Short / Long / Numerical — English essays,
stories, applications, letters, translations, tenses, comprehension, and Urdu
tashreeh, khulasa, mazmoon, darkhwast, tarjuma. Every question has a
**Format** (General, Essay, Story, Application, Letter, Translation, Tenses,
Comprehension, Tashreeh, Khulasa, Mazmoon, Darkhwast, Tarjuma):

- Set it when adding a question (**Add Question → Format** — the list only
  shows the formats for that subject: English shows Essay/Story/...,
  Urdu shows Tashreeh/Khulasa/..., other subjects only General), or in the
  Excel sheet's **Format** column (blank = General).
- On the Generate Paper page, click **+ Add Section**. First choose **what to
  add** (Essay, Story, Tashreeh, ... — again only that subject's formats):
  the section title, question type and marks fill in themselves, and you can
  change them. Essay / Tashreeh / Translation and the other writing formats
  have **no Theory / Exercise** — just say **how many** (e.g. 3 essay topics).
  Tick **"Give choice in this section"** to make it "Attempt any N out of M"
  (unticked = every question is compulsory). You can also write section
  instructions (e.g. "Write an essay on any ONE of the following topics").
- **Each section has its own chapters**: tick only the chapters it should
  draw from (all ticked = whole book). That is how a full-book test gets two
  Short sections from different chapters, or a Tashreeh section from one
  ghazal's chapter. Essay / Story / Application / Letter / Mazmoon /
  Darkhwast have **no chapters at all** — an essay is not from a chapter,
  so no chapter boxes show under them. Add as many sections as you like —
  there is no limit.
- **Pick the exact topics**: a writing section (Essay, Story, ...) lists the
  bank's topics of that format — tick the exact ones you want, or leave all
  unticked and the app picks any itself (ticked ones come first, the rest
  are topped up automatically). A writing section shows no Question type
  box and no part (a)/(b) split — an Essay section is just an Essay section.
- **Long questions with parts (a) and (b)**: in a Long section, tick
  "Split each Long question into part (a) and part (b)". Each part has its
  own type (e.g. (a) a Short question, (b) a Numerical), its own marks
  (e.g. 5 + 5 = 10) and its own chapters — leave all chapter boxes ticked
  and the app picks from any chapter itself. The paper and PDF print it as
  "Q5. (a) ... [5 marks] (b) ... [5 marks]".
- Sections print under their own headings in the preview and the PDF, the
  total marks count only the attempted questions, and sections are kept when
  you make a variant (A/B/C) or a copy.

## Subject-wise paper layout

Every subject does **not** get the same quantities grid. English and Urdu
papers have no Long or Numerical questions, so when you pick English or Urdu
the quantities grid shows only **MCQ + Short** (the Long/Numerical cards
disappear, and the server ignores them even if they are submitted). Physics,
Chemistry, Biology, Mathematics and Computer Science keep all four types.

## Add a teacher

Admin Panel → **Teachers → Add Teacher** → enter the teacher's name, email and a
temporary password (8+ characters) → Save → share the email + password with that
teacher **privately** (e.g. WhatsApp). The teacher logs in and should change the
password at **Change Password**. To block a teacher instantly: Teachers → **Disable**.
Disabled teachers cannot log in.

## Project structure

```
app.py                 Flask app: models, auth, admin, generator, PDF export
seed.py                Classes/subjects/chapters + 194 sample questions (idempotent)
templates/             Jinja pages (admin + teacher dashboards, generator, papers)
static/css/style.css   Mobile-first stylesheet (no CDN needed)
static/manifest.json   PWA manifest        static/sw.js  Service worker
static/icons/          PWA icons 192 + 512
requirements.txt  Procfile  render.yaml  runtime.txt  .env.example  .gitignore
tests/test_app.py      Automated checks (see TESTING.md)
```

## Tests

```
pip install pytest
python -m pytest tests/test_app.py -v
```
Or without pytest: `python tests/test_app.py`. See `TESTING.md` for the full manual checklist.
