"""
LanguageNut bot - Unified Commands Module

Includes:
  User commands:
    /login /logout /homework /do /status /settings
  Admin (owner only):
    /restart /shutdown /update /sync /clear /logs /reload /eval /online /offline

Optimized for:
  - Speed: cached homework results (short TTL) and a single shared HTTP session
  - Accuracy: robust token refresh, typed payloads
  - Autocomplete: fast cached lookup with short-circuit matching
  - UX: smooth component v2-style UI with dropdowns and multi-select
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import subprocess
import sys
import time
from typing import Any, Optional

import discord
from discord import ButtonStyle, Interaction, app_commands, ui
from discord.ext import commands

import config
from automation.api_direct import LNApiClient
from automation.discover import HomeworkDiscoverer
from automation.stealth import StealthManager
from utils.encryption import decrypt_value, encrypt_value

logger = logging.getLogger("lnut_bot.commands")

# ── Owner user id (admin commands) ──────────────────────────────────────────
OWNER_ID = 1453752725324955656

# ── Cache TTL (seconds) for per-guild homework fetch ────────────────────────
HOMEWORK_CACHE_TTL = 20.0


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
        logger.error(f"Send failed: {e}")


# ============================================================
# SETTINGS PANEL
# ============================================================
class SettingModal(ui.Modal):
    """Generic modal for numeric setting updates."""

    def __init__(
        self,
        key: str,
        label: str,
        current: Any,
        caster,
        validator,
        parent_view: "SettingsView",
    ):
        super().__init__(title=f"Update {label}")
        self.key = key
        self.caster = caster
        self.validator = validator
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
        try:
            raw = self.field.value.strip()
            value = self.caster(raw)
            if not self.validator(value):
                raise ValueError("Value out of allowed range.")
        except (ValueError, TypeError) as e:
            await safe_send(interaction, f"❌ Invalid value: {e}")
            return

        if interaction.guild_id is None:
            await safe_send(interaction, "❌ Guild only command.")
            return

        config.set_guild_setting(interaction.guild_id, self.key, value)
        embed = self.parent_view.build_embed(interaction.guild_id)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class SettingsView(ui.View):
    """Persistent settings panel with working controls."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=180)
        self.guild_id = guild_id

    def build_embed(self, guild_id: int) -> discord.Embed:
        s = config.get_guild_settings(guild_id)
        embed = discord.Embed(
            title="⚙️ LanguageNut Bot Settings",
            description="Configure automation behavior. Changes are saved immediately.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="⏱️ Speed (sec/task)", value=f"`{s['speed']}`", inline=True)
        embed.add_field(
            name="🎯 Accuracy Range",
            value=f"`{s['min_accuracy']}% – {s['max_accuracy']}%`",
            inline=True,
        )
        embed.add_field(
            name="⚡ Concurrency",
            value=f"`{s['concurrency']}` parallel tasks",
            inline=True,
        )
        embed.add_field(
            name="🛡️ Stealth",
            value="`ON`" if s["stealth_enabled"] else "`OFF`",
            inline=True,
        )
        embed.add_field(
            name="🔁 Auto Retry",
            value=f"`{'ON' if s['auto_retry'] else 'OFF'}` ({s['retry_attempts']}x)",
            inline=True,
        )
        embed.set_footer(text="Changes apply immediately to future tasks.")
        return embed

    # --- Row 0: timing ---
    @ui.button(label="⏱️ Speed", style=ButtonStyle.primary, row=0)
    async def speed_btn(self, interaction: Interaction, _: ui.Button):
        s = config.get_guild_settings(interaction.guild_id)
        await interaction.response.send_modal(
            SettingModal(
                key="speed",
                label="Seconds per task (3 – 120)",
                current=s["speed"],
                caster=float,
                validator=lambda v: 3.0 <= v <= 120.0,
                parent_view=self,
            )
        )

    @ui.button(label="🎯 Min Accuracy", style=ButtonStyle.primary, row=0)
    async def min_acc_btn(self, interaction: Interaction, _: ui.Button):
        s = config.get_guild_settings(interaction.guild_id)
        await interaction.response.send_modal(
            SettingModal(
                key="min_accuracy",
                label="Min accuracy % (50 – 100)",
                current=s["min_accuracy"],
                caster=int,
                validator=lambda v: 50 <= v <= 100,
                parent_view=self,
            )
        )

    @ui.button(label="🎯 Max Accuracy", style=ButtonStyle.primary, row=0)
    async def max_acc_btn(self, interaction: Interaction, _: ui.Button):
        s = config.get_guild_settings(interaction.guild_id)
        await interaction.response.send_modal(
            SettingModal(
                key="max_accuracy",
                label="Max accuracy % (50 – 100)",
                current=s["max_accuracy"],
                caster=int,
                validator=lambda v: 50 <= v <= 100,
                parent_view=self,
            )
        )

    # --- Row 1: performance ---
    @ui.button(label="⚡ Concurrency", style=ButtonStyle.success, row=1)
    async def conc_btn(self, interaction: Interaction, _: ui.Button):
        s = config.get_guild_settings(interaction.guild_id)
        await interaction.response.send_modal(
            SettingModal(
                key="concurrency",
                label="Parallel tasks (1 – 8)",
                current=s["concurrency"],
                caster=int,
                validator=lambda v: 1 <= v <= 8,
                parent_view=self,
            )
        )

    @ui.button(label="🔁 Retry Attempts", style=ButtonStyle.success, row=1)
    async def retry_btn(self, interaction: Interaction, _: ui.Button):
        s = config.get_guild_settings(interaction.guild_id)
        await interaction.response.send_modal(
            SettingModal(
                key="retry_attempts",
                label="Retry attempts (0 – 5)",
                current=s["retry_attempts"],
                caster=int,
                validator=lambda v: 0 <= v <= 5,
                parent_view=self,
            )
        )

    # --- Row 2: toggles ---
    @ui.button(label="🛡️ Toggle Stealth", style=ButtonStyle.secondary, row=2)
    async def stealth_btn(self, interaction: Interaction, _: ui.Button):
        if interaction.guild_id is None:
            await safe_send(interaction, "❌ Guild only.")
            return
        s = config.get_guild_settings(interaction.guild_id)
        config.set_guild_setting(
            interaction.guild_id, "stealth_enabled", not s["stealth_enabled"]
        )
        await interaction.response.edit_message(
            embed=self.build_embed(interaction.guild_id), view=self
        )

    @ui.button(label="🔁 Toggle Auto-Retry", style=ButtonStyle.secondary, row=2)
    async def autoretry_btn(self, interaction: Interaction, _: ui.Button):
        if interaction.guild_id is None:
            await safe_send(interaction, "❌ Guild only.")
            return
        s = config.get_guild_settings(interaction.guild_id)
        config.set_guild_setting(
            interaction.guild_id, "auto_retry", not s["auto_retry"]
        )
        await interaction.response.edit_message(
            embed=self.build_embed(interaction.guild_id), view=self
        )

    # --- Row 3: reset/close ---
    @ui.button(label="♻️ Reset Defaults", style=ButtonStyle.danger, row=3)
    async def reset_btn(self, interaction: Interaction, _: ui.Button):
        if interaction.guild_id is None:
            await safe_send(interaction, "❌ Guild only.")
            return
        config.reset_guild_settings(interaction.guild_id)
        await interaction.response.edit_message(
            embed=self.build_embed(interaction.guild_id), view=self
        )

    @ui.button(label="✖ Close", style=ButtonStyle.danger, row=3)
    async def close_btn(self, interaction: Interaction, _: ui.Button):
        await interaction.response.edit_message(
            content="Settings closed.", embed=None, view=None
        )


# ============================================================
# HOMEWORK PAGINATOR  (smoother v2 UI)
# ============================================================
class HomeworkPaginator(ui.View):
    """Paginated view for listing homeworks."""

    PER_PAGE = 4

    def __init__(self, homeworks: list[dict], user_id: int):
        super().__init__(timeout=300)
        self.homeworks = homeworks
        self.user_id = user_id
        self.page = 0
        self.total_pages = max(
            1, (len(homeworks) + self.PER_PAGE - 1) // self.PER_PAGE
        )
        self._update_button_state()

    def _update_button_state(self):
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= self.total_pages - 1

    def build_embed(self) -> discord.Embed:
        start = self.page * self.PER_PAGE
        end = start + self.PER_PAGE
        chunk = self.homeworks[start:end]

        # Count totals across ALL homeworks
        total_tasks = sum(len(hw.get("tasks", [])) for hw in self.homeworks)
        total_done = sum(
            1
            for hw in self.homeworks
            for t in hw.get("tasks", [])
            if t.get("gameResults") and t["gameResults"].get("percentage", 0) == 100
        )
        incomplete_count = total_tasks - total_done

        embed = discord.Embed(
            title="📚 LanguageNut Homework",
            description=(
                f"**{len(self.homeworks)}** assignment(s) • "
                f"**{total_tasks}** total tasks • "
                f"**{incomplete_count}** incomplete"
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(
            text=f"Page {self.page + 1}/{self.total_pages}  •  Use /do to complete tasks"
        )

        for hw in chunk:
            name = hw.get("name", "Unnamed")
            hw_id = hw.get("id", "?")
            tasks = hw.get("tasks", [])
            total = len(tasks)
            completed = sum(
                1
                for t in tasks
                if t.get("gameResults") and t["gameResults"].get("percentage", 0) == 100
            )
            pct_overall = round((completed / total * 100) if total else 0)

            # Progress bar (10 chars)
            filled = round(pct_overall / 10)
            bar = "█" * filled + "░" * (10 - filled)

            lines = [f"`{bar}` **{pct_overall}%** ({completed}/{total} done)"]

            incomplete_tasks = [
                t for t in tasks
                if not (t.get("gameResults") and t["gameResults"].get("percentage", 0) == 100)
            ]
            for task in incomplete_tasks[:5]:
                gr = task.get("gameResults") or {}
                pct = gr.get("percentage", 0) if gr else 0
                task_name = task.get("translation", "Unknown")
                if len(task_name) > 38:
                    task_name = task_name[:35] + "..."
                lines.append(f"  ↳ `{pct}%` {task_name}")

            remaining = len(incomplete_tasks) - 5
            if remaining > 0:
                lines.append(f"  ↳ *…and {remaining} more incomplete*")

            value = "\n".join(lines)
            if len(value) > 1024:
                value = value[:1020] + "..."

            embed.add_field(
                name=f"📖 {name[:180]}  `#{hw_id}`",
                value=value,
                inline=False,
            )

        return embed

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This menu isn't for you.", ephemeral=True
            )
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
        await interaction.response.edit_message(
            content="Closed.", embed=None, view=None
        )


# ============================================================
# /do  —  STEP 1: Homework selector dropdown
# ============================================================
class HomeworkSelect(ui.Select):
    """Dropdown to pick which homework (or ALL) to work on."""

    def __init__(self, homeworks: list[dict]):
        self.homeworks = homeworks

        options: list[discord.SelectOption] = [
            discord.SelectOption(
                label="✅ Do ALL incomplete tasks",
                value="__ALL__",
                description="Run every incomplete task across all assignments",
                emoji="⚡",
            )
        ]

        for hw in homeworks[:24]:  # Discord limit 25 options
            hw_id = str(hw.get("id", "?"))
            name = hw.get("name", "Unnamed")
            tasks = hw.get("tasks", [])
            incomplete = [
                t for t in tasks
                if not (t.get("gameResults") and t["gameResults"].get("percentage", 0) == 100)
            ]
            total = len(tasks)
            done = total - len(incomplete)
            pct = round((done / total * 100) if total else 0)

            if not incomplete:
                continue  # skip fully completed

            label = name[:95] if len(name) <= 95 else name[:92] + "..."
            desc = f"{pct}% done • {len(incomplete)} task(s) remaining"

            options.append(
                discord.SelectOption(
                    label=label,
                    value=hw_id,
                    description=desc[:100],
                    emoji="📖",
                )
            )

        if len(options) == 1:
            # Only the ALL option means nothing to do
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
            # Gather all incomplete tasks
            jobs: list[tuple[dict, dict]] = []
            for hw in self.homeworks:
                for task in hw.get("tasks", []):
                    gr = task.get("gameResults") or {}
                    pct = gr.get("percentage", 0) if gr else 0
                    try:
                        if int(pct) >= 100:
                            continue
                    except (ValueError, TypeError):
                        pass
                    jobs.append((hw, task))

            if not jobs:
                await interaction.response.edit_message(
                    content="✅ Nothing left to do!", embed=None, view=None
                )
                return

            await interaction.response.edit_message(
                content=f"⏳ Queuing **{len(jobs)}** incomplete task(s) across all assignments…",
                embed=None,
                view=None,
            )
            await view.run_jobs(interaction, jobs)
            return

        # Find the chosen homework
        hw_id_str = chosen
        target_hw = next(
            (h for h in self.homeworks if str(h.get("id", "")) == hw_id_str),
            None,
        )
        if not target_hw:
            await interaction.response.edit_message(
                content="❌ Homework not found.", embed=None, view=None
            )
            return

        # Move to task selector
        task_view = DoTaskView(target_hw, view.cog, view.guild_id, view.user_id)
        embed = task_view.build_embed()
        await interaction.response.edit_message(
            content=None, embed=embed, view=task_view
        )


class DoHomeworkView(ui.View):
    """Step 1 view: pick a homework."""

    def __init__(
        self,
        homeworks: list[dict],
        cog: "BotCommands",
        guild_id: int,
        user_id: int,
    ):
        super().__init__(timeout=180)
        self.homeworks = homeworks
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.add_item(HomeworkSelect(homeworks))

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This menu isn't for you.", ephemeral=True
            )
            return False
        return True

    async def run_jobs(
        self,
        interaction: Interaction,
        jobs: list[tuple[dict, dict]],
    ):
        """Execute a list of (homework, task) pairs."""
        await _execute_jobs(interaction, jobs, self.cog, self.guild_id)

    @ui.button(label="✖ Cancel", style=ButtonStyle.danger, row=1)
    async def cancel_btn(self, interaction: Interaction, _: ui.Button):
        await interaction.response.edit_message(
            content="Cancelled.", embed=None, view=None
        )


# ============================================================
# /do  —  STEP 2: Task multi-selector within a homework
# ============================================================
class TaskSelect(ui.Select):
    """Multi-select dropdown for incomplete tasks in a homework."""

    def __init__(self, homework: dict):
        self.homework = homework
        tasks = homework.get("tasks", [])
        incomplete = []
        for i, t in enumerate(tasks):
            gr = t.get("gameResults") or {}
            pct = gr.get("percentage", 0) if gr else 0
            try:
                if int(pct) >= 100:
                    continue
            except (ValueError, TypeError):
                pass
            incomplete.append((i, t, pct))

        options: list[discord.SelectOption] = [
            discord.SelectOption(
                label="✅ Do ALL tasks in this assignment",
                value="__ALL__",
                description="Complete every incomplete task here",
                emoji="⚡",
            )
        ]

        for idx, task, pct in incomplete[:24]:
            task_name = task.get("translation", "Unknown")
            label = task_name[:95] if len(task_name) <= 95 else task_name[:92] + "..."
            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(idx),
                    description=f"{pct}% complete",
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
        chosen = self.values
        tasks = self.homework.get("tasks", [])

        jobs: list[tuple[dict, dict]] = []

        if "__ALL__" in chosen:
            for task in tasks:
                gr = task.get("gameResults") or {}
                pct = gr.get("percentage", 0) if gr else 0
                try:
                    if int(pct) >= 100:
                        continue
                except (ValueError, TypeError):
                    pass
                jobs.append((self.homework, task))
        else:
            for val in chosen:
                try:
                    idx = int(val)
                except ValueError:
                    continue
                if 0 <= idx < len(tasks):
                    jobs.append((self.homework, tasks[idx]))

        if not jobs:
            await interaction.response.edit_message(
                content="❌ No valid tasks selected.", embed=None, view=None
            )
            return

        await interaction.response.edit_message(
            content=f"⏳ Queuing **{len(jobs)}** task(s)…",
            embed=None,
            view=None,
        )
        await _execute_jobs(interaction, jobs, view.cog, view.guild_id)


class DoTaskView(ui.View):
    """Step 2 view: pick tasks within a homework."""

    def __init__(
        self,
        homework: dict,
        cog: "BotCommands",
        guild_id: int,
        user_id: int,
    ):
        super().__init__(timeout=180)
        self.homework = homework
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id
        self.add_item(TaskSelect(homework))

    def build_embed(self) -> discord.Embed:
        hw = self.homework
        name = hw.get("name", "Unnamed")
        tasks = hw.get("tasks", [])
        total = len(tasks)
        done = sum(
            1
            for t in tasks
            if t.get("gameResults") and t["gameResults"].get("percentage", 0) == 100
        )
        pct_overall = round((done / total * 100) if total else 0)
        filled = round(pct_overall / 10)
        bar = "█" * filled + "░" * (10 - filled)

        embed = discord.Embed(
            title=f"📖 {name}",
            description=(
                f"`{bar}` **{pct_overall}%** complete ({done}/{total} tasks done)\n\n"
                "Select which tasks to complete below."
            ),
            color=discord.Color.orange(),
        )

        incomplete = [
            t for t in tasks
            if not (t.get("gameResults") and t["gameResults"].get("percentage", 0) == 100)
        ]
        if incomplete:
            lines = []
            for task in incomplete[:10]:
                gr = task.get("gameResults") or {}
                pct = gr.get("percentage", 0) if gr else 0
                task_name = task.get("translation", "Unknown")
                if len(task_name) > 40:
                    task_name = task_name[:37] + "..."
                lines.append(f"📝 `{pct}%` — {task_name}")
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
            await interaction.response.send_message(
                "This menu isn't for you.", ephemeral=True
            )
            return False
        return True

    @ui.button(label="◀ Back", style=ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: Interaction, _: ui.Button):
        # Go back to homework selector
        view = DoHomeworkView(
            self.cog._hw_cache.get(self.guild_id, (0, []))[1],
            self.cog,
            self.guild_id,
            self.user_id,
        )
        embed = discord.Embed(
            title="📚 Select a Homework",
            description="Choose an assignment to work on.",
            color=discord.Color.blue(),
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="✖ Cancel", style=ButtonStyle.danger, row=1)
    async def cancel_btn(self, interaction: Interaction, _: ui.Button):
        await interaction.response.edit_message(
            content="Cancelled.", embed=None, view=None
        )


# ============================================================
# SHARED JOB EXECUTOR
# ============================================================
async def _execute_jobs(
    interaction: Interaction,
    jobs: list[tuple[dict, dict]],
    cog: "BotCommands",
    guild_id: int,
) -> None:
    """Run (homework, task) jobs concurrently and post a result embed."""
    client = await cog._get_api_client(guild_id)
    if not client:
        await interaction.followup.send("❌ Not logged in.", ephemeral=True)
        return

    settings = config.get_guild_settings(guild_id)
    concurrency = max(1, min(settings["concurrency"], 8))
    max_retries = settings["retry_attempts"] if settings["auto_retry"] else 0
    sem = asyncio.Semaphore(concurrency)

    async def run_one(hw: dict, t_obj: dict) -> tuple[str, str, bool, str]:
        hw_name = hw.get("name", "Unnamed")
        task_name = t_obj.get("translation", "Unknown")
        game_link = t_obj.get("gameLink", "")
        async with sem:
            attempt = 0
            while True:
                attempt += 1
                try:
                    data = await client.fetch_task_data(t_obj, game_link)
                    if not data:
                        return hw_name, task_name, False, "No data for task"
                    result = await client.submit_score(t_obj, data)
                    if result.get("error"):
                        body = result.get("body", result)
                        if attempt <= max_retries:
                            await asyncio.sleep(1.5 * attempt)
                            continue
                        return hw_name, task_name, False, str(body)[:120]
                    return hw_name, task_name, True, ""
                except Exception as e:
                    logger.exception("Task automation failed")
                    if attempt <= max_retries:
                        await asyncio.sleep(1.5 * attempt)
                        continue
                    return hw_name, task_name, False, str(e)[:120]

    results = await asyncio.gather(
        *(run_one(hw, t) for hw, t in jobs), return_exceptions=False
    )

    ok = [r for r in results if r[2]]
    bad = [r for r in results if not r[2]]

    embed = discord.Embed(
        title=f"{'✅' if not bad else '⚠️'} Task Results",
        description=f"**{len(ok)}/{len(results)}** tasks completed successfully.",
        color=discord.Color.green() if not bad else discord.Color.orange(),
    )

    if ok:
        ok_lines = []
        for hw_name, task_name, _, _ in ok[:15]:
            ok_lines.append(f"✅ **{task_name}** *(in {hw_name[:30]})*")
        if len(ok) > 15:
            ok_lines.append(f"*…and {len(ok) - 15} more ✅*")
        embed.add_field(
            name=f"✅ Completed ({len(ok)})",
            value="\n".join(ok_lines),
            inline=False,
        )

    if bad:
        bad_lines = []
        for hw_name, task_name, _, err in bad[:10]:
            bad_lines.append(f"❌ **{task_name}** — `{err}`")
        embed.add_field(
            name=f"❌ Failed ({len(bad)})",
            value="\n".join(bad_lines),
            inline=False,
        )

    embed.set_footer(text="Cache refreshed — use /homework to see updated progress.")

    # Invalidate cache so stats refresh next fetch
    cog._hw_cache.pop(guild_id, None)

    try:
        await interaction.followup.send(embed=embed, ephemeral=True)
    except discord.HTTPException:
        await interaction.followup.send(
            content=f"✅ {len(ok)}/{len(results)} tasks done.",
            ephemeral=True,
        )


# ============================================================
# MAIN COG
# ============================================================
class BotCommands(commands.Cog):
    """Unified cog: user + admin commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> (timestamp, homeworks)
        self._hw_cache: dict[int, tuple[float, list[dict]]] = {}
        # guild_id -> asyncio.Lock for serializing client refresh
        self._locks: dict[int, asyncio.Lock] = {}

    # -----------------------------------------
    # Internal helpers
    # -----------------------------------------
    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        lock = self._locks.get(guild_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[guild_id] = lock
        return lock

    async def _get_api_client(self, guild_id: int) -> Optional[LNApiClient]:
        """Build authenticated API client with token refresh on failure."""
        account = config.get_account(guild_id)
        if not account:
            return None

        settings = config.get_guild_settings(guild_id)
        stealth = StealthManager(
            speed=settings["speed"],
            min_accuracy=settings["min_accuracy"],
            max_accuracy=settings["max_accuracy"],
        )

        client = LNApiClient(self.bot.aiohttp_session, stealth)
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
                        "assignmentController/getViewableAll",
                        {"token": token},
                    )
                    if not test.get("error"):
                        return client
                except Exception:
                    logger.exception("Token validation failed")

            if not username or not password:
                logger.warning(f"No stored credentials for guild {guild_id}")
                return None

            logger.info(f"Re-logging in for guild {guild_id}")
            new_token = await client.login(username, password)

            if new_token:
                config.update_token(guild_id, new_token)
                self._hw_cache.pop(guild_id, None)
                return client
            return None

    async def _get_homeworks_cached(
        self, guild_id: int, client: LNApiClient, *, force: bool = False
    ) -> list[dict]:
        """Fetch homeworks with a short TTL cache to speed up autocomplete."""
        now = time.monotonic()
        cached = self._hw_cache.get(guild_id)
        if not force and cached and (now - cached[0]) < HOMEWORK_CACHE_TTL:
            return cached[1]

        discoverer = HomeworkDiscoverer(client)
        try:
            homeworks = await discoverer.get_all_homeworks(client.token)
        except Exception:
            logger.exception("Homework fetch failed")
            if cached:
                return cached[1]
            return []

        self._hw_cache[guild_id] = (now, homeworks)
        return homeworks

    # =========================================================
    # LOGIN / LOGOUT
    # =========================================================
    @app_commands.command(
        name="login",
        description="Log in to LanguageNut and securely store credentials",
    )
    @app_commands.describe(
        username="Your LanguageNut username/email",
        password="Your LanguageNut password",
    )
    async def login(
        self,
        interaction: Interaction,
        username: str,
        password: str,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if interaction.guild_id is None:
            await interaction.followup.send(
                "❌ Must be used in a guild.", ephemeral=True
            )
            return

        settings = config.get_guild_settings(interaction.guild_id)
        stealth = StealthManager(speed=settings["speed"])
        client = LNApiClient(self.bot.aiohttp_session, stealth)

        token = await client.login(username, password)
        if not token:
            await interaction.followup.send(
                "❌ Login failed. Check your username and password.",
                ephemeral=True,
            )
            return

        fernet = self.bot.fernet
        enc_user = encrypt_value(fernet, username)
        enc_pass = encrypt_value(fernet, password)

        config.set_account(interaction.guild_id, enc_user, enc_pass, token)
        self._hw_cache.pop(interaction.guild_id, None)

        logger.info(f"User logged in for guild {interaction.guild_id}")
        await interaction.followup.send(
            "✅ Login successful! Credentials stored securely.\n"
            "Use `/homework` to view assignments.",
            ephemeral=True,
        )

    @app_commands.command(
        name="logout",
        description="Remove stored LanguageNut credentials",
    )
    async def logout(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if interaction.guild_id is None:
            await interaction.followup.send("❌ Guild only.", ephemeral=True)
            return

        if config.remove_account(interaction.guild_id):
            self._hw_cache.pop(interaction.guild_id, None)
            await interaction.followup.send(
                "✅ Logged out successfully.", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ No credentials stored.", ephemeral=True
            )

    # =========================================================
    # HOMEWORK
    # =========================================================
    @app_commands.command(
        name="homework",
        description="List all homework assignments with progress",
    )
    async def homework(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if interaction.guild_id is None:
            await interaction.followup.send("❌ Guild only.", ephemeral=True)
            return

        client = await self._get_api_client(interaction.guild_id)
        if not client:
            await interaction.followup.send(
                "❌ Not logged in. Use `/login` first.", ephemeral=True
            )
            return

        homeworks = await self._get_homeworks_cached(
            interaction.guild_id, client, force=True
        )
        if not homeworks:
            await interaction.followup.send("📭 No homework found.", ephemeral=True)
            return

        view = HomeworkPaginator(homeworks, interaction.user.id)
        await interaction.followup.send(
            embed=view.build_embed(), view=view, ephemeral=True
        )

    # =========================================================
    # DO TASK(S) — smooth dropdown UI
    # =========================================================
    @app_commands.command(
        name="do",
        description="Complete homework tasks using an interactive selector",
    )
    async def do_task(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if interaction.guild_id is None:
            await interaction.followup.send("❌ Guild only.", ephemeral=True)
            return

        client = await self._get_api_client(interaction.guild_id)
        if not client:
            await interaction.followup.send("❌ Not logged in. Use `/login` first.", ephemeral=True)
            return

        homeworks = await self._get_homeworks_cached(
            interaction.guild_id, client, force=True
        )

        if not homeworks:
            await interaction.followup.send("📭 No homework found.", ephemeral=True)
            return

        # Filter to only homeworks with incomplete tasks
        incomplete_hws = [
            hw for hw in homeworks
            if any(
                not (t.get("gameResults") and t["gameResults"].get("percentage", 0) == 100)
                for t in hw.get("tasks", [])
            )
        ]

        if not incomplete_hws:
            await interaction.followup.send(
                "✅ All homework is already at 100%! Nothing left to do.",
                ephemeral=True,
            )
            return

        # Count totals
        total_incomplete = sum(
            1
            for hw in incomplete_hws
            for t in hw.get("tasks", [])
            if not (t.get("gameResults") and t["gameResults"].get("percentage", 0) == 100)
        )

        embed = discord.Embed(
            title="📚 Select Homework to Complete",
            description=(
                f"Found **{len(incomplete_hws)}** assignment(s) with "
                f"**{total_incomplete}** incomplete task(s).\n\n"
                "Pick an assignment below, or choose **Do ALL** to run everything at once."
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="Only incomplete tasks (< 100%) are shown.")

        view = DoHomeworkView(
            incomplete_hws,
            self,
            interaction.guild_id,
            interaction.user.id,
        )
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
        await safe_send(
            interaction,
            embed=view.build_embed(interaction.guild_id),
            view=view,
        )

    # =========================================================
    # STATUS
    # =========================================================
    @app_commands.command(name="status", description="Show bot status")
    async def status_cmd(self, interaction: Interaction):
        embed = discord.Embed(
            title="🤖 Bot Status",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Servers", value=str(len(self.bot.guilds)))
        embed.add_field(name="Users", value=str(len(self.bot.users)))
        embed.add_field(
            name="Latency", value=f"{round(self.bot.latency * 1000)}ms"
        )
        embed.add_field(name="Python", value=platform.python_version())
        embed.add_field(name="Discord.py", value=discord.__version__)
        if interaction.guild_id is not None:
            acct = config.get_account(interaction.guild_id)
            embed.add_field(
                name="Logged in", value="✅" if acct else "❌", inline=True
            )
        await safe_send(interaction, embed=embed)

    # =========================================================
    # ============== ADMIN COMMANDS ===========================
    # =========================================================
    @app_commands.command(name="restart", description="Restart the bot (owner)")
    @owner_only()
    async def restart_cmd(self, interaction: Interaction):
        await safe_send(interaction, "♻️ Restarting bot...")
        await self.bot.close()
        os.execv(sys.executable, [sys.executable] + sys.argv)

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
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @app_commands.command(
        name="clear", description="Delete recent messages (owner)"
    )
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
            await interaction.followup.send(
                f"🗑️ Deleted {len(deleted)} messages", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ I don't have permission to delete messages.", ephemeral=True
            )

    @app_commands.command(name="logs", description="Show last 20 log lines (owner)")
    @owner_only()
    async def logs_cmd(self, interaction: Interaction):
        log_paths = ["logs/bot.log", "bot.log"]
        log_file = next((p for p in log_paths if os.path.exists(p)), None)
        if not log_file:
            await safe_send(interaction, "❌ No log file found.")
            return
        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-20:]
            content = "".join(lines)
            if len(content) > 1800:
                content = content[-1800:]
            await safe_send(interaction, f"```{content}```")
        except OSError as e:
            await safe_send(interaction, f"❌ Read failed: {e}")

    @app_commands.command(name="reload", description="Reload a cog (owner)")
    @owner_only()
    @app_commands.describe(cog="Cog name (e.g. 'commands' or 'commands.commands')")
    async def reload_cmd(self, interaction: Interaction, cog: str):
        await interaction.response.defer(ephemeral=True)
        candidates = [cog, f"commands.{cog}"] if "." not in cog else [cog]
        last_err = None
        for name in candidates:
            try:
                await self.bot.reload_extension(name)
                await interaction.followup.send(
                    f"✅ Reloaded `{name}`", ephemeral=True
                )
                return
            except Exception as e:
                last_err = e
                continue
        await interaction.followup.send(
            f"❌ Reload failed: {last_err}", ephemeral=True
        )

    @app_commands.command(name="eval", description="Eval python (owner)")
    @owner_only()
    @app_commands.describe(code="Python expression or statements")
    async def eval_cmd(self, interaction: Interaction, code: str):
        await interaction.response.defer(ephemeral=True)
        env: dict[str, Any] = {
            "bot": self.bot,
            "discord": discord,
            "interaction": interaction,
            "asyncio": asyncio,
        }
        try:
            body = "\n".join(f"    {line}" for line in code.split("\n"))
            exec(f"async def __ex():\n{body}", env)
            result = await env["__ex"]()
            await interaction.followup.send(
                f"```\n{str(result)[:1900]}\n```", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ {type(e).__name__}: {e}", ephemeral=True)

    @app_commands.command(name="online", description="Announce ONLINE (owner)")
    @owner_only()
    async def online_cmd(self, interaction: Interaction):
        await interaction.response.send_message("@everyone BOT IS ONLINE 🟢")

    @app_commands.command(name="offline", description="Announce OFFLINE (owner)")
    @owner_only()
    async def offline_cmd(self, interaction: Interaction):
        await interaction.response.send_message("@everyone BOT IS OFFLINE 🔴")


async def setup(bot: commands.Bot):
    await bot.add_cog(BotCommands(bot))