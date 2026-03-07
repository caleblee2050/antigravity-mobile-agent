# 🚀 안티그래비티 모바일 에이전트

> 모바일(디스코드/웹)에서 PC의 **Antigravity**를 원격 제어하는 시스템

## 시스템 아키텍처

```
📱 스마트폰 (디스코드 or 웹 대시보드)
    ↕ HTTP / WebSocket
🖥️ Flask 서버 (mailbox.json 기반 중계)
    ↕ 폴링
🤖 브레인 에이전트 (AppleScript + PyAutoGUI로 Antigravity에 입력)
    ↕ 키보드/마우스 자동화
🧠 Antigravity (추가 API 비용 없음)
    ↕ 화면 캡처
👁️ 오토 어프로버 (이미지 인식으로 승인 버튼 자동 클릭)
```

## ⚡ 빠른 설치

```bash
git clone https://github.com/caleblee2050/antigravity-mobile-agent.git
cd antigravity-mobile-agent
./setup.sh
```

## 📋 필수 조건

- **macOS** (AppleScript, PyAutoGUI 사용)
- **Python 3.10+**
- **Antigravity 앱** 설치 및 실행

### macOS 권한 (필수)
- `시스템 설정 > 개인정보 보호 > 접근성` → 터미널 허용
- `시스템 설정 > 개인정보 보호 > 화면 녹음` → 터미널 허용

## 🚀 실행

```bash
# .env 설정 (첫 실행 시)
cp .env.example .env
# .env 파일을 열어 비밀번호 설정

# 실행
./run.sh
```

스마트폰 브라우저에서 `http://<내_IP>:9150` 접속

## 📁 프로젝트 구조

```
├── antigravity_host.py    # 통신 허브 (Flask 서버)
├── agent_brain.py         # 브레인 에이전트 (메시지 → Antigravity 입력)
├── auto_approver.py       # 오토 어프로버 (승인 버튼 자동 클릭)
├── discord_bot.py         # 디스코드 봇 (/ask, /screenshot, /status)
├── send_reply.py          # AI 응답 전달 도구
├── capture_buttons.py     # 승인 버튼 이미지 캡처 도우미
├── templates/
│   └── dashboard.html     # 모바일 웹 대시보드
├── images/                # 승인 버튼 이미지 (사용자 캡처)
├── setup.sh               # 원커맨드 설치 스크립트
├── run.sh                 # 원터치 실행 스크립트
├── install_service.sh     # launchd 서비스 설치
├── uninstall_service.sh   # launchd 서비스 제거
├── setup_tailscale.sh     # Tailscale VPN 설정
├── test_e2e.py            # E2E 테스트 (16개 케이스)
└── requirements.txt
```

## 🤖 디스코드 봇 설정 (선택)

1. [Discord Developer Portal](https://discord.com/developers/applications)에서 봇 생성
2. Bot 설정에서 **Message Content Intent** 활성화
3. `.env`에 토큰과 채널 ID 입력
4. `./run.sh` 실행 시 자동으로 봇도 시작됨

| 명령어 | 설명 |
|--------|------|
| `/ask 질문` | Antigravity에 질문 전달 |
| `/screenshot` | 현재 화면 스크린샷 |
| `/status` | 시스템 상태 확인 |

## 🌐 Tailscale (외부 네트워크)

```bash
./setup_tailscale.sh
```

같은 Wi-Fi가 아니어도 어디서든 접속 가능

## 📜 라이선스

MIT License
