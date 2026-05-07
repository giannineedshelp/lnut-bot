import logging
from typing import Any, Iterable

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("lnut_bot.core")


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
                task_name = task.get("name") or task.get("title") or task.get("type") or "Task"
                task_id = cog._task_id(task)
                options.append(
                    discord.SelectOption(
                        label=f"{homework_name[:50]}",
                        description=f"{task_name[:90]}",
                        value=task_id,
                    )
                )

        if options:
            self.add_item(HomeworkSelect(self, options[:25]))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.interaction_user_id

    async def run_tasks(self, interaction: discord.Interaction, task_ids: list[str]):
        await interaction.response.defer(ephemeral=True, thinking=True)
        results = []

        for task_id in task_ids:
            result = await self.cog._complete_task(interaction, self.api, task_id)
            results.append(result)

        await interaction.followup.send("\n".join(results), ephemeral=True)


class HomeworkSelect(discord.ui.Select):
    def __init__(self, parent_view, options):
        super().__init__(
            placeholder="Select homework tasks to complete",
            min_values=1,
            max_values=len(options),
            options=options,
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.selected_task_ids = self.values
        await interaction.response.send_message(
            f"Selected {len(self.values)} task(s). Press 'Do Selected' to start.",
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
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _session(self):
        session = getattr(self.bot, "aiohttp_session", None) or getattr(self.bot, "session", None)
        if session is None or session.closed:
            raise RuntimeError("HTTP session is not ready yet.")
        return session

    async def _defer(self, interaction: discord.Interaction) -> None:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)

    async def _send(self, interaction: discord.Interaction, content: str, **kwargs: Any) -> None:
        if len(content) > 1900:
            content = content[:1890] + "\n... trimmed"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(content, ephemeral=True, **kwargs)
            else:
                await interaction.response.send_message(content, ephemeral=True, **kwargs)
        except discord.HTTPException:
            log.exception("Failed to send interaction response")

    @staticmethod
    def _homework_list(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if not isinstance(data, dict):
            return []
        for key in ("homework", "homeworks", "assignments", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if isinstance(data.get("tasks"), list):
            return [data]
        return []

    @staticmethod
    def _task_progress(task: dict[str, Any]) -> float:
        for key in ("progress", "completion", "percentComplete", "score"):
            value = task.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return 0.0

    @staticmethod
    def _task_completed(task: dict[str, Any]) -> bool:
        return task.get("completed") is True or Core._task_progress(task) >= 100

    @staticmethod
    def _task_id(task: dict[str, Any]) -> str:
        for key in ("uid", "catalog_uid", "catalogUid", "game_uid", "gameUid", "rel_module_uid"):
            value = task.get(key)
            if value:
                return str(value)
        base = task.get("base")
        if isinstance(base, list) and base:
            return str(base[-1])
        return "unknown"

    async def _login_api(self, interaction: discord.Interaction):
        from automation.api_direct import LanguageNutAPI
        from config import get_account, get_decrypted_password

        user_id = str(interaction.user.id)
        account = get_account(user_id)
        if not account:
            await self._send(interaction, "No saved account was found for your Discord user.")
            return None
        password = get_decrypted_password(user_id)
        if not password:
            await self._send(interaction, "Saved password could not be decrypted.")
            return None

        api = LanguageNutAPI(self._session())
        if not await api.login(account["username"], password):
            await self._send(interaction, "LanguageNut login failed.")
            return None
        return api

    async def _complete_task(self, interaction, api, task_id: str):
        from automation.task_handler import TaskCompleter
        from config import get_user_settings

        homeworks = self._homework_list(await api.get_homeworks())
        for homework in homeworks:
            for task in homework.get("tasks", []):
                if self._task_id(task) != task_id:
                    continue
                if self._task_completed(task):
                    return f"Skipped completed task {task_id}"

                settings = get_user_settings(str(interaction.user.id))
                language = task.get("languageCode") or homework.get("languageCode") or "es-ES"

                completer = TaskCompleter(
                    token=api.token,
                    task=task,
                    ietf=language,
                    speed_ms=settings["speed"],
                    accuracy_min=settings["accuracy_min"],
                    accuracy_max=settings["accuracy_max"],
                )
                try:
                    answers = await completer.get_data()
                    if not answers:
                        return f"No answers found for task {task_id}"
                    result = await completer.send_answers(answers)
                    score = result.get("score", 0) if isinstance(result, dict) else 0
                    return f"Completed task {task_id} | Score: {score}"
                finally:
                    await completer.close()
        return f"Task {task_id} not found"

    @app_commands.command(name="homework", description="Interactive homework manager")
    async def homework(self, interaction: discord.Interaction):
        log.info("Received /homework from %s", interaction.user)
        await self._defer(interaction)

        api = await self._login_api(interaction)
        if api is None:
            return

        homeworks = self._homework_list(await api.get_homeworks())
        homework_groups = []

        for homework in homeworks:
            valid_tasks = []
            for task in homework.get("tasks", []):
                if not isinstance(task, dict):
                    continue
                if self._task_completed(task):
                    continue
                valid_tasks.append(task)

            if valid_tasks:
                homework_groups.append({
                    "homework": homework,
                    "tasks": valid_tasks,
                })

        if not homework_groups:
            await self._send(interaction, "No incomplete homework found.")
            return

        view = HomeworkTaskView(self, api, interaction.user.id, homework_groups)
        view.add_item(DoSelectedButton())
        view.add_item(DoAllButton())

        total_tasks = sum(len(group["tasks"]) for group in homework_groups)
        await interaction.followup.send(
            f"Found {total_tasks} incomplete task(s). Select tasks below or use Do All Remaining.",
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="do", description="Run one or multiple homework tasks by task ids")
    @app_commands.describe(task_id="Single task id or comma-separated ids")
    async def do(self, interaction: discord.Interaction, task_id: str):
        log.info("Received /do from %s", interaction.user)
        await self._defer(interaction)

        api = await self._login_api(interaction)
        if api is None:
            return

        task_ids = [tid.strip() for tid in task_id.split(",") if tid.strip()]
        results = []
        for tid in task_ids:
            results.append(await self._complete_task(interaction, api, tid))

        await self._send(interaction, "\n".join(results))


async def setup(bot: commands.Bot):
    log.info("Loading Core cog")
    await bot.add_cog(Core(bot))
    log.info("Core cog loaded")
