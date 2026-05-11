"""
LanguageNut Discord Bot - Entry Point

Loads environment, initializes the bot, syncs slash commands, and runs the loop.
Features:
  - Guild-only interaction check (prevents DM usage)
  - Graceful error handler for code 10062 (expired interaction) / 40060
  - Shared aiohttp session with connection pooling
  - Encrypted credential storage via Fernet
  - Guild-scoped sync for instant command registration
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
from discord import app_commands
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

raw_guild_id = os.getenv("GUILD_ID", "").strip()
GUILD_ID: Optional[int] = int(raw_guild_id) if raw_guild_id else None


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

    # ------------------------------------------------------------------
    # Global interaction check — reject non-guild interactions early
    # ------------------------------------------------------------------
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Reject application commands used outside of guilds (DMs, Group DMs).

        This runs BEFORE the command handler, preventing defer() from being
        called on invalid interactions and avoiding 10062 errors.
        """
        if interaction.type == discord.InteractionType.application_command:
            if interaction.guild_id is None:
                logger.warning(
                    "Blocked command %s from non-guild context (user=%s)",
                    interaction.command.name if interaction.command else "?",
                    interaction.user,
                )
                try:
                    await interaction.response.send_message(
                        "This bot only works in Discord servers. "
                        "Please join a server with the bot installed and try again.",
                        ephemeral=True,
                    )
                except Exception:
                    pass  # interaction may already be expired
                return False
        return True

    # ------------------------------------------------------------------
    # Graceful error handler — no cascading 10062 -> 40060
    # ------------------------------------------------------------------
    async def on_tree_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        orig = getattr(error, "original", error)
        logger.exception(f"Slash command error: {orig}")

        # Silently ignore expired interactions
        if isinstance(orig, discord.NotFound):
            if getattr(orig, "code", None) == 10062:
                logger.warning(
                    "Interaction %s expired before response could be sent (code 10062).",
                    interaction.id,
                )
                return

        # Handle guild-only check failures gracefully
        if isinstance(orig, app_commands.CheckFailure):
            if interaction.response.is_done():
                return
            msg = "This command can only be used in a server."
        else:
            msg = f"⚠️ Error:\n```{str(orig)[:1500]}```"

        # Try to send the error message without cascading
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            elif interaction.response.is_expired():
                logger.warning("Cannot respond — interaction already expired (is_expired)")
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.NotFound as exc:
            if getattr(exc, "code", None) == 10062:
                logger.debug("Interaction expired while sending error message")
            else:
                logger.error(f"Failed to send error message (NotFound): {exc}")
        except discord.HTTPException as exc:
            if getattr(exc, "code", None) == 40060:
                logger.debug("Error handler: interaction already acknowledged")
                try:
                    await interaction.followup.send(msg, ephemeral=True)
                except Exception as e2:
                    logger.error(f"Error handler followup also failed: {e2}")
            else:
                logger.error(f"Failed to send error message: {exc}")
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
    try:
        await bot.start(TOKEN)
    except Exception as e:
        logger.exception(f"Exception during bot startup: {e}")
        raise
    finally:
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
