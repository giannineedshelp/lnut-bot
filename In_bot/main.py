"""
LanguageNut Discord Bot - Entry Point

Loads environment, initializes the bot, syncs slash commands, and runs the loop.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import aiohttp
import discord
from aiohttp import ClientSession, ClientTimeout
from discord.ext import commands
from dotenv import load_dotenv

# =========================
# PROJECT ROOT
# =========================
FILE_DIR = Path(__file__).resolve().parent
os.chdir(str(FILE_DIR))
sys.path.insert(0, str(FILE_DIR))

print("Running from:", os.getcwd())

# =========================
# PHONE PATH SUPPORT
# =========================
# Android internal storage can be at different mount points depending on device/app
PHONE_BASE_PATHS = [
    Path("/sdcard/Documents/lnut-bot/In_bot"),
    Path("/storage/emulated/0/Documents/lnut-bot/In_bot"),
    Path("/storage/self/primary/Documents/lnut-bot/In_bot"),
]

def resolve_project_root() -> Path:
    """
    Returns the project root to use for loading .env and resolving paths.
    Prefers the actual script location, but falls back to known phone paths
    if the script is being run from a non-standard location (e.g. Termux on Android).
    """
    # If the script itself lives inside one of the known phone paths, use that
    for phone_path in PHONE_BASE_PATHS:
        if phone_path.exists() and FILE_DIR == phone_path:
            print(f"Phone project root detected: {phone_path}")
            return phone_path

    # Check if any phone path exists and the script dir looks like a temp/unknown location
    for phone_path in PHONE_BASE_PATHS:
        if phone_path.exists():
            print(f"Phone project root found: {phone_path}")
            return phone_path

    # Default: use the script's own directory (standard PC behaviour)
    return FILE_DIR

PROJECT_ROOT = resolve_project_root()
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

print("Project root:", PROJECT_ROOT)

# =========================
# ENV
# =========================
ENV_PATHS = [
    FILE_DIR / ".env",
    FILE_DIR.parent / ".env",
    PROJECT_ROOT / ".env",
    PROJECT_ROOT.parent / ".env",
]
ENV_PATH = next((p for p in ENV_PATHS if p.exists()), None)

if not ENV_PATH:
    raise RuntimeError(
        ".env not found. Searched:\n" + "\n".join(str(p) for p in ENV_PATHS)
    )

load_dotenv(ENV_PATH, override=True)
print(f".env loaded from: {ENV_PATH}")

TOKEN: str = os.getenv("DISCORD_TOKEN", "")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN missing")

print("TOKEN LOADED:", bool(TOKEN))

# =========================
# LOCAL IMPORTS
# =========================
from utils.logger import setup_logging, log_user_command
from utils.encryption import get_fernet

logger = setup_logging()

raw_guild_id = os.getenv("GUILD_ID", "").strip()
GUILD_ID: Optional[int] = int(raw_guild_id) if raw_guild_id else None

ANNOUNCE_CHANNEL_ID: Optional[int] = None
raw_channel = os.getenv("ANNOUNCE_CHANNEL_ID", "").strip()
if raw_channel:
    try:
        ANNOUNCE_CHANNEL_ID = int(raw_channel)
    except ValueError:
        pass


# =========================
# BOT
# =========================
class LanguageNutBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name="/login | LanguageNut Automator",
            ),
        )

        self.aiohttp_session: Optional[ClientSession] = None
        self.fernet = get_fernet()

    async def setup_hook(self):
        connector = aiohttp.TCPConnector(limit=50, ttl_dns_cache=300)
        self.aiohttp_session = ClientSession(
            timeout=ClientTimeout(total=30, connect=10),
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            },
            connector=connector,
        )

        await self._load_cogs()

        try:
            if GUILD_ID:
                guild_obj = discord.Object(id=GUILD_ID)
                self.tree.copy_global_to(guild=guild_obj)
                synced = await self.tree.sync(guild=guild_obj)
                logger.info(f"Synced {len(synced)} commands to guild {GUILD_ID}")
            else:
                synced = await self.tree.sync()
                logger.info(f"Synced {len(synced)} global commands")
        except Exception as e:
            logger.error(f"Command sync failed: {e}")

        self.tree.error(self.on_tree_error)
        logger.info("Setup complete")

    async def _load_cogs(self):
        cogs: list[str] = ["commands.commands"]

        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.exception(f"Failed to load cog {cog}: {e}")

    async def on_ready(self):
        if self.user:
            logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info("Bot is online")
        logger.info("Logging systems initialized successfully")
        self.start_time = discord.utils.utcnow()
        await self._announce_online()

    async def _announce_online(self):
        channel_id = ANNOUNCE_CHANNEL_ID
        if not channel_id:
            for guild in self.guilds:
                if guild.system_channel:
                    channel_id = guild.system_channel.id
                    break
        if channel_id:
            self._announce_channel_id = channel_id
            channel = self.get_channel(channel_id)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    await channel.send("@everyone BOT IS ONLINE \U0001F7E2")
                    logger.info(f"Online announcement sent to #{channel.name}")
                except Exception as e:
                    logger.warning(f"Failed to send online announcement: {e}")

    async def _announce_offline(self):
        channel_id = getattr(self, "_announce_channel_id", ANNOUNCE_CHANNEL_ID)
        if not channel_id:
            return
        channel = self.get_channel(channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            try:
                await channel.send("@everyone BOT IS OFFLINE \U0001F534")
                logger.info("Offline announcement sent")
            except Exception as e:
                logger.warning(f"Failed to send offline announcement: {e}")

    async def on_disconnect(self):
        logger.warning("Bot disconnected from Discord gateway")
        await self._announce_offline()

    async def on_resumed(self):
        logger.info("Bot reconnected to Discord gateway")

    async def on_tree_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        orig = getattr(error, "original", error)
        logger.exception(f"Slash command error: {orig}")

        msg = f"\u26a0\ufe0f Error:\n```{str(orig)[:1500]}```"

        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception as exc:
            logger.error(f"Failed to send error message: {exc}")

    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        try:
            log_user_command(
                interaction.user.id,
                f"/{command.name}",
                f"Executed in guild {interaction.guild_id}",
            )
        except Exception as e:
            logger.warning(f"Failed command logging: {e}")

    async def close(self):
        await self._announce_offline()
        if self.aiohttp_session is not None and not self.aiohttp_session.closed:
            await self.aiohttp_session.close()
        await super().close()


# =========================
# MAIN
# =========================
async def main():
    bot = LanguageNutBot()
    try:
        await bot.start(TOKEN)
    except Exception as e:
        logger.exception(f"Exception during bot startup: {e}")
        raise
    finally:
        await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger("lnut_bot").info("Shutdown requested")
