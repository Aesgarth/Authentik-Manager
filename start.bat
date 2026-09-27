@echo off
echo Starting Authentik Access Manager...
cd /d "%~dp0"

if not exist ".env" (
    echo [.env file not found, copying from .env.example...]
    copy .env.example .env
)

cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
