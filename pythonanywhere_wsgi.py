# PythonAnywhere WSGI file — copy this into the WSGI editor on the Web tab.
# 1. Replace USERNAME below with your PythonAnywhere username (3 places).
# 2. Replace the placeholder values with your own (never commit real secrets).
# 3. On PythonAnywhere free, do NOT set DATABASE_URL — the app then uses
#    SQLite (instance/academy.db), which persists on PythonAnywhere's disk.
#    Free PythonAnywhere accounts cannot reach external Postgres (Neon).
import os
import sys

path = "/home/USERNAME/academy-test-generator-"
if path not in sys.path:
    sys.path.insert(0, path)

os.environ["SECRET_KEY"] = "PASTE-A-LONG-RANDOM-STRING-HERE"
os.environ["ADMIN_EMAIL"] = "your-admin-email@example.com"
os.environ["ADMIN_PASSWORD"] = "your-strong-admin-password-12-plus-chars"
os.environ["SESSION_COOKIE_SECURE"] = "1"
os.environ["ACADEMY_NAME"] = "My Academy"

from app import app as application
