"""
LanguageNut bot - Unified Commands Module

Includes:
  User commands:
    /login /logout /homework /do /status /settings
  Admin (owner only):
    /restart /shutdown /update /sync /clear /logs /reload /eval /online /offline
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import subprocess
import sys
import time
import math
from typing import Any, Optional
import aiohttp

import discord
from discord import ButtonStyle, Interaction, app_commands, ui
from discord.ext import commands

import config
from automation.api_direct import LNApiClient
from automation.discover import HomeworkDiscoverer
from automation.stealth import StealthManager, seconds_to_human
from utils.encryption import decrypt_value, encrypt_value
from utils.helper import _pct, _is_done
from utils.logger import log_user_command, log_homework_action, fetch_user_logs, fetch_homework_logs, fetch_bot_logs

logger = logging.getLogger("lnut_bot.commands")

# Owner user id (admin commands)
OWNER_ID = 1453752725324955656

# Cache TTL (seconds)
HOMEWORK_CACHE_TTL = 20.0

# Autocomplete cache (shared across guilds)
AC_CACHE: dict[int, list[dict]] = {}  # guild_id -> homeworks
AC_CACHE_TTL = 30.0  # seconds
AC_CACHE_TIME: dict[int, float] = {}  # guild_id -> fetch timestamp

# ============================================================
# HELPERS
# ============================================================

def _progress_bar(pct: int, length: int = 10) -> str:
    filled = round(max(0, min(100, pct)) / (100 / length))
    return "█" * filled + "░" * (length - filled)

# ============================================================
# OWNER CHECK
# ============================================================
def owner_only():
    async def predicate(interaction: Interaction) -> bool:
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "🚫 Owner only command.", ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

# ============================================================
# SAFE SEND HELPER
# ============================================================
async def safe_send(
    interaction: Interaction,
    content: Optional[str] = None,
    *,
    embed: Optional[discord.Embed] = None,
    view: Optional[ui.View] = None,
    ephemeral: bool = True,
) -> None:
    kwargs: dict[str, Any] = {"ephemeral": ephemeral}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if view is not None:
        kwargs["view"] = view
    try:
        if interaction.response.is_done():
            await interaction.followup.send(**kwargs)
        else:
            await interaction.response.send_message(**kwargs)
    except discord.HTTPException as e:
        logger.error("Send failed: %s", e)

# ============================================================
# SETTINGS PANEL
# ============================================================
class SettingModal(ui.Modal):
    """
    Generic single-field modal for editing a setting.

    Validates that:
      - The raw value can be cast with `caster`
      - `validator(value)` returns True
      - For accuracy fields, min_accuracy <= max_accuracy is enforced
        after the change is applied.
    """

    def __init__(self, key, label, current, caster, validator, parent_view):
        super().__init__(title=f"Update {label}")
        self.key         = key
        self.caster      = caster
        self.validator   = validator
        self.parent_view = parent_view
        self.field = ui.TextInput(
            label=label,
            placeholder=f"Current: {current}",
            default=str(current),
            required=True,
            max_length=20,
        )
        self.add_item(self.field)

    async def on_submit(self, interaction: Interaction):
        raw = self.field.value.strip()
        try:
            value = self.caster(raw)
            if not self.validator(value):
                raise ValueError("Value out of allowed range.")
        except (ValueError, TypeError) as e:
            await safe_send(interaction, f"❌ Invalid value: {e}")
            return

        if interaction.guild_id is None:
            await safe_send(interaction, "❌ Guild only command.")
            return

        # Cross-field validation: keep min_accuracy <= max_accuracy
        if self.key in ("min_accuracy", "max_accuracy"):
            current_settings = config.get_guild_settings(interaction.guild_id)
            if self.key == "min_accuracy":
                max_acc = current_settings.get("max_accuracy", 100)
                if value > max_acc:
                    await safe_send(
                        interaction,
                        f"❌ Min accuracy ({value}%) cannot exceed max accuracy ({max_acc}%)."
                    )
                    return
            elif self.key == "max_accuracy":
                min_acc = current_settings.get("min_accuracy", 0)
                if value < min_acc:
                    await safe_send(
                        interaction,
                        f"❌ Max accuracy ({value}%) cannot be less than min accuracy ({min_acc}%)."
                    )
                    return

        config.set_guild_setting(interaction.guild_id, self.key, value)
        embed = self.parent_view.build_embed(interaction.guild_id)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)

class SettingsView(ui.View):
    """
    Interactive settings panel.

    Displays all configurable options and provides buttons to edit them.
    Settings are saved immediately on change.
    """

    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id

    def build_embed(self, guild_id: int) -> discord.Embed:
        s          = config.get_guild_settings(guild_id)

        embed = discord.Embed(
            title="⚙️ LanguageNut Bot Settings",
            description=(
                "Configure automation behaviour.\n"
                "Changes are saved immediately and apply to all future tasks."
            ),
            color=discord.Color.blurple(),
        )

# Per-Question Timing
        from automation.stealth import StealthManager
        display = StealthManager(
            min_seconds_per_question=s["min_seconds_per_question"],
            max_seconds_per_question=s["max_seconds_per_question"],
        ).speed_display()
        embed.add_field(
            name="Time Per Question",
            value=f"{display}",
            inline=True,
        )
        embed.add_field(name="​", value="​", inline=True)
        # ── Accuracy ──────────────────────────────────────────────────────
        acc_bar = _progress_bar(
            round((s["min_accuracy"] + s["max_accuracy"]) / 2), length=10
        )
        embed.add_field(
            name="🎯 Accuracy Range",
            value=(
                f"`{s['min_accuracy']}%` – `{s['max_accuracy']}%`\n"
                f"`{acc_bar}` avg {round((s['min_accuracy'] + s['max_accuracy']) / 2)}%"
            ),
            inline=True,
        )

        # ── Concurrency & retry ───────────────────────────────────────────
        embed.add_field(
            name="⚡ Concurrency",
            value=f"`{s['concurrency']}` parallel tasks",
            inline=True,
        )
        embed.add_field(
            name="🔁 Auto Retry",
            value=f"`{'ON' if s['auto_retry'] else 'OFF'}` ({s['retry_attempts']}×)",
            inline=True,
        )

        # ── Stealth ───────────────────────────────────────────────────────
        embed.add_field(
            name="🛡️ Stealth",
            value="`ON`" if s["stealth_enabled"] else "`OFF`",
            inline=True,
        )

        embed.set_footer(text="Changes apply immediately to all future tasks.")
        return embed

    # ── Timing buttons ────────────────────────────────────────────────────
    @ui.button(label="⏱️ Speed", style=ButtonStyle.primary, row=0)
    async def speed_btn(self, interaction: Interaction, _: ui.Button):
        s = config.get_guild_settings(interaction.guild_id)
        await interaction.response.send_modal(
            SettingModal(
                "speed", "Seconds per task (3–3600)",
                s["speed"], float, lambda v: 3.0 <= v <= 3600.0, self,
            )
        )

    @ui.button(label="Time Per-Q Min", style=ButtonStyle.primary, row=0)
    async def min_sec_q_btn(self, interaction: Interaction, _: ui.Button):
        s = config.get_guild_settings(interaction.guild_id)
        await interaction.response.send_modal(
            SettingModal(
                "min_seconds_per_question", "Min seconds per question (1-300)",
                s["min_seconds_per_question"], float,
                lambda v: 1.0 <= v <= 300.0, self,
            )
        )

    @ui.button(label="Time Per-Q Max", style=ButtonStyle.primary, row=0)
    async def max_sec_q_btn(self, interaction: Interaction, _: ui.Button):
        s = config.get_guild_settings(interaction.guild_id)
        await interaction.response.send_modal(
            SettingModal(
                "max_seconds_per_question", "Max seconds per question (1-300)",
                s["max_seconds_per_question"], float,
                lambda v: 1.0 <= v <= 300.0, self,
            )
        )
    @ui.button(label="🎯 Min Accuracy", style=ButtonStyle.primary, row=1)
    async def min_acc_btn(self, interaction: Interaction, _: ui.Button):
        s = config.get_guild_settings(interaction.guild_id)
        await interaction.response.send_modal(
            SettingModal(
                "min_accuracy", "Min accuracy % (0–100)",
                s["min_accuracy"], int, lambda v: 0 <= v <= 100, self,
            )
        )

    @ui.button(label="🎯 Max Accuracy", style=ButtonStyle.primary, row=1)
    async def max_acc_btn(self, interaction: Interaction, _: ui.Button):
        s = config.get_guild_settings(interaction.guild_id)
        await interaction.response.send_modal(
            SettingModal(
                "max_accuracy", "Max accuracy % (0–100)",
                s["max_accuracy"], int, lambda v: 0 <= v <= 100, self,
            )
        )

    # ── Concurrency & retry buttons ───────────────────────────────────────
    @ui.button(label="⚡ Concurrency", style=ButtonStyle.success, row=2)
    async def conc_btn(self, interaction: Interaction, _: ui.Button):
        s = config.get_guild_settings(interaction.guild_id)
        await interaction.response.send_modal(
            SettingModal(
                "concurrency", "Parallel tasks (1–8)",
                s["concurrency"], int, lambda v: 1 <= v <= 8, self,
            )
        )

    @ui.button(label="🔁 Retry Attempts", style=ButtonStyle.success, row=2)
    async def retry_btn(self, interaction: Interaction, _: ui.Button):
        s = config.get_guild_settings(interaction.guild_id)
        await interaction.response.send_modal(
            SettingModal(
                "retry_attempts", "Retry attempts (0–5)",
                s["retry_attempts"], int, lambda v: 0 <= v <= 5, self,
            )
        )

    # ── Toggle buttons ────────────────────────────────────────────────────
    @ui.button(label="🛡️ Toggle Stealth", style=ButtonStyle.secondary, row=3)
    async def stealth_btn(self, interaction: Interaction, _: ui.Button):
        if interaction.guild_id is None:
            await safe_send(interaction, "❌ Guild only.")
            return
        s = config.get_guild_settings(interaction.guild_id)
        config.set_guild_setting(interaction.guild_id, "stealth_enabled", not s["stealth_enabled"])
        await interaction.response.edit_message(embed=self.build_embed(interaction.guild_id), view=self)

    @ui.button(label="🔁 Toggle Auto-Retry", style=ButtonStyle.secondary, row=3)
    async def autoretry_btn(self, interaction: Interaction, _: ui.Button):
        if interaction.guild_id is None:
            await safe_send(interaction, "❌ Guild only.")
            return
        s = config.get_guild_settings(interaction.guild_id)
        config.set_guild_setting(interaction.guild_id, "auto_retry", not s["auto_retry"])
        await interaction.response.edit_message(embed=self.build_embed(interaction.guild_id), view=self)

    # ── Reset / Close ─────────────────────────────────────────────────────
    @ui.button(label="♻️ Reset Defaults", style=ButtonStyle.danger, row=4)
    async def reset_btn(self, interaction: Interaction, _: ui.Button):
        if interaction.guild_id is None:
            await safe_send(interaction, "❌ Guild only.")
            return
        config.reset_guild_settings(interaction.guild_id)
        await interaction.response.edit_message(embed=self.build_embed(interaction.guild_id), view=self)

    @ui.button(label="✖ Close", style=ButtonStyle.danger, row=4)
    async def close_btn(self, interaction: Interaction, _: ui.Button):
        await interaction.response.edit_message(content="Settings closed.", embed=None, view=None)

# ============================================================
# HOMEWORK PAGINATOR
# ============================================================
class HomeworkPaginator(ui.View):
    PER_PAGE = 4

    def __init__(self, homeworks: list[dict], user_id: int):
        super().__init__(timeout=300)
        self.homeworks    = homeworks
        self.user_id      = user_id
        self.page         = 0
        self.total_pages  = max(1, (len(homeworks) + self.PER_PAGE - 1) // self.PER_PAGE)
        self._update_button_state()

    def _update_button_state(self):
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= self.total_pages - 1

    def build_embed(self) -> discord.Embed:
        start = self.page * self.PER_PAGE
        chunk = self.homeworks[start:start + self.PER_PAGE]

        total_tasks    = sum(len(hw.get("tasks", [])) for hw in self.homeworks)
        total_done     = sum(1 for hw in self.homeworks for t in hw.get("tasks", []) if _is_done(t))
        incomplete_cnt = total_tasks - total_done

        embed = discord.Embed(
            title="📚 LanguageNut Homework",
            description=(
                f"**{len(self.homeworks)}** assignment(s) • "
                f"**{total_tasks}** total tasks • "
                f"**{incomplete_cnt}** incomplete"
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(
            text=f"Page {self.page + 1}/{self.total_pages}  •  Use /do to complete tasks"
        )

        for hw in chunk:
            name    = hw.get("name", "Unnamed")
            hw_id   = hw.get("id", "?")
            tasks   = hw.get("tasks", [])
            total   = len(tasks)
            done    = sum(1 for t in tasks if _is_done(t))
            pct_all = round((done / total * 100) if total else 0)
            bar     = _progress_bar(pct_all)

            lines = [f"`{bar}` **{pct_all}%** ({done}/{total} done)"]
            incomplete_tasks = [t for t in tasks if not _is_done(t)]
            for task in incomplete_tasks[:5]:
                p         = _pct(task)
                task_name = task.get("translation", "Unknown")
                if len(task_name) > 38:
                    task_name = task_name[:35] + "..."
                lines.append(f"  ↳ `{p}%` {task_name}")
            if len(incomplete_tasks) > 5:
                lines.append(f"  ↳ *…and {len(incomplete_tasks) - 5} more incomplete*")

            value = "\n".join(lines)
            if len(value) > 1024:
                value = value[:1020] + "..."
            embed.add_field(name=f"📖 {name[:180]}  `#{hw_id}`", value=value, inline=False)

        return embed

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This menu isn't for you.", ephemeral=True)
            return False
        return True

    @ui.button(label="◀ Prev", style=ButtonStyle.secondary)
    async def prev_btn(self, interaction: Interaction, _: ui.Button):
        self.page = max(0, self.page - 1)
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @ui.button(label="Next ▶", style=ButtonStyle.secondary)
    async def next_btn(self, interaction: Interaction, _: ui.Button):
        self.page = min(self.total_pages - 1, self.page + 1)
        self._update_button_state()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @ui.button(label="✖ Close", style=ButtonStyle.danger)
    async def close_btn(self, interaction: Interaction, _: ui.Button):
        await interaction.response.edit_message(content="Closed.", embed=None, view=None)

# ============================================================
# /do — STEP 1: Homework selector
# ============================================================
class HomeworkSelect(ui.Select):
    def __init__(self, homeworks: list[dict]):
        self.homeworks = homeworks
        options: list[discord.SelectOption] = [
            discord.SelectOption(
                label="⚡ Do ALL incomplete tasks",
                value="__ALL__",
                description="Run every incomplete task across all assignments",
                emoji="⚡",
            )
        ]
        for hw in homeworks[:24]:
            hw_id      = str(hw.get("id", "?"))
            name       = hw.get("name", "Unnamed")
            tasks      = hw.get("tasks", [])
            incomplete = [t for t in tasks if not _is_done(t)]
            if not incomplete:
                continue
            total = len(tasks)
            done  = total - len(incomplete)
            pct   = round((done / total * 100) if total else 0)
            label = name[:95] if len(name) <= 95 else name[:92] + "..."
            options.append(
                discord.SelectOption(
                    label=label,
                    value=hw_id,
                    description=f"{pct}% done • {len(incomplete)} task(s) remaining"[:100],
                    emoji="📖",
                )
            )
        if len(options) == 1:
            options = [
                discord.SelectOption(
                    label="No incomplete homework",
                    value="__NONE__",
                    description="All tasks are at 100%",
                )
            ]

        super().__init__(
            placeholder="📚 Select a homework assignment…",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: Interaction):
        view: DoHomeworkView = self.view  # type: ignore
        chosen = self.values[0]

        if chosen == "__NONE__":
            await interaction.response.edit_message(
                content="✅ All homework is already at 100%!", embed=None, view=None
            )
            return

        if chosen == "__ALL__":
            jobs = [
                (hw, t)
                for hw in self.homeworks
                for t in hw.get("tasks", [])
                if not _is_done(t)
            ]
            if not jobs:
                await interaction.response.edit_message(
                    content="✅ Nothing left to do!", embed=None, view=None
                )
                return
            await interaction.response.edit_message(
                content=f"⏳ Starting **{len(jobs)}** task(s) across all assignments…",
                embed=None,
                view=None,
            )
            asyncio.create_task(
                _execute_jobs(interaction.followup, jobs, view.cog, view.guild_id, user_id=view.user_id)
            )
            return

        # Single homework selected — find by id string match
        target_hw = next(
            (h for h in self.homeworks if str(h.get("id", "")) == chosen), None
        )
        if not target_hw:
            await interaction.response.edit_message(
                content="❌ Homework not found.", embed=None, view=None
            )
            return

        task_view = DoTaskView(target_hw, view.cog, view.guild_id, view.user_id)
        await interaction.response.edit_message(
            content=None, embed=task_view.build_embed(), view=task_view
        )

class DoHomeworkView(ui.View):
    def __init__(
        self,
        homeworks: list[dict],
        cog: "BotCommands",
        guild_id: int,
        user_id: int,
    ):
        super().__init__(timeout=180)
        self.homeworks = homeworks
        self.cog       = cog
        self.guild_id  = guild_id
        self.user_id   = user_id
        self.add_item(HomeworkSelect(homeworks))

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This menu isn't for you.", ephemeral=True)
            return False
        return True

    @ui.button(label="✖ Cancel", style=ButtonStyle.danger, row=1)
    async def cancel_btn(self, interaction: Interaction, _: ui.Button):
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)

# ============================================================
# /do — STEP 2: Task multi-selector
# ============================================================
class TaskSelect(ui.Select):
    """
    Select individual tasks within a homework assignment.

    Task values are stored as their list index (str) so we can look them
    up directly with `tasks[int(val)]` — this is the correct approach
    mirroring the JS `c.id.split("-")` → `homeworks[parts[0]].tasks[parts[1]]`.
    """

    def __init__(self, homework: dict):
        self.homework = homework
        tasks      = homework.get("tasks", [])
        # Build (original_index, task) pairs for incomplete tasks only
        incomplete = [(i, t) for i, t in enumerate(tasks) if not _is_done(t)]

        options: list[discord.SelectOption] = [
            discord.SelectOption(
                label="⚡ Do ALL tasks in this assignment",
                value="__ALL__",
                description="Complete every incomplete task here",
                emoji="⚡",
            )
        ]
        for idx, task in incomplete[:24]:
            p         = _pct(task)
            task_name = task.get("translation", "Unknown")
            label     = task_name[:95] if len(task_name) <= 95 else task_name[:92] + "..."
            options.append(
                discord.SelectOption(
                    label=label,
                    # Store the REAL list index so tasks[int(val)] works correctly
                    value=str(idx),
                    description=f"{p}% complete",
                    emoji="📝",
                )
            )

        super().__init__(
            placeholder="📝 Select task(s) to complete…",
            min_values=1,
            max_values=min(len(options), 25),
            options=options,
        )

    async def callback(self, interaction: Interaction):
        view: DoTaskView = self.view  # type: ignore
        tasks  = self.homework.get("tasks", [])
        chosen = self.values

        if "__ALL__" in chosen:
            jobs = [(self.homework, t) for t in tasks if not _is_done(t)]
        else:
            jobs = []
            for val in chosen:
                try:
                    idx = int(val)
                    if 0 <= idx < len(tasks):
                        jobs.append((self.homework, tasks[idx]))
                    else:
                        logger.warning("Task index %d out of range (len=%d)", idx, len(tasks))
                except ValueError:
                    logger.warning("Non-integer task value in select: %r", val)

        if not jobs:
            await interaction.response.edit_message(
                content="❌ No valid tasks selected.", embed=None, view=None
            )
            return

        await interaction.response.edit_message(
            content=f"⏳ Starting **{len(jobs)}** task(s)…",
            embed=None,
            view=None,
        )
        asyncio.create_task(
            _execute_jobs(interaction.followup, jobs, view.cog, view.guild_id, user_id=view.user_id)
        )

class DoTaskView(ui.View):
    def __init__(
        self,
        homework: dict,
        cog: "BotCommands",
        guild_id: int,
        user_id: int,
    ):
        super().__init__(timeout=180)
        self.homework  = homework
        self.cog       = cog
        self.guild_id  = guild_id
        self.user_id   = user_id
        self.add_item(TaskSelect(homework))

    def build_embed(self) -> discord.Embed:
        hw      = self.homework
        name    = hw.get("name", "Unnamed")
        tasks   = hw.get("tasks", [])
        total   = len(tasks)
        done    = sum(1 for t in tasks if _is_done(t))
        pct_all = round((done / total * 100) if total else 0)
        bar     = _progress_bar(pct_all)

        embed = discord.Embed(
            title=f"📖 {name}",
            description=(
                f"`{bar}` **{pct_all}%** complete ({done}/{total} tasks done)\n\n"
                "Select which tasks to complete below."
            ),
            color=discord.Color.orange(),
        )
        incomplete = [t for t in tasks if not _is_done(t)]
        if incomplete:
            lines = []
            for task in incomplete[:10]:
                p         = _pct(task)
                task_name = task.get("translation", "Unknown")
                if len(task_name) > 40:
                    task_name = task_name[:37] + "..."
                lines.append(f"📝 `{p}%` — {task_name}")
            if len(incomplete) > 10:
                lines.append(f"*…and {len(incomplete) - 10} more*")
            embed.add_field(
                name=f"📋 Incomplete Tasks ({len(incomplete)})",
                value="\n".join(lines),
                inline=False,
            )
        embed.set_footer(text="Pick one or many tasks, or choose 'Do ALL' to complete everything.")
        return embed

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This menu isn't for you.", ephemeral=True)
            return False
        return True

    @ui.button(label="◀ Back", style=ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: Interaction, _: ui.Button):
        cached         = self.cog._hw_cache.get(self.guild_id, (0, []))[1]
        incomplete_hws = [hw for hw in cached if any(not _is_done(t) for t in hw.get("tasks", []))]
        view           = DoHomeworkView(incomplete_hws or cached, self.cog, self.guild_id, self.user_id)
        embed          = discord.Embed(
            title="📚 Select a Homework",
            description="Choose an assignment to work on.",
            color=discord.Color.blue(),
        )
        await interaction.response.edit_message(content=None, embed=embed, view=view)

    @ui.button(label="✖ Cancel", style=ButtonStyle.danger, row=1)
    async def cancel_btn(self, interaction: Interaction, _: ui.Button):
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)

# ============================================================
# SHARED JOB EXECUTOR
# ============================================================
async def _execute_jobs(
    followup: Any,
    jobs: list[tuple[dict, dict]],
    cog: "BotCommands",
    guild_id: int,
    user_id: int = 0,
) -> None:
    """
    Run (homework, task) jobs concurrently and post a result embed via followup.

    Uses an asyncio Semaphore to cap concurrency at the guild's setting,
    mirroring the JS asyncPool(funcs, 5) pattern.
    If user_id is provided, homework completion is logged to user analytics.
    """
    client = await cog._get_api_client(guild_id)
    if not client:
        try:
            await followup.send("❌ Not logged in. Use `/login` first.", ephemeral=True)
        except Exception:
            pass
        return

    settings    = config.get_guild_settings(guild_id)
    concurrency = max(1, min(settings["concurrency"], 8))
    sem         = asyncio.Semaphore(concurrency)

    async def run_one(hw: dict, t_obj: dict) -> tuple[str, str, bool, str]:
        hw_name   = hw.get("name", "Unnamed")
        task_name = t_obj.get("translation", "Unknown")
        game_link = t_obj.get("gameLink", "")
        to_lang   = hw.get("languageCode", "")

        async with sem:
            client.stealth.sync_settings(guild_id)
            attempt = 0
            while True:
                attempt += 1
                try:
                    data = await client.fetch_task_data(t_obj, game_link, to_lang)
                    if not data:
                        ls = config.get_guild_settings(guild_id)
                        retries = ls["retry_attempts"] if ls["auto_retry"] else 0
                        if attempt <= retries:
                            await asyncio.sleep(1.5 * attempt)
                            continue
                        return hw_name, task_name, False, "No data returned for task"

                    result = await client.submit_score(t_obj, data, hw)

                    if result.get("error"):
                        body = result.get("body", str(result))
                        # Auto-re-login if token expired (401/403) on first attempt
                        if result.get("status") in (401, 403) and attempt == 1:
                            logger.warning("Token expired, attempting re-login...")
                            try:
                                re_ok = await client.re_login()
                                if re_ok:
                                    continue
                            except Exception:
                                logger.exception("Re-login failed")
                        ls = config.get_guild_settings(guild_id)
                        retries = ls["retry_attempts"] if ls["auto_retry"] else 0
                        if attempt <= retries:
                            await asyncio.sleep(1.5 * attempt)
                            continue
                        return hw_name, task_name, False, str(body)[:120]

                    return hw_name, task_name, True, ""

                except Exception as e:
                    logger.exception("Task automation failed")
                    ls = config.get_guild_settings(guild_id)
                    retries = ls["retry_attempts"] if ls["auto_retry"] else 0
                    if attempt <= retries:
                        await asyncio.sleep(1.5 * attempt)
                        continue
                    return hw_name, task_name, False, str(e)[:120]

    # Stagger task starts with realistic human delays between them
    async def _staggered_start(hw: dict, t_obj: dict, delay: float) -> tuple[str, str, bool, str]:
        if delay > 0:
            await asyncio.sleep(delay)
        return await run_one(hw, t_obj)

    tasks = []
    for i, (hw, t) in enumerate(jobs):
        d = client.stealth.delay_between_tasks() if i > 0 else 0
        tasks.append(_staggered_start(hw, t, d))
    results = await asyncio.gather(*tasks)
    ok  = [r for r in results if r[2]]
    bad = [r for r in results if not r[2]]

    # Log homework results for analytics
    if user_id and jobs:
        for (hw, t_obj), (hw_name, task_name, success, err) in zip(jobs, results):
            hw_id = hw.get("id", "?")
            pct = 100 if success else 0
            log_homework_action(
                user_id=user_id,
                homework_id=str(hw_id),
                task_name=task_name,
                completion_pct=pct,
                duration=0,
                xp_gained=10 if success else 0,
            )

    embed = discord.Embed(
        title="✅ Task Results" if not bad else "⚠️ Task Results",
        description=f"**{len(ok)}/{len(results)}** tasks completed successfully.",
        color=discord.Color.green() if not bad else discord.Color.orange(),
    )
    if ok:
        lines = [f"✅ **{name}** *(in {hw[:30]})*" for hw, name, _, _ in ok[:15]]
        if len(ok) > 15:
            lines.append(f"*…and {len(ok) - 15} more ✅*")
        embed.add_field(name=f"✅ Completed ({len(ok)})", value="\n".join(lines), inline=False)
    if bad:
        lines = [f"❌ **{name}** — `{err}`" for _, name, _, err in bad[:10]]
        embed.add_field(name=f"❌ Failed ({len(bad)})", value="\n".join(lines), inline=False)
    embed.set_footer(text="Cache refreshed — use /homework to see updated progress.")

    # Invalidate homework cache so next /homework shows fresh data
    cog._hw_cache.pop(guild_id, None)

    try:
        await followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        logger.error("Failed to send result embed: %s", e)
        try:
            await followup.send(
                content=f"✅ {len(ok)}/{len(results)} tasks done.", ephemeral=True
            )
        except Exception:
            pass

async def task_autocomplete(
    interaction: Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    """Autocomplete for /quick-do parameter."""
    if not interaction.guild_id:
        return []
    cog = interaction.client.get_cog("BotCommands")
    if not cog:
        return []
    try:
        homeworks = await cog._get_autocomplete_data(interaction.guild_id)
    except Exception:
        logger.exception("Autocomplete failed")
        return []
    choices: list[app_commands.Choice[str]] = []
    current_lower = current.lower() if current else ""
    for hw in homeworks:
        hw_id = hw.get("id", "")
        hw_name = hw.get("name", "Unnamed") or "?"
        for idx, task in enumerate(hw.get("tasks", [])):
            if len(choices) >= 25:
                break
            if task.get("percentage", 0) >= 100:
                continue
            task_name = task.get("translation", "Unknown") or "?"
            value = str(hw_id) + ":" + str(idx)
            label = (str(hw_name)[:20] + " - " + str(task_name)[:30])[:75]
            if current_lower:
                if current_lower in value.lower() or current_lower in label.lower():
                    choices.append(app_commands.Choice(name=label, value=value))
            else:
                if len(choices) < 25:
                    choices.append(app_commands.Choice(name=label, value=value))
        if len(choices) >= 25:
            break
    return choices[:25]

# ============================================================
# MAIN COG
# ============================================================
class BotCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._hw_cache: dict[int, tuple[float, list[dict]]] = {}
        self._locks:    dict[int, asyncio.Lock]             = {}

    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._locks:
            self._locks[guild_id] = asyncio.Lock()
        return self._locks[guild_id]

    async def _get_api_client(self, guild_id: int) -> Optional[LNApiClient]:
        account = config.get_account(guild_id)
        if not account:
            return None

        settings = config.get_guild_settings(guild_id)
        stealth  = StealthManager(
            min_accuracy                = settings["min_accuracy"],
            max_accuracy                = settings["max_accuracy"],
            min_seconds_per_question    = settings["min_seconds_per_question"],
            max_seconds_per_question    = settings["max_seconds_per_question"],
        )
        client = LNApiClient(self.bot.aiohttp_session, stealth, guild_id=guild_id)
        fernet = self.bot.fernet

        enc_user = account.get("username", "")
        enc_pass = account.get("password", "")
        username = decrypt_value(fernet, enc_user) if enc_user else ""
        password = decrypt_value(fernet, enc_pass) if enc_pass else ""

        async with self._get_lock(guild_id):
            token = account.get("token", "")
            if token:
                client.token = token
                try:
                    test = await client.call_lnut(
                        "assignmentController/getViewableAll", {"token": token}
                    )
                    if not test.get("error"):
                        return client
                except Exception:
                    logger.exception("Token validation failed")

            if not username or not password:
                logger.warning("No stored credentials for guild %s", guild_id)
                return None

            logger.info("Re-logging in for guild %s", guild_id)
            new_token = await client.login(username, password)
            if new_token:
                config.update_token(guild_id, new_token)
                self._hw_cache.pop(guild_id, None)
                return client
            return None

    async def _get_homeworks_cached(
        self,
        guild_id: int,
        client: LNApiClient,
        *,
        force: bool = False,
    ) -> list[dict]:
        now    = time.monotonic()
        cached = self._hw_cache.get(guild_id)
        if not force and cached and (now - cached[0]) < HOMEWORK_CACHE_TTL:
            return cached[1]
        discoverer = HomeworkDiscoverer(client)
        try:
            homeworks = await discoverer.get_all_homeworks(client.token)
        except Exception:
            logger.exception("Homework fetch failed")
            return cached[1] if cached else []
        self._hw_cache[guild_id] = (now, homeworks)
        # Also populate autocomplete cache
        AC_CACHE[guild_id] = homeworks
        AC_CACHE_TIME[guild_id] = now
        return homeworks

    # =========================================================

    async def _get_autocomplete_data(self, guild_id: int) -> list[dict]:
        """Return cached homework for autocomplete, background refresh if stale."""
        now = time.monotonic()
        cached_time = AC_CACHE_TIME.get(guild_id, 0)
        cached_data = AC_CACHE.get(guild_id)
        # Fast path: return fresh cache immediately
        if cached_data and (now - cached_time) < AC_CACHE_TTL:
            return cached_data
        # Stale cache: return it, refresh in background
        if cached_data:
            asyncio.create_task(self._refresh_ac_cache(guild_id))
            return cached_data
        # No cache: try sync fetch (may timeout but first-call only)
        acct = config.get_account(guild_id)
        if not acct:
            return []
        client = await self._get_api_client(guild_id)
        if not client:
            return []
        discoverer = HomeworkDiscoverer(client)
        try:
            homeworks = await discoverer.get_all_homeworks(client.token)
            AC_CACHE[guild_id] = homeworks
            AC_CACHE_TIME[guild_id] = now
            return homeworks
        except Exception:
            logger.exception("Autocomplete initial fetch failed")
            return []

    async def _refresh_ac_cache(self, guild_id: int) -> None:
        """Background refresh. Never blocks autocomplete response."""
        try:
            acct = config.get_account(guild_id)
            if not acct:
                return
            client = await self._get_api_client(guild_id)
            if not client:
                return
            discoverer = HomeworkDiscoverer(client)
            homeworks = await discoverer.get_all_homeworks(client.token)
            AC_CACHE[guild_id] = homeworks
            AC_CACHE_TIME[guild_id] = time.monotonic()
            logger.info("AC cache refreshed for guild %s", guild_id)
        except Exception:
            logger.exception("AC background refresh failed")

    # LOGIN / LOGOUT
    # =========================================================
    @app_commands.command(name="login", description="Log in to LanguageNut and securely store credentials")
    @app_commands.describe(username="Your LanguageNut username/email", password="Your LanguageNut password")
    async def login(self, interaction: Interaction, username: str, password: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if interaction.guild_id is None:
            await interaction.followup.send("❌ Must be used in a guild.", ephemeral=True)
            return
        settings = config.get_guild_settings(interaction.guild_id)
        stealth  = StealthManager(
            speed               = settings["speed"],
            min_accuracy        = settings["min_accuracy"],
            max_accuracy        = settings["max_accuracy"],
            min_seconds_per_question    = settings["min_seconds_per_question"],
            max_seconds_per_question    = settings["max_seconds_per_question"],
        )
        client = LNApiClient(self.bot.aiohttp_session, stealth)
        token  = await client.login(username, password)
        if not token:
            await interaction.followup.send("❌ Login failed. Check your username and password.", ephemeral=True)
            return
        fernet = self.bot.fernet
        config.set_account(
            interaction.guild_id,
            encrypt_value(fernet, username),
            encrypt_value(fernet, password),
            token,
        )
        self._hw_cache.pop(interaction.guild_id, None)
        logger.info("User logged in for guild %s", interaction.guild_id)
        log_user_command(interaction.user.id, "/login", f"Guild {interaction.guild_id}")
        await interaction.followup.send(
            "✅ Login successful! Credentials stored securely.\nUse `/homework` to view assignments.",
            ephemeral=True,
        )

    @app_commands.command(name="logout", description="Remove stored LanguageNut credentials")
    async def logout(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if interaction.guild_id is None:
            await interaction.followup.send("❌ Guild only.", ephemeral=True)
            return
        if config.remove_account(interaction.guild_id):
            self._hw_cache.pop(interaction.guild_id, None)
            await interaction.followup.send("✅ Logged out successfully.", ephemeral=True)
        else:
            await interaction.followup.send("❌ No credentials stored.", ephemeral=True)

    # =========================================================
    # HOMEWORK
    # =========================================================
    @app_commands.command(name="homework", description="List all homework assignments with progress")
    async def homework(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if interaction.guild_id is None:
            await interaction.followup.send("❌ Guild only.", ephemeral=True)
            return
        client = await self._get_api_client(interaction.guild_id)
        if not client:
            await interaction.followup.send("❌ Not logged in. Use `/login` first.", ephemeral=True)
            return
        homeworks = await self._get_homeworks_cached(interaction.guild_id, client, force=True)
        if not homeworks:
            await interaction.followup.send("🔭 No homework found.", ephemeral=True)
            return
        view = HomeworkPaginator(homeworks, interaction.user.id)
        await interaction.followup.send(embed=view.build_embed(), view=view, ephemeral=True)

    # =========================================================
    # DO TASK(S) — dropdown UI
    # =========================================================
    # =========================================================
    # QUICK DO - autocomplete parameter
    # =========================================================
    @app_commands.command(name="quick-do", description="Quick-complete a task by homework:index (faster than /do dropdowns)")
    @app_commands.describe(task="Format: hwId:idx (e.g. 123:0) or comma-separated: 123:0,456:2")
    @app_commands.autocomplete(task=task_autocomplete)
    async def quick_do(self, interaction: Interaction, task: str):
        """Quick-complete one or more tasks using hwId:idx syntax."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not interaction.guild_id:
            await interaction.followup.send("Must be used in a guild.", ephemeral=True)
            return
        client = await self._get_api_client(interaction.guild_id)
        if not client:
            await interaction.followup.send("Not logged in. Use /login first.", ephemeral=True)
            return
        homeworks = await self._get_homeworks_cached(interaction.guild_id, client, force=True)
        if not homeworks:
            await interaction.followup.send("No homework found.", ephemeral=True)
            return
        # Parse task format: hwId:idx or comma-separated
        jobs: list[tuple[dict, dict]] = []
        parts = [p.strip() for p in task.split(",")]
        for part in parts:
            if ":" not in part:
                await interaction.followup.send("Invalid format: use hwId:idx", ephemeral=True)
                return
            hw_id_str, idx_str = part.split(":", 1)
            try:
                hw_id = int(hw_id_str); idx = int(idx_str)
            except ValueError:
                await interaction.followup.send("Invalid number in: " + repr(part), ephemeral=True)
                return
            hw = next((h for h in homeworks if h.get("id") == hw_id), None)
            if not hw:
                await interaction.followup.send("Homework #" + str(hw_id) + " not found.", ephemeral=True)
                return
            task_list = hw.get("tasks", [])
            if idx < 0 or idx >= len(task_list):
                await interaction.followup.send("Task index " + str(idx) + " out of range.", ephemeral=True)
                return
            task_obj = task_list[idx]
            if _is_done(task_obj):
                await interaction.followup.send("Task #" + str(hw_id) + ":" + str(idx) + " already done.", ephemeral=True)
                return
            jobs.append((hw, task_obj))
        if not jobs:
            await interaction.followup.send("No valid tasks to complete.", ephemeral=True)
            return
        await interaction.followup.send("Starting **" + str(len(jobs)) + "** task(s)...", ephemeral=True)
        asyncio.create_task(
            _execute_jobs(interaction.followup, jobs, self, interaction.guild_id, user_id=interaction.user.id)
        )

    @app_commands.command(name="do", description="Complete homework tasks using an interactive selector")
    async def do_task(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if interaction.guild_id is None:
            await interaction.followup.send("❌ Guild only.", ephemeral=True)
            return
        client = await self._get_api_client(interaction.guild_id)
        if not client:
            await interaction.followup.send("❌ Not logged in. Use `/login` first.", ephemeral=True)
            return
        homeworks = await self._get_homeworks_cached(interaction.guild_id, client, force=True)
        if not homeworks:
            await interaction.followup.send("🔭 No homework found.", ephemeral=True)
            return

        incomplete_hws = [
            hw for hw in homeworks
            if any(not _is_done(t) for t in hw.get("tasks", []))
        ]
        if not incomplete_hws:
            await interaction.followup.send(
                "✅ All homework is already at 100%! Nothing left to do.", ephemeral=True
            )
            return

        total_incomplete = sum(
            1 for hw in incomplete_hws for t in hw.get("tasks", []) if not _is_done(t)
        )
        embed = discord.Embed(
            title="📚 Select Homework to Complete",
            description=(
                f"Found **{len(incomplete_hws)}** assignment(s) with "
                f"**{total_incomplete}** incomplete task(s).\n\n"
                "Pick an assignment below, or choose **⚡ Do ALL** to run everything at once."
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Only incomplete tasks (< 100%) are shown.")
        log_user_command(
            interaction.user.id,
            "/do",
            f"Started homework selector with {len(incomplete_hws)} assignments",
        )
        view = DoHomeworkView(incomplete_hws, self, interaction.guild_id, interaction.user.id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # =========================================================
    # SETTINGS
    # =========================================================
    @app_commands.command(name="settings", description="Open the settings panel")
    async def settings_cmd(self, interaction: Interaction):
        if interaction.guild_id is None:
            await safe_send(interaction, "❌ Guild only.")
            return
        view = SettingsView(interaction.guild_id)
        await safe_send(interaction, embed=view.build_embed(interaction.guild_id), view=view)

    # =========================================================
    # STATUS
    # =========================================================
    @app_commands.command(name="tutorial", description="Show the bot tutorial / user guide")
    async def tutorial_cmd(self, interaction: Interaction):
        """Read tutorial.md and display it as a paginated embed."""
        await interaction.response.defer(ephemeral=True)
        tut_paths = [
            "tutorial.md",
            os.path.join(os.path.dirname(__file__), "..", "tutorial.md"),
        ]
        tut_file = next((p for p in tut_paths if os.path.exists(p)), None)
        if not tut_file:
            await interaction.followup.send("Tutorial file not found.", ephemeral=True)
            return
        try:
            with open(tut_file, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            await interaction.followup.send(f"Error reading tutorial: {e}", ephemeral=True)
            return
        pages = []
        current_section = ""
        current_lines = []
        for line in content.splitlines():
            if line.startswith("# ") and current_lines:
                body = chr(10).join(current_lines).strip()
                pages.append((current_section, body))
                current_lines = []
            if line.startswith("# "):
                current_section = line[2:].strip()
            else:
                current_lines.append(line)
        if current_lines:
            body = chr(10).join(current_lines).strip()
            pages.append((current_section, body))
        if not pages:
            await interaction.followup.send("Tutorial is empty.", ephemeral=True)
            return
        embed = discord.Embed(
            title=pages[0][0],
            description=pages[0][1][:4000],
            color=discord.Color.blue(),
        )
        embed.set_footer(
            text="Page 1/" + str(len(pages)) + " | /settings to customize"
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="status", description="Show bot status")
    async def status_cmd(self, interaction: Interaction):
        embed = discord.Embed(
            title="🤖 Bot Status",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Servers",     value=str(len(self.bot.guilds)))
        embed.add_field(name="Users",       value=str(len(self.bot.users)))
        embed.add_field(name="Latency",     value=f"{round(self.bot.latency * 1000)}ms")
        embed.add_field(name="Python",      value=platform.python_version())
        embed.add_field(name="Discord.py",  value=discord.__version__)
        if hasattr(self.bot, "start_time"):
            uptime = discord.utils.utcnow() - self.bot.start_time
            days = uptime.days
            hours, rem = divmod(uptime.seconds, 3600)
            minutes, _ = divmod(rem, 60)
            parts = []
            if days: parts.append(f"{days}d")
            if hours: parts.append(f"{hours}h")
            parts.append(f"{minutes}m")
            embed.add_field(name="Uptime", value=":".join(parts), inline=True)
        if interaction.guild_id is not None:
            acct = config.get_account(interaction.guild_id)
            embed.add_field(name="Logged in", value="✅" if acct else "❌", inline=True)
        await safe_send(interaction, embed=embed)

    @app_commands.command(name="leaderboard", description="View the LanguageNut leaderboard")
    @app_commands.describe(
        ltype="Leaderboard type: class, school, or global",
        position="Number of top entries to show (1-50)"
    )
    @app_commands.choices(ltype=[
        app_commands.Choice(name="Class Leaderboard", value="class"),
        app_commands.Choice(name="School Leaderboard", value="school"),
        app_commands.Choice(name="Global Leaderboard", value="global"),
    ])
    async def leaderboard_cmd(self, interaction: Interaction, ltype: str, position: app_commands.Range[int, 1, 50] = 10):
        """Display leaderboard rankings from LanguageNut."""
        await interaction.response.defer(ephemeral=True)
        if interaction.guild_id is None:
            await interaction.followup.send("Guild only.", ephemeral=True)
            return

        client = await self._get_api_client(interaction.guild_id)
        if not client:
            await interaction.followup.send("Not logged in. Use `/login` first.", ephemeral=True)
            return

        try:
            if ltype == "class":
                data = await client.get_class_leaderboard()
                if not data:
                    await interaction.followup.send("No class data found.", ephemeral=True)
                    return

                embed = discord.Embed(
                    title="Class Leaderboard",
                    description="Top classes by student scores",
                    color=discord.Color.blue(),
                )

                sorted_classes = sorted(
                    data,
                    key=lambda c: max(int(s.get("score", 0)) for s in c.get("list", [])) if c.get("list") else 0,
                    reverse=True,
                )

                for i, cls in enumerate(sorted_classes[:position], 1):
                    cls_name = cls.get("name", "Unknown Class")
                    students = cls.get("list", [])
                    top_score = max(int(s.get("score", 0)) for s in students) if students else 0
                    total_students = len(students)
                    medal = chr(0x1F947) if i == 1 else (chr(0x1F948) if i == 2 else (chr(0x1F949) if i == 3 else f"`#{i}`"))
                    embed.add_field(
                        name=f"{medal} {cls_name[:100]}",
                        value=f"Students: {total_students} | Top score: **{top_score:,}**",
                        inline=False,
                    )

                embed.set_footer(text=f"Showing top {min(position, len(sorted_classes))} classes")

            elif ltype == "school":
                data = await client.get_school_leaderboard()
                if not data:
                    await interaction.followup.send("No school leaderboard data found.", ephemeral=True)
                    return

                embed = discord.Embed(
                    title="School Leaderboard",
                    description="All students in your school ranked by score",
                    color=discord.Color.green(),
                )

                sorted_students = sorted(data, key=lambda s: int(s.get("score", 0)), reverse=True)
                total = len(sorted_students)
                user_rank = None
                for idx_s, s in enumerate(sorted_students):
                    if s.get("isUser") == "1":
                        user_rank = idx_s + 1
                        break

                desc_lines = [f"Total students: **{total}**"]
                if user_rank:
                    desc_lines.append(f"Your rank: **#{user_rank}**")
                embed.description = chr(10).join(desc_lines)

                top_n = min(position, len(sorted_students))
                lines = []
                for i in range(top_n):
                    s = sorted_students[i]
                    name = s.get("name", "Unknown")
                    score = int(s.get("score", 0))
                    medal = chr(0x1F947) if i == 0 else (chr(0x1F948) if i == 1 else (chr(0x1F949) if i == 2 else f"`#{i+1}`"))
                    lines.append(f"{medal} **{name}** -- {score:,} pts")

                embed.add_field(name=f"Top {top_n}", value=chr(10).join(lines), inline=False)

                if user_rank and user_rank > top_n:
                    u = sorted_students[user_rank - 1]
                    embed.add_field(name="Your Position", value=f"#{user_rank} -- **{u.get('name', 'You')}** ({int(u.get('score', 0)):,} pts)", inline=False)

            elif ltype == "global":
                data = await client.get_school_rankings()
                if not data:
                    await interaction.followup.send("No global leaderboard data found.", ephemeral=True)
                    return

                embed = discord.Embed(
                    title="Global School Rankings",
                    description="Top schools worldwide by total score",
                    color=discord.Color.purple(),
                )

                sorted_schools = sorted(data, key=lambda s: int(s.get("score", 0)), reverse=True)
                top_n = min(position, len(sorted_schools))

                lines = []
                for i in range(top_n):
                    s = sorted_schools[i]
                    name = s.get("name", "Unknown School")
                    score = int(s.get("score", 0))
                    rank = s.get("rank", str(i + 1))
                    medal = chr(0x1F947) if i == 0 else (chr(0x1F948) if i == 1 else (chr(0x1F949) if i == 2 else f"`#{rank}`"))
                    lines.append(f"{medal} **{name[:60]}** -- {score:,} pts")

                embed.add_field(name=f"Top {top_n} Schools", value=chr(10).join(lines), inline=False)

                user_school = next((s for s in sorted_schools if "Saint Ambrose" in s.get("name", "")), None)
                if user_school:
                    embed.set_footer(text=f"Your school rank: #{user_school.get('rank', '?')} worldwide")

            else:
                await interaction.followup.send(f"Unknown leaderboard type: {ltype}", ephemeral=True)
                return

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception("Leaderboard fetch failed")
            await interaction.followup.send(f"Failed to fetch leaderboard: {str(e)[:200]}", ephemeral=True)


    # =========================================================
    # ADMIN COMMANDS
    # =========================================================
    @app_commands.command(name="restart", description="Restart the bot (owner)")
    @owner_only()
    async def restart_cmd(self, interaction: Interaction):
        await safe_send(interaction, "♻️ Restarting bot...")
        await self.bot.close()
        subprocess.Popen([sys.executable] + sys.argv)
        os._exit(0)

    @app_commands.command(name="shutdown", description="Stop the bot (owner)")
    @owner_only()
    async def shutdown_cmd(self, interaction: Interaction):
        await safe_send(interaction, "🛑 Shutting down...")
        await self.bot.close()

    @app_commands.command(name="sync", description="Sync slash commands (owner)")
    @owner_only()
    async def sync_cmd(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            synced_guild = []
            if interaction.guild:
                synced_guild = await self.bot.tree.sync(guild=interaction.guild)
            synced_global = await self.bot.tree.sync()
            await interaction.followup.send(
                f"✅ Synced {len(synced_guild)} guild + {len(synced_global)} global commands",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Sync failed: {e}", ephemeral=True)

    @app_commands.command(name="update", description="Git pull + restart (owner)")
    @owner_only()
    async def update_cmd(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            result = subprocess.run(
                ["git", "pull"], capture_output=True, text=True, timeout=30
            )
        except subprocess.TimeoutExpired:
            await interaction.followup.send("❌ git pull timed out", ephemeral=True)
            return
        output = (result.stdout or "") + (result.stderr or "")
        await interaction.followup.send(
            f"```{output[:1800] or '(no output)'}```", ephemeral=True
        )
        if result.returncode != 0:
            return
        await asyncio.sleep(2)
        await self.bot.close()
        subprocess.Popen([sys.executable] + sys.argv)
        os._exit(0)

    @app_commands.command(name="clear", description="Delete recent messages (owner)")
    @owner_only()
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    async def clear_cmd(self, interaction: Interaction, amount: int):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await safe_send(interaction, "❌ Text channels only.")
            return
        amount = max(1, min(100, amount))
        await interaction.response.defer(ephemeral=True)
        try:
            deleted = await channel.purge(limit=amount)
            await interaction.followup.send(f"🗑️ Deleted {len(deleted)} messages", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to delete messages.", ephemeral=True)

    @app_commands.command(name="logs", description="View bot, user, or homework logs (owner)")
    @owner_only()
    @app_commands.describe(
        log_type="bot / user / homework",
        level="Filter level for bot logs",
        user="Target user (required for user/homework types)",
        lines="Number of log lines to show (5-200, default 30)",
    )
    @app_commands.choices(log_type=[
        app_commands.Choice(name="Bot Console Logs", value="bot"),
        app_commands.Choice(name="User Command History", value="user"),
        app_commands.Choice(name="Homework Results", value="homework"),
    ])
    @app_commands.choices(level=[
        app_commands.Choice(name="All levels", value="all"),
        app_commands.Choice(name="DEBUG", value="debug"),
        app_commands.Choice(name="INFO", value="info"),
        app_commands.Choice(name="WARNING", value="warning"),
        app_commands.Choice(name="ERROR", value="error"),
        app_commands.Choice(name="CRITICAL", value="critical"),
    ])
    async def logs_cmd(
        self,
        interaction: Interaction,
        log_type: str = "bot",
        level: str = "all",
        user: discord.Member = None,
        lines: app_commands.Range[int, 5, 200] = 30,
    ):
        await interaction.response.defer(ephemeral=True)

        log_type = log_type.lower()

        if log_type == "bot":
            level_filter = level if level != "all" else None
            logs = fetch_bot_logs(level=level_filter, lines=lines)
            if not logs:
                return await interaction.followup.send("No bot logs found.", ephemeral=True)
            content = "".join(logs)[-3800:]
            embed = discord.Embed(
                title=f"Bot Logs ({level})",
                description=f"```{content}```",
                color=discord.Color.red(),
            )
            embed.set_footer(text=f"{len(logs)} lines shown")
            return await interaction.followup.send(embed=embed, ephemeral=True)

        elif log_type == "user":
            if not user:
                return await interaction.followup.send("Provide a user with the `user` parameter.", ephemeral=True)
            logs = fetch_user_logs(user.id)
            if not logs:
                return await interaction.followup.send("No user logs found.", ephemeral=True)
            log_entries = [
                f"{x['timestamp']} | {x['command']} | {x['details']}"
                for x in logs[-lines:]
            ]
            embed = discord.Embed(
                title=f"{user.name}'s Command Logs",
                description=f"```{chr(10).join(log_entries)[:3800]}```",
                color=discord.Color.blue(),
            )
            embed.set_footer(text=f"{len(log_entries)} entries shown")
            return await interaction.followup.send(embed=embed, ephemeral=True)

        elif log_type == "homework":
            if not user:
                return await interaction.followup.send("Provide a user with the `user` parameter.", ephemeral=True)
            logs = fetch_homework_logs(user.id)
            if not logs:
                return await interaction.followup.send("No homework logs found.", ephemeral=True)
            log_entries = [
                f"{x['timestamp']} | HW:{x['homework_id']} | {x['task_name']} | "
                f"{x['completion_pct']}% | XP:{x['xp_gained']}"
                for x in logs[-lines:]
            ]
            embed = discord.Embed(
                title=f"{user.name}'s Homework Logs",
                description=f"```{chr(10).join(log_entries)[:3800]}```",
                color=discord.Color.green(),
            )
            embed.set_footer(text=f"{len(log_entries)} entries shown")
            return await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="reload", description="Reload a cog (owner)")
    @owner_only()
    @app_commands.describe(cog="Cog name (e.g. 'commands' or 'commands.commands')")
    async def reload_cmd(self, interaction: Interaction, cog: str):
        await interaction.response.defer(ephemeral=True)
        candidates = [cog, f"commands.{cog}"] if "." not in cog else [cog]
        last_err   = None
        for name in candidates:
            try:
                await self.bot.reload_extension(name)
                await interaction.followup.send(f"✅ Reloaded `{name}`", ephemeral=True)
                return
            except Exception as e:
                last_err = e
        await interaction.followup.send(f"❌ Reload failed: {last_err}", ephemeral=True)

    @app_commands.command(name="eval", description="Eval python (owner)")
    @owner_only()
    @app_commands.describe(code="Python expression or statements")
    async def eval_cmd(self, interaction: Interaction, code: str):
        await interaction.response.defer(ephemeral=True)
        env: dict[str, Any] = {
            "bot": self.bot, "discord": discord,
            "interaction": interaction, "asyncio": asyncio,
        }
        if not code.strip():
            await interaction.followup.send("Empty code.", ephemeral=True)
            return
        try:
            body   = "\n".join(f"    {line}" for line in code.split("\n"))
            exec(f"async def __ex():\n{body}", env)
            result = await env["__ex"]()
            await interaction.followup.send(f"```\n{str(result)[:1900]}\n```", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ {type(e).__name__}: {e}", ephemeral=True)

    @app_commands.command(name="online", description="Announce ONLINE (owner)")
    @owner_only()
    async def online_cmd(self, interaction: Interaction):
        await interaction.response.send_message("@everyone BOT IS ONLINE 🟢")

    @app_commands.command(name="offline", description="Announce OFFLINE (owner)")
    @owner_only()
    async def offline_cmd(self, interaction: Interaction):
        await interaction.response.send_message("@everyone BOT IS OFFLINE " + chr(0x1F534))

    @app_commands.command(name="say", description="Make the bot say something (owner)")
    @owner_only()
    @app_commands.describe(message="The message to send")
    async def say_cmd(self, interaction: Interaction, message: str):
        await interaction.response.send_message(message[:1900])

    @app_commands.command(name="embed", description="Send an embedded message (owner)")
    @owner_only()
    @app_commands.describe(title="Embed title", description="Embed description", color="Hex color e.g. 00ff00")
    async def embed_cmd(self, interaction: Interaction, title: str, description: str, color: str = "3498db"):
        try:
            color_int = int(color.strip("#"), 16)
        except ValueError:
            color_int = 0x3498db
        embed = discord.Embed(title=title, description=description, color=color_int)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Show info about a user (owner)")
    @owner_only()
    @app_commands.describe(user="The user to look up")
    async def userinfo_cmd(self, interaction: Interaction, user: discord.User):
        embed = discord.Embed(
            title=f"User Info - {user}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="ID", value=user.id, inline=True)
        embed.add_field(name="Name", value=user.name, inline=True)
        embed.add_field(name="Display Name", value=user.display_name, inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(user.created_at, style="R"), inline=True)
        embed.add_field(name="Bot", value="Yes" if user.bot else "No", inline=True)
        if isinstance(user, discord.Member):
            embed.add_field(name="Joined", value=discord.utils.format_dt(user.joined_at, style="R"), inline=True)
            roles = [r.mention for r in user.roles[1:]]
            if roles:
                embed.add_field(name=f"Roles ({len(roles)})", value=", ".join(roles[:5]) + (f" +{len(roles)-5}" if len(roles) > 5 else ""), inline=False)
        await safe_send(interaction, embed=embed)

    @app_commands.command(name="serverinfo", description="Show info about this server (owner)")
    @owner_only()
    async def serverinfo_cmd(self, interaction: Interaction):
        if not interaction.guild:
            await safe_send(interaction, "Guild only.")
            return
        guild = interaction.guild
        embed = discord.Embed(
            title=f"Server Info - {guild.name}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="ID", value=guild.id, inline=True)
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Channels", value=len(guild.channels), inline=True)
        embed.add_field(name="Roles", value=len(guild.roles), inline=True)
        embed.add_field(name="Boosts", value=guild.premium_subscription_count, inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, style="R"), inline=True)
        await safe_send(interaction, embed=embed)

    @app_commands.command(name="dm", description="DM a user (owner)")
    @owner_only()
    @app_commands.describe(user="The user to DM", message="The message to send")
    async def dm_cmd(self, interaction: Interaction, user: discord.User, message: str):
        await interaction.response.defer(ephemeral=True)
        try:
            await user.send(message[:1900])
            await interaction.followup.send(f"DM sent to **{user}**", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("Cannot DM that user (DMs closed or blocked).", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed: {e}", ephemeral=True)

    @app_commands.command(name="nickname", description="Change a user's nickname (owner)")
    @owner_only()
    @app_commands.describe(user="The user", nickname="New nickname (or blank to reset)")
    async def nickname_cmd(self, interaction: Interaction, user: discord.Member, nickname: str = ""):
        await interaction.response.defer(ephemeral=True)
        try:
            if nickname:
                await user.edit(nick=nickname[:32])
                await interaction.followup.send(f"Nickname set to **{nickname[:32]}** for {user.mention}", ephemeral=True)
            else:
                await user.edit(nick=None)
                await interaction.followup.send(f"Nickname reset for {user.mention}", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to change that user's nickname.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed: {e}", ephemeral=True)

    @app_commands.command(name="purge", description="Bulk delete messages from a channel (owner)")
    @owner_only()
    @app_commands.describe(amount="Number of messages to delete (1-500)")
    async def purge_cmd(self, interaction: Interaction, amount: app_commands.Range[int, 1, 500] = 50):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel) and not isinstance(channel, discord.Thread):
            await safe_send(interaction, "Text channels and threads only.")
            return
        await interaction.response.defer(ephemeral=True)
        try:
            deleted = await channel.purge(limit=amount, bulk=True)
            await interaction.followup.send(f"Purged {len(deleted)} messages.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed: {e}", ephemeral=True)

    @app_commands.command(name="lockdown", description="Lock or unlock a channel (owner)")
    @owner_only()
    @app_commands.describe(mode="lock to restrict or unlock to open")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Lock Channel", value="lock"),
        app_commands.Choice(name="Unlock Channel", value="unlock"),
    ])
    async def lockdown_cmd(self, interaction: Interaction, mode: str):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await safe_send(interaction, "Text channels only.")
            return
        await interaction.response.defer(ephemeral=True)
        try:
            guild = interaction.guild
            if not guild:
                return
            default_role = guild.default_role
            overwrite = channel.overwrites_for(default_role)
            if mode == "lock":
                overwrite.send_messages = False
                await channel.set_permissions(default_role, overwrite=overwrite)
                await interaction.followup.send(chr(0x1F512) + " Channel locked. Only users with special roles can talk.", ephemeral=True)
            else:
                overwrite.send_messages = None
                await channel.set_permissions(default_role, overwrite=overwrite)
                await interaction.followup.send(chr(0x1F513) + " Channel unlocked.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to manage this channel.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Failed: {e}", ephemeral=True)


# ============================================================
async def setup(bot: commands.Bot):
    await bot.add_cog(BotCommands(bot))