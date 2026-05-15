"""
commands.py — LanguageNut Command Centre
Hub, Login, Settings, Health, Homeworks, Leaderboard
All sync, curl_cffi with requests fallback.
"""

import asyncio
import json
import logging
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

logger = logging.getLogger("lnut-bot")

GREEN = discord.Colour(0x00FF88)
RED = discord.Colour(0xFF0044)
BLUE = discord.Colour(0x0088FF)
AMBER = discord.Colour(0xFFAA00)

# ─── Sync LN API ──────────────────────────────────────────────────────────

def _lnut_post(endpoint: str, payload: dict) -> dict:
    """Sync POST to languagenut API with auto fallback."""
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
        if resp.status_code == 200:
            return resp.json()
        body = resp.text[:500]
        return {"error": True, "status": resp.status_code, "body": body}
    except Exception as e:
        return {"error": True, "body": f"Connection error: {type(e).__name__}: {str(e)[:200]}"}


def do_login(username: str, password: str) -> Tuple[bool, str]:
    """Returns (success, token_or_error)."""
    result = _lnut_post("loginController/attemptLogin", {
        "username": username,
        "password": password,
    })
    if result.get("error"):
        return False, result.get("body", str(result)[:200])
    token = result.get("token") or result.get("newToken")
    if token:
        return True, token
    return False, f"No token in response: {str(result)[:200]}"


def check_health(token: str) -> dict:
    """Check account health. Returns dict with banned status."""
    result = _lnut_post("stats/get", {"token": token})
    if result.get("error"):
        return {"banned": True, "status": "error", "error_message": result.get("body", ""), "unban_in": None}
    # Banned accounts return specific fields
    error_msg = ""
    if isinstance(result, dict):
        error_msg = str(result.get("msg", result.get("message", "")))
    is_banned = bool(error_msg) and any(kw in error_msg.lower() for kw in ["ban", "suspend", "deni", "block"])
    return {
        "banned": is_banned,
        "status": "banned" if is_banned else "ok",
        "error_message": error_msg if is_banned else "",
        "unban_in": None,
    }

# ─── Account Helpers ──────────────────────────────────────────────────────

def get_accounts_dir(guild_id: Optional[int]) -> Path:
    d = Path("accounts") / str(guild_id or 0)
    d.mkdir(parents=True, exist_ok=True)
    return d

def load_account(guild_id: Optional[int]) -> Tuple[Optional[str], Optional[str]]:
    d = get_accounts_dir(guild_id)
    files = sorted(d.glob("*.txt"))
    if not files:
        return None, None
    try:
        content = files[0].read_text().strip()
        if ":" in content:
            u, p = content.split(":", 1)
            return u.strip(), p.strip()
        return content.strip(), None
    except Exception:
        return None, None

def save_account(guild_id: Optional[int], username: str, password: str):
    d = get_accounts_dir(guild_id)
    safe = username.replace("/", "_").replace("\\", "_")
    (d / f"{safe}.txt").write_text(f"{username}:{password}")

def delete_accounts(guild_id: Optional[int]):
    d = get_accounts_dir(guild_id)
    for f in d.glob("*.txt"):
        f.unlink()

# ─── Hub Embed ────────────────────────────────────────────────────────────

def build_hub_embed(guild_id: Optional[int]) -> discord.Embed:
    uname, _ = load_account(guild_id)
    embed = discord.Embed(
        title="\U0001F3E0 LanguageNut Hub",
        description=f"Logged in as **{uname}**" if uname else "Not logged in.",
        color=BLUE if uname else RED,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Status", value="\u2705 Logged in" if uname else "\u274C Not logged in", inline=True)
    embed.set_footer(text="Buttons below.")
    return embed

# ─── Views ────────────────────────────────────────────────────────────────

class LoginModal(ui.Modal, title="LanguageNut Login"):
    username = ui.TextInput(label="Username", placeholder="LN username", required=True)
    password = ui.TextInput(label="Password", placeholder="LN password", required=True)

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
            embed = discord.Embed(title="Login Successful", description=f"**{usr}**", color=GREEN)
        else:
            embed = discord.Embed(title="Login Failed", description=f"**{usr}**\nError: {result}", color=RED)
        await interaction.followup.send(embed=embed, ephemeral=True)


class HelpView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @ui.button(label="\U0001F4D6 Tutorial", style=discord.ButtonStyle.primary)
    async def tutorial(self, interaction: Interaction, btn: ui.Button):
        e = discord.Embed(title="Tutorial", color=BLUE, description=(
            "**1.** Click Login → enter LN credentials\n"
            "**2.** Use /homeworks to see assignments\n"
            "**3.** Use /health to check account status\n"
            "**4.** Use /leaderboard to see rankings"
        ))
        await interaction.response.edit_message(embed=e, view=self)

    @ui.button(label="\U0001F4CB Commands", style=discord.ButtonStyle.success)
    async def cmds(self, interaction: Interaction, btn: ui.Button):
        e = discord.Embed(title="Commands", color=GREEN)
        e.add_field(name="/hub", value="Control panel", inline=False)
        e.add_field(name="/login", value="Manual login", inline=False)
        e.add_field(name="/logout", value="Delete saved account", inline=False)
        e.add_field(name="/health", value="Check ban status", inline=False)
        e.add_field(name="/homeworks", value="List assignments", inline=False)
        e.add_field(name="/leaderboard", value="Rankings", inline=False)
        e.add_field(name="/status", value="Stats overview", inline=False)
        await interaction.response.edit_message(embed=e, view=self)

    @ui.button(label="Back", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: Interaction, btn: ui.Button):
        e = build_hub_embed(interaction.guild_id)
        v = HubView(interaction.guild_id)
        await interaction.response.edit_message(embed=e, view=v)


class HubView(ui.View):
    def __init__(self, guild_id: Optional[int]):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @ui.button(label="\U0001F511 Login", style=discord.ButtonStyle.success, row=0)
    async def login(self, interaction: Interaction, btn: ui.Button):
        await interaction.response.send_modal(LoginModal(self.guild_id))

    @ui.button(label="\U0001F6AA Logout", style=discord.ButtonStyle.danger, row=0)
    async def logout(self, interaction: Interaction, btn: ui.Button):
        delete_accounts(self.guild_id)
        embed = discord.Embed(title="Logged Out", color=RED)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="\u2699\uFE0F Settings", style=discord.ButtonStyle.primary, row=1)
    async def settings(self, interaction: Interaction, btn: ui.Button):
        await interaction.response.send_message(
            "Settings can be configured via `/settings` command (not yet implemented).", ephemeral=True
        )

    @ui.button(label="\u2764\uFE0F Health", style=discord.ButtonStyle.danger, row=1)
    async def health(self, interaction: Interaction, btn: ui.Button):
        await interaction.response.defer(ephemeral=True)
        uname, pwd = load_account(self.guild_id)
        if not uname:
            e = discord.Embed(title="Health Check", description="No account saved.", color=RED)
            return await interaction.followup.send(embed=e, ephemeral=True)
        ok, token = do_login(uname, pwd)
        if not ok:
            e = discord.Embed(title="Login Failed", description=token, color=RED)
            return await interaction.followup.send(embed=e, ephemeral=True)
        health = check_health(token)
        if health["banned"]:
            e = discord.Embed(title="\u274C Account Banned", description=f"Reason: {health['error_message']}", color=RED)
        else:
            stats = _lnut_post("stats/get", {"token": token})
            e = discord.Embed(title="\u2705 Healthy", color=GREEN)
            e.add_field(name="Tasks", value=str(stats.get("tasks", "?")), inline=True)
            e.add_field(name="Points", value=f"{stats.get('points', 0):,}", inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)

    @ui.button(label="\u2753 Help", style=discord.ButtonStyle.secondary, row=2)
    async def help(self, interaction: Interaction, btn: ui.Button):
        e = discord.Embed(title="Help", color=BLUE, description="Choose a topic:")
        v = HelpView()
        await interaction.response.edit_message(embed=e, view=v)

    @ui.button(label="\U0001F504 Refresh", style=discord.ButtonStyle.secondary, row=2)
    async def refresh(self, interaction: Interaction, btn: ui.Button):
        await interaction.response.defer()
        e = build_hub_embed(self.guild_id)
        v = HubView(self.guild_id)
        await interaction.edit_original_response(embed=e, view=v)

# ─── Cog ──────────────────────────────────────────────────────────────────

class CommandCentre(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="hub", description="Open LanguageNut control hub")
    async def hub(self, interaction: Interaction):
        await interaction.response.defer()
        e = build_hub_embed(interaction.guild_id)
        v = HubView(interaction.guild_id)
        await interaction.followup.send(embed=e, view=v)

    @app_commands.command(name="login", description="Login to LanguageNut")
    async def login(self, interaction: Interaction):
        await interaction.response.send_modal(LoginModal(interaction.guild_id))

    @app_commands.command(name="logout", description="Delete saved account")
    async def logout(self, interaction: Interaction):
        delete_accounts(interaction.guild_id)
        await interaction.response.send_message(embed=discord.Embed(title="Logged Out", color=RED), ephemeral=True)

    @app_commands.command(name="status", description="Account stats")
    async def status(self, interaction: Interaction):
        uname, pwd = load_account(interaction.guild_id)
        if not uname:
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ok, token = do_login(uname, pwd)
        if not ok:
            return await interaction.followup.send(f"Login: {token}", ephemeral=True)
        stats = _lnut_post("stats/get", {"token": token})
        e = discord.Embed(title="Account Status", colour=BLUE)
        e.add_field(name="Username", value=uname, inline=True)
        e.add_field(name="Tasks", value=str(stats.get("tasks", "N/A")), inline=True)
        e.add_field(name="Points", value=str(stats.get("points", "N/A")), inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="homeworks", description="List homeworks")
    async def homeworks(self, interaction: Interaction):
        uname, pwd = load_account(interaction.guild_id)
        if not uname:
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ok, token = do_login(uname, pwd)
        if not ok:
            return await interaction.followup.send(f"Login: {token}", ephemeral=True)
        result = _lnut_post("homeworkController/findHomeworkForStudent", {"token": token})
        items = result.get("list", result) if isinstance(result, dict) else result
        if isinstance(items, list) and items:
            lines = []
            for hw in items[:20]:
                title = hw.get("title", hw.get("name", "Unknown"))
                due = hw.get("dueDate", hw.get("due", "?"))
                status = "\u2705" if hw.get("completed") else "\U0001F4DD"
                lines.append(f"{status} **{title}** (due: {due})")
            text = "\n".join(lines)
        else:
            text = "No homeworks found."
        if len(text) > 1900:
            text = text[:1900] + "\n\n*(truncated)*"
        e = discord.Embed(title="Homeworks", description=text, colour=BLUE)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="leaderboard", description="View rankings")
    async def leaderboard(self, interaction: Interaction):
        uname, pwd = load_account(interaction.guild_id)
        if not uname:
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ok, token = do_login(uname, pwd)
        if not ok:
            return await interaction.followup.send(f"Login: {token}", ephemeral=True)
        data = _lnut_post("highscoreController/studentsAllAccount", {"token": token, "accountUid": ""})
        students = data.get("list", []) if isinstance(data, dict) else []
        e = discord.Embed(title="Leaderboard", colour=AMBER)
        if students:
            for i, s in enumerate(students[:15]):
                name = s.get("name", f"P{i+1}")
                pts = int(s.get("score", 0))
                medal = ["\U0001F947", "\U0001F948", "\U0001F949"][i] if i < 3 else f"`#{i+1}`"
                e.add_field(name=f"{medal} {name}", value=f"{pts:,} pts", inline=False)
        else:
            e.description = "No data."
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="health", description="Check account health")
    async def account_health(self, interaction: Interaction):
        uname, pwd = load_account(interaction.guild_id)
        if not uname:
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ok, token = do_login(uname, pwd)
        if not ok:
            return await interaction.followup.send(f"Login: {token}", ephemeral=True)
        health = check_health(token)
        if health["banned"]:
            e = discord.Embed(title="\u274C Account Banned", description=f"Reason: {health['error_message']}", colour=RED)
        else:
            e = discord.Embed(title="\u2705 Healthy", colour=GREEN)
            e.add_field(name="Username", value=uname, inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandCentre(bot))
    logger.info("CommandCentre loaded")
