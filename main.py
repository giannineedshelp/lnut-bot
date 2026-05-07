# main.py
# Cross-device compatible (Android + Laptop)

import asyncio
import logging
import os
import sys
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# =========================
# POSSIBLE PROJECT PATHS
# =========================

FILE_DIR = Path(__file__).resolve().parent

POSSIBLE_PATHS = [
    os.getenv("INBOT_BASE_DIR"),  # custom override
    "/storage/emulated/0/Documents/In_bot/lnut-bot",  # Android
    str(Path.home() / "Documents" / "In_bot" / "lnut-bot"),  # Windows/Linux laptop
    str(Path.cwd()),  # fallback = current directory
    str(FILE_DIR),  # fallback = folder containing this main.py
]

BASE_DIR = None

for path in POSSIBLE_PATHS:
    if path and Path(path).exists():
        BASE_DIR = Path(path)
        break

if not BASE_DIR:
    raise RuntimeError(
        "Project folder missing.\n"
        "Checked:\n" + "\n".join(str(p) for p in POSSIBLE_PATHS if p)
    )

print(f"[BOOT] BASE_DIR = {BASE_DIR}")

sys.path.insert(0, str(BASE_DIR))

# =========================
# ENV
# =========================

ENV_PATH = BASE_DIR / ".env"

if not ENV_PATH.exists():
    raise RuntimeError(f".env not found at {ENV_PATH}")

load_dotenv(dotenv_path=ENV_PATH, override=True)

TOKEN = os.getenv("DISCORD_TOKEN")

print(f"[BOOT] ENV LOADED = {ENV_PATH}")
print(f"[BOOT] TOKEN LOADED = {bool(TOKEN)}")

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
            help_command=None,
        )

        self.aiohttp_session = None
        self.session = None
        self.fernet = None
        self.tree.on_error = self.on_tree_error

    # =========================
    # SETUP
    # =========================

    async def setup_hook(self):
        logger.info("[HOOK] setup_hook START")

        try:
            self.aiohttp_session = aiohttp.ClientSession()
            self.session = self.aiohttp_session
            logger.info("[HOOK] HTTP session OK")

        except Exception as e:
            logger.exception(f"[HOOK] HTTP session failed: {e}")

        try:
            from utils.encryption import get_fernet

            self.fernet = get_fernet()

            logger.info("[HOOK] Encryption OK")

        except Exception as e:
            logger.exception(f"[HOOK] Encryption failed: {e}")

        try:
            await self.load_all_extensions()
        except Exception as e:
            logger.exception(f"[HOOK] Extension load failed: {e}")

        try:
            synced = await self.tree.sync()
            logger.info(f"[HOOK] Synced {len(synced)} commands")
        except Exception as e:
            logger.exception(f"[HOOK] Slash sync failed: {e}")

        logger.info("[HOOK] setup_hook END")

    # =========================
    # LOAD EXTENSIONS
    # =========================

    async def load_all_extensions(self):
        extensions = [
            "commands.core",
            "commands.commands_settings",
        ]

        for ext in extensions:
            try:
                logger.info(f"[COG] Loading {ext}")
                await self.load_extension(ext)
                logger.info(f"[COG] Loaded {ext}")

            except Exception as e:
                logger.exception(f"[COG] FAILED {ext}: {e}")

    # =========================
    # READY
    # =========================

    async def on_ready(self):
        logger.info(f"[READY] Logged in as {self.user}")

    # =========================
    # GLOBAL SLASH ERROR
    # =========================

    async def on_app_command_error(self, interaction: discord.Interaction, error):
        logger.exception(f"[SLASH ERROR] {error}")

        try:
            msg = f"âŒ Error:\n```{error}```"

            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)

        except Exception as e:
            logger.error(f"[SLASH ERROR RESPONSE FAILED] {e}")

    async def on_tree_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        logger.exception(f"[TREE ERROR] {error}")

        try:
            msg = f"Error:\n```{error}```"

            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)

        except Exception as e:
            logger.error(f"[TREE ERROR RESPONSE FAILED] {e}")

    # =========================
    # CLOSE
    # =========================

    async def close(self):
        logger.info("[SHUTDOWN] Closing bot")

        try:
            if self.aiohttp_session:
                await self.aiohttp_session.close()
                logger.info("[SHUTDOWN] Session closed")
        except Exception as e:
            logger.error(f"[SHUTDOWN ERROR] {e}")

        await super().close()

# =========================
# MAIN
# =========================

async def main():
    logger.info("[MAIN] Starting bot")
    bot = LanguageNutBot()

    async with bot:
        await bot.start(TOKEN)

# =========================
# START
# =========================

if __name__ == "__main__":
    try:
        asyncio.run(main())

    except KeyboardInterrupt:
        print("[STOP] Bot stopped manually")

    except Exception as e:
        logger.exception(f"[FATAL] Crash: {e}")
