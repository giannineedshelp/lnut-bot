import asyncio
import logging
import os
import time
from pathlib import Path
from dotenv import load_dotenv

import discord
from discord.ext import commands

# =========================
# PROJECT SETUP
# =========================
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN missing in .env")


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

        # lightweight init ONLY (no heavy stuff here)
        self.aiohttp_session = None
        self.fernet = None

    # =========================
    # STARTUP HOOK (OPTIMISED)
    # =========================
    async def setup_hook(self):
        import aiohttp
        from utils.encryption import get_fernet

        start = time.time()
        logger.info("Starting setup_hook...")

        # 1. Async HTTP session (fast, non-blocking)
        self.aiohttp_session = aiohttp.ClientSession()

        # 2. Load encryption AFTER startup begins (not init)
        self.fernet = get_fernet()

        # 3. Load cogs (safe + sequential for stability)
        await self._load_cogs()

        logger.info(f"Cogs loaded in {time.time() - start:.2f}s")

        # 4. Sync slash commands (separate step for clarity)
        logger.info("Syncing application commands...")
        try:
            await self.tree.sync()
            logger.info("Command sync complete")
        except Exception as e:
            logger.error(f"Command sync failed: {e}")

    # =========================
    # COG LOADER (STABLE)
    # =========================
    async def _load_cogs(self):
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
        logger.info("Bot is fully online")


# =========================
# CLEAN SHUTDOWN
# =========================
async def main():
    bot = LanguageNutBot()

    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())