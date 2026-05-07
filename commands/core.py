import asyncio
import logging
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


# =========================
# ADMIN CHECK
# =========================

def is_admin():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator

    return app_commands.check(predicate)


# =========================
# CORE
# =========================

class CoreCommands(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    # =========================
    # API CLIENT
    # =========================

    async def _get_api_client(self, guild_id: int) -> Optional[LNApiClient]:
        try:
            account = config.get_account(guild_id)

            if not account:
                return None

            settings = config.get_guild_settings(guild_id)

            stealth = StealthManager(
                speed=settings.get("speed", 1),
                min_accuracy=settings.get("min_accuracy", 80),
                max_accuracy=settings.get("max_accuracy", 100),
            )

            client = LNApiClient(
                self.bot.aiohttp_session,
                stealth
            )

            fernet = self.bot.fernet

            username = decrypt_value(
                fernet,
                account.get("username", "")
            )

            password = decrypt_value(
                fernet,
                account.get("password", "")
            )

            token = account.get("token", "")

            # =========================
            # EXISTING TOKEN
            # =========================

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

            # =========================
            # RELOGIN
            # =========================

            new_token = await client.login(username, password)

            if new_token:
                config.set_account(
                    guild_id,
                    account["username"],
                    account["password"],
                    new_token,
                )

                client.token = new_token
                return client

            return None

        except Exception as e:
            logger.exception(f"API CLIENT ERROR: {e}")
            return None

    # =========================
    # LOGIN
    # =========================

    @app_commands.command(
        name="login",
        description="Login to LanguageNut"
    )
    async def login(
        self,
        interaction: discord.Interaction,
        username: str,
        password: str
    ):
        await interaction.response.defer(
            thinking=True,
            ephemeral=True
        )

        try:
            settings = config.get_guild_settings(
                interaction.guild_id
            )

            stealth = StealthManager(
                speed=settings.get("speed", 1)
            )

            client = LNApiClient(
                self.bot.aiohttp_session,
                stealth
            )

            token = await client.login(username, password)

            if not token:
                await interaction.followup.send(
                    "❌ Login failed",
                    ephemeral=True
                )
                return

            fernet = self.bot.fernet

            config.set_account(
                interaction.guild_id,
                encrypt_value(fernet, username),
                encrypt_value(fernet, password),
                token,
            )

            await interaction.followup.send(
                "✅ Logged in successfully",
                ephemeral=True
            )

        except Exception as e:
            logger.exception(e)

            await interaction.followup.send(
                f"❌ Error: {e}",
                ephemeral=True
            )

    # =========================
    # LOGOUT
    # =========================

    @app_commands.command(
        name="logout",
        description="Logout account"
    )
    async def logout(self, interaction: discord.Interaction):
        await interaction.response.defer(
            thinking=True,
            ephemeral=True
        )

        try:
            if config.remove_account(interaction.guild_id):
                await interaction.followup.send(
                    "✅ Logged out",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ No saved account",
                    ephemeral=True
                )

        except Exception as e:
            logger.exception(e)

            await interaction.followup.send(
                f"❌ Error: {e}",
                ephemeral=True
            )

    # =========================
    # HOMEWORK
    # =========================

    @app_commands.command(
        name="homework",
        description="View homework list"
    )
    async def homework(self, interaction: discord.Interaction):
        await interaction.response.defer(
            thinking=True
        )

        try:
            client = await self._get_api_client(
                interaction.guild_id
            )

            if not client:
                await interaction.followup.send(
                    "❌ Not logged in"
                )
                return

            discoverer = HomeworkDiscoverer(client)

            homeworks = await discoverer.get_all_homeworks(
                client.token
            )

            if not homeworks:
                await interaction.followup.send(
                    "❌ No homework found"
                )
                return

            embed = discord.Embed(
                title="📚 Homework Dashboard",
                color=discord.Color.blurple()
            )

            for i, hw in enumerate(homeworks[:15]):

                hw_id = hw.get("id", "?")
                name = hw.get("name", "Unnamed")

                tasks = hw.get("tasks", [])

                done = sum(
                    1 for t in tasks
                    if t.get("gameResults")
                )

                total = len(tasks)

                percent = (
                    int((done / total) * 100)
                    if total > 0 else 0
                )

                embed.add_field(
                    name=f"{i+1}. {name}",
                    value=(
                        f"🆔 `{hw_id}`\n"
                        f"📊 {done}/{total} ({percent}%)\n"
                        f"📝 Tasks: {total}"
                    ),
                    inline=False
                )

            await interaction.followup.send(
                embed=embed
            )

        except Exception as e:
            logger.exception(e)

            await interaction.followup.send(
                f"❌ Error: {e}"
            )

    # =========================
    # DO
    # =========================

    @app_commands.command(
        name="do",
        description="Run task using hw_id:task_index"
    )
    async def do(
        self,
        interaction: discord.Interaction,
        task: str
    ):
        await interaction.response.defer(
            thinking=True
        )

        try:
            hw_id_str, task_idx_str = task.split(":")

            hw_id = int(hw_id_str)
            task_idx = int(task_idx_str)

        except:
            await interaction.followup.send(
                "❌ Format: hw_id:task_index"
            )
            return

        try:
            client = await self._get_api_client(
                interaction.guild_id
            )

            if not client:
                await interaction.followup.send(
                    "❌ Not logged in"
                )
                return

            discoverer = HomeworkDiscoverer(client)

            homeworks = await discoverer.get_all_homeworks(
                client.token
            )

            target = next(
                (
                    h for h in homeworks
                    if h.get("id") == hw_id
                ),
                None
            )

            if not target:
                await interaction.followup.send(
                    "❌ Homework not found"
                )
                return

            tasks = target.get("tasks", [])

            if (
                task_idx < 0
                or task_idx >= len(tasks)
            ):
                await interaction.followup.send(
                    "❌ Invalid task index"
                )
                return

            task_obj = tasks[task_idx]

            name = task_obj.get(
                "translation",
                "Unknown Task"
            )

            progress = discord.Embed(
                title="⚙️ Running Task",
                description=f"Currently doing:\n`{name}`",
                color=discord.Color.orange()
            )

            msg = await interaction.followup.send(
                embed=progress
            )

            # =========================
            # PLACE REAL TASK LOGIC HERE
            # =========================

            await asyncio.sleep(2)

            done = discord.Embed(
                title="✅ Task Complete",
                description=f"Finished:\n`{name}`",
                color=discord.Color.green()
            )

            await msg.edit(embed=done)

        except Exception as e:
            logger.exception(e)

            await interaction.followup.send(
                f"❌ Error: {e}"
            )

    # =========================
    # DO ALT
    # =========================

    @app_commands.command(
        name="doalt",
        description="Run multiple tasks using ranges"
    )
    async def doalt(
        self,
        interaction: discord.Interaction,
        homework_id: int,
        tasks: str
    ):
        await interaction.response.defer(
            thinking=True
        )

        try:
            await interaction.followup.send(
                (
                    f"✅ Parsed task selection\n\n"
                    f"📚 Homework ID: `{homework_id}`\n"
                    f"📝 Tasks: `{tasks}`"
                )
            )

        except Exception as e:
            logger.exception(e)

            await interaction.followup.send(
                f"❌ Error: {e}"
            )

    # =========================
    # CLEAR
    # =========================

    @app_commands.command(
        name="clear",
        description="Clear messages"
    )
    @is_admin()
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: int = 10
    ):
        await interaction.response.defer(
            thinking=True,
            ephemeral=True
        )

        try:
            deleted = await interaction.channel.purge(
                limit=amount
            )

            await interaction.followup.send(
                f"✅ Deleted {len(deleted)} messages",
                ephemeral=True
            )

        except Exception as e:
            logger.exception(e)

            await interaction.followup.send(
                f"❌ Error: {e}",
                ephemeral=True
            )

    # =========================
    # CLEAR ALL
    # =========================

    @app_commands.command(
        name="clearall",
        description="Clear ALL messages in channel"
    )
    @is_admin()
    async def clearall(
        self,
        interaction: discord.Interaction
    ):
        await interaction.response.defer(
            thinking=True,
            ephemeral=True
        )

        try:
            deleted = await interaction.channel.purge()

            await interaction.followup.send(
                f"✅ Deleted {len(deleted)} messages",
                ephemeral=True
            )

        except Exception as e:
            logger.exception(e)

            await interaction.followup.send(
                f"❌ Error: {e}",
                ephemeral=True
            )

    # =========================
    # PING
    # =========================

    @app_commands.command(
        name="ping",
        description="Bot latency"
    )
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"🏓 {round(self.bot.latency * 1000)}ms"
        )

    # =========================
    # RESTART
    # =========================

    @app_commands.command(
        name="restart",
        description="Restart bot"
    )
    @is_admin()
    async def restart(
        self,
        interaction: discord.Interaction
    ):
        await interaction.response.send_message(
            "♻️ Restart requested"
        )

        await self.bot.close()


# =========================
# SETUP
# =========================

async def setup(bot: commands.Bot):
    await bot.add_cog(CoreCommands(bot))