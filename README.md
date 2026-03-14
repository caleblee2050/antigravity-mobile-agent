# 🚀 안티그래비티 모바일 에이전트

> 모바일(텔레그램/웹)에서 PC의 **Antigravity**를 원격 제어하는 시스템

## 시스템 아키텍처

```
📱 스마트폰 (텔레그램 or 웹 대시보드)
    ↕ HTTP / Polling
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

- **macOS** 통과 (AppleScript, PyAutoGUI, LaunchAgent 적용)
- **Windows** 통과 (pygetwindow, Task Scheduler 호환 적용)
- **Python 3.10+**
- **Antigravity 앱** 설치 및 실행

### macOS 권한 (필수)
- `시스템 설정 > 개인정보 보호 > 접근성` → 터미널 허용
- `시스템 설정 > 개인정보 보호 > 화면 녹음` → 터미널 허용

## 🚀 실행

```bash
# .env 설정 (첫 실행 시)
cp .env.example .env

# Mac 실행 (백그라운드 서비스 등록 권장)
make install
make start

# Windows 실행 (작업 스케줄러 등록 권장)
install_service.bat
```

스마트폰 브라우저에서 `http://<내_IP>:9150` 접속

## 📁 프로젝트 구조

```
├── antigravity_host.py    # 통신 허브 (Flask 서버)
├── agent_brain.py         # 브레인 에이전트 (메시지 → Antigravity 입력)
├── auto_approver.py       # 오토 어프로버 (승인 버튼 자동 클릭)
├── telegram_bot.py        # 텔레그램 봇 (양방향 통신 + 음성 인식)
├── telegram_notifier.py   # 이벤트 기반 푸시 알림
├── voice_transcriber.py   # 음성 인식(STT) 모듈
├── send_reply.py          # AI 응답 전달 도구
├── discord_bot.py         # 디스코드 봇 (레거시)
├── capture_buttons.py     # 승인 버튼 이미지 캡처 도우미
├── templates/
│   └── dashboard.html     # 모바일 웹 대시보드
├── images/                # 승인 버튼 이미지 (사용자 캡처)
├── setup.sh               # 원커맨드 설치 스크립트
├── run.sh                 # 원터치 실행 스크립트
├── install_service.sh     # launchd 서비스 설치
├── uninstall_service.sh   # launchd 서비스 제거
├── setup_tailscale.sh     # Tailscale VPN 설정
├── test_e2e.py            # E2E 테스트
└── requirements.txt
```

## 📱 텔레그램 봇 설정 (기본)

### 1. 봇 생성

1. 텔레그램에서 **@BotFather** 검색 후 대화 시작
2. `/newbot` 명령어 입력
3. **봇 이름** 입력 (예: `내 안티그래비티`)
4. **봇 유저네임** 입력 (예: `my_antigravity_bot`)
5. 발급받은 **API 토큰** 복사

### 2. Chat ID 확인

1. 생성한 봇에게 아무 메시지 보내기
2. 브라우저에서 열기:
   ```
   https://api.telegram.org/bot<토큰>/getUpdates
   ```
3. `"chat":{"id": 숫자}` 에서 **숫자가 Chat ID**

### 3. .env 설정

```ini
TELEGRAM_TOKEN=발급받은_토큰
TELEGRAM_CHAT_ID=확인한_채팅_ID
```

### 텔레그램 명령어

| 명령어 | 설명 |
|--------|------|
| 일반 메시지 | Antigravity에 질문 전달 |
| 🎤 음성 메시지 | STT 변환 후 전달 (활성화 시) |
| `/screenshot` | 현재 화면 스크린샷 |
| `/status` | 시스템 상태 확인 |
| `/help` | 도움말 |

## 🎤 음성 인식(STT) 설정 (선택)

텔레그램에서 음성 메시지를 보내면 자동으로 텍스트로 변환하여 Antigravity에 전달합니다.

### 설정 방법

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. **API 및 서비스** > **사용 설정** > `Cloud Speech-to-Text API` 활성화
3. **사용자 인증 정보** > **API 키 만들기**
4. `.env` 파일 수정:

```ini
ENABLE_STT=true
GOOGLE_CLOUD_API_KEY=발급받은_API_키
```

5. 봇 재시작

> ⚠️ `ENABLE_STT=false`(기본값)이면 음성 메시지 수신 시 안내 메시지만 표시됩니다.

## 🌐 Tailscale (외부 네트워크)

```bash
./setup_tailscale.sh
```

같은 Wi-Fi가 아니어도 어디서든 접속 가능

## 🤖 디스코드 봇 (레거시)

> 텔레그램 사용을 권장합니다. 디스코드 봇은 호환성을 위해 유지됩니다.

`.env`에 `DISCORD_TOKEN`과 `DISCORD_CHANNEL_ID`를 설정하면 사용 가능합니다.

## 📜 라이선스

MIT License
## 💰 상용화 비전 (비즈니스 모델)

본 프로젝트는 오픈소스 커뮤니티 장악과 엔터프라이즈(B2B) 시장 진출을 동시에 노리는 투트랙(Two-Track) 상용화 기획을 갖추고 있습니다.

1. **[무료 생태계] 안티그래비티 모바일 개인 연동용 (오픈소스)**
   - Cursor, Windsurf 등 AI 코딩 편집기를 활용하는 개발자들의 개인 생산성을 폭발시키는 오픈소스 엔진 제공.
2. **[유료 생태계] Antigravity Cloud Enterprise (SaaS)**
   - 다중 컴퓨팅 자원 + 수백 대의 AI 에이전트를 모바일/클라우드 및 Slack 연동 환경에서 한눈에 모니터링하고 제어하는 기업 관리자용 대시보드 플랜 제공.
3. **[스토어 생태계] IDE 전용 커스텀 플러그인 생태계**
   - 개발 엔진(언리얼, 유니티, IntelliJ 등) 포커싱 및 템플릿 마켓 등 서드파티 스토어 개발 지원.
