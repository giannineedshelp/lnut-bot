# commands/core.py
"""
Core Discord slash commands for LanguageNut bot.
"""

import asyncio
import logging
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from automation.api_direct import LanguageNutAPI
from automation.task_handler import TaskHandler
from config import (
    get_account,
    get_decrypted_password,
    get_user_settings,
    remove_account,
    set_account,
)
from utils.encryption import encrypt_password

logger = logging.getLogger("lnut_bot.commands.core")


# =========================
# HELPER: Get API Client
# =========================

async def _get_api_client(interaction: discord.Interaction) -> Optional[LanguageNutAPI]:
    """
    Factory method to create an authenticated API client for the user.
    Returns None if user isn't logged in or login fails.
    """
    bot = interaction.client
    user_id = str(interaction.user.id)

    account = get_account(user_id)
    if not account:
        await interaction.followup.send(
            "❌ You're not logged in. Use `/login` first.",
            ephemeral=True,
        )
        return None

    password = get_decrypted_password(user_id)
    if not password:
        await interaction.followup.send(
            "❌ Could not decrypt your password. Use `/login` again.",
            ephemeral=True,
        )
        return None

    session = getattr(bot, "aiohttp_session", None)
    if not session:
        await interaction.followup.send(
            "❌ Bot session not available.",
            ephemeral=True,
        )
        return None

    api = LanguageNutAPI(session)
    success = await api.login(account["username"], password)

    if not success:
        await interaction.followup.send(
            "❌ Login failed. Check your credentials with `/login`.",
            ephemeral=True,
        )
        return None

    return api


# =========================
# PROGRESS EMBED BUILDER
# =========================

def build_progress_embed(
    current: int,
    total: int,
    task_name: str,
    score: Optional[int] = None,
    status: str = "in_progress",
) -> discord.Embed:
    """Build a live-updating progress embed."""
    if total == 0:
        progress = 1.0
    else:
        progress = current / total

    bar_length = 20
    filled = round(progress * bar_length)
    bar = "█" * filled + "░" * (bar_length - filled)

    embed = discord.Embed(
        title="📋 Completing Homework",
        color=discord.Color.blue(),
    )

    embed.add_field(
        name="Progress",
        value=f"`{bar}` **{current}/{total}** ({round(progress * 100)}%)",
        inline=False,
    )

    if status == "fetching":
        embed.add_field(
            name="⏳ Current Task",
            value=f"Fetching data for: **{task_name}**",
            inline=False,
        )
    elif status == "done":
        embed.add_field(
            name="✅ Completed",
            value=f"**{task_name}** — Score: **{score}**",
            inline=False,
        )
    elif status == "failed":
        embed.add_field(
            name="❌ Failed",
            value=f"**{task_name}** — Error occurred",
            inline=False,
        )

    embed.set_footer(text="This message updates live")

    return embed


def build_summary_embed(
    results: list,
    total_time: float,
    settings_used: dict,
) -> discord.Embed:
    """Build a final summary embed after all tasks complete."""
    success_count = sum(1 for r in results if r.get("success"))
    fail_count = sum(1 for r in results if not r.get("success"))
    total_score = sum(r.get("score", 0) for r in results)

    embed = discord.Embed(
        title="✅ Homework Complete!",
        color=discord.Color.green() if fail_count == 0 else discord.Color.orange(),
    )

    embed.add_field(
        name="Summary",
        value=(
            f"**Completed:** {success_count}/{len(results)} tasks\n"
            f"**Total Score:** {total_score}\n"
            f"**Time:** {total_time:.1f}s\n"
            f"**Failed:** {fail_count}"
        ),
        inline=False,
    )

    embed.add_field(
        name="⚙️ Settings Used",
        value=(
            f"Speed: {settings_used.get('speed_min_ms', 'N/A')} - "
            f"{settings_used.get('speed_max_ms', 'N/A')} ms\n"
            f"Accuracy: {settings_used.get('accuracy_min', 100)} - "
            f"{settings_used.get('accuracy_max', 100)}%"
        ),
        inline=False,
    )

    # Add per-task breakdown
    if results:
        breakdown = []
        for r in results:
            task_name = r.get("task", {}).get("name", "Unknown")
            status = "✅" if r.get("success") else "❌"
            score = r.get("score", 0)
            breakdown.append(f"{status} **{task_name}**: {score} pts")

        embed.add_field(
            name="📋 Task Breakdown",
            value="\n".join(breakdown[:10]),
            inline=False,
        )

    return embed


# =========================
# COG
# =========================

class CoreCommands(commands.Cog):
    """Core commands for LanguageNut bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._login_cooldowns = {}

    # =========================
    # AUTCOMPLETE for task names
    # =========================

    @app_commands.autocompleter
    async def _task_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete for homework task names."""
        user_id = str(interaction.user.id)
        account = get_account(user_id)
        if not account:
            return []

        password = get_decrypted_password(user_id)
        if not password:
            return []

        session = getattr(self.bot, "aiohttp_session", None)
        if not session:
            return []

        api = LanguageNutAPI(session)
        success = await api.login(account["username"], password)
        if not success:
            return []

        try:
            await api.get_homeworks()
            tasks = _extract_pending_tasks(api.homeworks)
        except Exception:
            return []

        choices = []
        for task in tasks:
            name = task.get("name", "Unnamed")
            uid = task.get("uid", "")
            label = f"{name} ({uid[:8]}...)" if uid else name

            if current.lower() in label.lower():
                choices.append(
                    app_commands.Choice(name=label[:100], value=uid)
                )

            if len(choices) >= 25:
                break

        return choices

    # =========================
    # COMMANDS
    # =========================

    @app_commands.command(
        name="login",
        description="Log into LanguageNut and store your credentials",
    )
    async def cmd_login(
        self,
        interaction: discord.Interaction,
        username: str,
        password: str,
    ):
        """Store encrypted credentials and verify login."""
        await interaction.response.defer(ephemeral=True)

        # Verify credentials by attempting login
        session = getattr(self.bot, "aiohttp_session", None)
        if not session:
            await interaction.followup.send(
                "❌ Bot session not available.",
                ephemeral=True,
            )
            return

        api = LanguageNutAPI(session)
        success = await api.login(username, password)

        if not success:
            await interaction.followup.send(
                "❌ Login failed. Check your username and password.",
                ephemeral=True,
            )
            return

        # Encrypt and store
        encrypted = encrypt_password(password)
        set_account(
            user_id=str(interaction.user.id),
            username=username,
            password_encrypted=encrypted,
        )

        await interaction.followup.send(
            "✅ Login successful! Credentials stored securely.",
            ephemeral=True,
        )

    @app_commands.command(
        name="logout",
        description="Remove your stored LanguageNut credentials",
    )
    async def cmd_logout(self, interaction: discord.Interaction):
        """Remove stored credentials."""
        await interaction.response.defer(ephemeral=True)

        removed = remove_account(str(interaction.user.id))
        if removed:
            await interaction.followup.send(
                "✅ Logged out and credentials removed.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "❌ No credentials found.",
                ephemeral=True,
            )

    @app_commands.command(
        name="homework",
        description="List your pending LanguageNut homework",
    )
    async def cmd_homework(self, interaction: discord.Interaction):
        """Fetch and display pending homework."""
        await interaction.response.defer(ephemeral=True)

        api = await _get_api_client(interaction)
        if not api:
            return

        try:
            homeworks = await api.get_homeworks()
            tasks = _extract_pending_tasks(homeworks)

            if not tasks:
                await interaction.followup.send(
                    "🎉 No pending homework!",
                    ephemeral=True,
                )
                return

            embed = discord.Embed(
                title="📚 Pending Homework",
                color=discord.Color