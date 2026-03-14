.PHONY: help install start stop restart logs status clean

PLIST_NAME=ai.a4k.antigravity-mobile-agent
PLIST_FILE=$(PLIST_NAME).plist
PLIST_TEMPLATE=$(PLIST_FILE).template
LAUNCH_AGENT_DIR=$(HOME)/Library/LaunchAgents
TARGET_PLIST=$(LAUNCH_AGENT_DIR)/$(PLIST_FILE)
CWD=$(shell pwd)

help:
	@echo "Antigravity Mobile Agent - 백그라운드 관리 도구"
	@echo ""
	@echo "명령어 목록:"
	@echo "  make install  - LaunchAgent 등록 및 백그라운드 구동 시작 (1회 필수)"
	@echo "  make start    - 백그라운드 에이전트 시작"
	@echo "  make stop     - 백그라운드 에이전트 정지 (PC 재부팅시 안 켜짐)"
	@echo "  make restart  - 백그라운드 에이전트 재시작"
	@echo "  make logs     - 실시간 로그 보기 (Ctrl+C 로 종료)"
	@echo "  make status   - 현재 실행 중인지 상태 확인"
	@echo "  make clean    - LaunchAgent에서 완전 제거"

install:
	@echo "==> $(PLIST_NAME) 시스템 등록 준비"
	@mkdir -p $(LAUNCH_AGENT_DIR)
	@mkdir -p $(CWD)/logs
	@# 템플릿의 {WORKING_DIR} 을 현재 절대경로로 치환하여 plist 생성
	@sed "s|{WORKING_DIR}|$(CWD)|g" $(PLIST_TEMPLATE) > $(PLIST_FILE)
	@cp $(PLIST_FILE) $(TARGET_PLIST)
	@echo "==> $(TARGET_PLIST) 복사 완료"
	@# 기존에 로드되어있을 수 있으니 먼저 언로드 시도 (에러 무시)
	@-launchctl unload $(TARGET_PLIST) 2>/dev/null || true
	@echo "==> 에이전트 로드 및 무중단 백그라운드 시작"
	@launchctl load -w $(TARGET_PLIST)
	@echo "✅ 설치 및 시작 완료! (종료하려면 'make stop', 상태확인은 'make status')"

start:
	@echo "==> 에이전트 시작 중..."
	@launchctl load -w $(TARGET_PLIST)
	@echo "✅ 됨!"

stop:
	@echo "==> 에이전트 정지 중..."
	@launchctl unload -w $(TARGET_PLIST)
	@echo "✅ 꺼짐!"

restart: stop start

logs:
	@echo "==> 에이전트 실시간 로그 추적 (종료: Ctrl+C) <=="
	@# 파이썬 내부 로그와, stdout/err 로그를 동시에 추적
	@tail -f logs/brain.log logs/agent.out logs/agent.err

status:
	@echo "==> 에이전트 상태 <=="
	@launchctl list | grep $(PLIST_NAME) || echo "실행 중이 아닙니다."

clean: stop
	@echo "==> LaunchAgent에서 PLIST 파일 제거 중..."
	@rm -f $(TARGET_PLIST)
	@rm -f $(PLIST_FILE)
	@echo "✅ 스케줄러 등록 해제 완료."
