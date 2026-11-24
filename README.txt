ACADEMY TEST GENERATOR — PRIVATE ACCESS MVP

MOBILE APP INSTALLATION
- This build includes PWA manifest and service worker support. After deployment on an HTTPS domain, open it in Android Chrome and choose Install app / Add to Home screen.
- The icon opens the hosted app in a standalone app-style view. No Python installation is needed on the phone.
- HTTPS is required for normal PWA installation.

ACCESS RULES
- There is one Main Admin account only.
- Public sign-up/registration is disabled; there is no public account-creation route.
- Only the Main Admin can create teacher accounts from Manage Teachers.
- New accounts are always created with the teacher role; the form cannot create another admin.
- Main Admin can disable/enable teacher accounts.
- Teachers cannot open the Manage Teachers admin page; server-side role checks enforce this.
- Admin and teachers can change their own passwords after login.

LOCAL TESTING (Windows)
1. Install Python 3.10 or newer on the computer running the server.
2. Extract this ZIP and run run_windows.bat.
3. Open http://127.0.0.1:5000 in that computer's browser.

Initial local-only Main Admin credentials:
Email: admin@academy.local
Password: Admin@12345
Change this password immediately after first login using Change password.

HOSTING / ONLINE USE
This ZIP is not yet a live hosted app. To publish it for mobile and desktop access, deploy it to a Python-capable web host with HTTPS and persistent database/file storage. Set these environment variables before first start:
- SECRET_KEY: a long random secret value
- ADMIN_EMAIL: your private Main Admin email
- ADMIN_PASSWORD: a strong initial password (at least 8 characters)
- COOKIE_SECURE=1 when HTTPS is enabled
- PORT: supplied automatically by many hosts

Important: set ADMIN_EMAIL and ADMIN_PASSWORD before the first deployment, while the database is empty. Once the first admin is created, changing these environment variables will not change the existing admin login; use Change password for the password. Keep the admin credentials private. Do not share them with teachers.

Included features
- Admin and teacher login with server-side role checks
- Admin creates and disables teacher accounts
- Classes, subjects and chapter management
- PDF textbook upload and download
- Manual question bank with question type, Theory/Exercise source, difficulty, answer and marks
- Paper generation, history and print/Save as PDF

Current limitations
- No email invitation delivery or password reset email yet; Admin shares temporary login details securely.
- PDF files are stored but are not automatically extracted; AI question generation is not integrated yet.
- Local SQLite database is suitable for testing, not recommended for multi-user production hosting without persistent storage and a proper database migration.
- Before public production use, add CSRF protection, login rate limiting, managed PostgreSQL, private object storage, automated backups, monitoring and email-based password reset.
- No student portal.
