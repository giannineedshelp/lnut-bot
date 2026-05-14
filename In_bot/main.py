"""
main.py — LanguageNut Farming Bot
Discord bot with stealth anti-detection, announcements channel,
voice channel status indicator, and comprehensive UI.
"""
import os
import sys
import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands
from dotenv import load_dotenv
import aiohttp

# Auto-load .env file
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('lnut-bot')

from config import ACCOUNTS_DIR

# ─── Config ──────────────────────────────────────────────────────────────────

class Config:
    """Bot configuration loaded from environment."""

    def __init__(self):
        self.token = os.getenv('DISCORD_TOKEN', '')
        self.prefix = os.getenv('COMMAND_PREFIX', '!')
        self.announce_channel_id = int(os.getenv('ANNOUNCE_CHANNEL_ID', '0'))
        self.status_channel_id = int(os.getenv('BOT_STATUS_CHANNEL_ID', '0'))
        self.accounts = self._load_accounts()

        if not self.token:
            raise ValueError("DISCORD_TOKEN not set in environment")

    def _load_accounts(self) -> list:
        """Load accounts from environment variables."""
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


# ─── Bot Class ───────────────────────────────────────────────────────────────

class LNutBot(commands.Bot):
    """Main bot class with lifecycle management and status reporting."""

    def __init__(self):
        self._config = Config()
        self.aiohttp_session = None

        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True

        super().__init__(
            command_prefix=commands.when_mentioned_or(self._config.prefix),
            intents=intents,
            help_command=None
        )

        self.start_time = None
        self._status_task = None
        self._last_status = "unknown"

    @property
    def config(self):
        return self._config

    # ─── Lifecycle ────────────────────────────────────────────────────────

    async def setup_hook(self):
        """Async initialisation: load cogs, create aiohttp session."""
        self.aiohttp_session = aiohttp.ClientSession()

        cogs_to_load = [
            "commands.commands",
            "commands.xp_commands",
            "commands.hub",
        ]

        for cog_path in cogs_to_load:
            try:
                await self.load_extension(cog_path)
                print(f"  ✅ Loaded {cog_path}")
                logger.info(f"Loaded cog: {cog_path}")
            except Exception as e:
                print(f"  ❌ Failed to load {cog_path}: {e}")
                logger.error(f"Failed to load {cog_path}: {e}")

        # Clear old cached commands first to fix CommandNotFound bug
        try:
            for guild in self.guilds:
                self.tree.clear_commands(guild=guild)
        except Exception:
            pass

        try:
            synced = await self.tree.sync()
            print(f"  ✅ Synced {len(synced)} slash command(s)")
            logger.info(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            print(f"  ❌ Failed to sync commands: {e}")
            logger.error(f"Failed to sync commands: {e}")

        self._status_task = self.loop.create_task(self._update_status_loop())
        print("  📊 Status updater task started")

    async def on_ready(self):
        """Called when the bot has connected and initialised."""
        self.start_time = discord.utils.utcnow()
        self._last_status = "connected"

        print()
        print("═" * 50)
        print(f"  ✅ Bot is ready! Logged in as {self.user}")
        print("═" * 50)
        print()

        await self._update_voice_status("connected")
        await self._send_announcement("startup")

    async def on_disconnect(self):
        """Called when the bot disconnects from Discord."""
        self._last_status = "disconnected"
        await self._update_voice_status("disconnected")
        await self._send_announcement("disconnect")
        print("🔴 Bot disconnected from Discord")

    async def on_resumed(self):
        """Called when the bot reconnects after a disconnect."""
        self._last_status = "connected"
        await self._update_voice_status("connected")
        await self._send_announcement("reconnect")
        print("🟢 Bot reconnected to Discord")

    async def _send_announcement(self, event_type: str):
        """Send an announcement to the configured announcements channel."""
        if not self.config.announce_channel_id:
            return

        channel = self.get_channel(self.config.announce_channel_id)
        if not channel:
            logger.warning(f"Announcement channel {self.config.announce_channel_id} not found")
            return

        announcements = {
            "startup": {
                "title": "🟢 Bot Online",
                "description": (
                    f"**LanguageNut Farmer** is now online!\n"
                    f"Started at: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                ),
                "color": discord.Color.green()
            },
            "shutdown": {
                "title": "🔴 Bot Offline",
                "description": "**LanguageNut Farmer** is going offline for maintenance/restart.",
                "color": discord.Color.red()
            },
            "disconnect": {
                "title": "🟡 Bot Disconnected",
                "description": (
                    f"**LanguageNut Farmer** lost connection to Discord at "
                    f"{discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}."
                ),
                "color": discord.Color.orange()
            },
            "reconnect": {
                "title": "🟢 Bot Reconnected",
                "description": (
                    f"**LanguageNut Farmer** has reconnected to Discord.\n"
                    f"Time: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
                ),
                "color": discord.Color.green()
            },
            "error": {
                "title": "🔴 Bot Error",
                "description": "**LanguageNut Farmer** encountered an error. Check logs for details.",
                "color": discord.Color.red()
            }
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
        embed.set_footer(text="LanguageNut Farmer • Status Monitor")

        try:
            await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send announcement: {e}")

    def _get_uptime(self) -> str:
        """Get a human-readable uptime string."""
        if not self.start_time:
            return "N/A"
        delta = discord.utils.utcnow() - self.start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"

    async def _update_status_loop(self):
        """Background task to update voice channel with real bot status.
        
        Fixes bugs:
        - Rate limiting (429): uses exponential backoff with jitter
        - Voice channel not working: simplified to just channel name edits
        - Status not syncing: checks actual account files on disk
        """
        await self.wait_until_ready()
        retry_delay = 60  # start at 60s

        while not self.is_closed():
            try:
                if self.is_ready():
                    # Check if any guild has actual account files
                    has_accounts = False
                    for guild in self.guilds:
                        acc_dir = ACCOUNTS_DIR / str(guild.id)
                        if acc_dir.exists() and list(acc_dir.glob("*.txt")):
                            has_accounts = True
                            break
                    status = "farming" if has_accounts else "idle"
                else:
                    status = "disconnected"

                self._last_status = status
                await self._update_voice_status(status)
                retry_delay = 60  # reset on success

            except discord.HTTPException as e:
                if e.status == 429:
                    # Rate limited — exponential backoff with jitter
                    retry_delay = min(retry_delay * 2, 600)
                    jitter = random.uniform(0, retry_delay * 0.1)
                    logger.warning(f"429 on status update — retrying in {retry_delay + jitter:.0f}s")
                    await asyncio.sleep(retry_delay + jitter)
                    continue
                else:
                    logger.error(f"Status update HTTP error: {e}")
            except Exception as e:
                logger.error(f"Status update error: {e}")

            await asyncio.sleep(60)

    async def _update_voice_status(self, status: str):
        """Update voice channel name to reflect real bot status.
        
        Fixed: cleaner names, no user_limit changes (caused 429s),
        only edits when name actually changes.
        """
        if not self.config.status_channel_id:
            return

        channel = self.get_channel(self.config.status_channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            return

        try:
            names = {
                "connected":    "🟢 Online",
                "farming":      "🌾 Farming",
                "idle":         "🟡 Idle",
                "disconnected": "🔴 Offline",
                "error":        "🔴 Error",
                "maintenance":  "🟠 Maintenance",
                "unknown":      "⚪ Unknown",
            }
            name = names.get(status, "⚪ Unknown")
            if channel.name != name:
                await channel.edit(name=name)
                logger.debug(f"Status channel → {name}")

        except discord.Forbidden:
            logger.warning("No permission to edit status voice channel")
        except discord.HTTPException as e:
            if e.status != 429:  # Don't log 429s here, handled in loop
                logger.error(f"Failed to update voice channel: {e}")

    async def close(self):
        """Clean shutdown."""
        logger.info("Bot shutting down...")

        if self._status_task:
            self._status_task.cancel()

        if self.aiohttp_session and not self.aiohttp_session.closed:
            await self.aiohttp_session.close()

        await self._send_announcement("shutdown")
        await self._update_voice_status("maintenance")

        await super().close()

    def run(self):
        """Start the bot."""
        try:
            super().run(self.config.token, reconnect=True)
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            logger.info("Bot stopped")


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("═" * 50)
    print("  🚀 LanguageNut Farmer Bot")
    print("═" * 50)
    print()

    bot = LNutBot()
    bot.run()