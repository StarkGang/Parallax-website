import os
import sys

# Ensure backend and root directories are in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
backend_dir = os.path.join(root_dir, "backend")

for path in (backend_dir, root_dir):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.main import app

# Vercel Serverless ASGI entrypoint for FastAPI
app = app

