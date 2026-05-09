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
# ENV
# =========================
ENV_PATHS = [FILE_DIR / ".env", FILE_DIR.parent / ".env"]
ENV_PATH = next((p for p in ENV_PATHS if p.exists()), None)

if not ENV_PATH:
    raise RuntimeError(".env not found")

load_dotenv(ENV_PATH, override=True)

TOKEN: str = os.getenv("DISCORD_TOKEN", "")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN missing")

print("TOKEN LOADED:", bool(TOKEN))

# =========================
# LOCAL IMPORTS
# =========================
from utils.logger import setup_logging
from utils.encryption import get_fernet

logger = setup_logging()

GUILD_ID_RAW = os.getenv("GUILD_ID", "").strip()
try:
    GUILD_ID: Optional[int] = int(GUILD_ID_RAW) if GUILD_ID_RAW else None
except ValueError:
    GUILD_ID = None


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
        # Shared HTTP session with sensible timeout and connection pooling
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

        # Sync ONCE — guild-scoped if GUILD_ID set (instant), otherwise global (up to 1 hr)
        try:
            if GUILD_ID:
                guild_obj = discord.Object(id=GUILD_ID)
                # App commands in this cog are declared globally, so copy them into
                # the dev guild before a guild-scoped sync.
                self.tree.copy_global_to(guild=guild_obj)
                synced = await self.tree.sync(guild=guild_obj)
                logger.info(f"Synced {len(synced)} commands to guild {GUILD_ID}")
            else:
                synced = await self.tree.sync()
                logger.info(f"Synced {len(synced)} global commands")
        except Exception as e:
            logger.error(f"Command sync failed: {e}")

        # Global error handler for slash commands
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

    async def on_tree_error(
        self, interaction: discord.Interaction, error: Exception
    ):
        orig = getattr(error, "original", error)
        logger.exception(f"Slash command error: {orig}")

        msg = f"⚠️ Error:\n```{str(orig)[:1500]}```"

        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception as exc:
            logger.error(f"Failed to send error message: {exc}")

    async def close(self):
        if self.aiohttp_session is not None and not self.aiohttp_session.closed:
            await self.aiohttp_session.close()
        await super().close()


# =========================
# MAIN
# =========================
async def main():
    bot = LanguageNutBot()
    await bot.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger("lnut_bot").info("Shutdown requested")
