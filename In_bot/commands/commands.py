"""
commands.py — LanguageNut Command Centre

Contains all bot commands accessible via /hub dashboard buttons
or individual slash commands. No admin/teacher commands included.
"""

import asyncio
import json
import logging
import random
import time
import traceback
from datetime import datetime, timedelta, timezone
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

# Language options (languageCode -> display name)
LANGUAGES = {
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "it": "Italian",
    "en": "English",
    "zh": "Mandarin Chinese",
    "ar": "Arabic",
    "ja": "Japanese",
    "ko": "Korean",
    "pt": "Portuguese",
    "ru": "Russian",
    "nl": "Dutch",
    "pl": "Polish",
    "sv": "Swedish",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "el": "Greek",
    "he": "Hebrew",
    "hi": "Hindi",
    "th": "Thai",
    "cy": "Welsh",
    "ga": "Irish",
    "gd": "Scottish Gaelic",
    "mt": "Maltese",
    "ro": "Romanian",
    "hu": "Hungarian",
    "cs": "Czech",
    "sk": "Slovak",
    "sl": "Slovenian",
    "hr": "Croatian",
    "sr": "Serbian",
    "bg": "Bulgarian",
    "uk": "Ukrainian",
    "et": "Estonian",
    "lv": "Latvian",
    "lt": "Lithuanian",
}

# XP targets for quick select
XP_QUICK_OPTIONS = [500, 1000, 2500, 5000, 10000, 25000, 50000]


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
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _check_account_banned(client: LanguagenutClient, token: str) -> dict:
    """
    Check if an account is banned/suspended by probing endpoints.

    Returns:
      banned: bool
      status: str (banned, suspended, rate_limited, active, unknown)
      error_message: str or None
      unban_timestamp: datetime or None
      unban_in: str or None
    """
    result = {
        "banned": False,
        "status": "active",
        "error_message": None,
        "unban_timestamp": None,
        "unban_in": None,
    }

    try:
        test = client.call_lnut("assignmentController/getViewableAll", {"token": token})
        if isinstance(test, dict) and test.get("error"):
            status_code = test.get("status", 0)
            body = test.get("body", {})
            err_msg = ""
            if isinstance(body, dict):
                err_msg = str(body.get("message", body.get("error", "")))
            elif isinstance(body, str):
                err_msg = body

            if status_code in (401, 403):
                ban_keywords = ["banned", "suspended", "disabled", "terminated",
                                "blocked", "locked", "deactivated"]
                if any(k in err_msg.lower() for k in ban_keywords):
                    result["banned"] = True
                    result["status"] = "banned"
                    result["error_message"] = err_msg or "Account has been banned/suspended"
                else:
                    result["banned"] = True
                    result["status"] = "suspended"
                    result["error_message"] = err_msg or "Access denied (401/403)"
            elif status_code == 429:
                result["status"] = "rate_limited"
                result["error_message"] = err_msg or "Rate limited by LanguageNut"
            elif status_code >= 500:
                result["status"] = "error"
                result["error_message"] = err_msg or f"Server error ({status_code})"
            else:
                result["status"] = "error"
                result["error_message"] = err_msg or f"Unknown error (code {status_code})"

            if isinstance(body, dict):
                unban_time = body.get("unbanAt") or body.get("unban_at") or body.get("suspendedUntil")
                if unban_time:
                    try:
                        if isinstance(unban_time, (int, float)):
                            ts = datetime.fromtimestamp(unban_time, tz=timezone.utc)
                        else:
                            ts = datetime.fromisoformat(unban_time.replace("Z", "+00:00"))
                        result["unban_timestamp"] = ts
                        remaining = ts - datetime.now(timezone.utc)
                        if remaining.total_seconds() > 0:
                            days = remaining.days
                            hours, rem = divmod(remaining.seconds, 3600)
                            minutes, _ = divmod(rem, 60)
                            parts = []
                            if days > 0: parts.append(f"{days}d")
                            if hours > 0: parts.append(f"{hours}h")
                            if minutes > 0: parts.append(f"{minutes}m")
                            result["unban_in"] = " ".join(parts) if parts else "Less than 1 minute"
                        else:
                            result["unban_in"] = "Any minute now"
                    except (ValueError, TypeError):
                        pass
            return result
    except Exception as e:
        result["status"] = "error"
        result["error_message"] = str(e)[:200]
        return result

    try:
        stats = client.call_lnut("stats/get", {"token": token})
        if isinstance(stats, dict) and not stats.get("error"):
            result["status"] = "active"
            result["banned"] = False
        else:
            result["status"] = "degraded"
            result["error_message"] = "Stats endpoint unavailable, limited access"
    except Exception:
        result["status"] = "active"

    return result


def _get_language_emoji(code: str) -> str:
    """Get a flag emoji for a language code."""
    flags = {
        "fr": "\U0001F1EB\U0001F1F7", "es": "\U0001F1EA\U0001F1F8", "de": "\U0001F1E9\U0001F1EA",
        "it": "\U0001F1EE\U0001F1F9", "en": "\U0001F1EC\U0001F1E7", "zh": "\U0001F1E8\U0001F1F3",
        "ar": "\U0001F1E6\U0001F1F7", "ja": "\U0001F1EF\U0001F1F5", "ko": "\U0001F1F0\U0001F1F7",
        "pt": "\U0001F1E7\U0001F1F7", "ru": "\U0001F1F7\U0001F1FA", "nl": "\U0001F1F3\U0001F1F1",
        "pl": "\U0001F1F5\U0001F1F1", "sv": "\U0001F1F8\U0001F1EA",
    }
    return flags.get(code, "\U0001F30D")


# ══════════════════════════════════════════════════════════════════════════════
#  MODALS
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


class XPModal(discord.ui.Modal, title="XP Target"):
    """Modal for entering a custom XP target amount."""
    xp_target = discord.ui.TextInput(
        label="XP Target",
        placeholder="Enter amount (e.g. 5000)",
        default="5000",
        min_length=1,
        max_length=8,
    )

    def __init__(self, user_id: int, language_code: str, topic: str):
        super().__init__()
        self.user_id = user_id
        self.language_code = language_code
        self.topic = topic

    async def on_submit(self, interaction: Interaction):
        try:
            xp = int(self.xp_target.value.strip())
            if xp < 100:
                raise ValueError("Minimum 100 XP")
            if xp > 999999:
                raise ValueError("Maximum 999,999 XP")
        except ValueError as e:
            embed = discord.Embed(title="Invalid XP Target", description=str(e), colour=RED)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Store the farm config in sessions and launch
        sess = get_session(self.user_id)
        sess["farm_config"] = {
            "language": self.language_code,
            "topic": self.topic,
            "xp_target": xp,
        }

        await interaction.response.defer(ephemeral=True)
        await _execute_farm(interaction, self.user_id, self.language_code, self.topic, xp, interaction.followup)


# ══════════════════════════════════════════════════════════════════════════════
#  FARM EXECUTION
# ══════════════════════════════════════════════════════════════════════════════

async def _execute_farm(
    interaction_or_ctx: Any,
    user_id: int,
    language_code: str,
    topic: str,
    xp_target: int,
    followup: Any,
):
    """Core farm execution — finds tasks for the given language/topic and grinds XP."""

    sess = get_session(user_id)
    token = sess.get("token")
    if not token:
        embed = discord.Embed(title="Not Logged In", colour=RED)
        return await followup.send(embed=embed, ephemeral=True)

    client = LanguagenutClient()
    client.token = token

    # Health check
    health = _check_account_banned(client, token)
    if health["banned"]:
        embed = discord.Embed(
            title="❌ Cannot Farm — Account Banned",
            description=health.get("error_message", "Account is banned/suspended"),
            colour=RED
        )
        if health["unban_in"]:
            embed.add_field(name="Unban Countdown", value=health["unban_in"])
        return await followup.send(embed=embed, ephemeral=True)

    # Discover tasks
    discoverer = HomeworkDiscoverer(client)
    try:
        all_homeworks = await discoverer.get_all_homeworks(token)
    except Exception as e:
        embed = discord.Embed(title="Error fetching homeworks", description=str(e)[:200], colour=RED)
        return await followup.send(embed=embed, ephemeral=True)

    # Filter by language
    lang_homeworks = [hw for hw in all_homeworks if hw.get("languageCode", "").lower() == language_code.lower()]

    if not lang_homeworks:
        lang_display = LANGUAGES.get(language_code, language_code.upper())
        embed = discord.Embed(
            title="No Homeworks Found",
            description=f"No homeworks for **{_get_language_emoji(language_code)} {lang_display}**",
            colour=AMBER
        )
        return await followup.send(embed=embed, ephemeral=True)

    # Collect all incomplete tasks, tracking which homework they belong to
    all_incomplete: List[tuple[dict, dict]] = []  # (homework, task)
    for hw in lang_homeworks:
        for task in hw.get("tasks", []):
            if not _is_done(task):
                all_incomplete.append((hw, task))

    if not all_incomplete:
        lang_display = LANGUAGES.get(language_code, language_code.upper())
        embed = discord.Embed(
            title="No Incomplete Tasks",
            description=f"All tasks completed for **{_get_language_emoji(language_code)} {lang_display}**!",
            colour=GREEN
        )
        return await followup.send(embed=embed, ephemeral=True)

    # Filter by topic if specified
    if topic and topic.lower() != "all":
        topic_lower = topic.lower()
        filtered: List[tuple[dict, dict]] = []
        for hw, task in all_incomplete:
            hw_name = (hw.get("name") or "").lower()
            task_name = (task.get("translation") or "").lower()
            task_module = (task.get("module_translation") or "").lower()
            verb_name = (task.get("verb_name") or "").lower()
            if topic_lower in hw_name or topic_lower in task_name or topic_lower in task_module or topic_lower in verb_name:
                filtered.append((hw, task))
        if filtered:
            all_incomplete = filtered
        else:
            # Topic filter matched nothing — just use all tasks
            pass

    if not all_incomplete:
        embed = discord.Embed(title="No Tasks Match", description="No incomplete tasks match your filters.", colour=AMBER)
        return await followup.send(embed=embed, ephemeral=True)

    total = len(all_incomplete)
    done = 0
    failed = 0
    total_xp = 0
    stealth = StealthManager()

    lang_display = LANGUAGES.get(language_code, language_code.upper())
    embed = discord.Embed(
        title=f"{_get_language_emoji(language_code)} Farming {lang_display}",
        description=f"Target: **{xp_target:,} XP**\nTasks found: **{total}**\nStarting...",
        colour=AMBER
    )
    msg = await followup.send(embed=embed, ephemeral=True)

    for i, (hw, task) in enumerate(all_incomplete):
        if total_xp >= xp_target:
            break

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
                status = result.get("status", 0)
                if status in (401, 403):
                    embed = discord.Embed(
                        title="❌ Farming Stopped — Account Banned",
                        description="Account was banned during farming",
                        colour=RED
                    )
                    await msg.edit(embed=embed)
                    return
                failed += 1
            else:
                done += 1
                this_xp = num_items * 200
                total_xp += this_xp

        except Exception:
            failed += 1

        if (i + 1) % 3 == 0 or i == total - 1 or total_xp >= xp_target:
            pct = min(100, int(total_xp / xp_target * 100)) if xp_target else 0
            embed.description = (
                f"Progress: `{done}/{total}` tasks | `{total_xp:,}/{xp_target:,}` XP\n"
                f"Failed: `{failed}`"
            )
            embed.set_footer(text=f"{pct}% of target")
            await msg.edit(embed=embed)

        await asyncio.sleep(stealth.delay_between_tasks())

    embed.colour = GREEN if total_xp >= xp_target else AMBER
    embed.description = (
        f"**Complete!** `{done}/{total}` tasks\n"
        f"XP earned: **{total_xp:,}** / {xp_target:,}\n"
        f"Language: {_get_language_emoji(language_code)} {lang_display}"
    )
    if topic and topic.lower() != "all":
        embed.description += f"\nTopic: `{topic}`"
    if failed:
        embed.description += f"\nFailed: `{failed}`"
        embed.colour = AMBER
    await msg.edit(embed=embed)


# ══════════════════════════════════════════════════════════════════════════════
#  SELECT MENUS
# ══════════════════════════════════════════════════════════════════════════════

class LanguageSelect(discord.ui.Select):
    """Select a language for farming."""

    def __init__(self, user_id: int):
        self._user_id = user_id
        options = []
        for code, name in sorted(LANGUAGES.items(), key=lambda x: x[1]):
            flag = _get_language_emoji(code)
            options.append(
                discord.SelectOption(
                    label=name,
                    value=code,
                    description=f"Farm tasks in {name}",
                    emoji=flag,
                )
            )
        super().__init__(
            placeholder="Choose a language...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: Interaction):
        lang_code = self.values[0]
        lang_name = LANGUAGES.get(lang_code, lang_code.upper())

        # Store chosen language in session
        sess = get_session(self._user_id)
        sess["farm_language"] = lang_code

        # Get topics for this language from their homeworks
        token = sess.get("token")
        topics = ["All"]
        if token:
            try:
                client = LanguagenutClient()
                client.token = token
                discoverer = HomeworkDiscoverer(client)
                homeworks = await discoverer.get_all_homeworks(token)
                # Get unique homework names for this language
                seen = set()
                for hw in homeworks:
                    if hw.get("languageCode", "").lower() == lang_code.lower():
                        name = hw.get("name", "").strip()
                        if name and name.lower() not in seen:
                            topics.append(name)
                            seen.add(name.lower())
                        # Also grab task translations as topics
                        for t in hw.get("tasks", []):
                            tname = t.get("translation", "").strip()
                            if tname and tname.lower() not in seen:
                                topics.append(tname)
                                seen.add(tname.lower())

                topics = topics[:25]  # Discord max 25 options
            except Exception:
                pass

        # Build topic selection view
        topic_view = discord.ui.View(timeout=120)
        topic_select = TopicSelect(self._user_id, lang_code, topics)
        topic_view.add_item(topic_select)

        embed = discord.Embed(
            title=f"{_get_language_emoji(lang_code)} {lang_name}",
            description="Select a topic to farm or choose **All** for everything:",
            colour=BLUE
        )

        await interaction.response.edit_message(embed=embed, view=topic_view)


class TopicSelect(discord.ui.Select):
    """Select a topic (homework name) within a language."""

    def __init__(self, user_id: int, language_code: str, topics: list):
        self._user_id = user_id
        self._language_code = language_code
        options = []
        for topic in topics[:25]:
            label = topic if len(topic) <= 100 else topic[:97] + "..."
            desc = "All available tasks" if topic == "All" else f"Tasks in {topic}"
            options.append(
                discord.SelectOption(
                    label=label,
                    value=topic,
                    description=desc,
                    emoji="\U0001F4CB" if topic == "All" else "\U0001F4D6",
                )
            )
        super().__init__(
            placeholder="Choose a topic...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: Interaction):
        topic = self.values[0]
        self._topic = topic

        # XP selection view
        xp_view = discord.ui.View(timeout=120)
        xp_select = XPSelect(self._user_id, self._language_code, topic)
        xp_view.add_item(xp_select)

        lang_name = LANGUAGES.get(self._language_code, self._language_code.upper())
        topic_display = "All Topics" if topic == "All" else topic

        embed = discord.Embed(
            title=f"{_get_language_emoji(self._language_code)} {lang_name} — {topic_display}",
            description="Select an XP target or choose **Custom** to enter your own amount:",
            colour=AMBER
        )

        await interaction.response.edit_message(embed=embed, view=xp_view)


class XPSelect(discord.ui.Select):
    """Select an XP target amount."""

    def __init__(self, user_id: int, language_code: str, topic: str):
        self._user_id = user_id
        self._language_code = language_code
        self._topic = topic
        options = [
            discord.SelectOption(label="Custom", value="custom", description="Enter your own XP amount", emoji="\u270F\uFE0F"),
        ]
        for xp in XP_QUICK_OPTIONS:
            label = f"{xp:,} XP"
            desc = f"Farm {xp:,} XP worth of tasks"
            options.append(
                discord.SelectOption(label=label, value=str(xp), description=desc, emoji="\u2B50")
            )
        super().__init__(
            placeholder="Choose XP target...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: Interaction):
        value = self.values[0]
        if value == "custom":
            modal = XPModal(self._user_id, self._language_code, self._topic)
            await interaction.response.send_modal(modal)
        else:
            xp_target = int(value)
            await interaction.response.defer(ephemeral=True)
            await _execute_farm(
                interaction,
                self._user_id,
                self._language_code,
                self._topic,
                xp_target,
                interaction.followup,
            )


# ══════════════════════════════════════════════════════════════════════════════
#  BUTTONS
# ══════════════════════════════════════════════════════════════════════════════

class LoginButton(discord.ui.Button):
    def __init__(self, user_id: int, logged_in: bool = False):
        label = "Logged In ✅" if logged_in else "Login"
        style = discord.ButtonStyle.success if logged_in else discord.ButtonStyle.primary
        super().__init__(style=style, label=label, disabled=logged_in)
        self.user_id = user_id

    async def callback(self, interaction: Interaction):
        modal = LoginModal(self.user_id)
        await interaction.response.send_modal(modal)


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

        # Show language selection
        view = discord.ui.View(timeout=120)
        view.add_item(LanguageSelect(self.user_id))

        embed = discord.Embed(
            title="🌾 Farm XP",
            description="Select a language to farm tasks for:",
            colour=AMBER
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


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
        embed.add_field(name="Tasks Done", value=data.get("tasks", "N/A"), inline=True)
        embed.add_field(name="Points", value=data.get("points", "N/A"), inline=True)
        embed.add_field(name="Username", value=sess.get("username", "N/A"), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)


class SettingsButton(discord.ui.Button):
    def __init__(self, user_id: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="⚙️ Settings", row=2)
        self.user_id = user_id

    async def callback(self, interaction: Interaction):
        settings = get_settings(self.user_id)
        embed = discord.Embed(title="Settings", colour=BLUE)
        embed.add_field(name="Stealth", value="Enabled" if settings.get("stealth_enabled") else "Disabled", inline=True)
        embed.add_field(name="Concurrency", value=f"`{settings.get('concurrency', 3)}`", inline=True)
        embed.add_field(name="Auto Retry", value="Yes" if settings.get("auto_retry") else "No", inline=True)
        embed.add_field(name="Min Accuracy", value=f"`{settings.get('min_accuracy', 85)}%`", inline=True)
        embed.add_field(name="Max Accuracy", value=f"`{settings.get('max_accuracy', 92)}%`", inline=True)
        embed.add_field(name="Speed", value=f"`{settings.get('speed', 10)}`", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AccountHealthButton(discord.ui.Button):
    def __init__(self, user_id: int):
        super().__init__(style=discord.ButtonStyle.danger, label="❤️ Account Health", row=2)
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

        health = _check_account_banned(client, token)

        if health["banned"]:
            embed = discord.Embed(title="❌ Account Banned", colour=RED)
            status_label = health.get("status", "banned").capitalize()
            err = health.get("error_message", "No details provided")
            embed.description = f"**Status:** {status_label}\n**Reason:** {err}"

            if health["unban_in"]:
                embed.add_field(name="⏳ Unban Countdown", value=f"**{health['unban_in']}** remaining", inline=False)
            if health["unban_timestamp"]:
                embed.add_field(
                    name="Unban ETA",
                    value=f"<t:{int(health['unban_timestamp'].timestamp())}:F>",
                    inline=False
                )
            embed.set_footer(text="Account cannot be used until unban")
            return await interaction.followup.send(embed=embed, ephemeral=True)

        try:
            stats = client.call_lnut("stats/get", {"token": token})
            profile = client.call_lnut("profile/get", {"token": token})
        except Exception as e:
            embed = discord.Embed(title="Error fetching health data", description=str(e)[:200], colour=RED)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        tasks_done = stats.get("tasks", 0) if isinstance(stats, dict) else 0
        points = stats.get("points", 0) if isinstance(stats, dict) else 0
        streak = profile.get("streak", 0) if isinstance(profile, dict) else 0
        accuracy = stats.get("accuracy", 0) if isinstance(stats, dict) else 0

        embed = discord.Embed(title="❤️ Account Health — ✅ Healthy", colour=GREEN)
        embed.add_field(name="Tasks Completed", value=f"`{tasks_done}`", inline=True)
        embed.add_field(name="Total Points", value=f"`{points:,}`", inline=True)
        embed.add_field(name="Streak", value=f"`{streak} days`", inline=True)
        embed.add_field(name="Accuracy", value=f"`{accuracy}%`", inline=True)

        warnings = []
        if tasks_done > 500:
            warnings.append("⚠️ High activity volume — consider lowering concurrency")
        if isinstance(accuracy, (int, float)) and accuracy > 95:
            warnings.append("⚠️ Accuracy too high (>95%) — may be flagged as automation")
        if isinstance(accuracy, (int, float)) and accuracy < 60 and tasks_done > 10:
            warnings.append("⚠️ Accuracy too low — may look like random guessing")

        if warnings:
            embed.add_field(name="Risk Factors", value="\n".join(warnings), inline=False)
        else:
            embed.add_field(name="Risk Level", value="✅ Low — account looks natural", inline=False)

        embed.set_footer(text=f"Checked for {sess.get('username', 'user')}")
        await interaction.followup.send(embed=embed, ephemeral=True)


class HelpButton(discord.ui.Button):
    def __init__(self, user_id: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="❓ Help / Tutorial", row=3)
        self.user_id = user_id

    async def callback(self, interaction: Interaction):
        embed = discord.Embed(
            title="LanguageNut Bot — Help & Tutorial",
            description="Welcome to the LanguageNut automation bot!",
            colour=BLUE
        )
        embed.add_field(
            name="🚀 Getting Started",
            value="1. Click **Login** and enter your LanguageNut credentials\n"
                   "2. Use **📋 Homeworks** to see your pending tasks\n"
                   "3. Click **🌾 Farm XP** → pick a language → pick a topic → set XP target\n"
                   "4. Check **📊 Status** and **❤️ Account Health** for stats",
            inline=False
        )
        embed.add_field(
            name="🌾 Farming XP",
            value="Click **Farm XP** → you'll be asked to:\n"
                   "1. **Select a language** (French, Spanish, German, etc.)\n"
                   "2. **Select a topic** (homework name) or choose **All**\n"
                   "3. **Set an XP target** — pick a quick amount or enter **Custom**\n"
                   "4. The bot will farm until the target is reached or tasks run out",
            inline=False
        )
        embed.add_field(
            name="📝 All Commands",
            value="`/hub` — Open the dashboard\n"
                   "`/login` — Login to LanguageNut\n"
                   "`/logout` — Logout\n"
                   "`/farm` — Start farming XP (language/topic/XP selection)\n"
                   "`/homeworks` — List your homeworks\n"
                   "`/status` — Check account stats\n"
                   "`/account-health` — Ban/health check with unban timer\n"
                   "`/leaderboard` — View the leaderboard",
            inline=False
        )
        embed.add_field(
            name="❤️ Account Health",
            value="The health check pings LanguageNut to see if your account is:\n"
                   "• **✅ Active** — All good, keep farming\n"
                   "• **⚠️ At risk** — Unusual activity detected, adjust stealth settings\n"
                   "• **❌ Banned/Suspended** — Shows unban countdown if LanguageNut provides one",
            inline=False
        )
        embed.set_footer(text="Buttons time out after 5 min — just re-run /hub")
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

        # Row 0: Auth
        if logged_in:
            self.add_item(LoginButton(self.user_id, logged_in=True))
        else:
            self.add_item(LoginButton(self.user_id, logged_in=False))
        if logged_in:
            self.add_item(LogoutButton(self.user_id))

        # Row 1: Actions
        self.add_item(FarmButton(self.user_id))
        self.add_item(HomeworkListButton(self.user_id))
        self.add_item(LeaderboardButton(self.user_id))

        # Row 2: Info & Health
        self.add_item(StatusButton(self.user_id))
        self.add_item(SettingsButton(self.user_id))
        self.add_item(AccountHealthButton(self.user_id))

        # Row 3: Help
        self.add_item(HelpButton(self.user_id))


# ══════════════════════════════════════════════════════════════════════════════
#  EMBED BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

def _build_dashboard_embed(user_id: int) -> discord.Embed:
    sess = get_session(user_id)
    logged_in = sess.get("token") is not None
    username = sess.get("username", "Not logged in")

    embed = discord.Embed(
        title="LanguageNut Command Centre",
        description="All bot features accessible from this panel",
        colour=PURPLE if logged_in else BLUE,
    )
    embed.add_field(name="Status", value="✅ Logged in" if logged_in else "❌ Not logged in", inline=True)
    embed.add_field(name="Account", value=f"`{username}`", inline=True)
    embed.set_footer(text="Buttons time out after 5 min • Press any button to interact")
    return embed


# ══════════════════════════════════════════════════════════════════════════════
#  COG
# ══════════════════════════════════════════════════════════════════════════════

class CommandCentre(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="hub",
        description="Open the LanguageNut Command Centre dashboard"
    )
    async def hub(self, interaction: Interaction):
        embed = _build_dashboard_embed(interaction.user.id)
        view = CommandCentreView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(
        name="dashboard",
        description="Open the LanguageNut Command Centre"
    )
    async def dashboard(self, interaction: Interaction):
        embed = _build_dashboard_embed(interaction.user.id)
        view = CommandCentreView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(
        name="login",
        description="Login to LanguageNut"
    )
    async def login(self, interaction: Interaction):
        sess = get_session(interaction.user.id)
        if sess.get("token"):
            embed = discord.Embed(title="Already Logged In", colour=GREEN)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        modal = LoginModal(interaction.user.id)
        await interaction.response.send_modal(modal)

    @app_commands.command(
        name="logout",
        description="Logout of LanguageNut"
    )
    async def logout(self, interaction: Interaction):
        sess = get_session(interaction.user.id)
        sess["token"] = None
        sess["username"] = None
        sess["uid"] = None
        embed = discord.Embed(title="Logged Out", colour=RED)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="status",
        description="Check your LanguageNut account stats"
    )
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
        embed = discord.Embed(title="Account Status", colour=BLUE)
        embed.add_field(name="Tasks Done", value=data.get("tasks", "N/A"), inline=True)
        embed.add_field(name="Points", value=data.get("points", "N/A"), inline=True)
        embed.add_field(name="Username", value=sess.get("username", "N/A"), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="farm",
        description="Farm XP — choose language, topic, and XP target"
    )
    async def farm(self, interaction: Interaction):
        sess = get_session(interaction.user.id)
        token = sess.get("token")
        if not token:
            embed = discord.Embed(title="Not Logged In", colour=RED)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # Show language selection
        view = discord.ui.View(timeout=120)
        view.add_item(LanguageSelect(interaction.user.id))

        embed = discord.Embed(
            title="🌾 Farm XP",
            description="Select a language to farm tasks for:",
            colour=AMBER
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(
        name="homeworks",
        description="List your LanguageNut homeworks"
    )
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

    @app_commands.command(
        name="leaderboard",
        description="View the LanguageNut leaderboard"
    )
    async def leaderboard(self, interaction: Interaction):
        sess = get_session(interaction.user.id)
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

    @app_commands.command(
        name="account-health",
        description="Check if your account is banned, at risk, or healthy with unban timer"
    )
    async def account_health(self, interaction: Interaction):
        sess = get_session(interaction.user.id)
        token = sess.get("token")
        if not token:
            embed = discord.Embed(title="Not Logged In", colour=RED)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        client = LanguagenutClient()
        client.token = token

        health = _check_account_banned(client, token)

        if health["banned"]:
            embed = discord.Embed(title="❌ Account Banned / Suspended", colour=RED)
            status_label = health.get("status", "banned").capitalize()
            err = health.get("error_message", "No details provided")
            embed.description = f"**Status:** {status_label}\n**Reason:** {err}"

            if health["unban_in"]:
                embed.add_field(name="⏳ Unban Countdown", value=f"**{health['unban_in']}** remaining", inline=False)
            if health["unban_timestamp"]:
                embed.add_field(
                    name="Unban ETA",
                    value=f"<t:{int(health['unban_timestamp'].timestamp())}:F>",
                    inline=False
                )
            embed.set_footer(text="Account cannot be used until the ban/suspension lifts")
            return await interaction.followup.send(embed=embed, ephemeral=True)

        try:
            stats = client.call_lnut("stats/get", {"token": token})
            profile = client.call_lnut("profile/get", {"token": token})
        except Exception as e:
            embed = discord.Embed(title="Error fetching health data", description=str(e)[:200], colour=RED)
            return await interaction.followup.send(embed=embed, ephemeral=True)

        tasks_done = stats.get("tasks", 0) if isinstance(stats, dict) else 0
        points = stats.get("points", 0) if isinstance(stats, dict) else 0
        streak = profile.get("streak", 0) if isinstance(profile, dict) else 0
        accuracy = stats.get("accuracy", 0) if isinstance(stats, dict) else 0

        embed = discord.Embed(title="❤️ Account Health — ✅ Healthy", colour=GREEN)
        embed.add_field(name="Tasks Completed", value=f"`{tasks_done}`", inline=True)
        embed.add_field(name="Total Points", value=f"`{points:,}`", inline=True)
        embed.add_field(name="Streak", value=f"`{streak} days`", inline=True)
        embed.add_field(name="Accuracy", value=f"`{accuracy}%`", inline=True)

        warnings = []
        if tasks_done > 500:
            warnings.append("⚠️ High activity volume — consider lowering concurrency in settings")
        if isinstance(accuracy, (int, float)) and accuracy > 95:
            warnings.append("⚠️ Accuracy too high (>95%) — LanguageNut may flag as automation")
        if isinstance(accuracy, (int, float)) and accuracy < 60 and tasks_done > 10:
            warnings.append("⚠️ Accuracy too low — may look like random guessing")

        if warnings:
            embed.add_field(name="Risk Factors", value="\n".join(warnings), inline=False)
        else:
            embed.add_field(name="Risk Level", value="✅ Low — account behaviour looks natural", inline=False)

        embed.set_footer(text=f"Checked for {sess.get('username', 'user')}")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandCentre(bot))