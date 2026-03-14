@echo off
REM Antigravity Mobile Agent - Windows Background Launcher (No Console)
cd /d "%~dp0"

REM 로그 폴더 생성
if not exist "logs" mkdir "logs"

REM 에이전트 브레인, 호스트 서버, 오토 어프로버, 텔레그램 봇 4종을 pythonw.exe 로 실행
REM pythonw.exe는 cmd 창 없이 백그라운드 환경에서만 동작합니다.
start "" "venv\Scripts\pythonw.exe" antigravity_host.py
timeout /t 2 /nobreak >nul
start "" "venv\Scripts\pythonw.exe" auto_approver.py
start "" "venv\Scripts\pythonw.exe" telegram_bot.py
start "" "venv\Scripts\pythonw.exe" agent_brain.py
