@echo off
REM Antigravity Mobile Agent - Windows Task Scheduler 설지기
cd /d "%~dp0"
set SCRIPT_DIR=%cd%

echo 🚀 Antigravity 무중단 백그라운드 에이전트 (Windows) 설치를 시작합니다.
echo.

if not exist "venv\Scripts\pythonw.exe" (
    echo [!] 가상환경(venv)이 구성되지 않았습니다. setup.bat 등을 먼저 실행해주세요.
    pause
    exit /b 1
)

echo [1] 기존 AntigravityAgent 스케줄이 있다면 삭제합니다...
schtasks /delete /tn "AntigravityAgent" /f >nul 2>&1

echo [2] 새 작업 스케줄러 등록 중 (로그온 시 자동 실행, 최고 권한)...
schtasks /create /tn "AntigravityAgent" /tr "\"%SCRIPT_DIR%\runw.bat\"" /sc onlogon /rl highest /f

echo.
echo [✅] Windows 작업 스케줄러 등록이 완료되었습니다!
echo 이제 윈도우를 다시 시작하거나 로그인하면 에이전트가 백그라운드에서 투명하게 실행됩니다.
echo 당장 시작하려면 작업 스케줄러 관리자에서 수동으로 '실행'하시거나, PC를 재부팅하세요.
pause
