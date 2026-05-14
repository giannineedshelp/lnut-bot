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
    def config(self) -> Config:
        return self._config

    async def _load_extensions(self):
        """Load command extensions that actually exist."""
        extensions = ['commands.commands', 'commands.xp_commands']
        loaded = 0
        failed = 0
        for ext in extensions:
            try:
                await self.load_extension(ext)
                logger.info(f"  ✅ Loaded extension: {ext}")
                loaded += 1
            except Exception as e:
                logger.error(f"  ❌ Failed to load extension {ext}: {e}")
                failed += 1
        logger.info(f"Extensions: {loaded} loaded, {failed} failed")
        return loaded, failed

    async def on_ready(self):
        """Called when the bot is ready and connected to Discord."""
        self.start_time = discord.utils.utcnow()

        print()
        print("═" * 50)
        print(f"  🤖 Bot connected as {self.user} (ID: {self.user.id})")
        print(f"  🌐 Connected to {len(self.guilds)} guild(s)")
        print(f"  👤 Accounts configured: {len(self.config.accounts)}")
        print("═" * 50)
        print()

        logger.info(f"Bot connected as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")

        # Load extensions now that the bot is connected
        print("📦 Loading extensions...")
        loaded, failed = await self._load_extensions()
        print(f"📦 Done: {loaded} loaded, {failed} failed")
        print()

        # Set bot activity
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="for language farming commands"
            )
        )
        print("🎯 Activity set")

        # Sync slash commands — cogs are loaded now
        print("🔄 Syncing slash commands...")
        try:
            synced = await self.tree.sync()
            print(f"  ✅ Synced {len(synced)} slash command(s)")
            logger.info(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            print(f"  ❌ Failed to sync commands: {e}")
            logger.error(f"Failed to sync commands: {e}")

        # Start voice channel status updater
        self._status_task = self.loop.create_task(self._update_status_loop())
        print("📊 Status updater task started")

        # Send startup announcement
        await self._send_announcement("startup")

        print()
        print("═" * 50)
        print(f"  ✅ Bot is ready! Logged in as {self.user}")
        print("═" * 50)
        print()

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
                "description": f"**LanguageNut Farmer** is now online!\nStarted at: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
                "color": discord.Color.green()
            },
            "shutdown": {
                "title": "🔴 Bot Offline",
                "description": "**LanguageNut Farmer** is going offline for maintenance/restart.",
                "color": discord.Color.red()
            },
            "disconnect": {
                "title": "🟡 Bot Disconnected",
                "description": f"**LanguageNut Farmer** lost connection to Discord at {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}.",
                "color": discord.Color.orange()
            },
            "reconnect": {
                "title": "🟢 Bot Reconnected",
                "description": f"**LanguageNut Farmer** has reconnected to Discord.\nTime: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
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
        """Background task to periodically update voice channel status."""
        await self.wait_until_ready()

        while not self.is_closed():
            try:
                if self.is_ready():
                    healthy_accounts = 0
                    for acc in self.config.accounts:
                        healthy_accounts += 1
                    status = "connected" if healthy_accounts > 0 else "degraded"
                else:
                    status = "disconnected"

                self._last_status = status
                await self._update_voice_status(status)

            except Exception as e:
                logger.error(f"Status update error: {e}")
                self._last_status = "error"
                await self._update_voice_status("error")

            await asyncio.sleep(60)

    async def _update_voice_status(self, status: str):
        if not self.config.status_channel_id:
            return

        channel = self.get_channel(self.config.status_channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            return

        try:
            status_config = {
                "connected": {"name": "🟢 Bot Online", "user_limit": 0},
                "degraded": {"name": "🟠 Bot Degraded", "user_limit": 1},
                "disconnected": {"name": "🔴 Bot Offline", "user_limit": 0},
                "error": {"name": "🔴 Bot Error", "user_limit": 0},
                "farming": {"name": "🟢 Farming Active", "user_limit": 0},
                "idle": {"name": "🟡 Bot Idle", "user_limit": 1},
                "maintenance": {"name": "🟠 Maintenance", "user_limit": 0},
                "unknown": {"name": "⚪ Status Unknown", "user_limit": 0}
            }

            config = status_config.get(status, status_config["unknown"])

            if channel.name != config["name"]:
                await channel.edit(
                    name=config["name"],
                    user_limit=config["user_limit"]
                )
                logger.debug(f"Updated status channel to: {config['name']}")

        except discord.Forbidden:
            logger.warning("No permission to edit status voice channel")
        except discord.HTTPException as e:
            logger.error(f"Failed to update voice channel: {e}")

    async def close(self):
        """Clean shutdown."""
        logger.info("Bot shutting down...")

        if self._status_task:
            self._status_task.cancel()

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