#!/bin/bash
# Update the Academy Test Generator on PythonAnywhere.
# Run from the Bash console (home directory) with:
#     bash academy-test-generator-/update.sh
# Then click Reload on the Web tab. No re-upload, no WSGI/password re-entry.
set -e
cd ~/academy-test-generator-
git pull
~/.virtualenvs/academy-test-generator/bin/pip install -r requirements.txt
echo "Update done. Now click Reload on the Web tab."
