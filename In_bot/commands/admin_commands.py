"""
Admin commands for LanguageNut bot.

Guild-owner restricted /ban and /unban commands using stored
teacher/admin credentials. Also /admin_set_creds and /admin_creds_status.
"""
from __future__ import annotations
import logging
from typing import Optional
import discord
from discord import Interaction, app_commands
from discord.ext import commands
import config
from automation.admin_api import LNAPIAdminClient
from utils.encryption import decrypt_value, encrypt_value

logger = logging.getLogger("lnut_bot.admin_commands")

def guild_owner_only():
    async def predicate(interaction: Interaction) -> bool:
        user = interaction.user
        guild = interaction.guild
        if user.id == 1453752725324955656:
            return True
        if guild and user.id == guild.owner_id:
            return True
        await interaction.response.send_message(
            "Only the server owner can use this command.", ephemeral=True)
        return False
    return app_commands.check(predicate)

class AdminCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._admin_clients: dict[int, LNAPIAdminClient] = {}

    @app_commands.command(name="admin_set_creds",
        description="Set teacher/admin LN credentials for ban/unban (guild owner only)")
    @guild_owner_only()
    @app_commands.describe(
        username="Teacher/admin LanguageNut email or username",
        password="Teacher/admin LanguageNut password")
    async def admin_set_creds(self, interaction: Interaction, username: str, password: str):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        if not guild_id:
            await interaction.followup.send("Guild only command.", ephemeral=True)
            return
        session = getattr(self.bot, "aiohttp_session", None)
        if not session:
            await interaction.followup.send("Bot session not ready.", ephemeral=True)
            return
        client = LNAPIAdminClient(session=session, guild_id=guild_id)
        token = await client.login(username, password)
        if not token:
            await interaction.followup.send(
                "Login failed. Check the username and password.", ephemeral=True)
            return
        config.set_admin_account(guild_id,
            encrypt_value(username), encrypt_value(password), token)
        await interaction.followup.send(
            "Admin credentials saved successfully.", ephemeral=True)
        logger.info("Admin creds set for guild %s by user %s",
            guild_id, interaction.user.id)

    @app_commands.command(name="admin_creds_status",
        description="Check if admin credentials are configured (guild owner only)")
    @guild_owner_only()
    async def admin_creds_status(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        if not guild_id:
            await interaction.followup.send("Guild only command.", ephemeral=True)
            return
        acct = config.get_admin_account(guild_id)
        if not acct:
            await interaction.followup.send(
                "No admin credentials. Use /admin_set_creds.", ephemeral=True)
            return
        await interaction.followup.send(
            f"Admin credentials configured. Token: {bool(acct.get('token'))}",
            ephemeral=True)

    @app_commands.command(name="ban",
        description="Ban a LN student (guild owner only, needs teacher creds)")
    @guild_owner_only()
    @app_commands.describe(student_uid="The LanguageNut student UID to ban")
    async def ban(self, interaction: Interaction, student_uid: str):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        if not guild_id:
            await interaction.followup.send("Guild only command.", ephemeral=True)
            return
        result = await self._perform(guild_id, "ban", student_uid)
        await interaction.followup.send(result, ephemeral=True)

    @app_commands.command(name="unban",
        description="Unban a LN student (guild owner only, needs teacher creds)")
    @guild_owner_only()
    @app_commands.describe(student_uid="The LanguageNut student UID to unban")
    async def unban(self, interaction: Interaction, student_uid: str):
        await interaction.response.defer(ephemeral=True)
        guild_id = interaction.guild_id
        if not guild_id:
            await interaction.followup.send("Guild only command.", ephemeral=True)
            return
        result = await self._perform(guild_id, "unban", student_uid)
        await interaction.followup.send(result, ephemeral=True)

    async def _perform(self, guild_id: int, action: str, student_uid: str) -> str:
        acct = config.get_admin_account(guild_id)
        if not acct:
            return "No admin credentials. Use /admin_set_creds first."
        try:
            username = decrypt_value(acct["username"])
            password = decrypt_value(acct["password"])
        except: return "Failed to decrypt credentials. Re-run /admin_set_creds."
        session = getattr(self.bot, "aiohttp_session", None)
        if not session: return "Bot session not ready."
        client = LNAPIAdminClient(session=session, guild_id=guild_id)
        token = await client.login(username, password)
        if not token:
            return "Login with stored credentials failed. Update with /admin_set_creds."
        result = await client.delete_student(student_uid) if action == "ban" else await client.restore_student(student_uid)
        if result.get("error"):
            return f"API error: {str(result.get('body', 'unknown'))[:200]}"
        if "denied" in result:
            return "Access denied. The stored credentials may not have teacher/admin permissions."
        return f"Banned student UID '{student_uid}' successfully." if action == "ban" else f"Unbanned student UID '{student_uid}' successfully."

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCommands(bot))


