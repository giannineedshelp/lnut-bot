"""
LanguageNut Bot - Admin/Teacher Management Commands

Requires teacher credentials. Provides ban/unban, student listing,
password resets, and staff management via the LN admin API.

All commands are owner-only.
"""

from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import Interaction, app_commands
from discord.ext import commands

import config
from automation.admin_api import LNAPIAdminClient
from utils.logger import log_user_command

logger = logging.getLogger("lnut_bot.admin_commands")

OWNER_ID = 1453752725324955656


def owner_check():
    async def predicate(interaction: Interaction) -> bool:
        return interaction.user.id == OWNER_ID
    return app_commands.check(predicate)


class AdminCommands(commands.Cog):
    """Teacher/admin management commands for LanguageNut."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._admin_clients: dict[int, LNAdminClient] = {}

    async def _get_admin(self, guild_id: int) -> Optional[LNAdminClient]:
        """Return a cached (and still valid) admin client, or try to
        auto-login with stored credentials."""
        if guild_id in self._admin_clients:
            ac = self._admin_clients[guild_id]
            if await ac.check_auth():
                return ac
            logger.info("Admin session expired for guild %s, reconnecting...", guild_id)
            del self._admin_clients[guild_id]

        stored = config.get_admin_account(guild_id)
        if stored:
            username = stored.get("username", "")
            password = stored.get("password", "")
            if username and password:
                client = LNAPIAdminClient()
                token = await client.login(username, password)
                if token:
                    self._admin_clients[guild_id] = client
                    config.set_admin_account(guild_id, stored["username"], stored["password"], token)
                    return client
                logger.warning("Auto-login failed for guild %s (bad stored creds?)", guild_id)
        return None

    # ------------------------------------------------------------------
    # /admin_set_creds — one-step creds setup
    # ------------------------------------------------------------------
    @app_commands.command(name="admin_set_creds",
        description="Set teacher/admin LN credentials for ban/unban")
    @owner_check()
    @app_commands.describe(
        username="Teacher/admin LanguageNut email or username",
        password="Teacher/admin LanguageNut password")
    async def admin_set_creds(self, interaction: Interaction, username: str, password: str):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id or 0
        if not gid:
            await interaction.followup.send("Guild only command.", ephemeral=True)
            return
        client = LNAPIAdminClient()
        token = await client.login(username, password)
        if not token:
            await interaction.followup.send("Login failed. Check the username and password.", ephemeral=True)
            return
        config.set_admin_account(gid, username, password, token)
        self._admin_clients[gid] = client
        embed = discord.Embed(
            title="\U0001f510 Admin Credentials Set",
            description=(
                f"Logged in as **{client.admin_name}**\n"
                "Credentials saved -- ban/unban will auto-login."
            ),
            color=discord.Color.green(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info("Admin creds set for guild %s by user %s", gid, interaction.user.id)

    # ------------------------------------------------------------------
    # /admin_creds_status
    # ------------------------------------------------------------------
    @app_commands.command(name="admin_creds_status",
        description="Check if admin credentials are configured")
    @owner_check()
    async def admin_creds_status(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id or 0
        if not gid:
            await interaction.followup.send("Guild only command.", ephemeral=True)
            return
        acct = config.get_admin_account(gid)
        if not acct:
            await interaction.followup.send("No admin credentials. Use /admin_set_creds.", ephemeral=True)
            return
        await interaction.followup.send(
            f"Admin credentials configured. Token: {bool(acct.get('token'))}",
            ephemeral=True)

    # ------------------------------------------------------------------
    # /admin-login
    # ------------------------------------------------------------------
    @app_commands.command(name="admin-login", description="Login as teacher/admin to manage students")
    @owner_check()
    @app_commands.describe(
        username="Teacher/admin email",
        password="Teacher/admin password",
    )
    async def admin_login_cmd(self, interaction: Interaction, username: str, password: str):
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id != OWNER_ID:
            return await interaction.followup.send("\U0001f6ab Owner only.", ephemeral=True)

        client = LNAPIAdminClient()
        token = await client.login(username, password)
        if token:
            gid = interaction.guild_id or 0
            self._admin_clients[gid] = client
            config.set_admin_account(gid, username, password, token)
            embed = discord.Embed(
                title="\U0001f510 Admin Login Successful",
                description=(
                    f"Logged in as **{client.admin_name}**\n"
                    "Credentials saved -- ban/unban will auto-login."
                ),
                color=discord.Color.green(),
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send("\u274c Login failed. Check credentials.", ephemeral=True)

    # ------------------------------------------------------------------
    # /admin-logout
    # ------------------------------------------------------------------
    @app_commands.command(name="admin-logout", description="Logout from teacher/admin session")
    @owner_check()
    async def admin_logout_cmd(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id or 0
        if gid in self._admin_clients:
            await self._admin_clients[gid].close()
            del self._admin_clients[gid]
        config.remove_admin_account(gid)
        await interaction.followup.send("\U0001f6aa Logged out and credentials removed.", ephemeral=True)

    # ------------------------------------------------------------------
    # /ban (shorthand for admin-ban)
    # ------------------------------------------------------------------
    @app_commands.command(name="ban",
        description="Ban a LN student (needs teacher creds)")
    @owner_check()
    @app_commands.describe(student_uid="The LanguageNut student UID to ban")
    async def ban(self, interaction: Interaction, student_uid: str):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id or 0
        admin = await self._get_admin(gid)
        if not admin:
            return await interaction.followup.send("\u274c Not logged in as admin. Use `/admin-login`.", ephemeral=True)
        result = await admin.delete_student(student_uid)
        if result.get("error"):
            await interaction.followup.send(f"\u274c Ban failed: {result.get('body', 'unknown error')}", ephemeral=True)
        else:
            embed = discord.Embed(
                title="\U0001f6ab Student Banned",
                description=f"Student UID `{student_uid}` has been deleted/banned.",
                color=discord.Color.red(),
            )
            await interaction.followup.send
