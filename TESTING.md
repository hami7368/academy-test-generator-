# Testing Checklist — Academy Test Generator

Automated tests: `python -m pytest tests/test_app.py -v` (or `python tests/test_app.py`).
They cover: admin login, teacher login, invalid-email login fails, no registration
route (404), teacher blocked from `/admin/*` (403), admin adds a teacher, disabling a
teacher blocks login, password change, question creation, Theory/Exercise separation
in generation, marks calculation, PDF + answer-key download, paper history, shortfall
warning, and `/setup` locking after an admin exists.

Manual checklist (from the project spec) — tick each one on the live deployment:

- [ ] Admin login works (env-created admin, or `/setup` one-time page).
- [ ] Teacher login works with an admin-created email + password.
- [ ] Invalid / unregistered email login fails.
- [ ] No public registration: `/register` and `/signup` return 404; no signup link anywhere.
- [ ] Teacher opening any `/admin/*` URL gets 403 (not just a hidden button).
- [ ] Admin can add a teacher; the teacher can then log in.
- [ ] Admin can disable a teacher; that teacher immediately cannot log in.
- [ ] Admin can enable, edit, reset password for, and delete a teacher.
- [ ] Teacher can change own password (Change Password page).
- [ ] Admin can add a question (MCQ with 4 options + correct option; Short/Long/Numerical).
- [ ] Theory and Exercise are separate fields on every question, and separate quantity
      fields in the generator for every question type.
- [ ] Paper generation respects the exact Theory/Exercise quantities asked for.
- [ ] Shortfall: ask for more questions than exist → clear warning, no silent short paper.
- [ ] Marks calculation: total marks = sum of (quantity × marks per type), shown live.
- [ ] Paper preview, edit question text/marks, remove, replace, move up/down, save.
- [ ] Paper A / B / C variants use different question selections.
- [ ] Answer key downloads as a separate PDF (answers not on the student paper).
- [ ] PDF download works and opens correctly; layout has academy name, class, subject,
      date, time, total marks, sections, marks in brackets, page numbers.
- [ ] Paper history: teacher sees only own papers; search, class/subject/date filter,
      reopen, download old PDF, copy a paper. Admin sees all teachers' papers.
- [ ] Mobile responsiveness: generator and dashboards usable on a phone screen.
- [ ] PWA: manifest loads (`/manifest.json`), service worker registers, icons load,
      Chrome "Add to Home Screen" / "Install app" appears.
- [ ] Database persistence: create a paper, restart the service, paper is still there
      (Postgres/Neon). Note: uploaded PDFs on Render free are NOT persistent (see README).
- [ ] App restart: after a Render redeploy, login and data still work.
- [ ] Book upload: admin uploads a PDF, it lists, downloads, and deletes.
- [ ] `/setup` after an admin exists redirects to login (locked forever).
