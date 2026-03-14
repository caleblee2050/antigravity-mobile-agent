@echo off
REM Antigravity Mobile Agent - Windows Task Scheduler 제거기
cd /d "%~dp0"

echo 🛑 Antigravity 백그라운드 에이전트 등록을 해제합니다.
echo.

schtasks /delete /tn "AntigravityAgent" /f

echo.
echo [✅] Windows 작업 스케줄러 삭제가 완료되었습니다.
echo 백그라운드 프로세스를 즉시 종료하려면 작업 관리자에서 pythonw.exe를 종료하세요.
pause
