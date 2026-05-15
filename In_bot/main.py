"""main.py — LanguageNut Farming Bot"""
import os
import sys
import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands
from dotenv import load_dotenv
import aiohttp

load_dotenv()

from pathlib import Path
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('lnut-bot')

import random

class Config:
    def __init__(self):
        self.token = os.getenv('DISCORD_TOKEN', '')
        self.prefix = os.getenv('COMMAND_PREFIX', '!')
        self.announce_channel_id = int(os.getenv('ANNOUNCE_CHANNEL_ID', '0'))
        self.status_channel_id = int(os.getenv('BOT_STATUS_CHANNEL_ID', '0'))
        self.accounts = self._load_accounts()
        if not self.token:
            raise ValueError("DISCORD_TOKEN not set in environment")

    def _load_accounts(self) -> list:
        accounts = []
        i = 1
        while True:
            username = os.getenv(f'ACCOUNT_{i}_USERNAME')
            password = os.getenv(f'ACCOUNT_{i}_PASSWORD')
            if not username or not password:
                break
            accounts.append({'username': username, 'password': password})
            i += 1
        return accounts

class LNutBot(commands.Bot):
    def __init__(self):
        self._config = Config()
        self.aiohttp_session = None
        self._last_status = "unknown"
        self.start_time = None
        self._status_task = None

        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True

        super().__init__(
            command_prefix=commands.when_mentioned_or(self._config.prefix),
            intents=intents
        )

    @property
    def config(self):
        return self._config

    async def setup_hook(self):
        self.start_time = discord.utils.utcnow()
        self.aiohttp_session = aiohttp.ClientSession()

        # Load cogs
        initial_extensions = [
            "commands.commands",
            "commands.hub",
        ]
        for ext in initial_extensions:
            try:
                await self.load_extension(ext)
                print(f"  Loaded {ext}")
                logger.info(f"Loaded cog: {ext}")
            except Exception as e:
                print(f"  Failed to load {ext}: {e}")
                logger.error(f"Failed to load {ext}: {e}")

        # Sync commands
        try:
            synced = await self.tree.sync()
            print(f"  Synced {len(synced)} slash command(s)")
            logger.info(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            print(f"  Failed to sync commands: {e}")
            logger.error(f"Failed to sync commands: {e}")

        # Start status loop
        self._status_task = self.loop.create_task(self._update_status_loop())
        print("  Status updater task started")

    async def on_ready(self):
        print(f"\n{'=' * 50}")
        print(f"  Bot is ready! Logged in as {self.user}")
        print(f"{'=' * 50}\n")
        await self._send_announcement("startup")
        await self._update_voice_status("connected")

    async def on_disconnect(self):
        self._last_status = "disconnected"
        try:
            await self._update_voice_status("disconnected")
        except Exception:
            pass
        try:
            await self._send_announcement("disconnect")
        except Exception:
            pass
        print("Bot disconnected from Discord")

    async def on_resumed(self):
        self._last_status = "connected"
        try:
            await self._update_voice_status("connected")
        except Exception:
            pass
        try:
            await self._send_announcement("reconnect")
        except Exception:
            pass
        print("Bot reconnected to Discord")

    async def _send_announcement(self, event_type: str, retry_seconds: int = 0):
        if not self.config.announce_channel_id:
            return
        channel = self.get_channel(self.config.announce_channel_id)
        if not channel:
            logger.warning(f"Announcement channel {self.config.announce_channel_id} not found")
            return

        announcements = {
            "startup": {
                "title": "Bot Online",
                "description": (
                    f"**LanguageNut Farmer** is now online!\n"
                    f"Started at: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                ),
                "color": discord.Color.green()
            },
            "shutdown": {
                "title": "Bot Offline",
                "description": "**LanguageNut Farmer** is going offline.",
                "color": discord.Color.red()
            },
            "disconnect": {
                "title": "Bot Disconnected",
                "description": (
                    f"**LanguageNut Farmer** lost connection at "
                    f"{discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}."
                ),
                "color": discord.Color.orange()
            },
            "reconnect": {
                "title": "Bot Reconnected",
                "description": (
                    f"**LanguageNut Farmer** reconnected.\n"
                    f"Time: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                ),
                "color": discord.Color.green()
            },
            "error": {
                "title": "Bot Error",
                "description": "**LanguageNut Farmer** error. Check logs.",
                "color": discord.Color.red()
            },
            "rate_limit": {
                "title": "Rate Limited",
                "description": (
                    f"**LanguageNut Farmer** hit a rate limit (429).\n"
                    f"Retrying in **{retry_seconds}s** - {discord.utils.utcnow().strftime('%H:%M:%S UTC')}"
                ),
                "color": discord.Color.orange()
            },
        }

        info = announcements.get(event_type, announcements['startup'])
        embed = discord.Embed(
            title=info['title'],
            description=info['description'],
            color=info['color'],
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Accounts", value=str(len(self.config.accounts)), inline=True)
        embed.add_field(name="Uptime", value=self._get_uptime(), inline=True)
        embed.set_footer(text="LanguageNut Farmer - Status Monitor")

        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send announcement: {e}")

    def _get_uptime(self) -> str:
        if not self.start_time:
            return "N/A"
        delta = discord.utils.utcnow() - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"

    async def _update_status_loop(self):
        """Background task - announces rate limit retry timers."""
        await self.wait_until_ready()
        retry_delay = 60
        last_announcement_tag = ""

        while not self.is_closed():
            try:
                if self.is_ready():
                    has_accounts = False
                    for guild in self.guilds:
                        acc_dir = Path("accounts") / str(guild.id)
                        if acc_dir.exists() and list(acc_dir.glob("*.txt")):
                            has_accounts = True
                            break
                    status = "farming" if has_accounts else "idle"
                else:
                    status = "disconnected"

                self._last_status = status
                await self._update_voice_status(status)
                retry_delay = 60

            except discord.HTTPException as e:
                if e.status == 429:
                    retry_delay = min(retry_delay * 2, 600)
                    jitter = random.uniform(0, retry_delay * 0.1)
                    total_sleep = retry_delay + jitter
                    logger.warning(f"429 on status update - retrying in {total_sleep:.0f}s")

                    tag = f"429-{int(total_sleep)}"
                    if tag != last_announcement_tag:
                        last_announcement_tag = tag
                        await self._send_announcement("rate_limit", retry_seconds=int(total_sleep))

                    await asyncio.sleep(total_sleep)
                    continue
                else:
                    logger.error(f"Status update HTTP error: {e}")
                    retry_delay = 60
            except Exception as e:
                logger.error(f"Status update error: {e}")
                retry_delay = 60

            await asyncio.sleep(60)

    async def _update_voice_status(self, status: str):
        if not self.config.status_channel_id:
            return
        channel = self.get_channel(self.config.status_channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            return
        try:
            names = {
                "connected":    "Online",
                "farming":      "Farming",
                "idle":         "Idle",
                "disconnected": "Offline",
                "error":        "Error",
                "maintenance":  "Maintenance",
                "unknown":      "Unknown",
            }
            name = names.get(status, "Unknown")
            if channel.name != name:
                await channel.edit(name=name)
        except discord.Forbidden:
            logger.warning("No permission to edit status voice channel")
        except discord.HTTPException as e:
            if e.status != 429:
                logger.error(f"Failed to update voice channel: {e}")

    async def close(self):
        logger.info("Bot shutting down...")
        if self._status_task:
            self._status_task.cancel()
        if self.aiohttp_session and not self.aiohttp_session.closed:
            await self.aiohttp_session.close()
        try:
            await self._send_announcement("shutdown")
        except Exception:
            pass
        try:
            await self._update_voice_status("maintenance")
        except Exception:
            pass
        await super().close()

    def run(self):
        try:
            super().run(self.config.token, reconnect=True)
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            logger.info("Bot stopped")

if __name__ == "__main__":
    print()
    print("=" * 50)
    print("  LanguageNut Farmer Bot")
    print("=" * 50)
    print()
    bot = LNutBot()
    bot.run()
