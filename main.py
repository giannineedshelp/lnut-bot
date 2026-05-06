import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

import discord
from discord.ext import commands

# =========================
# PROJECT ROOT SETUP
# =========================
BASE_DIR = "/storage/emulated/0/Documents/In_bot"

os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

print("Running from:", os.getcwd())

# =========================
# LOAD ENV (ONLY ONCE)
# =========================
load_dotenv(".env", override=True)

TOKEN = os.getenv("DISCORD_TOKEN")
print("TOKEN LOADED:", TOKEN)

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN missing in .env")

# =========================
# LOCAL IMPORTS (AFTER PATH FIX)
# =========================
from utils.logger import setup_logging
from utils.encryption import get_fernet

logger = setup_logging()


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
                name="/login | LanguageNut Automator",
            ),
        )

        self.aiohttp_session = None
        self.fernet = get_fernet()

    async def setup_hook(self):
        import aiohttp

        self.aiohttp_session = aiohttp.ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "Origin": "https://www.languagenut.com",
                "Referer": "https://www.languagenut.com/",
            }
        )

        await self._load_cogs()
        await self.tree.sync()
        logger.info("Command tree synced")

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
                logger.error(f"Failed to load cog {cog}: {e}")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info("Bot is online")


# =========================
# MAIN START
# =========================
async def main():
    bot = LanguageNutBot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())