import logging
from typing import Any, Iterable

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("lnut_bot.core")


class Core(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _session(self):
        session = getattr(self.bot, "aiohttp_session", None) or getattr(
            self.bot,
            "session",
            None,
        )
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
    def _iter_tasks(homeworks: Iterable[dict[str, Any]]) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:
        for homework in homeworks:
            tasks = homework.get("tasks", [])
            if not isinstance(tasks, list):
                continue

            for task in tasks:
                if not isinstance(task, dict):
                    continue

                merged = dict(task)
                for key in ("languageCode", "ietf", "toietf", "toLanguage"):
                    if key not in merged and key in homework:
                        merged[key] = homework[key]

                yield homework, merged

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

    @classmethod
    def _task_matches(cls, task: dict[str, Any], task_id: str) -> bool:
        candidates = {
            str(task.get(key))
            for key in ("uid", "catalog_uid", "catalogUid", "game_uid", "gameUid", "rel_module_uid")
            if task.get(key)
        }

        base = task.get("base")
        if isinstance(base, list):
            candidates.update(str(value) for value in base if value)

        candidates.add(cls._task_id(task))
        return task_id in candidates

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
        ok = await api.login(account["username"], password)
        if not ok:
            await self._send(interaction, "LanguageNut login failed.")
            return None

        return api

    @app_commands.command(name="ping", description="Test bot response")
    async def ping(self, interaction: discord.Interaction):
        log.info("Received /ping from %s", interaction.user)
        await self._send(interaction, "Pong. Bot is working.")

    @app_commands.command(name="debug", description="Check bot systems")
    async def debug(self, interaction: discord.Interaction):
        log.info("Received /debug from %s", interaction.user)
        await self._defer(interaction)

        session = getattr(self.bot, "aiohttp_session", None) or getattr(self.bot, "session", None)
        status = [
            f"Bot latency: {round(self.bot.latency * 1000)}ms",
            f"HTTP session active: {session is not None and not session.closed}",
            f"Loaded commands: {', '.join(sorted(command.name for command in self.bot.tree.get_commands()))}",
            f"User: {interaction.user}",
            "Core loaded: True",
        ]

        await self._send(interaction, "```" + "\n".join(status) + "```")

    @app_commands.command(name="homework", description="List available homework tasks")
    async def homework(self, interaction: discord.Interaction):
        log.info("Received /homework from %s", interaction.user)
        await self._defer(interaction)

        try:
            api = await self._login_api(interaction)
            if api is None:
                return

            homeworks = self._homework_list(await api.get_homeworks())
            if not homeworks:
                await self._send(interaction, "No homework was found for this account.")
                return

            lines = [f"Found {len(homeworks)} homework item(s):"]
            for index, (homework, task) in enumerate(self._iter_tasks(homeworks), start=1):
                if index > 15:
                    lines.append("More tasks are available, but only the first 15 are shown.")
                    break

                homework_name = homework.get("name") or homework.get("title") or "Homework"
                task_name = task.get("name") or task.get("title") or task.get("type") or "Task"
                lines.append(f"{index}. {homework_name} - {task_name} - id: {self._task_id(task)}")

            await self._send(interaction, "\n".join(lines))

        except Exception as exc:
            log.exception("/homework failed")
            await self._send(interaction, f"Homework failed:\n```{exc}```")

    @app_commands.command(name="do", description="Run a homework task by task id")
    @app_commands.describe(task_id="Task id shown by /homework")
    async def do(self, interaction: discord.Interaction, task_id: str):
        log.info("Received /do from %s", interaction.user)
        await self._defer(interaction)

        completer = None
        try:
            from automation.task_handler import TaskCompleter
            from config import get_user_settings

            api = await self._login_api(interaction)
            if api is None:
                return

            homeworks = self._homework_list(await api.get_homeworks())
            task = None
            homework = None

            for candidate_homework, candidate_task in self._iter_tasks(homeworks):
                if self._task_matches(candidate_task, task_id):
                    homework = candidate_homework
                    task = candidate_task
                    break

            if task is None:
                await self._send(interaction, f"Task id `{task_id}` was not found. Run `/homework` for current task ids.")
                return

            settings = get_user_settings(str(interaction.user.id))
            language = (
                task.get("languageCode")
                or task.get("ietf")
                or task.get("toietf")
                or homework.get("languageCode")
                or "es-ES"
            )

            completer = TaskCompleter(
                token=api.token,
                task=task,
                ietf=language,
                speed_ms=settings["speed"],
                accuracy_min=settings["accuracy_min"],
                accuracy_max=settings["accuracy_max"],
            )

            answers = await completer.get_data()
            if not answers:
                await self._send(interaction, "No answer data was found for that task.")
                return

            result = await completer.send_answers(answers)
            score = result.get("score", 0) if isinstance(result, dict) else 0
            await self._send(interaction, f"Done. Score: {score}")

        except Exception as exc:
            log.exception("/do failed")
            await self._send(interaction, f"Task failed:\n```{exc}```")

        finally:
            if completer is not None:
                try:
                    await completer.close()
                except Exception:
                    log.exception("Failed to close task completer")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        command_name = interaction.data.get("name") if isinstance(interaction.data, dict) else None
        if command_name:
            log.info("Interaction received: /%s", command_name)


async def setup(bot: commands.Bot):
    log.info("Loading Core cog")
    await bot.add_cog(Core(bot))
    log.info("Core cog loaded")
