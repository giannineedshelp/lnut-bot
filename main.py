import asyncio
import os
import time
import logging
from pathlib import Path
from dotenv import load_dotenv

import discord
from discord.ext import commands

from colorama import Fore, Style, init

# =========================
# COLORAMA SETUP
# =========================
init(autoreset=True)

def log_info(msg): print(f"{Fore.CYAN}[INFO]{Style.RESET_ALL} {msg}")
def log_good(msg): print(f"{Fore.GREEN}[OK]{Style.RESET_ALL} {msg}")
def log_warn(msg): print(f"{Fore.YELLOW}[WARN]{Style.RESET_ALL} {msg}")
def log_bad(msg): print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {msg}")

# =========================
# LOAD ENV
# =========================
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    log_bad("DISCORD_TOKEN missing in .env")
    raise RuntimeError("Missing token")

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
                name="/login • LanguageNut"
            )
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
        log_info("Booting bot...")

        # HTTP session
        self.aiohttp_session = aiohttp.ClientSession()
        log_good("HTTP session ready")

        # encryption
        self.fernet = get_fernet()
        log_good("Encryption loaded")

        # load cogs
        await self.load_cogs()

        log_good(f"Cogs loaded in {time.time() - start:.2f}s")

        # sync commands
        try:
            log_info("Syncing slash commands...")
            await self.tree.sync()
            log_good("Slash commands synced")
        except Exception as e:
            log_bad(f"Command sync failed: {e}")

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
                log_good(f"Loaded {cog}")
            except Exception as e:
                log_bad(f"Failed {cog}: {e}")

    # =========================
    # READY EVENT
    # =========================
    async def on_ready(self):
        log_good(f"Logged in as {self.user}")
        log_info("Bot is ONLINE 🟢")


# =========================
# CLEAN EXIT
# =========================
async def main():
    bot = LanguageNutBot()

    async with bot:
        log_info("Starting Discord connection...")
        await bot.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log_warn("Bot shutdown manually")