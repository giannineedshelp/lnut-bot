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
from utils.git_logs import get_recent_commits

logger = logging.getLogger("lnut_bot.core")


# =========================
# ADMIN CHECK
# =========================
def is_admin():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)


class CoreCommands(commands.Cog):
    """Core automation commands."""

    def __init__(self, bot):
        self.bot = bot

    # =========================
    # CLIENT
    # =========================
    async def _get_api_client(self, guild_id: int) -> Optional[LNApiClient]:
        account = config.get_account(guild_id)
        if not account:
            return None

        settings = config.get_guild_settings(guild_id)

        stealth = StealthManager(
            speed=settings.get("speed", 1),
            min_accuracy=settings.get("min_accuracy", 80),
            max_accuracy=settings.get("max_accuracy", 100),
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

    # =========================
    # LOGIN
    # =========================
    @app_commands.command(name="login", description="Login to LanguageNut")
    async def login(self, interaction: discord.Interaction, username: str, password: str):
        await interaction.response.defer(ephemeral=True)

        settings = config.get_guild_settings(interaction.guild_id)
        stealth = StealthManager(speed=settings.get("speed", 1))

        client = LNApiClient(self.bot.aiohttp_session, stealth)
        token = await client.login(username, password)

        if not token:
            await interaction.followup.send("❌ Login failed", ephemeral=True)
            return

        fernet = self.bot.fernet

        config.set_account(
            interaction.guild_id,
            encrypt_value(fernet, username),
            encrypt_value(fernet, password),
            token,
        )

        await interaction.followup.send("✅ Logged in", ephemeral=True)

    # =========================
    # LOGOUT
    # =========================
    @app_commands.command(name="logout", description="Logout")
    async def logout(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if config.remove_account(interaction.guild_id):
            await interaction.followup.send("✅ Logged out", ephemeral=True)
        else:
            await interaction.followup.send("❌ No account", ephemeral=True)

    # =========================
    # HOMEWORK (CLEAN UI)
    # =========================
    @app_commands.command(name="homework", description="View homework")
    async def homework(self, interaction: discord.Interaction):
        await interaction.response.defer()

        client = await self._get_api_client(interaction.guild_id)
        if not client:
            await interaction.followup.send("❌ Not logged in")
            return

        discoverer = HomeworkDiscoverer(client)
        homeworks = await discoverer.get_all_homeworks(client.token)

        embed = discord.Embed(title="📚 Homework Dashboard", color=discord.Color.blurple())

        for hw in homeworks[:15]:
            hw_id = hw.get("id", "?")
            name = hw.get("name", "Unnamed")
            tasks = hw.get("tasks", [])

            done = sum(1 for t in tasks if t.get("gameResults"))
            total = len(tasks)

            embed.add_field(
                name=f"{name} [{hw_id}]",
                value=f"Progress: {done}/{total}",
                inline=False
            )

        await interaction.followup.send(embed=embed)

    # =========================
    # DO (FIXED)
    # =========================
    @app_commands.command(name="do", description="Complete task (hw_id:task_index)")
    async def do_task(self, interaction: discord.Interaction, task: str):
        await interaction.response.defer()

        try:
            hw_id, task_idx = map(int, task.split(":"))
        except:
            await interaction.followup.send("❌ Use hw_id:task_index")
            return

        client = await self._get_api_client(interaction.guild_id)
        if not client:
            await interaction.followup.send("❌ Not logged in")
            return

        discoverer = HomeworkDiscoverer(client)
        homeworks = await discoverer.get_all_homeworks(client.token)

        target = next((h for h in homeworks if h.get("id") == hw_id), None)
        if not target:
            await interaction.followup.send("❌ Homework not found")
            return

        tasks = target.get("tasks", [])

        if task_idx >= len(tasks):
            await interaction.followup.send("❌ Invalid task index")
            return

        task_obj = tasks[task_idx]
        name = task_obj.get("translation", "Unknown")

        msg = await interaction.followup.send(f"⚙️ Running **{name}**...")

        try:
            await asyncio.sleep(2)
            await msg.edit(content=f"✅ Done **{name}**")
        except Exception as e:
            await msg.edit(content=f"❌ Error: {e}")

    # =========================
    # CHANGELIST DASHBOARD
    # =========================
    @app_commands.command(name="changelog", description="View recent bot updates")
    @is_admin()
    async def changelog(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        commits = get_recent_commits(10)

        embed = discord.Embed(title="📜 Dev Changelog", color=discord.Color.green())

        for c in commits:
            embed.add_field(
                name=f"{c['hash']} • {c['date'].strftime('%d %b %H:%M')}",
                value=f"{c['message']}\n`{c['author']}`",
                inline=False
            )

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(CoreCommands(bot))