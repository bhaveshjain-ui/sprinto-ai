# Sprinto AI

1. Copy `.env.example` to `.env` (project root) and fill in the keys. `MY_EMAIL` is the only address emails are ever sent to.
2. Backend: `.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --port 8000`
3. Frontend: `cd frontend && npm run dev` then open http://localhost:5173
4. Tests: `cd backend && ..\.venv\Scripts\python -m pytest -q`
