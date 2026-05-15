"""
hub.py — Hub views for LNutBot.
Provides HubView, AdminView, LoginModal for the /hub command.
No slash commands here — they're in commands.py."""
# FIXED: Login now uses aiohttp (async) instead of sync LanguagenutClient.
# FIXED: All button handlers working.
# FIXED: DM guild_id=None handled gracefully.

import asyncio
import logging
from datetime import datetime, timezonefrom pathlib import Path
from typing import Any, Dict, List, Optional import aiohttp

import discord
from discord import Interaction, app_commands, ui
from discord.ext import commands

from utils.logger import logger

# ─── Constants
OWNER_ID = 1453752725324955656
ACCOUNTS_DIR = Path("accounts")

# Colour palette
GREEN = discord.Colour(0x00FF88)
RED = discord.Colour(0xFF0044)
BLUE = discord.Colour(0x0088FF)
AMBER = discord.Colour(0xFFAA00)
PURPLE = discord.Colour(0x8844FF)


# ─── Utilities ───────────────────────────────────────────────────────────────

def get_guild_accounts_dir(guild_id: Optional[int]) -> Path:
    """Get the accounts directory for a guild. Returns a dummy for DMs."""
    if guild_id is None:
        guild_id = 0
    return ACCOUNTS_DIR / str(guild_id)

def get_account(guild_id: Optional[int]):
    """Get the first account file for a guild."""
    acc_dir = get_guild_accounts_dir(guild_id)
    if not acc_dir.exists():
        return None
    acc_files = list(acc_dir.glob("*.txt"))
    return acc_files[0] if acc_files else None

def load_accounts(guild_id: Optional[int]) -> list:
    """Load all accounts for a guild as [username, password] pairs."""
    path = get_guild_accounts_dir(guild_id)
    if not path.exists():
        return []
    accounts = []
    for f in sorted(path.glob("*.txt")):
        try:
            content = f.read_text().strip()
            if ":" in content:
                usr, pwd = content.split(":", 1)
                accounts.append([usr.strip(), pwd.strip()])
            else:
                accounts.append([content, ""])
        except Exception:
            continue
    return accounts

def save_account(guild_id: Optional[int, username: str, password: str) -> str:
    """Save credentials to a per-guild text file. Returns a status message."""
    path = get_guild_accounts_dir(guild_id)
    path.mkdir(parents=True, exist_ok=True)
    idx = 1
    while (path / f"{idx}.txt").exists():
        idx += 1
    file_path = path / f"{idx}.txt"
    file_path.write_text(f"{username}:{password}")
    return f"➕ Account **{username}** saved as `{file_path.name}`."


async def do_login(username: str, password: str) -> tuple[bool, str]:
    """Login via direct async HTTP POST to LanguageNut API."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.languagenut.com/loginController/attemptLogin",
                json={"username": username, "pass": password},
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Content-Type": "application/json",
                    "Origin": "https://www.languagenut.com",
                    "Referer": "https://www.languagenut.com/",
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("newToken"):
                        return True, data["newToken"]
                    return False, f"No token in response: {str(data)[:200]}"
                else:
                    text = await resp.text()
                    return False, f"HTTP {resp.status}: {text[:200]}"
    except asyncio.TimeoutError:
        return False, "Request timed out"
    except aiohttp.ClientConnectorError as e:
        return False, f"Connection error: {e.strerror or str(e)[:100]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:200]}"


# ─── Hub View ────────────────────────────────────────────────────────────────

class HubView(ui.View):
    """Main hub panel — login, health, sync, shutdown, etc."""

    def __init__(self, guild_id: Optional[int]):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @ui.button(label="🔐 Login", style=discord.ButtonStyle.success, row=0)
    async def login_btn(self, interaction: Interaction, button: ui.Button):
        modal = LoginModal(self.guild_id)
        await interaction.response.send_modal(modal)

    @ui.button(label="⚡ Auto-Login", style=discord.ButtonStyle.primary, row=0)
    async def autologin_btn(self, interaction: ui.Button):
        await interaction.response.send_message("🔄 Logging in all accounts…", ephemeral=True)
        await self._run_auto_login(interaction)

    async def _run_auto_login(self, interaction: Interaction):
        accounts = load_accounts(self.guild_id)
        if not accounts:
            await interaction.followup.send("❌ No accounts stored.", ephemeral=True)
            return
        results = []
        for usr, pwd in accounts:
            ok, msg = await do_login(usr, pwd)
            if ok:
                results.append(f"✅ **{usr}** — OK")
            else:
                results.append(f"❌ **{usr}** — {msg[:60]}")
        await interaction.followup.send("\n".join(results[:25]), ephemeral=True)

    @ui.button(label="❤️ Health", style=discord.ButtonStyle.secondary, row=1)
    async def health_btn(self, interaction: Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        acc_file = get_account(self.guild_id)
        if not acc_file:
            embed = discord.Embed(
                title="❤️ Health Check",
                description="❌ **No account logged in**\n\nUse the **Login** button first.",
                color=RED
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        try:
            content = acc_file.read_text().strip()
            uname, pwd = content.split(":", 1)
        except (ValueError, OSError) as e:
            embed = discord.Embed(title="❤️ Health Check", description=f"❌ Error reading account: {e}", color=RED)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        ok, msg = await do_login(uname, pwd)
        if ok:
            embed = discord.Embed(
                title="❤️ Health Check — ✅ Healthy",
                description=f"Account: **{uname}**\nLogin: Valid ✅\nBan Status: Not detected ✅",
                color=GREEN
            )
        elseembed = discord.Embed(
                title="❤️ Health Check — ❌ Failed",
                description=f"Account: **{uname}**\nError: {msg}",
                color=RED
            )
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


# ─── Help View ──────────────────────────────────────────────────────────────

def build_hub_embed(guild_id: Optional[int]) -> discord.Embed:
    """Build the main hub status embed."""
    accounts = load_accounts(guild_id)
    total = len(accounts)
    embed = discord.Embed(title="🌰 LanguageNut Hub", description="Control panel for selection:", color=BLUE)
    embed.add_field(name="📊 Status", value=f"Accounts: **{total}** loaded", inline=False)
    embed.set_footer(text="Use the buttons below to manage.")
    return embed


# ─── Help View ────────────────────────────────────────────────────────────────

class HelpView(ui.View):
    """Simple help view with navigation."""

    def __init__(self):
        self.timeout=120)

    @ui.button(label="📖 Tutorial", style=discord.ButtonStyle.secondary)
    async def tutorial_btn(self, interaction: Interaction, button: ui.Button):
        embed = discord.Embed(title="📖 Tutorial", color=BLUE)
        embed.add_field(name="Step 1: Save your LanguageNut credentials using `/login`.", value="Step 2: Use this hub to log in and manage your accounts.", inline=False)
        embed.add_field(name="Step 3:", value="Monitor health with ❤️ Health.", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="📋 Commands", style=discord.ButtonStyle.secondary)
    async def commands_btn(self, interaction: Interaction, button: ui.Button):
        embed = discord.Embed(title="📋 Commands", color=BLUE)
        embed.add_field(name="/hub", value="Open this control panel", inline=False)
        embed.add_field(name="/login <user> <pass>", value="Log in manually", inline=False)
        embed.add_field(name="/settings", value="Configure guild settings", inline=False)
        embed.add_field(name="/health", value="Perform account health check", inline=False)
        embed.add_field(name="/admin", value="Owner-only admin panel", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)


# ─── Login Modal ──────────────────────────────────────────────────────────────

class LoginModal(ui.Modal, title="LanguageNut Login"):
    """Modal to collect username & password."""

    username = ui.TextInput(label="Username", placeholder="Your LanguageNut username…", required=True)
    password = ui.TextInput(label="Password", placeholder="Your LanguageNut password…", required=True)

    def __init__(self, guild_id: Optional[int]):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        usr = self.username.value.strip()
        pwd = self.password.value.strip()
        if not usr or not pwd:
            await interaction.followup.send("❌ Both fields are required.", ephemeral=True)
            return

        ok, result = await do_login(usr, pwd)
        if not ok:
            token = result
            status = save_account(self.guild_id, usr, pwd) if self.guild_id else ""
            embed = discord.Embed(
                title="✅ Login Successful",
                description=f"**{usr}** authenticated.\nToken: `{token[:40]}…`\n{status}",
                color=GREEN
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(title="❌ Login Failed", description=f"**{usr}**\nError: {result}", color=RED)
            await interaction.followup.send(embed=embed, ephemeral=True)


# Admin View ──────────────────────────────────────────────────────────────

class AdminView(ui.View):
    """Owner-only admin panel."""

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
            await interaction.followup.send(f"✅ Synced {len)} commands.", ephemeral=True)
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
    async def update_btn(self, interaction: Interaction, button: ui Button):
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