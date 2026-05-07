"""
Private owner-only admin commands for LanguageNut bot.
Restricted to bot owner only.
"""

import os
import sys
import asyncio
import logging
import platform
import subprocess
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("lnut_bot.admin")

# Replace this with your actual Discord user ID
OWNER_ID = 1208300294872395876


def owner_only():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            raise app_commands.CheckFailure("Unauthorized.")
        return True
    return app_commands.check(predicate)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def safe_send(self, interaction, msg=None, embed=None):
        if interaction.response.is_done():
            await interaction.followup.send(msg, embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(msg, embed=embed, ephemeral=True)

    @app_commands.command(name="restart", description="Restart the bot")
    @owner_only()
    async def restart(self, interaction: discord.Interaction):
        await interaction.response.send_message("Restarting bot...", ephemeral=True)
        log.warning("Bot restart initiated by owner")
        await self.bot.close()
        python = sys.executable
        os.execv(python, [python] + sys.argv)

    @app_commands.command(name="shutdown", description="Shutdown the bot")
    @owner_only()
    async def shutdown(self, interaction: discord.Interaction):
        await interaction.response.send_message("Shutting down bot...", ephemeral=True)
        log.warning("Bot shutdown initiated by owner")
        await self.bot.close()

    @app_commands.command(name="sync", description="Sync slash commands")
    @owner_only()
    async def sync(self, interaction: discord.Interaction):
        synced = await self.bot.tree.sync()
        await self.safe_send(interaction, f"Synced {len(synced)} command(s).")

    @app_commands.command(name="update", description="Pull latest GitHub update and restart")
    @owner_only()
    async def update(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            result = subprocess.run(
                ["git", "pull"],
                capture_output=True,
                text=True,
                timeout=60
            )

            output = result.stdout or result.stderr

            if result.returncode != 0:
                await interaction.followup.send(
                    f"Update failed:\n```{output[:1800]}```",
                    ephemeral=True,
                )
                return

            await interaction.followup.send(
                f"Update successful:\n```{output[:1500]}```\nRestarting...",
                ephemeral=True,
            )

            await asyncio.sleep(2)
            python = sys.executable
            os.execv(python, [python] + sys.argv)

        except Exception as e:
            await interaction.followup.send(
                f"Update error: {e}",
                ephemeral=True,
            )

    @app_commands.command(name="clear", description="Delete recent messages")
    @app_commands.describe(amount="Number of messages to delete")
    @owner_only()
    async def clear(self, interaction: discord.Interaction, amount: int):
        if amount < 1:
            await self.safe_send(interaction, "Amount must be at least 1.")
            return

        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(
            f"Deleted {len(deleted)} messages.",
            ephemeral=True,
        )

    @app_commands.command(name="status", description="View bot status")
    @owner_only()
    async def status(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Bot Status",
            timestamp=datetime.utcnow(),
        )

        embed.add_field(name="Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Users", value=str(len(self.bot.users)), inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="Python", value=platform.python_version(), inline=True)
        embed.add_field(name="OS", value=platform.system(), inline=True)

        await self.safe_send(interaction, embed=embed)

    @app_commands.command(name="logs", description="View recent logs")
    @owner_only()
    async def logs(self, interaction: discord.Interaction):
        log_file = "bot.log"
        if not os.path.exists(log_file):
            await self.safe_send(interaction, "No log file found.")
            return

        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-20:]

        content = "".join(lines)
        await self.safe_send(interaction, f"```{content[:1800]}```")

    @app_commands.command(name="reload", description="Reload a cog")
    @app_commands.describe(cog="Cog name")
    @owner_only()
    async def reload(self, interaction: discord.Interaction, cog: str):
        try:
            await self.bot.reload_extension(f"commands.{cog}")
            await self.safe_send(interaction, f"Reloaded cog: {cog}")
        except Exception as e:
            await self.safe_send(interaction, f"Reload failed: {e}")

    @app_commands.command(name="load", description="Load a cog")
    @app_commands.describe(cog="Cog name")
    @owner_only()
    async def load(self, interaction: discord.Interaction, cog: str):
        try:
            await self.bot.load_extension(f"commands.{cog}")
            await self.safe_send(interaction, f"Loaded cog: {cog}")
        except Exception as e:
            await self.safe_send(interaction, f"Load failed: {e}")

    @app_commands.command(name="unload", description="Unload a cog")
    @app_commands.describe(cog="Cog name")
    @owner_only()
    async def unload(self, interaction: discord.Interaction, cog: str):
        try:
            await self.bot.unload_extension(f"commands.{cog}")
            await self.safe_send(interaction, f"Unloaded cog: {cog}")
        except Exception as e:
            await self.safe_send(interaction, f"Unload failed: {e}")


async def setup(bot):
    await bot.add_cog(Admin(bot))
