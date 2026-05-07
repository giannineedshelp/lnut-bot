import asyncio
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

import discord
from discord import app_commands
from discord.ext import commands

# =========================
# PROJECT ROOT SETUP
# =========================
FILE_DIR = Path(__file__).resolve().parent

POSSIBLE_BASE_DIRS = [
    os.getenv("INBOT_BASE_DIR"),
    "/storage/emulated/0/Documents/In_bot",
    str(FILE_DIR),
    str(FILE_DIR.parent),
]

BASE_DIR = None
for path in POSSIBLE_BASE_DIRS:
    if path and Path(path).exists():
        BASE_DIR = Path(path)
        break

if not BASE_DIR:
    raise RuntimeError(
        "Project folder missing. Checked:\n"
        + "\n".join(str(path) for path in POSSIBLE_BASE_DIRS if path)
    )

os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))

print("Running from:", os.getcwd())

# =========================
# LOAD ENV (ONLY ONCE)
# =========================
ENV_PATHS = [
    BASE_DIR / ".env",
    BASE_DIR.parent / ".env",
    Path("/storage/emulated/0/Documents/In_bot/.env"),
]

ENV_PATH = next((path for path in ENV_PATHS if path.exists()), None)
if not ENV_PATH:
    raise RuntimeError(
        ".env not found. Checked:\n"
        + "\n".join(str(path) for path in ENV_PATHS)
    )

load_dotenv(ENV_PATH, override=True)

TOKEN = (os.getenv("DISCORD_TOKEN") or "").strip().strip('"').strip("'")
print("TOKEN LOADED:", bool(TOKEN))

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
        self.session = None
        self.fernet = get_fernet()
        self.tree.on_error = self.on_tree_error

    async def setup_hook(self):
        import aiohttp

        self.aiohttp_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "Origin": "https://www.languagenut.com",
                "Referer": "https://www.languagenut.com/",
            }
        )
        self.session = self.aiohttp_session

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

    async def on_tree_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        logger.exception(f"Slash command error: {error}")

        try:
            message = f"Error:\n```{error}```"
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except Exception as exc:
            logger.error(f"Failed to send slash error response: {exc}")

    async def close(self):
        if self.aiohttp_session:
            await self.aiohttp_session.close()
        await super().close()


# =========================
# MAIN START
# =========================
async def main():
    bot = LanguageNutBot()
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
