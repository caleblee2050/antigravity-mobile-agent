# 🚀 안티그래비티 모바일 에이전트

> 모바일(텔레그램/웹)에서 PC의 **Antigravity**를 원격 제어하는 시스템

## ✨ 최신 업데이트 핵심 기능 (v1.2)

- **💬 카카오톡 REST API 연동**: 카카오 OAuth 인증, 나에게 메시지 보내기, 친구 목록 조회, 친구에게 메시지 전송 기능 지원. 토큰 자동 갱신 및 안전한 저장.
- **🧠 Zero-Config 자연어 룰 저장 파이프라인**: 텔레그램에서 "이건 에이전트 룰이야" 또는 "이건 개발자 룰이야" 라고 말하는 것만으로 복잡한 파일 설정 없이 전역(비서용)/지역(코딩용) 컨텍스트를 분리하여 자동 영구 기억.
- **📱 텔레그램 공식 봇 전환 & 음성인식(STT) 결합**: 디스코드를 넘어 글로벌 메신저인 텔레그램을 기본 모바일 컨트롤러로 채택하여 접근성 극대화.
- **🖥️ 완벽한 크로스 플랫폼 데몬 지원**: macOS(`launchd`) 뿐만 아니라 Windows(`Task Scheduler`, `pygetwindow`) 환경에서도 보이지 않는 형태의 완벽한 백그라운드 서비스 동작 보장.
- **🎯 마우스 강제 포커싱 락 우회**: VS Code 등 일부 IDE가 마우스 입력을 가로채는 포커스 트랩(Focus Trap) 현상을 백그라운드에서 하이브리드 강제 클릭 제어로 완벽히 우회 설계.

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
├── kakao_api.py           # 카카오톡 REST API 연동 모듈
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
| `/windows` | 열린 안티그래비티 창 목록 + 현재 타겟 |
| `/target [번호]` | 특정 창으로 타겟 변경 |
| `/target auto` | 자동 탐색 모드 (에이전트 폴더 매칭) |
| `/help` | 도움말 |

## 🎯 워크스페이스 시스템 (멀티 창 관리)

안티그래비티를 여러 창으로 열어두고(개발용 + 에이전트용), 텔레그램에서 특정 창을 타겟팅할 수 있습니다.

### 자동 타겟팅

`agent_config.json`의 `workspace.agent_folder`에 설정된 폴더명이 창 제목에 포함된 안티그래비티 창을 자동으로 찾습니다.

```json
{
  "workspace": {
    "agent_folder": "~/.gemini/antigravity/anti-agent",
    "target_window_index": null
  }
}
```

### 타겟 우선순위

1. `/target`으로 수동 지정된 창
2. `agent_config.json`에 저장된 인덱스
3. 창 제목에 에이전트 폴더명이 포함된 창 (자동 탐색)
4. 기본값: 1번 창

### `/에이전트` 워크플로우

안티그래비티 채팅에서 `/에이전트`를 입력하면 에이전트 전용 폴더를 새 창으로 자동 오픈합니다.

```bash
# 수동 실행
antigravity --new-window ~/.gemini/antigravity/anti-agent
```

## 🧠 커스텀 룰(규칙) 자동 세팅 가이드

이 프로젝트의 진정한 강력함은 텔레그램 채팅 창에서 말 한마디로 개인 비서를 커스텀하는 **Zero-Config 룰 엔진**에 있습니다. 코드를 열어볼 필요 없이 모바일에서 다음과 같이 지시해 보세요.

**1. 전용 비서 룰 (에이전트 룰 / 전역 적용)**
일상적인 대화와 보고 체계를 지시할 때 사용합니다. 
* 🗣️ **사용자 입력 예시**: "앞으로 나를 캡틴이라고 부르고 보고할때는 3줄로 핵심만 요약해. **이건 에이전트 룰이야.**"
* 🤖 **동작 방식**: 봇이 의도를 파악하고 글로벌 시스템 환경(`~/.gemini/antigravity/rules/agent_rules.md`)에 규칙을 영구 기록합니다.

**2. 프로젝트 룰 (개발자 룰 / 지역 적용)**
안티그래비티를 통해 특정 개발 폴더에서 코딩을 지시할 때 사용하는 전문 규칙입니다.
* 🗣️ **사용자 입력 예시**: "React 컴포넌트를 만들 때는 무조건 화살표 함수를 쓰고 TypeScript 타입을 명시해. **이건 개발자 룰이야.**"
* 🤖 **동작 방식**: 글로벌 룰을 오염시키지 않고, 현재 작업 중인 프로젝트 디렉토리에만 종속된 파일(`.cursorrules` 또는 `dev_rules.md`)에 저장하여 에이전트 모드 간의 간섭을 완전히 차단합니다.

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

## 💬 카카오톡 연동 (선택)

한국 사용자 대상 카카오톡 메시지 전송을 지원합니다.

### 설정 방법

1. [Kakao Developers](https://developers.kakao.com/) 접속 후 앱 생성
2. **카카오 로그인** 활성화 및 **Redirect URI** 등록: `http://localhost:9250/oauth`
3. **동의항목**에서 `talk_message`, `friends` 권한 활성화
4. `.env` 파일 설정:

```ini
KAKAO_REST_API_KEY=발급받은_REST_API_키
KAKAO_CLIENT_SECRET=클라이언트_시크릿
KAKAO_REDIRECT_URI=http://localhost:9250/oauth
```

5. OAuth 인증 실행:

```bash
python kakao_api.py auth
```

### 카카오톡 명령어

| 명령어 | 설명 |
|--------|------|
| `python kakao_api.py auth` | OAuth 인증 (최초 1회) |
| `python kakao_api.py send [메시지]` | 나에게 카톡 보내기 |
| `python kakao_api.py friends` | 친구 목록 조회 |
| `python kakao_api.py send_friend <UUID> [메시지]` | 친구에게 보내기 |
| `python kakao_api.py status` | 연동 상태 확인 |

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
