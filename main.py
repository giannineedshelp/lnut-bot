import asyncio
import logging
import os
import time
from pathlib import Path
from dotenv import load_dotenv

import discord
from discord.ext import commands

# =========================
# ENV LOADER (UNIVERSAL)
# =========================
BASE_DIR = Path(__file__).resolve().parent

def load_environment():
    possible_paths = [
        BASE_DIR / ".env",                     # PC project root
        Path(".env"),                          # current working dir
        Path.home() / ".env",                 # server/home
        Path("/storage/emulated/0/In_bot/.env"),  # Android/Pydroid
    ]

    for path in possible_paths:
        if path.exists():
            load_dotenv(path, override=True)
            print(f"[ENV] Loaded from: {path}")
            return

    print("[WARN] No .env file found. Using system environment only.")

load_environment()

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN missing (check .env or system env)")


# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lnut_bot")


# =========================
# BOT CLASS
# =========================
class LanguageNutBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name="/login | LanguageNut Bot",
            ),
        )

        self.aiohttp_session = None
        self.fernet = None

    # =========================
    # STARTUP
    # =========================
    async def setup_hook(self):
        import aiohttp
        from utils.encryption import get_fernet

        start = time.time()
        logger.info("Starting setup_hook...")

        self.aiohttp_session = aiohttp.ClientSession()
        self.fernet = get_fernet()

        await self.load_cogs()

        logger.info(f"Cogs loaded in {time.time() - start:.2f}s")

        try:
            await self.tree.sync()
            logger.info("Slash commands synced")
        except Exception as e:
            logger.error(f"Command sync failed: {e}")

    # =========================
    # COG LOADER
    # =========================
    async def load_cogs(self):
        cogs = [
            "commands.core",
            "commands.settings",
        ]

        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load {cog}: {e}")

    # =========================
    # READY EVENT
    # =========================
    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info("Bot is fully online 🚀")

    # =========================
    # CLEAN SHUTDOWN
    # =========================
    async def close(self):
        logger.info("Shutting down bot...")

        if self.aiohttp_session:
            await self.aiohttp_session.close()

        await super().close()


# =========================
# RUN BOT
# =========================
async def main():
    bot = LanguageNutBot()

    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())