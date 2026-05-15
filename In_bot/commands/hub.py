"""
hub.py — Hub views for LNutBot.
Provides HubView, AdminView, LoginModal, HelpView for the /hub command.
No slash commands here — they're in commands.py.
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import discord
from discord import Interaction, app_commands, ui
from discord.ext import commands

from automation.api_direct import LNApiClient, LanguagenutClient
from automation.discover import HomeworkDiscoverer
from automation.stealth import StealthManager, seconds_to_human
from commands.commands import get_session, _check_account_banned
from utils.helper import format_homework_list, _is_done
from utils.logger import setup_logging, log_user_command

logger = logging.getLogger(__name__)

OWNER_ID = 1453752725324955656
ACCOUNTS_DIR = Path("accounts")

# Colour palette
GREEN = discord.Colour(0x00FF88)
RED = discord.Colour(0xFF0044)
BLUE = discord.Colour(0x0088FF)
AMBER = discord.Colour(0xFFAA00)
PURPLE = discord.Colour(0x8844FF)

# ─── Utilities ───────────────────────────────────────────────────────────────

def get_guild_accounts_dir(guild_id: int):
    return ACCOUNTS_DIR / str(guild_id)

def get_account(guild_id: int):
    acc_dir = get_guild_accounts_dir(guild_id)
    if not acc_dir.exists():
        return None
    acc_files = list(acc_dir.glob("*.txt"))
    return acc_files[0] if acc_files else None

async def do_login(username: str, password: str) -> tuple[bool, str]:
    """Login using the sync LanguagenutClient wrapped in executor."""
    def _sync_login():
        try:
            client = LanguagenutClient()
            resp = client.session.post(
                "https://api.languagenut.com/loginController/attemptLogin",
                json={"username": username, "pass": password},
                timeout=30
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("newToken"):
                client.token = data["newToken"]
                client.session.headers["Authorization"] = f"Bearer {client.token}"
                return True, ""
            return False, data.get("error", str(data))[:200]
        except Exception as e:
            return False, str(e)[:200]
    return await asyncio.get_event_loop().run_in_executor(None, _sync_login)

# ─── Modals ──────────────────────────────────────────────────────────────────

class LoginModal(ui.Modal, title="Login to LanguageNut"):
    username = ui.TextInput(label="Username", placeholder="Enter your LanguageNut username", min_length=1, max_length=100, required=True)
    password = ui.TextInput(label="Password", placeholder="Enter your LanguageNut password", min_length=1, max_length=100, required=True)

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        acc_dir = get_guild_accounts_dir(self.guild_id)
        acc_dir.mkdir(parents=True, exist_ok=True)
        acc_file = acc_dir / f"{self.username.value}.txt"
        success, err = await do_login(self.username.value, self.password.value)
        if success:
            acc_file.write_text(f"{self.username.value}:{self.password.value}")
            embed = discord.Embed(title="✅ Login Successful", description=f"Logged in as **{self.username.value}**", color=GREEN)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(title="❌ Login Failed", description=f"Invalid credentials.\n`{err}`", color=RED)
            await interaction.followup.send(embed=embed, ephemeral=True)

class LogoutConfirm(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=30)
        self.guild_id = guild_id

    @ui.button(label="✅ Yes, log out", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: Interaction, button: ui.Button):
        acc_file = get_account(self.guild_id)
        if acc_file:
            acc_file.unlink()
        embed = discord.Embed(title="🚪 Logged Out", description="Your account has been removed from this server.", color=GREEN)
        await interaction.response.edit_message(embed=embed, view=None)

    @ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: Interaction, button: ui.Button):
        embed = discord.Embed(title="Cancelled", description="Logout cancelled.", color=AMBER)
        await interaction.response.edit_message(embed=embed, view=None)

# ─── Help View ───────────────────────────────────────────────────────────────

class HelpView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @ui.button(label="📖 Tutorial", style=discord.ButtonStyle.primary)
    async def tutorial_btn(self, interaction: Interaction, button: ui.Button):
        embed = discord.Embed(
            title="📖 Tutorial",
            description=(
                "**Quick Start:**\n"
                "1. Click **Login** to add your LanguageNut account\n"
                "2. Click **Farm** to start earning XP\n"
                "3. Click **Homeworks** to see assignments\n"
                "4. Click **Health** to check account status\n\n"
                "**Commands:**\n"
                "• `/login` — Log in to LanguageNut\n"
                "• `/logout` — Remove stored credentials\n"
                "• `/farm` — Farm XP in a language\n"
                "• `/homeworks` — View assignments\n"
                "• `/leaderboard` — Check rankings\n"
                "• `/account-health` — Check ban status\n"
                "• `/settings` — Adjust farming parameters\n"
                "• `/status` — View your stats"
            ),
            color=BLUE
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="📋 Commands", style=discord.ButtonStyle.secondary)
    async def commands_btn(self, interaction: Interaction, button: ui.Button):
        embed = discord.Embed(
            title="📋 All Commands",
            description=(
                "**User Commands:**\n"
                "`/hub` — Open this dashboard\n"
                "`/login` — Log in to LanguageNut\n"
                "`/logout` — Remove stored credentials\n"
                "`/farm` — Farm XP (language → topic → target)\n"
                "`/homeworks` — View all assignments\n"
                "`/do` — Interactive task selector\n"
                "`/quick-do` — Quick complete by ID\n"
                "`/leaderboard` — View rankings\n"
                "`/account-health` — Check ban status\n"
                "`/settings` — Adjust bot parameters\n"
                "`/status` — View your stats\n\n"
                "**Admin (owner only):**\n"
                "`/sync` — Refresh slash commands\n"
                "`/reload` — Reload cogs\n"
                "`/logs` — View bot logs\n"
                "`/restart` — Restart the bot\n"
                "`/shutdown` — Stop the bot"
            ),
            color=BLUE
        )
        await interaction.response.edit_message(embed=embed, view=self)

# ─── Hub Embed Builder ───────────────────────────────────────────────────────

def build_hub_embed(guild_id: int) -> discord.Embed:
    acc_file = get_account(guild_id)
    if acc_file:
        status = f"✅ Logged in as **{acc_file.stem}**"
    else:
        status = "❌ Not logged in"
    embed = discord.Embed(
        title="🌐 LanguageNut Hub",
        description=f"**Status:** {status}\n\nSelect an action below:",
        color=BLUE,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="🔑 Login / 🚪 Logout", value="Manage your account", inline=True)
    embed.add_field(name="🌾 Farm XP", value="Farm tasks for XP", inline=True)
    embed.add_field(name="📋 Homeworks", value="View assignments", inline=True)
    embed.add_field(name="📊 Leaderboard", value="Check rankings", inline=True)
    embed.add_field(name="❤️ Health", value="Account status check", inline=True)
    embed.add_field(name="⚙️ Settings", value="Adjust parameters", inline=True)
    embed.set_footer(text="LanguageNut Hub")
    return embed

# ─── Hub View ────────────────────────────────────────────────────────────────

class HubView(ui.View):
    """Main hub view with all action buttons."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id

    @ui.button(label="🔑 Login", style=discord.ButtonStyle.success, row=0)
    async def login_btn(self, interaction: Interaction, button: ui.Button):
        modal = LoginModal(self.guild_id)
        await interaction.response.send_modal(modal)

    @ui.button(label="🚪 Logout", style=discord.ButtonStyle.danger, row=0)
    async def logout_btn(self, interaction: Interaction, button: ui.Button):
        acc_file = get_account(self.guild_id)
        if not acc_file:
            embed = discord.Embed(title="Not Logged In", description="You are not currently logged in.", color=AMBER)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        embed = discord.Embed(title="Confirm Logout", description=f"Log out **{acc_file.stem}**?", color=AMBER)
        view = LogoutConfirm(self.guild_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @ui.button(label="🌾 Farm XP", style=discord.ButtonStyle.success, row=1)
    async def farm_btn(self, interaction: Interaction, button: ui.Button):
        cmd = interaction.client.tree.get_command("farm")
        if cmd:
            await cmd.callback(interaction)
        else:
            await interaction.response.send_message("Command `/farm` not found.", ephemeral=True)

    @ui.button(label="📋 Homeworks", style=discord.ButtonStyle.primary, row=1)
    async def homeworks_btn(self, interaction: Interaction, button: ui.Button):
        cmd = interaction.client.tree.get_command("homeworks")
        if cmd:
            await cmd.callback(interaction)
        else:
            await interaction.response.send_message("Command `/homeworks` not found.", ephemeral=True)

    @ui.button(label="📊 Leaderboard", style=discord.ButtonStyle.secondary, row=2)
    async def leaderboard_btn(self, interaction: Interaction, button: ui.Button):
        cmd = interaction.client.tree.get_command("leaderboard")
        if cmd:
            await cmd.callback(interaction)
        else:
            await interaction.response.send_message("Command `/leaderboard` not found.", ephemeral=True)

    @ui.button(label="❤️ Health", style=discord.ButtonStyle.danger, row=2)
    async def health_btn(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        acc_file = get_account(self.guild_id)
        if not acc_file:
            embed = discord.Embed(title="❤️ Health Check", description="❌ **No account logged in**\n\nUse the **Login** button first.", color=RED)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        username = acc_file.stem
        try:
            content = acc_file.read_text().strip()
            uname, pwd = content.split(":", 1)
            import asyncio
            success, err = await do_login(uname, pwd)
            if not success:
                embed = discord.Embed(title="❤️ Health Check", description=f"❌ **Login Failed**\nAccount: **{username}**\nCredentials may be invalid or account banned.", color=RED)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            embed = discord.Embed(title="❤️ Health Check — ✅ Healthy", description=f"Account: **{username}**\nLogin: Valid ✅\nBan Status: Not detected ✅", color=GREEN)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Health check error: {e}")
            embed = discord.Embed(title="❤️ Health Check", description=f"❌ Error: `{e}`", color=RED)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="⚙️ Settings", style=discord.ButtonStyle.primary, row=3)
    async def settings_btn(self, interaction: Interaction, button: ui.Button):
        cmd = interaction.client.tree.get_command("settings")
        if cmd:
            await cmd.callback(interaction)
        else:
            await interaction.response.send_message("Command `/settings` not found.", ephemeral=True)

    @ui.button(label="❓ Help", style=discord.ButtonStyle.secondary, row=3)
    async def help_btn(self, interaction: Interaction, button: ui.Button):
        embed = discord.Embed(title="❓ Help Menu", description="Choose an option below:", color=BLUE)
        embed.add_field(name="📖 Tutorial", value="Step-by-step guide", inline=False)
        embed.add_field(name="📋 Commands", value="Full command list", inline=False)
        view = HelpView()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="🔄 Refresh", style=discord.ButtonStyle.secondary, row=3)
    async def refresh_btn(self, interaction: Interaction, button: ui.Button):
        embed = build_hub_embed(self.guild_id)
        view = HubView(self.guild_id)
        await interaction.response.edit_message(embed=embed, view=view)

# ─── Admin View ──────────────────────────────────────────────────────────────

class AdminView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message("⛔ Owner only.", ephemeral=True)
            return False
        return True

    @ui.button(label="🔄 Sync Commands", style=discord.ButtonStyle.primary, row=0)
    async def sync_btn(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            for guild in interaction.client.guilds:
                interaction.client.tree.clear_commands(guild=guild)
            synced = await interaction.client.tree.sync()
            await interaction.followup.send(f"✅ Synced {len(synced)} commands.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Sync failed: {e}", ephemeral=True)

    @ui.button(label="🔁 Reload Cogs", style=discord.ButtonStyle.secondary, row=0)
    async def reload_btn(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        results = []
        for cog in list(interaction.client.extensions.keys()):
            try:
                await interaction.client.reload_extension(cog)
                results.append(f"✅ {cog}")
            except Exception as e:
                results.append(f"❌ {cog}: {e}")
        await interaction.followup.send("\n".join(results), ephemeral=True)

    @ui.button(label="📜 Bot Logs", style=discord.ButtonStyle.secondary, row=0)
    async def logs_btn(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            with open("bot.log", "r") as f:
                lines = f.readlines()[-20:]
            text = "".join(lines)
            if len(text) > 1900:
                text = text[-1900:]
            await interaction.followup.send(f"```\n{text}\n```", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Could not read logs: {e}", ephemeral=True)

    @ui.button(label="🔄 Git Update", style=discord.ButtonStyle.success, row=1)
    async def update_btn(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        import subprocess
        try:
            result = subprocess.run(["git", "pull"], capture_output=True, text=True, timeout=30)
            out = result.stdout + result.stderr
            await interaction.followup.send(f"```\n{out[:1900]}\n```", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Update failed: {e}", ephemeral=True)

    @ui.button(label="🔴 Restart", style=discord.ButtonStyle.danger, row=1)
    async def restart_btn(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_message("🔄 Restarting...", ephemeral=True)
        import subprocess, sys
        subprocess.Popen([sys.executable, "main.py"])
        await interaction.client.close()

    @ui.button(label="⛔ Shutdown", style=discord.ButtonStyle.danger, row=1)
    async def shutdown_btn(self, interaction: Interaction, button: ui.Button):
        await interaction.response.send_message("⛔ Shutting down...", ephemeral=True)
        await interaction.client.close()

# ─── Cog ─────────────────────────────────────────────────────────────────────

class HubCog(commands.Cog):
    """Cog that provides the admin panel command. The /hub command is in commands.py."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="admin", description="Open the admin control panel (owner only)")
    async def admin(self, interaction: Interaction):
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message("⛔ Owner only.", ephemeral=True)
            return
        embed = discord.Embed(title="🔧 Admin Panel", description="Select an action:", color=PURPLE)
        view = AdminView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HubCog(bot))
    logger.info("HubCog loaded")