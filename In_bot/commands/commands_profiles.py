"""Profile management — multi-user support with per-Discord-ID configs."""

import json
import asyncio
from pathlib import Path
import discord
from discord import ui, ButtonStyle, Interaction

from config import get_config, USERS_DIR
from utils.logger import logger


class ProfileSelectView(ui.View):
    """Show all available profiles for a user."""

    def __init__(self):
        super().__init__(timeout=120)

    @ui.button(label="➕ New Profile", style=ButtonStyle.success, row=0)
    async def new_btn(self, interaction: Interaction, btn: ui.Button):
        config = get_config(str(interaction.user.id))
        config["username"] = ""
        config["password_encrypted"] = ""
        config["created_at"] = __import__("datetime").datetime.now().isoformat()
        config["last_used"] = ""
        config.save()
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✅ Profile Created",
                description="Your profile is ready! Set credentials with `/set username` and `/set password`",
                color=0x00ff88,
            ),
            view=None,
        )

    @ui.button(label="📋 View Profile", style=ButtonStyle.blurple, row=0)
    async def view_btn(self, interaction: Interaction, btn: ui.Button):
        config = get_config(str(interaction.user.id))
        embed = discord.Embed(
            title="👤 Your Profile",
            description=f"**Username:** {config['username'] or 'Not set'} | **Region:** {config.region}",
            color=0x4488ff,
        )
        embed.add_field(name="🎯 Accuracy", value=f"{config['accuracy_min']*100:.0f}% – {config['accuracy_max']*100:.0f}%")
        embed.add_field(name="⏱️ Delays", value=f"Think: {config['think_delay_min']}–{config['think_delay_max']}s")
        embed.add_field(name="🛡️ Anti-Detect", value=f"Time: {'ON' if config['fake_time_enabled'] else 'OFF'}\nGeo: {'ON' if config['fake_geolocation_enabled'] else 'OFF'}")
        embed.add_field(name="🌐 Browser", value=f"Headless: {config['headless']}\nMax Q: {config['max_questions']}")
        embed.set_footer(text=f"Profile created: {config['created_at'][:10] if config['created_at'] else 'N/A'}")
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="🗑️ Delete Profile", style=ButtonStyle.danger, row=1)
    async def delete_btn(self, interaction: Interaction, btn: ui.Button):
        config = get_config(str(interaction.user.id))
        config.delete()
        await interaction.response.edit_message(
            embed=discord.Embed(title="🗑️ Profile Deleted", description="Your settings have been removed.", color=0xff4444),
            view=None,
        )

    @ui.button(label="🔙 Back", style=ButtonStyle.gray, row=1)
    async def back_btn(self, interaction: Interaction, btn: ui.Button):
        from commands.core import ModeSelectView
        await interaction.response.edit_message(
            embed=discord.Embed(title="🎮 LanguageNut Bot", description="Choose a mode or configure settings:"),
            view=ModeSelectView(),
        )


def setup_profile_commands(bot):
    """Register profile-related slash commands."""

    @bot.tree.command(name="profile", description="View or manage your profile")
    async def profile_cmd(interaction: Interaction):
        await interaction.response.send_message(
            embed=discord.Embed(title="👤 Profile Manager", description="Manage your profile settings:"),
            view=ProfileSelectView(),
            ephemeral=True,
        )

    @bot.tree.command(name="deleteprofile", description="Delete your profile and all saved data")
    async def deleteprofile_cmd(interaction: Interaction):
        config = get_config(str(interaction.user.id))
        config.delete()
        await interaction.response.send_message(
            embed=discord.Embed(title="🗑️ Profile Deleted", description="All your data has been removed.", color=0xff4444),
            ephemeral=True,
        )

    logger.info("Profile commands registered")
