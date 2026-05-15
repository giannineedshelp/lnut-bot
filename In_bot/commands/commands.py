"""
commands.py \u2014 LanguageNut Command Centre
Hub, Login, Logout, Settings, Health, Homeworks, Leaderboard, Farm
All use sync LanguagenutClient via curl_cffi / requests directly.
"""

import asyncio
import logging
import json
import os
import random
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord import Interaction, app_commands, ui
from discord.ext import commands

import config
from automation.stealth import StealthManager, seconds_to_human
from automation.discover import HomeworkDiscoverer
from utils.helper import _pct, _is_done, format_homework_list, seconds_to_string
from utils.logger import setup_logging, log_user_command, log_homework_action

logger = setup_logging()

OWNER_ID = 1453752725324955656

GREEN = discord.Colour(0x00FF88)
RED = discord.Colour(0xFF0044)
BLUE = discord.Colour(0x0088FF)
AMBER = discord.Colour(0xFFAA00)
PURPLE = discord.Colour(0x8844FF)

sessions: Dict[int, Dict[str, Any]] = {}

def get_session(uid: int) -> dict:
    if uid not in sessions:
        sessions[uid] = {"token": None, "username": None, "uid": None}
    return sessions[uid]

# ─── Direct LN API calls (sync, no LanguagenutClient wrapper) ─────────────

def _lnut_post(endpoint: str, payload: dict) -> dict:
    """Make a sync POST to languagenut API."""
    try:
        import curl_cffi.requests as cr
    except ImportError:
        import requests as cr

    url = f"https://api.languagenut.com/{endpoint}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.languagenut.com",
        "Referer": "https://www.languagenut.com/",
    }
    try:
        resp = cr.post(url, json=payload, headers=headers, timeout=30)
        data = resp.json()
        if resp.status_code == 200:
            return data
        return {"error": True, "status": resp.status_code, "body": str(data)[:500]}
    except Exception as e:
        return {"error": True, "body": f"{type(e).__name__}: {str(e)[:200]}"}


def do_login(username: str, password: str) -> Tuple[bool, str]:
    """Login and return (success, token_or_error)."""
    result = _lnut_post("loginController/attemptLogin", {
        "username": username,
        "password": password,
    })
    token = result.get("token") or result.get("newToken")
    if token:
        return True, token
    return False, result.get("body", str(result)[:200])


def check_health(token: str) -> dict:
    """Check account health. Returns dict with keys: banned, status, error_message, unban_in."""
    result = _lnut_post("stats/get", {"token": token})
    if result.get("error"):
        return {"banned": True, "status": "error", "error_message": str(result.get("body", "")), "unban_in": None}
    # Check for ban indicators in the response
    msg = ""
    if isinstance(result, dict):
        msg = str(result.get("msg", result.get("message", "")))
    is_banned = any(kw in msg.lower() for kw in ["ban", "suspend", "block", "denied"]) if msg else False
    return {
        "banned": is_banned,
        "status": "banned" if is_banned else "ok",
        "error_message": msg if is_banned else "",
        "unban_in": None,
    }

# ─── Helpers ───────────────────────────────────────────────────────────────

def get_guild_accounts_dir(guild_id: Optional[int]) -> Path:
    if guild_id is None:
        guild_id = 0
    d = Path("accounts") / str(guild_id)
    d.mkdir(parents=True, exist_ok=True)
    return d

def get_account_file(guild_id: Optional[int]) -> Optional[Path]:
    d = get_guild_accounts_dir(guild_id)
    files = list(d.glob("*.txt"))
    return files[0] if files else None

def load_account(guild_id: Optional[int]) -> Tuple[Optional[str], Optional[str]]:
    f = get_account_file(guild_id)
    if not f:
        return None, None
    try:
        content = f.read_text().strip()
        if ":" in content:
            parts = content.split(":", 1)
            return parts[0], parts[1]
        return content, None
    except Exception:
        return None, None

def save_account(guild_id: Optional[int], username: str, password: str) -> str:
    d = get_guild_accounts_dir(guild_id)
    safe_name = username.replace("/", "_").replace("\\", "_")
    f = d / f"{safe_name}.txt"
    f.write_text(f"{username}:{password}")
    return f"+ Account **{username}** saved."

# ─── Hub Embed ─────────────────────────────────────────────────────────────

def build_hub_embed(guild_id: Optional[int]) -> discord.Embed:
    uname, _ = load_account(guild_id)
    embed = discord.Embed(
        title="\U0001F3E0 LanguageNut Hub",
        description=f"Logged in as **{uname}**" if uname else "Not logged in.",
        color=BLUE if uname else RED,
        timestamp=discord.utils.utcnow(),
    )
    if uname:
        embed.add_field(name="Status", value="\u2705 Logged in", inline=True)
    else:
        embed.add_field(name="Status", value="\u274C Not logged in", inline=True)
    embed.set_footer(text="Use the buttons below.")
    return embed

# ─── Views ─────────────────────────────────────────────────────────────────

class HelpView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @ui.button(label="\U0001F4D6 Tutorial", style=discord.ButtonStyle.primary)
    async def tutorial_btn(self, interaction: Interaction, btn: ui.Button):
        embed = discord.Embed(
            title="Tutorial",
            description=(
                "**Step 1:** Click Login and enter your LN credentials\n"
                "**Step 2:** Use /settings to configure timing\n"
                "**Step 3:** Use /homeworks to view assignments\n"
                "**Step 4:** Use /farm to start earning XP"
            ),
            color=BLUE,
        )
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="\U0001F4CB Commands", style=discord.ButtonStyle.success)
    async def commands_btn(self, interaction: Interaction, btn: ui.Button):
        embed = discord.Embed(title="Commands", color=GREEN)
        embed.add_field(name="/hub", value="Open control panel", inline=False)
        embed.add_field(name="/login", value="Log in manually", inline=False)
        embed.add_field(name="/settings", value="Configure guild", inline=False)
        embed.add_field(name="/health", value="Check account health", inline=False)
        embed.add_field(name="/homeworks", value="List assignments", inline=False)
        embed.add_field(name="/leaderboard", value="View rankings", inline=False)
        embed.add_field(name="/farm", value="Farm XP", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def back_btn(self, interaction: Interaction, btn: ui.Button):
        gid = interaction.guild_id
        embed = build_hub_embed(gid)
        view = HubView(gid)
        await interaction.response.edit_message(embed=embed, view=view)


class LoginModal(ui.Modal, title="LanguageNut Login"):
    username = ui.TextInput(label="Username", placeholder="Your LN username...", required=True)
    password = ui.TextInput(label="Password", placeholder="Your LN password...", required=True, style=discord.TextStyle.short)

    def __init__(self, guild_id: Optional[int]):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        usr = self.username.value.strip()
        pwd = self.password.value.strip()
        ok, result = do_login(usr, pwd)
        if ok:
            save_account(self.guild_id, usr, pwd)
            sess = get_session(interaction.user.id)
            sess["token"] = result
            sess["username"] = usr
            embed = discord.Embed(title="Login Successful", description=f"**{usr}**", color=GREEN)
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(title="Login Failed", description=f"**{usr}**\nError: {result}", color=RED)
            await interaction.followup.send(embed=embed, ephemeral=True)


class HubView(ui.View):
    def __init__(self, guild_id: Optional[int]):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @ui.button(label="\U0001F511 Login", style=discord.ButtonStyle.success)
    async def login_btn(self, interaction: Interaction, btn: ui.Button):
        modal = LoginModal(self.guild_id)
        await interaction.response.send_modal(modal)

    @ui.button(label="\U0001F6AA Logout", style=discord.ButtonStyle.danger)
    async def logout_btn(self, interaction: Interaction, btn: ui.Button):
        d = get_guild_accounts_dir(self.guild_id)
        for f in d.glob("*.txt"):
            f.unlink()
        sess = get_session(interaction.user.id)
        sess["token"] = None
        sess["username"] = None
        embed = discord.Embed(title="Logged Out", color=RED)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="\u2699\uFE0F Settings", style=discord.ButtonStyle.primary)
    async def settings_btn(self, interaction: Interaction, btn: ui.Button):
        await interaction.response.send_message(
            "Open /settings in chat or run `/settings` directly.",
            ephemeral=True,
        )

    @ui.button(label="\u2764\uFE0F Health", style=discord.ButtonStyle.danger)
    async def health_btn(self, interaction: Interaction, btn: ui.Button):
        await interaction.response.defer(ephemeral=True)
        uname, pwd = load_account(self.guild_id)
        if not uname or not pwd:
            embed = discord.Embed(title="Health Check", description="No account saved.", color=RED)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        ok, token = do_login(uname, pwd)
        if not ok:
            embed = discord.Embed(title="Health Check - Login Failed", description=token, color=RED)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        health = check_health(token)
        if health["banned"]:
            embed = discord.Embed(
                title="\u274C Account Banned",
                description=f"Status: **{health['status']}**\nReason: {health['error_message']}",
                color=RED,
            )
        else:
            stats = _lnut_post("stats/get", {"token": token})
            tasks = stats.get("tasks", "?")
            points = stats.get("points", 0)
            embed = discord.Embed(title="\u2705 Account Healthy", color=GREEN)
            embed.add_field(name="Tasks", value=str(tasks), inline=True)
            embed.add_field(name="Points", value=f"{points:,}", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="\u2753 Help", style=discord.ButtonStyle.secondary)
    async def help_btn(self, interaction: Interaction, btn: ui.Button):
        embed = discord.Embed(title="Help Menu", color=BLUE)
        view = HelpView()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="\U0001F504 Refresh", style=discord.ButtonStyle.secondary)
    async def refresh_btn(self, interaction: Interaction, btn: ui.Button):
        embed = build_hub_embed(self.guild_id)
        view = HubView(self.guild_id)
        await interaction.response.edit_message(embed=embed, view=view)


# ─── Cog ───────────────────────────────────────────────────────────────────

class CommandCentre(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="hub", description="Open the LanguageNut hub")
    async def hub(self, interaction: Interaction):
        embed = build_hub_embed(interaction.guild_id)
        view = HubView(interaction.guild_id)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="login", description="Login to LanguageNut")
    async def login(self, interaction: Interaction):
        modal = LoginModal(interaction.guild_id)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="logout", description="Logout")
    async def logout(self, interaction: Interaction):
        d = get_guild_accounts_dir(interaction.guild_id)
        for f in d.glob("*.txt"):
            f.unlink()
        embed = discord.Embed(title="Logged Out", color=RED)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="status", description="Check account status")
    async def status(self, interaction: Interaction):
        uname, pwd = load_account(interaction.guild_id)
        if not uname:
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ok, token = do_login(uname, pwd)
        if not ok:
            return await interaction.followup.send(f"Login failed: {token}", ephemeral=True)
        stats = _lnut_post("stats/get", {"token": token})
        embed = discord.Embed(title="Account Status", colour=BLUE)
        embed.add_field(name="Username", value=uname, inline=True)
        embed.add_field(name="Tasks Done", value=str(stats.get("tasks", "N/A")), inline=True)
        embed.add_field(name="Points", value=str(stats.get("points", "N/A")), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="homeworks", description="List your homeworks")
    async def homeworks(self, interaction: Interaction):
        uname, pwd = load_account(interaction.guild_id)
        if not uname:
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ok, token = do_login(uname, pwd)
        if not ok:
            return await interaction.followup.send(f"Login failed: {token}", ephemeral=True)
        from automation.api_direct import LanguagenutClient
        client = LanguagenutClient()
        client.token = token
        disc = HomeworkDiscoverer(client)
        try:
            homeworks = disc.get_all_homeworks(token)
        except Exception as e:
            return await interaction.followup.send(f"Error: {e}", ephemeral=True)
        text = format_homework_list(homeworks)
        if len(text) > 1900:
            text = text[:1900] + "\n\n*(truncated)*"
        embed = discord.Embed(title="Your Homeworks", description=text, colour=BLUE)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="leaderboard", description="View leaderboard")
    async def leaderboard(self, interaction: Interaction):
        uname, pwd = load_account(interaction.guild_id)
        if not uname:
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ok, token = do_login(uname, pwd)
        if not ok:
            return await interaction.followup.send(f"Login failed: {token}", ephemeral=True)
        data = _lnut_post("highscoreController/studentsAllAccount", {"token": token, "accountUid": ""})
        students = data.get("list", []) if isinstance(data, dict) else []
        embed = discord.Embed(title="Leaderboard", colour=AMBER)
        if students:
            for i, s in enumerate(students[:15]):
                name = s.get("name", f"Player {i+1}")
                pts = int(s.get("score", 0))
                medal = ["\U0001F947", "\U0001F948", "\U0001F949"][i] if i < 3 else f"`#{i+1}`"
                embed.add_field(name=f"{medal} {name}", value=f"{pts:,} pts", inline=False)
        else:
            embed.description = "No data."
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="health", description="Check account health")
    async def account_health(self, interaction: Interaction):
        uname, pwd = load_account(interaction.guild_id)
        if not uname:
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ok, token = do_login(uname, pwd)
        if not ok:
            return await interaction.followup.send(f"Login failed: {token}", ephemeral=True)
        health = check_health(token)
        if health["banned"]:
            embed = discord.Embed(
                title="\u274C Account Banned",
                description=f"Status: **{health['status']}**\nReason: {health['error_message']}",
                colour=RED,
            )
        else:
            embed = discord.Embed(title="\u2705 Healthy", colour=GREEN)
            embed.add_field(name="Username", value=uname, inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandCentre(bot))
