import asyncio
import logging
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import config
from automation.api_direct import LNApiClient
from automation.discover import HomeworkDiscoverer
from automation.stealth import StealthManager
from utils.encryption import decrypt_value, encrypt_value

logger = logging.getLogger("lnut_bot.core")


class CoreCommands(commands.Cog):
    """Core automation commands: login, logout, homework, do."""

    def __init__(self, bot):
        self.bot = bot

    async def _get_api_client(self, guild_id: int) -> Optional[LNApiClient]:
        """Build authenticated API client."""
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
        username = decrypt_value(fernet, account.get("username", ""))
        password = decrypt_value(fernet, account.get("password", ""))

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
                pass

        logger.info(f"Token expired or missing for guild {guild_id}, re-logging in")

        new_token = await client.login(username, password)

        if new_token:
            config.set_account(
                guild_id,
                account["username"],
                account["password"],
                new_token,
            )
            return client

        return None

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
        interaction: discord.Interaction,
        username: str,
        password: str,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        settings = config.get_guild_settings(interaction.guild_id)
        stealth = StealthManager(speed=settings["speed"])

        client = LNApiClient(self.bot.aiohttp_session, stealth)

        token = await client.login(username, password)

        if not token:
            await interaction.followup.send(
                "Login failed. Check your username and password.",
                ephemeral=True,
            )
            return

        fernet = self.bot.fernet
        enc_user = encrypt_value(fernet, username)
        enc_pass = encrypt_value(fernet, password)

        config.set_account(
            interaction.guild_id,
            enc_user,
            enc_pass,
            token,
        )

        logger.info(f"User logged in for guild {interaction.guild_id}")

        await interaction.followup.send(
            "Login successful. Credentials stored securely.\n"
            "Use `/homework` to view assignments.",
            ephemeral=True,
        )

    @app_commands.command(
        name="logout",
        description="Remove stored LanguageNut credentials",
    )
    async def logout(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        if config.remove_account(interaction.guild_id):
            await interaction.followup.send(
                "Logged out successfully.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "No credentials stored.",
                ephemeral=True,
            )

    @app_commands.command(
        name="homework",
        description="List all homework assignments",
    )
    async def homework(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        client = await self._get_api_client(interaction.guild_id)

        if not client:
            await interaction.followup.send(
                "Not logged in. Use `/login` first.",
                ephemeral=True,
            )
            return

        discoverer = HomeworkDiscoverer(client)

        try:
            homeworks = await discoverer.get_all_homeworks(client.token)
        except Exception as e:
            logger.exception("Homework fetch failed")
            await interaction.followup.send(
                f"Error fetching homework: {e}",
                ephemeral=True,
            )
            return

        if not homeworks:
            await interaction.followup.send("No homework found.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Your LanguageNut Homeworks",
            color=discord.Color.blue(),
        )

        for hw in homeworks:
            name = hw.get("name", "Unnamed")
            hw_id = hw.get("id", "?")
            tasks = hw.get("tasks", [])

            completed = sum(
                1 for t in tasks if t.get("gameResults")
            )

            total = len(tasks)
            lines = []

            for i, task in enumerate(tasks[:8]):
                pct = "-"
                if task.get("gameResults"):
                    pct = task["gameResults"].get("percentage", "-")

                task_name = task.get("translation", "Unknown")
                lines.append(f"`[{i}]` {task_name} - **{pct}%**")

            if len(tasks) > 8:
                lines.append(f"*...and {len(tasks)-8} more tasks*")

            embed.add_field(
                name=f"{name} (ID: {hw_id})",
                value=(
                    f"Progress: {completed}/{total}\n"
                    + "\n".join(lines)
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _task_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ):
        client = await self._get_api_client(interaction.guild_id)

        if not client:
            return []

        discoverer = HomeworkDiscoverer(client)

        try:
            homeworks = await discoverer.get_all_homeworks(client.token)
        except Exception:
            return []

        choices = []

        for hw in homeworks:
            hw_id = hw.get("id", 0)
            hw_name = hw.get("name", "Unnamed")

            for i, task in enumerate(hw.get("tasks", [])):
                task_name = task.get("translation", "Unknown")

                pct = 0
                if task.get("gameResults"):
                    pct = task["gameResults"].get("percentage", 0)

                label = f"[{hw_id}:{i}] {hw_name} - {task_name} ({pct}%)"

                if current.lower() in label.lower():
                    choices.append(
                        app_commands.Choice(
                            name=label[:100],
                            value=f"{hw_id}:{i}",
                        )
                    )

                if len(choices) >= 25:
                    break

            if len(choices) >= 25:
                break

        return choices

    @app_commands.command(
        name="do",
        description="Complete a specific task",
    )
    @app_commands.describe(task="Task to complete")
    @app_commands.autocomplete(task=_task_autocomplete)
    async def do_task(
        self,
        interaction: discord.Interaction,
        task: str,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            hw_id, task_idx = task.split(":")
            hw_id = int(hw_id)
            task_idx = int(task_idx)

        except (ValueError, IndexError):
            await interaction.followup.send("Invalid task format.", ephemeral=True)
            return

        client = await self._get_api_client(interaction.guild_id)

        if not client:
            await interaction.followup.send("Not logged in.", ephemeral=True)
            return

        discoverer = HomeworkDiscoverer(client)

        try:
            homeworks = await discoverer.get_all_homeworks(client.token)
        except Exception as e:
            await interaction.followup.send(
                f"Error fetching homework: {e}",
                ephemeral=True,
            )
            return

        target_hw = None

        for hw in homeworks:
            if hw.get("id") == hw_id:
                target_hw = hw
                break

        if not target_hw:
            await interaction.followup.send(
                f"Homework `{hw_id}` not found.",
                ephemeral=True,
            )
            return

        tasks = target_hw.get("tasks", [])

        if task_idx < 0 or task_idx >= len(tasks):
            await interaction.followup.send(
                f"Task index `{task_idx}` invalid.",
                ephemeral=True,
            )
            return

        task_obj = tasks[task_idx]
        task_name = task_obj.get("translation", "Unknown")
        game_link = task_obj.get("gameLink", "")

        msg = await interaction.followup.send(
            f"Working on **{task_name}**...",
            ephemeral=True,
            wait=True,
        )

        try:
            task_data = await client.fetch_task_data(task_obj, game_link)

            if not task_data:
                await msg.edit(content=f"No data found for **{task_name}**.")
                return

            result = await client.submit_score(task_obj, task_data)
            if result.get("error"):
                await msg.edit(
                    content=(
                        f"Failed to submit **{task_name}**: "
                        f"{result.get('body', result)}"
                    )
                )
                return

            await msg.edit(content=f"Successfully completed **{task_name}**.")

        except Exception as e:
            logger.exception("Task automation failed")
            await msg.edit(content=f"Failed to complete **{task_name}**: {e}")
            return


async def setup(bot):
    await bot.add_cog(CoreCommands(bot))
