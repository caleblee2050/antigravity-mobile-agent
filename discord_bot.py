#!/usr/bin/env python3
"""
안티그래비티 모바일 에이전트 — 디스코드 봇
디스코드를 통해 안티그래비티를 원격 제어합니다.

기능:
- 특정 채널 메시지 수신 → Host 서버에 전달
- AI 응답 폴링 → 디스코드 채널에 전달
- 슬래시 커맨드: /ask, /screenshot, /status

설정:
  1. Discord Developer Portal에서 봇 생성
  2. .env에 DISCORD_TOKEN, DISCORD_CHANNEL_ID 설정
  3. 봇을 서버에 초대 (Message Content Intent 활성화 필수)
"""

import os
import asyncio
import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

TOKEN = os.getenv("DISCORD_TOKEN", "")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0"))
HOST_URL = f"http://localhost:{os.getenv('PORT', '9150')}"
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "antigravity2026")

if not TOKEN:
    print("❌ DISCORD_TOKEN이 .env에 설정되지 않았습니다.")
    print("   Discord Developer Portal에서 봇을 생성하고 토큰을 .env에 추가하세요.")
    print("   DISCORD_TOKEN=your_token_here")
    exit(1)

if CHANNEL_ID == 0:
    print("❌ DISCORD_CHANNEL_ID가 .env에 설정되지 않았습니다.")
    print("   디스코드 채널 ID를 .env에 추가하세요.")
    print("   DISCORD_CHANNEL_ID=123456789")
    exit(1)


class AntigravityBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.last_outbound_timestamp = ""
        self.session = None

    async def setup_hook(self):
        """봇 시작 시 슬래시 커맨드 등록"""
        await self.tree.sync()
        self.poll_replies.start()

    async def on_ready(self):
        print(f"🤖 디스코드 봇 시작! {self.user}")
        print(f"📡 Host 서버: {HOST_URL}")
        print(f"📺 감시 채널: {CHANNEL_ID}")
        self.session = aiohttp.ClientSession()

        channel = self.get_channel(CHANNEL_ID)
        if channel:
            await channel.send("🚀 **안티그래비티 모바일 에이전트** 연결됨!")

    async def on_message(self, message: discord.Message):
        """채널 메시지 수신 → Host 서버로 전달"""
        if message.author.bot:
            return
        if message.channel.id != CHANNEL_ID:
            return

        text = message.content.strip()
        if not text or text.startswith("/"):
            return

        try:
            async with self.session.post(
                f"{HOST_URL}/api/msg",
                json={"text": text, "password": AUTH_PASSWORD},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    await message.add_reaction("📨")
                else:
                    await message.add_reaction("❌")
        except Exception as e:
            await message.reply(f"❌ 서버 연결 실패: {e}")

    @tasks.loop(seconds=5)
    async def poll_replies(self):
        """Host 서버에서 AI 응답 폴링"""
        if not self.session:
            return

        try:
            async with self.session.get(
                f"{HOST_URL}/api/sync",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    outbound = data.get("outbound", {})

                    if (
                        outbound.get("text")
                        and outbound.get("timestamp") != self.last_outbound_timestamp
                    ):
                        self.last_outbound_timestamp = outbound["timestamp"]
                        channel = self.get_channel(CHANNEL_ID)
                        if channel:
                            # 2000자 제한 대응
                            text = outbound["text"]
                            if len(text) > 1900:
                                chunks = [text[i : i + 1900] for i in range(0, len(text), 1900)]
                                for chunk in chunks:
                                    await channel.send(f"🧠 **AI 응답:**\n{chunk}")
                            else:
                                await channel.send(f"🧠 **AI 응답:**\n{text}")
        except Exception:
            pass

    @poll_replies.before_loop
    async def before_poll(self):
        await self.wait_until_ready()

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()


bot = AntigravityBot()


@bot.tree.command(name="ask", description="안티그래비티에게 질문합니다")
async def ask_command(interaction: discord.Interaction, question: str):
    """슬래시 커맨드: /ask"""
    await interaction.response.defer()
    try:
        async with bot.session.post(
            f"{HOST_URL}/api/msg",
            json={"text": question, "password": AUTH_PASSWORD},
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status == 200:
                await interaction.followup.send(f"📨 질문 전송됨: {question}")
            else:
                await interaction.followup.send("❌ 메시지 전송 실패")
    except Exception as e:
        await interaction.followup.send(f"❌ 서버 연결 실패: {e}")


@bot.tree.command(name="screenshot", description="현재 화면 스크린샷을 가져옵니다")
async def screenshot_command(interaction: discord.Interaction):
    """슬래시 커맨드: /screenshot"""
    await interaction.response.defer()
    try:
        async with bot.session.get(
            f"{HOST_URL}/api/screenshot",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data.get("data"):
                    import base64
                    import io

                    img_bytes = base64.b64decode(data["data"])
                    file = discord.File(io.BytesIO(img_bytes), filename="screenshot.jpg")
                    await interaction.followup.send("📸 현재 화면:", file=file)
                else:
                    await interaction.followup.send("📸 스크린샷이 아직 없습니다.")
    except Exception as e:
        await interaction.followup.send(f"❌ 스크린샷 가져오기 실패: {e}")


@bot.tree.command(name="status", description="에이전트 시스템 상태를 확인합니다")
async def status_command(interaction: discord.Interaction):
    """슬래시 커맨드: /status"""
    await interaction.response.defer()
    try:
        async with bot.session.get(
            f"{HOST_URL}/api/status",
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                components = data.get("components", {})

                status_lines = ["**📊 시스템 상태:**"]
                for name, info in components.items():
                    status_icon = "🟢" if info.get("status") == "running" else "🔴"
                    status_lines.append(f"  {status_icon} {name}: {info.get('status', 'unknown')}")

                if data.get("tailscale_ip"):
                    status_lines.append(f"  🌐 Tailscale: {data['tailscale_ip']}")

                await interaction.followup.send("\n".join(status_lines))
            else:
                await interaction.followup.send("❌ 상태 확인 실패")
    except Exception as e:
        await interaction.followup.send(f"❌ 서버 연결 실패: {e}")


if __name__ == "__main__":
    print("🤖 안티그래비티 — 디스코드 봇 시작!")
    bot.run(TOKEN)
