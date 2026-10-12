@echo off
REM One-command local start (Windows). Requires Python 3.10+ on PATH.
cd /d "%~dp0"

if not exist .venv (
  echo Creating virtual environment...
  python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt || goto :error

if not exist .env (
  copy .env.example .env >nul
  echo.
  echo Created .env from .env.example. Set LLM_API_KEY ^(or point LLM_BASE_URL at Ollama^) and re-run.
  pause
  exit /b 1
)

set PORT=8080
for /f "tokens=1,2 delims==" %%a in ('findstr /b "PORT=" .env') do set PORT=%%b
echo Enfactum AI Assistant -^> http://localhost:%PORT%
uvicorn app.main:app --host 0.0.0.0 --port %PORT%
goto :eof

:error
echo Setup failed.
pause
exit /b 1
