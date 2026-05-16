"""Hub, account management, and XP farm launcher commands"""

import asyncio
import json
import os
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from automation.api_direct import LNApiClient
from automation.stealth import StealthManager
from commands.xp_commands import XPFarmView, CURRICULUM_LANGUAGES, load_config, save_config

logger = logging.getLogger(__name__)


def load_config():
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"saved_accounts": {}}


def save_config(config):
    with open("config.json", "w") as f:
        json.dump(config, f, indent=2)


class SaveAccountModal(discord.ui.Modal, title="Save LanguageNut Account"):
    """Modal for saving a LanguageNut account."""

    username_input = discord.ui.TextInput(
        label="Username",
        placeholder="Enter your LN username",
        required=True,
        max_length=50,
    )
    password_input = discord.ui.TextInput(
        label="Password",
        placeholder="Enter your LN password",
        required=True,
        max_length=100,
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        username = self.username_input.value.strip()
        password = self.password_input.value.strip()

        if not username or not password:
            await interaction.response.send_message("Username and password required.", ephemeral=True)
            return

        # Verify credentials by logging in
        client = LNApiClient()
        try:
            await client.login(username, password)
        except Exception as e:
            await interaction.response.send_message(f"Login failed: {e}", ephemeral=True)
            return

        # Save to config.json
        config = load_config()
        config.setdefault("saved_accounts", {})
        config["saved_accounts"].setdefault(guild_id, {})
        config["saved_accounts"][guild_id][username] = {
            "username": username,
            "password": password,
        }
        save_config(config)

        # Also save to individual file for redundancy
        accounts_dir = f"accounts/{guild_id}"
        os.makedirs(accounts_dir, exist_ok=True)
        with open(f"{accounts_dir}/{username}.txt", "w") as f:
            f.write(f"{username}:{password}")

        await interaction.response.send_message(
            f"Account `{username}` saved successfully!",
            ephemeral=True,
        )


class LanguageSelectView(discord.ui.View):
    """Dropdown for selecting a language to XP farm."""

    def __init__(self, ctx, client: LNApiClient, username: str, curriculums: list):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.client = client
        self.username = username
        self.curriculums = curriculums

        options = []
        for c in curriculums:
            uid = c.get("uid", "?")
            name = c.get("language") or c.get("name") or f"UID {uid}"
            known_emoji = "✅" if uid in CURRICULUM_LANGUAGES else "🌐"
            options.append(discord.SelectOption(
                label=name,
                value=str(uid),
                description=f"Farm XP in {name} (UID {uid})",
                emoji=known_emoji,
            ))

        # Discord max 25 options per select
        options = options[:25]

        select = discord.ui.Select(
            placeholder="Choose a language to farm...",
            options=options,
            custom_id="xp_language_select",
        )
        select.callback = self._language_callback
        self.add_item(select)

    async def _language_callback(self, interaction: discord.Interaction):
        uid = int(interaction.data["values"][0])
        lang_name = next(
            (
                c.get("language") or c.get("name", "Unknown")
                for c in self.curriculums
                if c.get("uid") == uid
            ),
            "Unknown",
        )

        # Initialize stealth engine for this session
        stealth = StealthManager(
            speed=10.0,
            min_accuracy=85,
            max_accuracy=92,
            min_seconds_per_question=5.0,
            max_seconds_per_question=8.0,
            user_id=interaction.user.id,
            guild_id=interaction.guild_id,
        )
        stealth.username = self.username

        # Launch XP farm view
        view = XPFarmView(
            ctx=interaction,
            client=self.client,
            curriculum_uid=uid,
            language=lang_name,
            max_rounds=20,
            stealth=stealth,
            username=self.username,
        )

        embed = discord.Embed(
            title=f"⚡ XP Farm — {lang_name}",
            description=(
                f"**Account:** `{self.username}`\n"
                f"**Language:** {lang_name}\n"
                f"**UID:** `{uid}`\n\n"
                "Press **▶ Start** to begin farming XP.\n"
                "Press **⏹ Stop** to end early.\n\n"
                "🔒 Stealth v3.0 active:\n"
                "• Anti-ban timing & accuracy\n"
                "• Fatigue & burst-pause patterns\n"
                "• Session memory (no repeats)"
            ),
            color=discord.Color.blue(),
        )
        await interaction.response.edit_message(embed=embed, view=view)


class HubView(discord.ui.View):
    """Main hub view with XP Farm, Homeworks, Account buttons."""

    def __init__(self, ctx):
        super().__init__(timeout=180)
        self.ctx = ctx

    @discord.ui.button(label="⚡ XP Farm", style=discord.ButtonStyle.success, row=0)
    async def xp_farm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._launch_xp_farm(interaction)

    @discord.ui.button(label="📋 Homeworks", style=discord.ButtonStyle.primary, row=0)
    async def homeworks(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show_homeworks(interaction)

    @discord.ui.button(label="👤 Account", style=discord.ButtonStyle.secondary, row=0)
    async def account(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = load_config()
        guild_id = str(interaction.guild_id)
        saved = config.get("saved_accounts", {}).get(guild_id, {})

        if not saved:
            await interaction.response.send_message(
                "No saved accounts. Use `/save` or press the button below.",
                ephemeral=True,
                view=SaveAccountButtonView(),
            )
            return

        lines = [f"• `{name}`" for name in saved.keys()]
        embed = discord.Embed(
            title="Saved Accounts",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _launch_xp_farm(self, interaction: discord.Interaction):
        """Show language selection for XP farming."""
        await interaction.response.defer(ephemeral=True)

        config = load_config()
        guild_id = str(interaction.guild_id)
        saved = config.get("saved_accounts", {}).get(guild_id, {})

        if not saved:
            await interaction.followup.send(
                "No saved accounts. Use `/save` first.",
                ephemeral=True,
                view=SaveAccountButtonView(),
            )
            return

        first_acct = list(saved.keys())[0]
        creds = saved[first_acct]

        client = LNApiClient()
        try:
            login_result = await client.login(creds["username"], creds["password"])
        except Exception as e:
            await interaction.followup.send(f"Login failed: {e}", ephemeral=True)
            return

        curriculums = (
            login_result.get("curriculums")
            or login_result.get("user", {}).get("curriculums")
            or []
        )
        if not curriculums:
            await interaction.followup.send("No languages available for this account.", ephemeral=True)
            return

        view = LanguageSelectView(
            ctx=interaction,
            client=client,
            username=creds["username"],
            curriculums=curriculums,
        )

        await interaction.followup.send(
            f"🌐 **Select a language to farm**\nAccount: `{creds['username']}`",
            view=view,
            ephemeral=True,
        )

    async def _show_homeworks(self, interaction: discord.Interaction):
        """Fetch and display assignments."""
        await interaction.response.defer(ephemeral=True)

        config = load_config()
        guild_id = str(interaction.guild_id)
        saved = config.get("saved_accounts", {}).get(guild_id, {})

        if not saved:
            await interaction.followup.send("No saved accounts. Use `/save` first.", ephemeral=True)
            return

        first_acct = list(saved.keys())[0]
        creds = saved[first_acct]

        client = LNApiClient()
        try:
            await client.login(creds["username"], creds["password"])
            assignments = await client.get_assignments()
        except Exception as e:
            await interaction.followup.send(f"Error: {e}", ephemeral=True)
            return

        if not assignments:
            await interaction.followup.send("No assignments found.", ephemeral=True)
            return

        assignment_list = (
            assignments.get("assignments")
            or assignments.get("data")
            or assignments.get("results")
            or []
        )

        if not assignment_list:
            await interaction.followup.send("No assignments found.", ephemeral=True)
            return

        lines = []
        for a in assignment_list:
            title = a.get("title") or a.get("name") or "Untitled"
            status = a.get("status", "")
            due = a.get("dueDate") or a.get("due_date", "")
            score = a.get("score", "")
            parts = [f"• **{title}**"]
            if status:
                parts.append(f"[{status}]")
            if due:
                parts.append(f"Due: {due}")
            if score:
                parts.append(f"Score: {score}")
            lines.append(" ".join(parts))

        embed = discord.Embed(
            title=f"📋 Assignments — {creds['username']}",
            description="\n".join(lines) if lines else "No assignments found.",
            color=discord.Color.blue(),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


class SaveAccountButtonView(discord.ui.View):
    """Minimal view with just a Save Account button."""

    @discord.ui.button(label="💾 Save Account", style=discord.ButtonStyle.primary)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SaveAccountModal()
        await interaction.response.send_modal(modal)


class Commands(commands.Cog):
    """Main commands cog — hub, save, accounts, languages, sync."""

    def __init__(self, bot):
        self.bot = bot

    # ----------------------------------------------------------------
    # Hub
    # ----------------------------------------------------------------

    @app_commands.command(name="hub", description="Open the main hub")
    async def hub(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📚 LN Bot Hub",
            description=(
                "**⚡ XP Farm** — Farm XP on your LanguageNut languages\n"
                "**📋 Homeworks** — View your assignments\n"
                "**👤 Account** — View saved accounts\n\n"
                "Use `/save` to add an account first."
            ),
            color=discord.Color.gold(),
        )
        view = HubView(interaction)
        await interaction.response.send_message(embed=embed, view=view)

    # ----------------------------------------------------------------
    # Save account
    # ----------------------------------------------------------------

    @app_commands.command(name="save", description="Save a LanguageNut account")
    async def save(self, interaction: discord.Interaction):
        modal = SaveAccountModal()
        await interaction.response.send_modal(modal)

    # ----------------------------------------------------------------
    # List accounts
    # ----------------------------------------------------------------

    @app_commands.command(name="accounts", description="List saved accounts")
    async def accounts(self, interaction: discord.Interaction):
        config = load_config()
        guild_id = str(interaction.guild_id)
        saved = config.get("saved_accounts", {}).get(guild_id, {})

        if not saved:
            await interaction.response.send_message("No saved accounts. Use `/save`.", ephemeral=True)
            return

        lines = [f"• `{name}`" for name in saved.keys()]
        embed = discord.Embed(
            title="📋 Saved Accounts",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ----------------------------------------------------------------
    # Delete account
    # ----------------------------------------------------------------

    @app_commands.command(name="delete-account", description="Delete a saved account")
    @app_commands.describe(account="Username to delete")
    async def delete_account(self, interaction: discord.Interaction, account: str):
        config = load_config()
        guild_id = str(interaction.guild_id)
        saved = config.get("saved_accounts", {}).get(guild_id, {})

        if account not in saved:
            await interaction.response.send_message(f"Account `{account}` not found.", ephemeral=True)
            return

        del config["saved_accounts"][guild_id][account]

        # Clean up empty guild entries
        if not config["saved_accounts"][guild_id]:
            del config["saved_accounts"][guild_id]

        save_config(config)

        # Remove individual file
        acct_file = f"accounts/{guild_id}/{account}.txt"
        if os.path.exists(acct_file):
            os.remove(acct_file)

        await interaction.response.send_message(f"Deleted account `{account}`.", ephemeral=True)

    # ----------------------------------------------------------------
    # Languages — shows what languages a saved account has
    # ----------------------------------------------------------------

    @app_commands.command(name="languages", description="Show languages available for a saved account")
    @app_commands.describe(account="Saved account username")
    async def languages(self, interaction: discord.Interaction, account: str):
        await interaction.response.defer()

        config = load_config()
        guild_id = str(interaction.guild_id)
        saved = config.get("saved_accounts", {}).get(guild_id, {})

        if account not in saved:
            await interaction.followup.send(f"Account `{account}` not found.", ephemeral=True)
            return

        creds = saved[account]
        username = creds.get("username", account)
        password = creds.get("password")

        if not password:
            await interaction.followup.send("No password saved. Re-save with `/save`.", ephemeral=True)
            return

        client = LNApiClient()
        try:
            login_result = await client.login(username, password)
        except Exception as e:
            await interaction.followup.send(f"Login failed: {e}", ephemeral=True)
            return

        curriculums = (
            login_result.get("curriculums")
            or login_result.get("user", {}).get("curriculums")
            or []
        )
        if not curriculums:
            await interaction.followup.send(f"No languages found for `{username}`.", ephemeral=True)
            return

        lines = []
        for c in curriculums:
            uid = c.get("uid", "?")
            name = c.get("language") or c.get("name") or f"UID {uid}"
            known = "✅" if uid in CURRICULUM_LANGUAGES else "🌐"
            lines.append(f"{known} **{name}** — UID `{uid}`")

        embed = discord.Embed(
            title=f"🌐 Languages — {username}",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="✅ = mapped in bot  |  🌐 = unmapped (use UID directly)")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ----------------------------------------------------------------
    # Admin: sync slash commands
    # ----------------------------------------------------------------

    @app_commands.command(name="admin-sync", description="Sync all slash commands (admin only)")
    @app_commands.default_permissions(administrator=True)
    async def admin_sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await interaction.followup.send(
                f"✅ Synced {len(synced)} slash commands.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Sync error: {e}", ephemeral=True)

    # ----------------------------------------------------------------
    # Admin: test login
    # ----------------------------------------------------------------

    @app_commands.command(name="test-login", description="Test login for a saved account (admin)")
    @app_commands.describe(account="Saved account username")
    @app_commands.default_permissions(administrator=True)
    async def test_login(self, interaction: discord.Interaction, account: str):
        await interaction.response.defer(ephemeral=True)

        config = load_config()
        guild_id = str(interaction.guild_id)
        saved = config.get("saved_accounts", {}).get(guild_id, {})

        if account not in saved:
            await interaction.followup.send(f"Account `{account}` not found.", ephemeral=True)
            return

        creds = saved[account]
        client = LNApiClient()
        try:
            result = await client.login(creds["username"], creds["password"])
            token_preview = client.token[:20] + "..." if client.token else "NONE"
            curriculum_count = len(
                result.get("curriculums") or result.get("user", {}).get("curriculums") or []
            )
            await interaction.followup.send(
                f"✅ **Login successful**\n"
                f"User: `{creds['username']}`\n"
                f"Token: `{token_preview}`\n"
                f"Languages available: {curriculum_count}",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Login failed: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Commands(bot))