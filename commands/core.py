import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("lnut_bot.core")
MAX_SELECT_OPTIONS = 25


class HomeworkTaskView(discord.ui.View):
    def __init__(self, cog, api, interaction_user_id: int, homework_groups: list[dict[str, Any]]):
        super().__init__(timeout=300)
        self.cog = cog
        self.api = api
        self.interaction_user_id = interaction_user_id
        self.homework_groups = homework_groups
        self.selected_task_ids: list[str] = []

        options = []
        for group in homework_groups:
            homework = group["homework"]
            homework_name = homework.get("name") or homework.get("title") or "Homework"
            for task in group["tasks"]:
                if len(options) >= MAX_SELECT_OPTIONS:
                    break
                task_name = task.get("name") or task.get("title") or task.get("type") or "Task"
                task_id = cog._task_id(task)
                options.append(
                    discord.SelectOption(
                        label=homework_name[:100],
                        description=task_name[:100],
                        value=task_id,
                    )
                )

        if options:
            self.add_item(HomeworkSelect(self, options))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.interaction_user_id

    async def run_tasks(self, interaction: discord.Interaction, task_ids: list[str]):
        await interaction.response.defer(ephemeral=True, thinking=True)
        results = []
        for task_id in task_ids:
            results.append(await self.cog._complete_task(interaction, self.api, task_id))
        await interaction.followup.send("\n".join(results)[:1900], ephemeral=True)


class HomeworkSelect(discord.ui.Select):
    def __init__(self, parent_view, options):
        super().__init__(
            placeholder="Select homework tasks",
            min_values=1,
            max_values=min(len(options), MAX_SELECT_OPTIONS),
            options=options,
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.selected_task_ids = list(self.values)
        await interaction.response.send_message(
            f"Selected {len(self.values)} task(s).",
            ephemeral=True,
        )


class DoSelectedButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Do Selected", style=discord.ButtonStyle.green)

    async def callback(self, interaction: discord.Interaction):
        if not self.view.selected_task_ids:
            await interaction.response.send_message("No tasks selected.", ephemeral=True)
            return
        await self.view.run_tasks(interaction, self.view.selected_task_ids)


class DoAllButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Do All Remaining", style=discord.ButtonStyle.blurple)

    async def callback(self, interaction: discord.Interaction):
        task_ids = []
        for group in self.view.homework_groups:
            for task in group["tasks"]:
                task_ids.append(self.view.cog._task_id(task))
        await self.view.run_tasks(interaction, task_ids)


class Core(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _session(self):
        session = getattr(self.bot, "aiohttp_session", None) or getattr(self.bot, "session", None)
        if session is None or session.closed:
            raise RuntimeError("HTTP session is not ready yet.")
        return session

    async def _defer(self, interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)

    async def _send(self, interaction, content: str, **kwargs):
        content = content[:1900]
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=True, **kwargs)
        else:
            await interaction.response.send_message(content, ephemeral=True, **kwargs)

    @staticmethod
    def _homework_list(data):
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("homework", "homeworks", "assignments", "data"):
                if isinstance(data.get(key), list):
                    return [x for x in data[key] if isinstance(x, dict)]
            if isinstance(data.get("tasks"), list):
                return [data]
        return []

    @staticmethod
    def _task_progress(task):
        for key in ("progress", "completion", "percentComplete", "score"):
            value = task.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return 0.0

    @classmethod
    def _task_completed(cls, task):
        return task.get("completed") is True or cls._task_progress(task) >= 100

    @staticmethod
    def _task_id(task):
        for key in ("uid", "catalog_uid", "catalogUid", "game_uid", "gameUid", "rel_module_uid"):
            if task.get(key):
                return str(task[key])
        base = task.get("base")
        if isinstance(base, list) and base:
            return str(base[-1])
        return "unknown"

    async def _login_api(self, interaction):
        from automation.api_direct import LanguageNutAPI
        from config import get_account, get_decrypted_password

        user_id = str(interaction.user.id)
        account = get_account(user_id)
        password = get_decrypted_password(user_id)
        if not account or not password:
            await self._send(interaction, "Saved account details missing.")
            return None

        api = LanguageNutAPI(self._session())
        if not await api.login(account["username"], password):
            await self._send(interaction, "LanguageNut login failed.")
            return None
        return api

    async def _complete_task(self, interaction, api, task_id):
        from automation.task_handler import TaskCompleter
        from config import get_user_settings

        for homework in self._homework_list(await api.get_homeworks()):
            for task in homework.get("tasks", []):
                if self._task_id(task) != task_id:
                    continue
                if self._task_completed(task):
                    return f"Skipped {task_id} (completed)"

                settings = get_user_settings(str(interaction.user.id))
                completer = TaskCompleter(
                    token=api.token,
                    task=task,
                    ietf=task.get("languageCode") or homework.get("languageCode") or "es-ES",
                    speed_ms=settings["speed"],
                    accuracy_min=settings["accuracy_min"],
                    accuracy_max=settings["accuracy_max"],
                )
                try:
                    answers = await completer.get_data()
                    if not answers:
                        return f"No answers for {task_id}"
                    result = await completer.send_answers(answers)
                    return f"Done {task_id} | Score: {result.get('score', 0) if isinstance(result, dict) else 0}"
                finally:
                    await completer.close()
        return f"Task {task_id} not found"

    @app_commands.command(name="homework", description="Interactive homework manager")
    async def homework(self, interaction):
        await self._defer(interaction)
        api = await self._login_api(interaction)
        if not api:
            return

        homework_groups = []
        total_tasks = 0
        for homework in self._homework_list(await api.get_homeworks()):
            tasks = [t for t in homework.get("tasks", []) if isinstance(t, dict) and not self._task_completed(t)]
            if tasks:
                homework_groups.append({"homework": homework, "tasks": tasks})
                total_tasks += len(tasks)

        if not homework_groups:
            await self._send(interaction, "No incomplete homework found.")
            return

        view = HomeworkTaskView(self, api, interaction.user.id, homework_groups)
        view.add_item(DoSelectedButton())
        view.add_item(DoAllButton())

        extra = ""
        if total_tasks > MAX_SELECT_OPTIONS:
            extra = f" Showing first {MAX_SELECT_OPTIONS} in selector. Use /do for others."

        await interaction.followup.send(
            f"Found {total_tasks} incomplete task(s).{extra}",
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="do", description="Run one or multiple homework tasks")
    async def do(self, interaction, task_id: str):
        await self._defer(interaction)
        api = await self._login_api(interaction)
        if not api:
            return
        results = []
        for tid in [x.strip() for x in task_id.split(",") if x.strip()]:
            results.append(await self._complete_task(interaction, api, tid))
        await self._send(interaction, "\n".join(results))


async def setup(bot):
    await bot.add_cog(Core(bot))
