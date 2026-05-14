"""
commands.py — LanguageNut Command Centre

Slash commands for farming, account management, and settings.
All API calls go through LanguagenutClient for consistent auth and stealth.
"""

import asyncio
import json
import logging
import random
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import discord
from discord import Interaction, app_commands
from discord.ext import commands

from automation.api_direct import LanguagenutClient
from automation.discover import HomeworkDiscoverer
from automation.stealth import StealthManager, seconds_to_human
import config
from utils.helper import (
    _pct,
    _is_done,
    extract_task_id,
    format_homework_list,
    seconds_to_string,
    cooldown_timestamp,
)
from utils.logger import setup_logging, log_user_command, log_homework_action

logger = setup_logging()

OWNER_ID = 1453752725324955656

# Colour palette
GREEN = discord.Colour(0x00FF88)
RED = discord.Colour(0xFF0044)
BLUE = discord.Colour(0x0088FF)
AMBER = discord.Colour(0xFFAA00)
PURPLE = discord.Colour(0x8844FF)

# ─── Session Store ──────────────────────────────────────────────────────────
sessions: Dict[int, Dict[str, Any]] = {}
settings_cache: Dict[int, Dict[str, Any]] = {}


def get_session(user_id: int) -> Dict[str, Any]:
    if user_id not in sessions:
        sessions[user_id] = {"token": None, "username": None, "uid": None}
    return sessions[user_id]


def get_settings(user_id: int) -> Dict[str, Any]:
    if user_id not in settings_cache:
        mgr = StealthManager(user_id=user_id)
        settings_cache[user_id] = mgr.sync_settings()
    return settings_cache[user_id]


# ══════════════════════════════════════════════════════════════════════════════
#  BUTTONS
# ══════════════════════════════════════════════════════════════════════════════

class LoginModal(discord.ui.Modal, title="LanguageNut Login"):
    username = discord.ui.TextInput(label="Username", placeholder="Enter your LanguageNut username")
    password = discord.ui.TextInput(label="Password", placeholder="Enter your password", style=discord.TextStyle.short)

    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: Interaction):
        client = LanguagenutClient()
        success, error = client.login(self.username.value, self.password.value)
        if success:
            sess = get_session(self.user_id)
            sess["token"] = client.token
            sess["username"] = self.username.value
            embed = discord.Embed(title="Login Successful", colour=GREEN)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(title="Login Failed", description=error, colour=RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)


class LogoutButton(discord.ui.Button):
    def __init__(self, user_id: int):
        super().__init__(style=discord.ButtonStyle.danger, label="Logout")
        self.user_id = user_id

    async def callback(self, interaction: Interaction):
        sess = get_session(self.user_id)
        sess["token"] = None
        sess["username"] = None
        sess["uid"] = None
        embed = discord.Embed(title="Logged Out", colour=RED)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class LoginButton(discord.ui.Button):
    def __init__(self, user_id: int, logged_in: bool = False):
        label = "Logged In ✅" if logged_in else "Login"
        style = discord.ButtonStyle.success if logged_in else discord.ButtonStyle.primary
        super().__init__(style=style, label=label, disabled=logged_in)
        self.user_id = user_id

    async def callback(self, interaction: Interaction):
        modal = LoginModal(self.user_id)
        await interaction.response.send_modal(modal)


class FarmButton(discord.ui.Button):
    def __init__(self, user_id: int):
        super().__init__(style=discord.ButtonStyle.success, label="🌾 Farm XP", row=1)
        self.user_id = user_id

    async def callback(self, interaction: Interaction):
        sess = get_session(self.user_id)
        token = sess.get("token")
        if not token:
            embed = discord.Embed(title="Not Logged In", colour=RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        client = LanguagenutClient()
        client.token = token

        discoverer = HomeworkDiscoverer(client)
        try:
            incomplete = await discoverer.get_incomplete_tasks(token)
        except Exception as e:
            embed = discord.Embed(title="Error fetching tasks", description=str(e)[:200], colour=RED)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if not incomplete:
            embed = discord.Embed(title="No incomplete tasks!", colour=GREEN)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        total = len(incomplete)
        done = 0
        failed = 0
        total_xp = 0

        embed = discord.Embed(
            title="🌾 Farming XP",
            description=f"Starting {total} tasks...",
            colour=AMBER
        )
        msg = await interaction.followup.send(embed=embed, ephemeral=True)

        for i, (hw, task) in enumerate(incomplete):
            try:
                task_name = task.get("translation", "Unknown")
                game_link = task.get("gameLink", "")
                to_lang = hw.get("languageCode", "en")

                vocabs = client.fetch_task_data(task, game_link, to_lang)
                if not vocabs:
                    failed += 1
                    continue

                # Build submission payload with stealth timing
                stealth = StealthManager()
                num_items = len(vocabs)
                correct_indices, incorrect_indices = stealth.determine_accuracy(num_items)
                wrong_uids = stealth.generate_wrong_answers(
                    [vocabs[i] for i in correct_indices],
                    incorrect_indices,
                    vocabs
                )
                timestamp = stealth.compute_timestamp(num_items)

                payload = {
                    "token": token,
                    "taskUid": task.get("gameUid", ""),
                    "gameLink": game_link,
                    "percentage": round(len(correct_indices) / num_items * 100),
                    "timeSpent": timestamp,
                    "correctVocabUids": [vocabs[i].get("uid", "") for i in correct_indices],
                    "incorrectVocabUids": wrong_uids,
                }

                result = client.submit_score(payload)
                if result.get("error"):
                    failed += 1
                else:
                    done += 1
                    total_xp += num_items * 200

            except Exception:
                failed += 1

            if (i + 1) % 3 == 0 or i == total - 1:
                embed.description = (
                    f"Progress: `{done}/{total}` tasks\n"
                    f"XP earned: `{total_xp:,}`\n"
                    f"Failed: `{failed}`"
                )
                embed.set_footer(text=f"{((i + 1) / total) * 100:.0f}%")
                await msg.edit(embed=embed)

            await asyncio.sleep(stealth.delay_between_tasks())

        embed.colour = GREEN
        embed.description = (
            f"**Complete!** `{done}/{total}` tasks\n"
            f"XP earned: `{total_xp:,}`"
        )
        if failed:
            embed.description += f"\nFailed: `{failed}`"
            embed.colour = AMBER
        await msg.edit(embed=embed)


class HomeworkListButton(discord.ui.Button):
    def __init__(self, user_id: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="📋 Homeworks", row=1)
        self.user_id = user_id

    async def callback(self, interaction: Interaction):
        sess = get_session(self.user_id)
        token = sess.get("token")
        if not token:
            embed = discord.Embed(title="Not Logged In", colour=RED)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        client = LanguagenutClient()
        client.token = token
        discoverer = HomeworkDiscoverer(client)
        try:
            homeworks = await discoverer.get_all_homeworks(token)
        except Exception as e:
            embed = discord.Embed(title="Error", description=str(e)[:200], colour=RED)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        text = format_homework_list(homeworks)
        if len(text) > 1900:
            text = text[:1900] + "\n\n*(truncated)*"
        embed = discord.Embed(title="Your Homeworks", description=text, colour=BLUE)
        await interaction.followup.send(embed=embed, ephemeral=True)


class LeaderboardButton(discord.ui.Button):
    def __init__(self, user_id: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="🏆 Leaderboard", row=1)
        self.user_id = user_id

    async def callback(self, interaction: Interaction):
        sess = get_session(self.user_id)
        token = sess.get("token")
        if not token:
            embed = discord.Embed(title="Not Logged In", colour=RED)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        client = LanguagenutClient()
        client.token = token
        success, data = client.get_leaderboard()
        if not success:
            embed = discord.Embed(title="Error fetching leaderboard", colour=RED)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        embed = discord.Embed(title="Leaderboard", colour=AMBER)
        if data:
            for i, entry in enumerate(data[:15]):
                ename = entry.get("name", f"Player {i + 1}")
                pts = entry.get("points", 0)
                medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"`#{i + 1}`"
                embed.add_field(name=f"{medal} {ename}", value=f"{pts} pts", inline=False)
        else:
            embed.description = "No data available."
        await interaction.followup.send(embed=embed, ephemeral=True)


class StatusButton(discord.ui.Button):
    def __init__(self, user_id: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="📊 Status", row=2)
        self.user_id = user_id

    async def callback(self, interaction: Interaction):
        sess = get_session(self.user_id)
        token = sess.get("token")
        if not token:
            embed = discord.Embed(title="Not Logged In", colour=RED)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        client = LanguagenutClient()
        client.token = token
        try:
            data = client.call_lnut("stats/get", {"token": token})
        except Exception as e:
            embed = discord.Embed(title="Error", description=str(e)[:200], colour=RED)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        embed = discord.Embed(title="Account Status", colour=BLUE)
        embed.add_field(name="Tasks Done", value=data.get("tasks", "N/A"))
        embed.add_field(name="Points", value=data.get("points", "N/A"))
        embed.add_field(name="Username", value=sess.get("username", "N/A"))
        await interaction.followup.send(embed=embed, ephemeral=True)


class SettingsButton(discord.ui.Button):
    def __init__(self, user_id: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="⚙️ Settings", row=2)
        self.user_id = user_id

    async def callback(self, interaction: Interaction):
        settings = get_settings(self.user_id)
        embed = discord.Embed(title="Settings", colour=BLUE)
        embed.add_field(name="Stealth", value="Enabled" if settings.get("stealth_enabled") else "Disabled")
        embed.add_field(name="Concurrency", value=f"`{settings.get('concurrency', 3)}`")
        embed.add_field(name="Auto Retry", value="Yes" if settings.get("auto_retry") else "No")
        embed.add_field(name="Min Accuracy", value=f"`{settings.get('min_accuracy', 85)}%`")
        embed.add_field(name="Max Accuracy", value=f"`{settings.get('max_accuracy', 92)}%`")
        embed.add_field(name="Speed", value=f"`{settings.get('speed', 10)}`")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════════
#  DASHBOARD VIEW
# ══════════════════════════════════════════════════════════════════════════════

class CommandCentreView(discord.ui.View):
    """The main dashboard with buttons for everything."""

    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self._build_buttons()

    def _build_buttons(self):
        sess = get_session(self.user_id)
        logged_in = sess.get("token") is not None

        if logged_in:
            self.add_item(LoginButton(self.user_id, logged_in=True))
        else:
            self.add_item(LoginButton(self.user_id, logged_in=False))

        if logged_in:
            self.add_item(LogoutButton(self.user_id))

        self.add_item(FarmButton(self.user_id))
        self.add_item(HomeworkListButton(self.user_id))
        self.add_item(LeaderboardButton(self.user_id))
        self.add_item(StatusButton(self.user_id))
        self.add_item(SettingsButton(self.user_id))


# ══════════════════════════════════════════════════════════════════════════════
#  EMBED BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def _build_dashboard_embed(user_id: int) -> discord.Embed:
    sess = get_session(user_id)
    logged_in = sess.get("token") is not None
    username = sess.get("username", "Not logged in")

    embed = discord.Embed(
        title="LanguageNut Command Centre",
        colour=PURPLE if logged_in else BLUE,
    )
    embed.add_field(name="Status", value="✅ Logged in" if logged_in else "❌ Not logged in")
    embed.add_field(name="Account", value=f"`{username}`")
    embed.set_footer(text="Use the buttons below to control the bot")
    return embed


# ══════════════════════════════════════════════════════════════════════════════
#  COG
# ══════════════════════════════════════════════════════════════════════════════

class CommandCentre(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="dashboard",
        description="Open the LanguageNut Command Centre"
    )
    async def dashboard(self, interaction: Interaction):
        embed = _build_dashboard_embed(interaction.user.id)
        view = CommandCentreView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="login", description="Login to LanguageNut")
    async def login(self, interaction: Interaction):
        sess = get_session(interaction.user.id)
        if sess.get("token"):
            embed = discord.Embed(title="Already Logged In", colour=GREEN)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        modal = LoginModal(interaction.user.id)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="logout", description="Logout of LanguageNut")
    async def logout(self, interaction: Interaction):
        sess = get_session(interaction.user.id)
        sess["token"] = None
        sess["username"] = None
        sess["uid"] = None
        embed = discord.Embed(title="Logged Out", colour=RED)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="status", description="Check your account status")
    async def status(self, interaction: Interaction):
        sess = get_session(interaction.user.id)
        token = sess.get("token")
        if not token:
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        client = LanguagenutClient()
        client.token = token
        try:
            data = client.call_lnut("stats/get", {"token": token})
        except Exception as e:
            return await interaction.followup.send(f"Error: {e}", ephemeral=True)
        embed = discord.Embed(title="Status", colour=BLUE)
        embed.add_field(name="Tasks Done", value=data.get("tasks", "N/A"))
        embed.add_field(name="Points", value=data.get("points", "N/A"))
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="farm", description="Start farming XP")
    async def farm(self, interaction: Interaction):
        sess = get_session(interaction.user.id)
        token = sess.get("token")
        if not token:
            embed = discord.Embed(title="Not Logged In", colour=RED)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        await interaction.response.defer(ephemeral=True)

        client = LanguagenutClient()
        client.token = token
        discoverer = HomeworkDiscoverer(client)
        try:
            incomplete = await discoverer.get_incomplete_tasks(token)
        except Exception as e:
            embed = discord.Embed(title="Error fetching tasks", description=str(e)[:200], colour=RED)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        if not incomplete:
            embed = discord.Embed(title="No incomplete tasks!", colour=GREEN)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        total = len(incomplete)
        done = 0
        failed = 0
        total_xp = 0

        embed = discord.Embed(
            title="🌾 Farming XP",
            description=f"Starting {total} tasks...",
            colour=AMBER
        )
        msg = await interaction.followup.send(embed=embed, ephemeral=True)

        stealth = StealthManager()

        for i, (hw, task) in enumerate(incomplete):
            try:
                game_link = task.get("gameLink", "")
                to_lang = hw.get("languageCode", "en")

                vocabs = client.fetch_task_data(task, game_link, to_lang)
                if not vocabs:
                    failed += 1
                    continue

                num_items = len(vocabs)
                correct_indices, incorrect_indices = stealth.determine_accuracy(num_items)
                wrong_uids = stealth.generate_wrong_answers(
                    [vocabs[j] for j in correct_indices],
                    incorrect_indices,
                    vocabs
                )
                timestamp = stealth.compute_timestamp(num_items)

                payload = {
                    "token": token,
                    "taskUid": task.get("gameUid", ""),
                    "gameLink": game_link,
                    "percentage": round(len(correct_indices) / num_items * 100),
                    "timeSpent": timestamp,
                    "correctVocabUids": [vocabs[j].get("uid", "") for j in correct_indices],
                    "incorrectVocabUids": wrong_uids,
                }

                result = client.submit_score(payload)
                if result.get("error"):
                    failed += 1
                else:
                    done += 1
                    total_xp += num_items * 200

            except Exception:
                failed += 1

            if (i + 1) % 3 == 0 or i == total - 1:
                embed.description = (
                    f"Progress: `{done}/{total}` tasks\n"
                    f"XP earned: `{total_xp:,}`\n"
                    f"Failed: `{failed}`"
                )
                embed.set_footer(text=f"{((i + 1) / total) * 100:.0f}%")
                await msg.edit(embed=embed)

            await asyncio.sleep(stealth.delay_between_tasks())

        embed.colour = GREEN
        embed.description = (
            f"**Complete!** `{done}/{total}` tasks\n"
            f"XP earned: `{total_xp:,}`"
        )
        if failed:
            embed.description += f"\nFailed: `{failed}`"
            embed.colour = AMBER
        await msg.edit(embed=embed)

    @app_commands.command(name="homeworks", description="List your homeworks")
    async def homeworks(self, interaction: Interaction):
        sess = get_session(interaction.user.id)
        token = sess.get("token")
        if not token:
            embed = discord.Embed(title="Not Logged In", colour=RED)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        client = LanguagenutClient()
        client.token = token
        discoverer = HomeworkDiscoverer(client)
        try:
            homeworks = await discoverer.get_all_homeworks(token)
        except Exception as e:
            embed = discord.Embed(title="Error", description=str(e)[:200], colour=RED)
            return await interaction.followup.send(embed=embed, ephemeral=True)
        text = format_homework_list(homeworks)
        if len(text) > 1900:
            text = text[:1900] + "\n\n*(truncated)*"
        embed = discord.Embed(title="Your Homeworks", description=text, colour=BLUE)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandCentre(bot))
