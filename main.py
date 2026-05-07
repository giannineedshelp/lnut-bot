# main.py

import asyncio
import logging
import os
import sys
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv

# =========================
# PROJECT ROOT
# =========================

BASE_DIR = Path("/storage/emulated/0/Documents/In_bot/lnut-bot")

if not BASE_DIR.exists():
    raise RuntimeError(f"Project folder missing: {BASE_DIR}")

sys.path.insert(0, str(BASE_DIR))

# =========================
# ENV
# =========================

ENV_PATH = BASE_DIR / ".env"

if not ENV_PATH.exists():
    raise RuntimeError(f".env not found at {ENV_PATH}")

load_dotenv(dotenv_path=ENV_PATH, override=True)

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
# BOT CLASS
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

        # IMPORTANT
        self.aiohttp_session = None
        self.fernet = None

    # =========================
    # SETUP HOOK
    # =========================

    async def setup_hook(self):

        logger.info("Running setup_hook...")

        # encryption
        from utils.encryption import get_fernet

        self.aiohttp_session = aiohttp.ClientSession()
        self.fernet = get_fernet()

        logger.info("Encryption initialized")

        # load cogs
        await self.load_all_extensions()

        # sync slash commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} commands")

        except Exception as e:
            logger.exception(f"Slash sync failed: {e}")

    # =========================
    # LOAD COGS
    # =========================

    async def load_all_extensions(self):

        extensions = [
            "commands.core",
            # "commands.settings",  # removed — all settings commands are now in core.py
        ]

        for ext in extensions:

            try:
                await self.load_extension(ext)
                logger.info(f"Loaded cog: {ext}")

            except Exception as e:
                logger.exception(f"FAILED loading {ext}: {e}")

    # =========================
    # READY EVENT
    # =========================

    async def on_ready(self):

        logger.info(f"Logged in as {self.user}")
        logger.info("Bot fully online")

    # =========================
    # SLASH ERROR HANDLER
    # =========================

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error
    ):

        logger.exception(f"Slash command error: {error}")

        try:

            if interaction.response.is_done():

                await interaction.followup.send(
                    f"❌ Error:\n```{error}```",
                    ephemeral=True
                )

            else:

                await interaction.response.send_message(
                    f"❌ Error:\n```{error}```",
                    ephemeral=True
                )

        except Exception:
            pass

    # =========================
    # CLOSE
    # =========================

    async def close(self):

        logger.info("Shutting down bot...")

        try:

            if self.aiohttp_session:
                await self.aiohttp_session.close()

        except Exception as e:
            logger.error(f"Session close error: {e}")

        await super().close()

# =========================
# MAIN
# =========================

async def main():

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
        print("Bot stopped manually")

    except Exception as e:
        logger.exception(f"Fatal crash: {e}")