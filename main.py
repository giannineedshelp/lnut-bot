# main.py
"""
LanguageNut Discord Bot — entry point.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

# =========================
# PROJECT ROOT (LOCKED)
# =========================

BASE_DIR = Path("/storage/emulated/0/Documents/In_bot/lnut-bot")
sys.path.insert(0, str(BASE_DIR))

# =========================
# ENV LOAD
# =========================

ENV_PATH = BASE_DIR / ".env"

if not ENV_PATH.exists():
    raise RuntimeError(f".env not found at {ENV_PATH}")

load_dotenv(ENV_PATH, override=True)
print(f"[ENV] Loaded from: {ENV_PATH}")

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN missing in .env")

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

logger = logging.getLogger("lnut_bot")


# =========================
# BOT
# =========================

class LanguageNutBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="?",
            intents=intents,
            owner_id=1453752725324955656,
        )

        self.aiohttp_session = None
        self.fernet = None

    async def setup_hook(self):
        import aiohttp
        from utils.encryption import get_fernet

        self.aiohttp_session = aiohttp.ClientSession()
        self.fernet = get_fernet()

        await self.load_all_cogs()

        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} commands")
        except Exception as e:
            logger.error(f"Sync failed: {e}")

    async def load_all_cogs(self):
        cogs = [
            "commands.core",
            "commands.settings",
        ]

        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.exception(f"Failed loading {cog}: {e}")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user}")
        logger.info("Bot fully online")

        try:
            synced = await self.tree.sync()
            logger.info(f"[READY SYNC] {len(synced)} commands synced")
        except Exception as e:
            logger.error(f"[READY SYNC ERROR] {e}")

    async def close(self):
        logger.info("Shutting down...")

        if self.aiohttp_session:
            await self.aiohttp_session.close()

        await super().close()


# =========================
# MAIN
# =========================

async def main():
    bot = LanguageNutBot()

    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())