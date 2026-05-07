# commands/settings.py
"""
Settings slash commands for LanguageNut bot.
Allows users to customize speed range, accuracy range, and per-user overrides.
"""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import (
    get_user_settings,
    load_settings,
    save_settings,
    update_user_setting,
)

logger = logging.getLogger("lnut_bot.commands.settings")


# =========================
# HELPERS
# =========================

def build_settings_embed(
    user_id: str,
    settings: dict,
) -> discord.Embed:
    """Build a settings overview embed."""
    embed = discord.Embed(
        title="⚙️ Your LanguageNut Settings",
        color=discord.Color.purple(),
    )

    embed.add_field(
        name="⏱ Speed Range",
        value=(
            f"Min: **{settings.get('speed_min_ms', 'N/A')} ms**\n"
            f"Max: **{settings.get('speed_max_ms', 'N/A')} ms**"
        ),
        inline=True,
    )

    embed.add_field(
        name="🎯 Accuracy Range",
        value=(
            f"Min: **{settings.get('accuracy_min', 'N/A')}%**\n"
            f"Max: **{settings.get('accuracy_max', 'N/A')}%**"
        ),
        inline=True,
    )

    embed.add_field(
        name="🔧 Other",
        value=(
            f"Concurrency: **{settings.get('concurrency', 5)}**\n"
            f"Don't Store Stats: **{settings.get('dont_store_stats', True)}**\n"
            f"Product: **{settings.get('product', 'secondary')}**"
        ),
        inline=False,
    )

    embed.set_footer(
        text="Use /settings speed or /settings accuracy to adjust"
    )

    return embed


# =========================
# CHOICE ENUMS
# =========================

class SpeedAction(str):
    pass

# =========================
# COG
# =========================

class SettingsCommands(commands.Cog):
    """Settings management commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =========================
    # GROUP: /settings
    # =========================

    @app_commands.command(
        name="settings",
        description="View your current LanguageNut settings",
    )
    async def cmd_settings(self, interaction: discord.Interaction):
        """Display current settings for the user."""
        await interaction.response.defer(ephemeral=True)

        user_id = str(interaction.user.id)
        settings = get_user_settings(user_id)

        embed = build_settings_embed(user_id, settings)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # =========================
    # SUBCOMMAND: /settings speed
    # =========================

    @app_commands.command(
        name="settings-speed",
        description="Set your speed range (min and max in milliseconds)",
    )
    @app_commands.describe(
        min_ms="Minimum time per task in ms (e.g., 5000 = 5s)",
        max_ms="Maximum time per task in ms (e.g., 15000 = 15s)",
    )
    async def cmd_settings_speed(
        self,
        interaction: discord.Interaction,
        min_ms: int,
        max_ms: int,
    ):
        """Set the speed range for homework completion."""
        await interaction.response.defer(ephemeral=True)

        # Validation
        if min_ms < 1000:
            await interaction.followup.send(
                "❌ Minimum speed must be at least 1000 ms (1 second).",
                ephemeral=True,
            )
            return

        if max_ms > 60000:
            await interaction.followup.send(
                "❌ Maximum speed cannot exceed 60000 ms (60 seconds).",
                ephemeral=True,
            )
            return

        if min_ms >= max_ms:
            await interaction.followup.send(
                "❌ Minimum speed must be less than maximum speed.",
                ephemeral=True,
            )
            return

        user_id = str(interaction.user.id)
        update_user_setting(user_id, "speed_min_ms", min_ms)
        update_user_setting(user_id, "speed_max_ms", max_ms)

        await interaction.followup.send(
            f"✅ Speed range updated!\n"
            f"**Min:** {min_ms} ms | **Max:** {max_ms} ms\n\n"
            f"Your bot will complete tasks in "
            f"**{min_ms/1000:.1f}s–{max_ms/1000:.1f}s** each.",
            ephemeral=True,
        )

    # =========================
    # SUBCOMMAND: /settings accuracy
    # =========================

    @app_commands.command(
        name="settings-accuracy",
        description="Set your accuracy range (0-100%)",
    )
    @app_commands.describe(
        min_pct="Minimum accuracy % (e.g., 85)",
        max_pct="Maximum accuracy % (e.g., 100)",
    )
    async def cmd_settings_accuracy(
        self,
        interaction: discord.Interaction,
        min_pct: int,
        max_pct: int,
    ):
        """Set the accuracy range for stealth."""
        await interaction.response.defer(ephemeral=True)

        # Validation
        if min_pct < 0 or min_pct > 100:
            await interaction.followup.send(
                "❌ Minimum accuracy must be between 0 and 100.",
                ephemeral=True,
            )
            return

        if max_pct < 0 or max_pct > 100:
            await interaction.followup.send(
                "❌ Maximum accuracy must be between 0 and 100.",
                ephemeral=True,
            )
            return

        if min_pct >= max_pct:
            await interaction.followup.send(
                "❌ Minimum accuracy must be less than maximum accuracy.",
                ephemeral=True,
            )
            return

        user_id = str(interaction.user.id)
        update_user_setting(user_id, "accuracy_min", min_pct)
        update_user_setting(user_id, "accuracy_max", max_pct)

        await interaction.followup.send(
            f"✅ Accuracy range updated!\n"
            f"**Min:** {min_pct}% | **Max:** {max_pct}%\n\n"
            f"Your bot will randomly score between "
            f"**{min_pct}%–{max_pct}%** on each task.",
            ephemeral=True,
        )

    # =========================
    # SUBCOMMAND: /settings reset
    # =========================

    @app_commands.command(
        name="settings-reset",
        description="Reset your settings to defaults",
    )
    async def cmd_settings_reset(self, interaction: discord.Interaction):
        """Reset per-user settings to global defaults."""
        await interaction.response.defer(ephemeral=True)

        user_id = str(interaction.user.id)
        data = load_settings()
        per_user = data.setdefault("per_user", {})

        if user_id in per_user:
            del per_user[user_id]
            save_settings(data)

        await interaction.followup.send(
            "✅ Settings reset to defaults!",
            ephemeral=True,
        )


# =========================
# SETUP
# =========================

async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsCommands(bot))