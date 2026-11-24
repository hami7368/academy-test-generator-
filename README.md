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
