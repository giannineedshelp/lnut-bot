import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, List, Dict, Any
import asyncio
import sys
import os
import time
import json
import io
import textwrap
import traceback
from datetime import datetime, timedelta
from automation.api_direct import LNApiClient
from automation.discover import HomeworkDiscoverer
from automation.stealth import StealthManager
import config
from utils.helper import *
from utils.logger import Logger

logger = Logger("Commands")

OWNER_ID = 1453752725324955656
GREEN = discord.Colour(int("00ff88", 16))
RED = discord.Colour(int("ff0044", 16))
BLUE = discord.Colour(int("0088ff", 16))
AMBER = discord.Colour(int("ffaa00", 16))
PURPLE = discord.Colour(int("8844ff", 16))

# ─── SESSION STORE ───────────────────────────────────────────────────────────
sessions: Dict[int, Dict[str, Any]] = {}
settings_cache: Dict[int, Dict[str, Any]] = {}


def get_session(user_id: int) -> Dict[str, Any]:
    if user_id not in sessions:
        sessions[user_id] = {chr(116): None, chr(111): None, chr(117): None}
    return sessions[user_id]


def get_settings(user_id: int) -> Dict[str, Any]:
    if user_id not in settings_cache:
        mgr = StealthManager(user_id)
        settings_cache[user_id] = mgr.sync_settings()
    return settings_cache[user_id]


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN DASHBOARD VIEW — THE COMMAND CENTRE
# ═══════════════════════════════════════════════════════════════════════════════

class CommandCentreView(discord.ui.View):
    """The main dashboard with buttons for everything."""

    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self._build_buttons()

    def _build_buttons(self):
        sess = get_session(self.user_id)
        logged_in = sess.get(chr(116)) is not None

        if logged_in:
            self.add_item(LoginButton(self.user_id, logged_in=True))
        else:
            self.add_item(LoginButton(self.user_id, logged_in=False))

        self.add_item(HomeworkButton(self.user_id, disabled=not logged_in))
        self.add_item(DoTasksButton(self.user_id, disabled=not logged_in))
        self.add_item(LeaderboardButton(self.user_id, disabled=not logged_in))

        self.add_item(StatusButton(self.user_id, disabled=not logged_in))
        self.add_item(SettingsButton(self.user_id))
        self.add_item(HelpButton(self.user_id))

        if self.user_id == OWNER_ID:
            self.add_item(AdminPanelButton(self.user_id))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            msg = self.message
            if msg:
                await msg.edit(view=self)
        except:
            pass


# ─── DASHBOARD BUTTONS ───────────────────────────────────────────────────────

class LoginButton(discord.ui.Button):
    def __init__(self, user_id: int, logged_in: bool):
        self.target_user = user_id
        emoji = "🔓" if not logged_in else "🔒"
        label = "Login" if not logged_in else "Logout"
        style = discord.ButtonStyle.success if not logged_in else discord.ButtonStyle.danger
        super().__init__(style=style, label=label, emoji=emoji, row=0, custom_id=f"ln_{user_id}")

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_user:
            return await interaction.response.send_message("This isn't your dashboard.", ephemeral=True)

        sess = get_session(self.target_user)

        if sess.get(chr(116)):
            sess[chr(116)] = None
            sess[chr(111)] = None
            sess[chr(117)] = None
            embed = discord.Embed(title="Logged Out", description="Session cleared.", colour=RED)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            await _refresh_dashboard(interaction, self.target_user)
            return

        modal = LoginModal(self.target_user)
        await interaction.response.send_modal(modal)


class LoginModal(discord.ui.Modal, title="Login to LanguageNut"):
    username_input = discord.ui.TextInput(
        label="Username / Email",
        placeholder="Enter your username or email...",
        max_length=100,
        required=True
    )
    password_input = discord.ui.TextInput(
        label="Password",
        placeholder="Enter your password...",
        style=discord.TextStyle.short,
        max_length=100,
        required=True
    )

    def __init__(self, user_id: int):
        super().__init__()
        self.target_user = user_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        username = self.username_input.value
        password = self.password_input.value
        client = LNApiClient()
        result = client.login(username, password)
        if not result or not result.get(chr(115)):
            embed = discord.Embed(title="Login Failed", description="Invalid credentials or server error.", colour=RED)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        sess = get_session(self.target_user)
        sess[chr(116)] = result[chr(116)]
        sess[chr(111)] = result[chr(111)]
        sess[chr(117)] = result[chr(117)]

        embed = discord.Embed(
            title="Login Successful",
            description=f"Welcome **{result.get(chr(110), 'User')}**!",
            colour=GREEN
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        await _refresh_dashboard(interaction, self.target_user)


class HomeworkButton(discord.ui.Button):
    def __init__(self, user_id: int, disabled: bool = False):
        self.target_user = user_id
        super().__init__(
            style=discord.ButtonStyle.secondary, label="Homework",
            emoji="📚", row=1, disabled=disabled, custom_id=f"hw_{user_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_user:
            return await interaction.response.send_message("Not your dashboard.", ephemeral=True)
        sess = get_session(self.target_user)
        token = sess.get(chr(116))
        if not token:
            return await interaction.response.send_message("You're not logged in.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        discoverer = HomeworkDiscoverer()
        try:
            homeworks = discoverer.get_all_homeworks(token)
        except Exception as e:
            return await interaction.followup.send(f"Failed to fetch homework: {e}", ephemeral=True)

        if not homeworks:
            embed = discord.Embed(
                title="📚 Homework",
                description="No homework assigned!",
                colour=GREEN
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        view = HomeworkDashboardView(self.target_user, homeworks, 0)
        embed = _build_homework_embed(homeworks[0], 0, len(homeworks))
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class DoTasksButton(discord.ui.Button):
    def __init__(self, user_id: int, disabled: bool = False):
        self.target_user = user_id
        super().__init__(
            style=discord.ButtonStyle.primary, label="Do Tasks",
            emoji="⚡", row=1, disabled=disabled, custom_id=f"do_{user_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_user:
            return await interaction.response.send_message("Not your dashboard.", ephemeral=True)
        sess = get_session(self.target_user)
        token = sess.get(chr(116))
        if not token:
            return await interaction.response.send_message("Not logged in.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        discoverer = HomeworkDiscoverer()
        try:
            homeworks = discoverer.get_all_homeworks(token)
        except Exception as e:
            return await interaction.followup.send(f"Error: {e}", ephemeral=True)

        if not homeworks:
            embed = discord.Embed(
                title="⚡ Do Tasks",
                description="No homework available. All done!",
                colour=GREEN
            )
            return await interaction.followup.send(embed=embed, ephemeral=True)

        view = TaskSelectView(self.target_user, homeworks, token)
        embed = discord.Embed(
            title="⚡ Select Homework to Work On",
            description="Choose which homework set to do tasks from.",
            colour=AMBER
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class LeaderboardButton(discord.ui.Button):
    def __init__(self, user_id: int, disabled: bool = False):
        self.target_user = user_id
        super().__init__(
            style=discord.ButtonStyle.secondary, label="Leaderboard",
            emoji="🏆", row=1, disabled=disabled, custom_id=f"lb_{user_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_user:
            return await interaction.response.send_message("Not your dashboard.", ephemeral=True)
        sess = get_session(self.target_user)
        token = sess.get(chr(116))
        if not token:
            return await interaction.response.send_message("Not logged in.", ephemeral=True)

        client = LNApiClient()
        await interaction.response.defer(ephemeral=True)
        try:
            world = client.get_world_leaderboard(token)
            school = client.get_school_leaderboard(token)
            klass = client.get_class_leaderboard(token)
        except Exception as e:
            return await interaction.followup.send(f"Error fetching leaderboards: {e}", ephemeral=True)

        view = LeaderboardView(self.target_user, world, school, klass)
        embed = _build_leaderboard_embed("world", world)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class StatusButton(discord.ui.Button):
    def __init__(self, user_id: int, disabled: bool = False):
        self.target_user = user_id
        super().__init__(
            style=discord.ButtonStyle.secondary, label="Status",
            emoji="📊", row=2, disabled=disabled, custom_id=f"st_{user_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_user:
            return await interaction.response.send_message("Not your dashboard.", ephemeral=True)
        sess = get_session(self.target_user)
        token = sess.get(chr(116))
        if not token:
            return await interaction.response.send_message("Not logged in.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        settings = get_settings(self.target_user)
        client = LNApiClient()
        try:
            data = client.call_lnut(
                token,
                chr(115) + chr(116) + chr(97) + chr(116) + chr(115),
                chr(103) + chr(101) + chr(116)
            )
        except Exception as e:
            return await interaction.followup.send(f"Error fetching status: {e}", ephemeral=True)

        uid = sess.get(chr(111), "?")
        uname = sess.get(chr(117), "?")

        embed = discord.Embed(title="📊 Account Status", colour=BLUE)
        embed.add_field(name="User ID", value=f"`{uid}`", inline=True)
        embed.add_field(name="Username", value=f"`{uname}`", inline=True)
        embed.add_field(
            name="Delay",
            value=f"{settings.get(chr(100) + chr(101) + chr(108) + chr(97) + chr(121), 2)}s",
            inline=True
        )
        embed.add_field(
            name="Speed Display",
            value=settings.get(chr(115) + chr(112) + chr(101) + chr(101) + chr(100), "Normal"),
            inline=True
        )
        embed.add_field(
            name="Tasks Done",
            value=data.get(chr(116) + chr(97) + chr(115) + chr(107) + chr(115), "N/A"),
            inline=True
        )
        embed.add_field(
            name="Points",
            value=data.get(chr(112) + chr(111) + chr(105) + chr(110) + chr(116) + chr(115), "N/A"),
            inline=True
        )
        lang_key = chr(108) + chr(97) + chr(110) + chr(103) + chr(117) + chr(97) + chr(103) + chr(101)
        if data.get(lang_key):
            embed.add_field(name="Language", value=data[lang_key], inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)


class SettingsButton(discord.ui.Button):
    def __init__(self, user_id: int):
        self.target_user = user_id
        super().__init__(
            style=discord.ButtonStyle.secondary, label="Settings",
            emoji="⚙️", row=2, custom_id=f"set_{user_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_user:
            return await interaction.response.send_message("Not your dashboard.", ephemeral=True)
        settings = get_settings(self.target_user)
        view = SettingsDashboardView(self.target_user, settings)
        embed = _build_settings_embed(settings)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class HelpButton(discord.ui.Button):
    def __init__(self, user_id: int):
        self.target_user = user_id
        super().__init__(
            style=discord.ButtonStyle.secondary, label="Help / Tutorial",
            emoji="❓", row=2, custom_id=f"help_{user_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_user:
            return await interaction.response.send_message("Not your dashboard.", ephemeral=True)
        embed = discord.Embed(title="❓ Help & Tutorial", colour=PURPLE)
        embed.add_field(
            name="Login",
            value="Start by logging into your LanguageNut account.",
            inline=False
        )
        embed.add_field(
            name="Homework",
            value="View your assigned homework and see progress.",
            inline=False
        )
        embed.add_field(
            name="Do Tasks",
            value="Auto-complete homework tasks. Configure delay and speed in Settings.",
            inline=False
        )
        embed.add_field(
            name="Leaderboard",
            value="Check rankings: World, School, or Class.",
            inline=False
        )
        embed.add_field(
            name="Status",
            value="View your account stats and current session.",
            inline=False
        )
        embed.add_field(
            name="Settings",
            value="Adjust task delay, speed display, and preferences.",
            inline=False
        )
        embed.set_footer(text="All operations run in your session. Stay logged in between uses.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AdminPanelButton(discord.ui.Button):
    def __init__(self, user_id: int):
        self.target_user = user_id
        super().__init__(
            style=discord.ButtonStyle.danger, label="Admin Panel",
            emoji="🛡️", row=3, custom_id=f"adm_{user_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("Access denied.", ephemeral=True)
        view = AdminPanelView()
        embed = discord.Embed(title="Admin Control Panel", colour=RED)
        embed.add_field(
            name="Commands Available",
            value="Use the buttons below for bot administration.",
            inline=False
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  HOMEWORK DASHBOARD (paginator)
# ═══════════════════════════════════════════════════════════════════════════════

class HomeworkDashboardView(discord.ui.View):
    def __init__(self, user_id: int, homeworks: list, page: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.homeworks = homeworks
        self.page = page
        self._build()

    def _build(self):
        self.clear_items()
        total = len(self.homeworks)
        if total > 1:
            self.add_item(PrevHwButton(self, disabled=(self.page == 0)))
            self.add_item(PageIndicatorButton(f"{self.page + 1}/{total}"))
            self.add_item(NextHwButton(self, disabled=(self.page >= total - 1)))
        self.add_item(DoThisHomeworkButton(self.user_id, self.homeworks[self.page]))


class PrevHwButton(discord.ui.Button):
    def __init__(self, parent_view: HomeworkDashboardView, disabled: bool):
        self.parent_view = parent_view
        self.target_user = parent_view.user_id
        self.current_page = parent_view.page
        super().__init__(style=discord.ButtonStyle.primary, label="◀", row=0, disabled=disabled)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_user:
            return await interaction.response.send_message("Not yours.", ephemeral=True)
        new_page = self.current_page - 1
        if new_page < 0:
            return await interaction.response.send_message("Already on first page.", ephemeral=True)
        new_view = HomeworkDashboardView(self.target_user, self.parent_view.homeworks, new_page)
        embed = _build_homework_embed(
            self.parent_view.homeworks[new_page], new_page, len(self.parent_view.homeworks)
        )
        await interaction.response.edit_message(embed=embed, view=new_view)


class NextHwButton(discord.ui.Button):
    def __init__(self, parent_view: HomeworkDashboardView, disabled: bool):
        self.parent_view = parent_view
        self.target_user = parent_view.user_id
        self.current_page = parent_view.page
        super().__init__(style=discord.ButtonStyle.primary, label="▶", row=0, disabled=disabled)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_user:
            return await interaction.response.send_message("Not yours.", ephemeral=True)
        new_page = self.current_page + 1
        if new_page >= len(self.parent_view.homeworks):
            return await interaction.response.send_message("Already on last page.", ephemeral=True)
        new_view = HomeworkDashboardView(self.target_user, self.parent_view.homeworks, new_page)
        embed = _build_homework_embed(
            self.parent_view.homeworks[new_page], new_page, len(self.parent_view.homeworks)
        )
        await interaction.response.edit_message(embed=embed, view=new_view)


class PageIndicatorButton(discord.ui.Button):
    def __init__(self, label: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=label, row=0, disabled=True)


class DoThisHomeworkButton(discord.ui.Button):
    def __init__(self, user_id: int, homework: dict):
        self.target_user = user_id
        self.homework = homework
        super().__init__(
            style=discord.ButtonStyle.success, label="Do This Homework",
            emoji="⚡", row=1
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_user:
            return await interaction.response.send_message("Not yours.", ephemeral=True)
        sess = get_session(self.target_user)
        token = sess.get(chr(116))
        if not token:
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await _run_homework_tasks(interaction, self.target_user, token, self.homework)


# ═══════════════════════════════════════════════════════════════════════════════
#  TASK SELECT VIEW
# ═══════════════════════════════════════════════════════════════════════════════

class TaskSelectView(discord.ui.View):
    def __init__(self, user_id: int, homeworks: list, token: str):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.token = token
        options = []
        for i, hw in enumerate(homeworks[:25]):
            hname = hw.get(chr(110) + chr(97) + chr(109) + chr(101), f"Homework {i + 1}")
            options.append(
                discord.SelectOption(
                    label=hname[:100], value=str(i), description=f"Set {i + 1}"
                )
            )
        self.add_item(TaskSelectDropdown(options, homeworks, user_id, token))


class TaskSelectDropdown(discord.ui.Select):
    def __init__(self, options: list, homeworks: list, user_id: int, token: str):
        self.homeworks = homeworks
        self.target_user = user_id
        self.token = token
        super().__init__(
            placeholder="Choose a homework set...",
            min_values=1, max_values=1, options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_user:
            return await interaction.response.send_message("Not yours.", ephemeral=True)
        idx = int(self.values[0])
        hw = self.homeworks[idx]
        await interaction.response.defer(ephemeral=True)
        await _run_homework_tasks(interaction, self.target_user, self.token, hw)


# ═══════════════════════════════════════════════════════════════════════════════
#  LEADERBOARD VIEW
# ═══════════════════════════════════════════════════════════════════════════════

class LeaderboardView(discord.ui.View):
    def __init__(self, user_id: int, world: list, school: list, klass: list):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.world = world
        self.school = school
        self.klass = klass
        self.add_item(
            LeaderboardTabButton("World", "world", user_id, style=discord.ButtonStyle.primary)
        )
        self.add_item(
            LeaderboardTabButton("School", "school", user_id, style=discord.ButtonStyle.secondary)
        )
        self.add_item(
            LeaderboardTabButton("Class", "class", user_id, style=discord.ButtonStyle.secondary)
        )


class LeaderboardTabButton(discord.ui.Button):
    def __init__(self, label: str, scope: str, user_id: int, style: discord.ButtonStyle):
        self.target_user = user_id
        self.scope = scope
        super().__init__(style=style, label=label, emoji="🏆", row=0)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_user:
            return await interaction.response.send_message("Not yours.", ephemeral=True)
        sess = get_session(self.target_user)
        token = sess.get(chr(116))
        if not token:
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        client = LNApiClient()
        try:
            if self.scope == "world":
                data = client.get_world_leaderboard(token)
            elif self.scope == "school":
                data = client.get_school_leaderboard(token)
            else:
                data = client.get_class_leaderboard(token)
        except Exception as e:
            return await interaction.followup.send(f"Error: {e}", ephemeral=True)
        embed = _build_leaderboard_embed(self.scope, data)
        await interaction.followup.send(embed=embed, ephemeral=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  SETTINGS DASHBOARD VIEW
# ═══════════════════════════════════════════════════════════════════════════════

class SettingsDashboardView(discord.ui.View):
    def __init__(self, user_id: int, settings: dict):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.settings = settings
        self.add_item(EditDelayButton(user_id, settings))
        self.add_item(ToggleSpeedButton(user_id, settings))
        self.add_item(ResetSettingsButton(user_id))


class EditDelayButton(discord.ui.Button):
    def __init__(self, user_id: int, settings: dict):
        self.target_user = user_id
        self.current_delay = settings.get(
            chr(100) + chr(101) + chr(108) + chr(97) + chr(121), 2
        )
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=f"Delay: {self.current_delay}s",
            emoji="⏱️", row=0
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_user:
            return await interaction.response.send_message("Not yours.", ephemeral=True)
        modal = DelayModal(self.target_user, self.current_delay)
        await interaction.response.send_modal(modal)


class DelayModal(discord.ui.Modal, title="Set Task Delay"):
    delay_input = discord.ui.TextInput(
        label="Delay (seconds)", placeholder="2",
        max_length=4, required=True
    )

    def __init__(self, user_id: int, current: int):
        super().__init__()
        self.target_user = user_id
        self.delay_input.default = str(current)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = float(self.delay_input.value)
            if val < 0.5 or val > 30:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                "Enter a number between 0.5 and 30.", ephemeral=True
            )
        mgr = StealthManager(self.target_user)
        mgr.delay_between_tasks(val)
        settings_cache.pop(self.target_user, None)
        embed = discord.Embed(
            title="Delay Updated",
            description=f"Set to **{val}s**",
            colour=GREEN
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ToggleSpeedButton(discord.ui.Button):
    def __init__(self, user_id: int, settings: dict):
        self.target_user = user_id
        self.current = settings.get(
            chr(115) + chr(112) + chr(101) + chr(101) + chr(100), "Normal"
        )
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=f"Speed: {self.current}",
            emoji="🚀", row=0
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_user:
            return await interaction.response.send_message("Not yours.", ephemeral=True)
        mgr = StealthManager(self.target_user)
        new_speed = "Fast" if self.current == "Normal" else "Normal"
        mgr.speed_display(new_speed)
        settings_cache.pop(self.target_user, None)
        embed = discord.Embed(
            title="Speed Updated",
            description=f"Set to **{new_speed}**",
            colour=GREEN
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ResetSettingsButton(discord.ui.Button):
    def __init__(self, user_id: int):
        self.target_user = user_id
        super().__init__(
            style=discord.ButtonStyle.danger,
            label="Reset Settings", emoji="🔄", row=0
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.target_user:
            return await interaction.response.send_message("Not yours.", ephemeral=True)
        mgr = StealthManager(self.target_user)
        mgr.delay_between_tasks(2)
        mgr.speed_display("Normal")
        settings_cache.pop(self.target_user, None)
        embed = discord.Embed(
            title="Settings Reset",
            description="Back to defaults (2s delay, Normal speed).",
            colour=GREEN
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  ADMIN PANEL VIEW
# ═══════════════════════════════════════════════════════════════════════════════

class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(AdminActionButton("Restart", "restart", discord.ButtonStyle.danger, "🔄"))
        self.add_item(AdminActionButton("Shutdown", "shutdown", discord.ButtonStyle.danger, "⛔"))
        self.add_item(AdminActionButton("Sync Cmds", "sync", discord.ButtonStyle.primary, "🔁"))
        self.add_item(AdminActionButton("Clear Sessions", "clear", discord.ButtonStyle.secondary, "🧹"))
        self.add_item(AdminActionButton("Logs", "logs", discord.ButtonStyle.secondary, "📋"))
        self.add_item(AdminActionButton("Reload", "reload", discord.ButtonStyle.primary, "📦"))
        self.add_item(AdminActionButton("Online", "online", discord.ButtonStyle.success, "🟢"))
        self.add_item(AdminActionButton("Offline", "offline", discord.ButtonStyle.danger, "🔴"))


class AdminActionButton(discord.ui.Button):
    def __init__(self, label: str, action: str, style: discord.ButtonStyle, emoji: str):
        self.action = action
        super().__init__(
            style=style, label=label, emoji=emoji,
            row=0 if len(label) < 10 else 1
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("Access denied.", ephemeral=True)

        bot = interaction.client

        if self.action == "sync":
            await interaction.response.defer(ephemeral=True)
            try:
                synced = await bot.tree.sync()
                await interaction.followup.send(
                    f"Synced {len(synced)} commands.", ephemeral=True
                )
            except Exception as e:
                await interaction.followup.send(f"Sync failed: {e}", ephemeral=True)

        elif self.action == "clear":
            sessions.clear()
            settings_cache.clear()
            await interaction.response.send_message(
                "Cleared all sessions & settings cache.", ephemeral=True
            )

        elif self.action == "logs":
            await interaction.response.defer(ephemeral=True)
            try:
                with open("logs/latest.log", "r") as f:
                    content = f.read()[-2000:]
                await interaction.followup.send(f"```log\n{content}\n```", ephemeral=True)
            except:
                await interaction.followup.send("No log file found.", ephemeral=True)

        elif self.action == "reload":
            await interaction.response.defer(ephemeral=True)
            try:
                await bot.reload_extension("commands")
                await interaction.followup.send("Reloaded commands.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"Reload failed: {e}", ephemeral=True)

        elif self.action == "online":
            await bot.change_presence(
                status=discord.Status.online,
                activity=discord.Game(name="Command Centre")
            )
            await interaction.response.send_message("Status set to Online.", ephemeral=True)

        elif self.action == "offline":
            await bot.change_presence(status=discord.Status.invisible)
            await interaction.response.send_message("Status set to Invisible.", ephemeral=True)

        elif self.action == "restart":
            await interaction.response.send_message("Restarting...", ephemeral=True)
            os.execv(sys.executable, ["python"] + sys.argv)

        elif self.action == "shutdown":
            await interaction.response.send_message("Shutting down...", ephemeral=True)
            await bot.close()
            sys.exit(0)


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

async def _refresh_dashboard(interaction: discord.Interaction, user_id: int):
    embed = _build_dashboard_embed(user_id)
    view = CommandCentreView(user_id)
    await interaction.edit_original_response(embed=embed, view=view)


def _build_dashboard_embed(user_id: int) -> discord.Embed:
    sess = get_session(user_id)
    logged_in = sess.get(chr(116)) is not None
    uname = sess.get(chr(117), "Not logged in") if logged_in else "Not logged in"

    embed = discord.Embed(
        title="LanguageNut Command Centre",
        colour=GREEN if logged_in else RED
    )
    embed.add_field(
        name="Account",
        value=f"`{uname}`" if logged_in else "`No session`",
        inline=True
    )
    embed.add_field(
        name="Status",
        value="Logged in" if logged_in else "Logged out",
        inline=True
    )
    if logged_in:
        embed.add_field(
            name="User ID",
            value=f"`{sess.get(chr(111), '?')}`",
            inline=True
        )
    embed.set_footer(text="Use the buttons below to navigate.")
    return embed


def _build_homework_embed(hw: dict, idx: int, total: int) -> discord.Embed:
    name = hw.get(chr(110) + chr(97) + chr(109) + chr(101), "Unnamed")
    desc = hw.get(
        chr(100) + chr(101) + chr(115) + chr(99) +
        chr(114) + chr(105) + chr(112) + chr(116) +
        chr(105) + chr(111) + chr(110) + chr(115),
        "No description"
    )
    progress = hw.get(
        chr(112) + chr(114) + chr(111) + chr(103) +
        chr(114) + chr(101) + chr(115) + chr(115),
        "0%"
    )
    due = hw.get(chr(100) + chr(117) + chr(101), "No due date")
    embed = discord.Embed(title=f"{name}", description=desc, colour=BLUE)
    embed.add_field(name="Progress", value=progress, inline=True)
    embed.add_field(name="Due", value=due, inline=True)
    embed.set_footer(text=f"Homework {idx + 1} of {total}")
    return embed


def _build_leaderboard_embed(scope: str, data: list) -> discord.Embed:
    title_map = {
        "world": "World Leaderboard",
        "school": "School Leaderboard",
        "class": "Class Leaderboard"
    }
    embed = discord.Embed(
        title=title_map.get(scope, "Leaderboard"),
        colour=AMBER
    )
    if data:
        for i, entry in enumerate(data[:15]):
            ename = entry.get(chr(110) + chr(97) + chr(109) + chr(101), f"Player {i + 1}")
            pts = entry.get(chr(112) + chr(111) + chr(105) + chr(110) + chr(116) + chr(115), 0)
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"`#{i + 1}`"
            embed.add_field(name=f"{medal} {ename}", value=f"{pts} pts", inline=False)
    else:
        embed.description = "No data available."
    return embed


def _build_settings_embed(settings: dict) -> discord.Embed:
    delay = settings.get(chr(100) + chr(101) + chr(108) + chr(97) + chr(121), 2)
    speed = settings.get(chr(115) + chr(112) + chr(101) + chr(101) + chr(100), "Normal")
    embed = discord.Embed(title="Settings", colour=BLUE)
    embed.add_field(name="Task Delay", value=f"`{delay}s`", inline=True)
    embed.add_field(name="Speed Display", value=f"`{speed}`", inline=True)
    return embed


async def _run_homework_tasks(
    interaction: discord.Interaction,
    user_id: int,
    token: str,
    homework: dict
):
    settings = get_settings(user_id)
    delay = settings.get(chr(100) + chr(101) + chr(108) + chr(97) + chr(121), 2)
    client = LNApiClient()

    hw_name = homework.get(chr(110) + chr(97) + chr(109) + chr(101), "Homework")
    embed = discord.Embed(
        title=f"Working on: {hw_name}",
        description="Starting...",
        colour=AMBER
    )
    msg = await interaction.followup.send(embed=embed, ephemeral=True)

    try:
        tasks = client.fetch_task_data(token, homework)
    except Exception as e:
        embed.description = f"Failed to fetch tasks: {e}"
        embed.colour = RED
        return await msg.edit(embed=embed)

    if not tasks:
        embed.description = "No tasks to do - all complete!"
        embed.colour = GREEN
        return await msg.edit(embed=embed)

    total = len(tasks)
    done = 0
    failed = 0

    for i, task in enumerate(tasks):
        try:
            client.submit_score(token, task)
            done += 1
        except Exception:
            failed += 1

        if (i + 1) % 3 == 0 or i == total - 1:
            embed.description = f"Progress: `{done}/{total}` tasks completed"
            if failed:
                embed.description += f" | `{failed}` failed"
            embed.set_footer(text=f"{((i + 1) / total) * 100:.0f}%")
            await msg.edit(embed=embed)

        await asyncio.sleep(delay)

    embed.colour = GREEN
    embed.description = f"**Finished!** Done `{done}/{total}` tasks" + (
        f" ({failed} failed)" if failed else ""
    )
    embed.set_footer(text="All done!")
    await msg.edit(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════════
#  COG & SLASH COMMAND
# ═══════════════════════════════════════════════════════════════════════════════

class CommandCentre(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="dashboard",
        description="Open the LanguageNut Command Centre"
    )
    async def dashboard(self, interaction: discord.Interaction):
        embed = _build_dashboard_embed(interaction.user.id)
        view = CommandCentreView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="login", description="Login to LanguageNut")
    async def login(self, interaction: discord.Interaction):
        sess = get_session(interaction.user.id)
        if sess.get(chr(116)):
            embed = discord.Embed(title="Already Logged In", colour=GREEN)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        modal = LoginModal(interaction.user.id)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="logout", description="Logout of LanguageNut")
    async def logout(self, interaction: discord.Interaction):
        sess = get_session(interaction.user.id)
        sess[chr(116)] = None
        sess[chr(111)] = None
        sess[chr(117)] = None
        embed = discord.Embed(title="Logged Out", colour=RED)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="status", description="Check your account status")
    async def status(self, interaction: discord.Interaction):
        sess = get_session(interaction.user.id)
        token = sess.get(chr(116))
        if not token:
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        client = LNApiClient()
        try:
            data = client.call_lnut(
                token,
                chr(115) + chr(116) + chr(97) + chr(116) + chr(115),
                chr(103) + chr(101) + chr(116)
            )
        except Exception as e:
            return await interaction.followup.send(f"Error: {e}", ephemeral=True)
        embed = discord.Embed(title="Status", colour=BLUE)
        embed.add_field(
            name="Tasks Done",
            value=data.get(chr(116) + chr(97) + chr(115) + chr(107) + chr(115), "N/A")
        )
        embed.add_field(
            name="Points",
            value=data.get(chr(112) + chr(111) + chr(105) + chr(110) + chr(116) + chr(115), "N/A")
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandCentre(bot))