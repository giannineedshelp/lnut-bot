"""
hub.py — Central hub command cog for LNutBot.
Provides a /hub panel with Login, Logout, Settings, Help, Health, and Refresh buttons.
"""
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord import app_commands, ui

from config import ACCOUNTS_DIR
from automation.api_direct import LNApiClient
from automation.stealth import StealthManager
from commands.commands import SettingsView

logger = logging.getLogger(__name__)

# ─── Utilities ───────────────────────────────────────────────────────────────

def get_guild_accounts_dir(guild_id: int):
    """Get the accounts directory path for a guild."""
    return ACCOUNTS_DIR / str(guild_id)


def get_account(guild_id: int):
    """Check if a logged-in account exists for this guild."""
    acc_dir = get_guild_accounts_dir(guild_id)
    if not acc_dir.exists():
        return None
    acc_files = list(acc_dir.glob("*.txt"))
    return acc_files[0] if acc_files else None


async def get_api_client(guild_id: int) -> LNApiClient:
    """Get an LNApiClient with the stored credentials for this guild."""
    acc_file = get_account(guild_id)
    if not acc_file:
        return None
    try:
        content = acc_file.read_text().strip()
        username, password = content.split(":", 1)
        client = LNApiClient(username, password)
        success = await client.login()
        if success:
            return client
        return None
    except Exception as e:
        logger.error(f"Failed to create API client: {e}")
        return None

# ─── Modals & Views ──────────────────────────────────────────────────────────

class LoginModal(ui.Modal, title="Login to LanguageNut"):
    """Modal for entering LanguageNut credentials."""

    username = ui.TextInput(
        label="Username",
        placeholder="Enter your LanguageNut username",
        min_length=1,
        max_length=100,
        required=True,
    )
    password = ui.TextInput(
        label="Password",
        placeholder="Enter your LanguageNut password",
        min_length=1,
        max_length=100,
        required=True,
    )

    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            client = LNApiClient(self.username.value, self.password.value)
            success = await client.login()
            if not success:
                await interaction.followup.send(
                    "❌ Login failed. Check your credentials.", ephemeral=True
                )
                return

            acc_dir = get_guild_accounts_dir(self.guild_id)
            acc_dir.mkdir(parents=True, exist_ok=True)

            sanitized = self.username.value.replace("/", "_").replace("\\", "_")
            acc_file = acc_dir / f"{sanitized}.txt"
            acc_file.write_text(f"{self.username.value}:{self.password.value}")

            embed = discord.Embed(
                title="✅ Login Successful",
                description=f"Logged in as **{self.username.value}**",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(text="LanguageNut Hub")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Login error: {e}")
            await interaction.followup.send(
                f"❌ An error occurred during login: {e}", ephemeral=True
            )


class LogoutConfirm(ui.View):
    """Confirmation dialog for logout."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=60)
        self.guild_id = guild_id

    @ui.button(label="Yes, Logout", style=discord.ButtonStyle.danger)
    async def confirm_logout(self, interaction: discord.Interaction, button: ui.Button):
        acc_file = get_account(self.guild_id)
        if acc_file:
            acc_file.unlink()

        embed = discord.Embed(
            title="🚪 Logged Out",
            description="Your LanguageNut account has been logged out.",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="LanguageNut Hub")
        await interaction.response.edit_message(embed=embed, view=None)

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_logout(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="Logout Cancelled",
            color=discord.Color.greyple(),
            timestamp=discord.utils.utcnow(),
        )
        await interaction.response.edit_message(embed=embed, view=None)


class HelpView(ui.View):
    """Sub-menu for Help: Tutorial and Commands Help."""

    def __init__(self):
        super().__init__(timeout=120)

    @ui.button(label="📖 Tutorial", style=discord.ButtonStyle.primary)
    async def tutorial_btn(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="📖 LanguageNut Bot Tutorial",
            description=(
                "**Welcome to LanguageNut Farmer Bot!**\n\n"
                "**Step 1: Login**\n"
                "Use `/hub` and click **Login** to enter your LanguageNut credentials.\n\n"
                "**Step 2: Configure Settings**\n"
                "Click **Settings** to adjust:\n"
                "• Speed (seconds per task)\n"
                "• Min/Max accuracy (%)\n"
                "• Concurrency (parallel tasks)\n"
                "• Retry attempts\n"
                "• Stealth mode toggle\n"
                "• Auto-retry toggle\n\n"
                "**Step 3: View Homework**\n"
                "Use `/homework` to see available assignments.\n\n"
                "**Step 4: Complete Tasks**\n"
                "Use `/do` to start working on tasks.\n\n"
                "**Step 5: Monitor**\n"
                "Use `/hub` → **Health** to check account status."
            ),
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="LanguageNut Hub • Tutorial")
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="📋 Commands", style=discord.ButtonStyle.success)
    async def commands_btn(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="📋 Command Reference",
            description="All available commands for LanguageNut Farmer Bot:",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="🔄 General",
            value=(
                "`/hub` — Open the central control panel\n"
                "`/settings` — Configure farming parameters\n"
                "`/homework` — View available assignments\n"
                "`/logs` — View bot log output"
            ),
            inline=False,
        )
        embed.add_field(
            name="⚙️ Task Commands",
            value=(
                "`/do <tasks>` — Execute comma-separated tasks\n"
                "`/stop` — Stop current task execution"
            ),
            inline=False,
        )
        embed.add_field(
            name="👤 Account",
            value=(
                "`/xp` — View your XP and progress\n"
                "`/leaderboard` — View server leaderboard"
            ),
            inline=False,
        )
        embed.add_field(
            name="🔧 Owner",
            value=(
                "`/restart` — Restart the bot\n"
                "`/update` — Pull latest code and restart\n"
                "`/reload` — Reload a cog (e.g. `/reload commands.hub`)\n"
                "`/sync` — Sync slash commands globally"
            ),
            inline=False,
        )
        embed.set_footer(text="LanguageNut Hub • Commands")
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="🔙 Back", style=discord.ButtonStyle.secondary)
    async def back_btn(self, interaction: discord.Interaction, button: ui.Button):
        embed = build_hub_embed(interaction.guild_id)
        view = HubView(interaction.guild_id)
        await interaction.response.edit_message(embed=embed, view=view)


def build_hub_embed(guild_id: int) -> discord.Embed:
    """Build the main hub embed."""
    acc_file = get_account(guild_id)
    logged_in = acc_file is not None
    username = acc_file.stem if acc_file else None

    embed = discord.Embed(
        title="🏠 LanguageNut Hub",
        description="Control panel for LanguageNut Farmer Bot.",
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )

    if logged_in:
        embed.add_field(
            name="🔑 Status",
            value=f"✅ Logged in as **{username}**",
            inline=False,
        )
    else:
        embed.add_field(
            name="🔑 Status",
            value="❌ Not logged in",
            inline=False,
        )

    embed.add_field(
        name="💡 Quick Tips",
        value=(
            "• Click **Login** to add your LanguageNut account\n"
            "• Click **Settings** to adjust farming parameters\n"
            "• Click **Health** to check account status\n"
            "• Click **Help** for tutorial & commands"
        ),
        inline=False,
    )
    embed.set_footer(text="LanguageNut Hub")
    return embed


class HubView(ui.View):
    """Main hub view with all control buttons."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id

    @ui.button(label="🔑 Login", style=discord.ButtonStyle.success)
    async def login_btn(self, interaction: discord.Interaction, button: ui.Button):
        modal = LoginModal(self.guild_id)
        await interaction.response.send_modal(modal)

    @ui.button(label="🚪 Logout", style=discord.ButtonStyle.danger)
    async def logout_btn(self, interaction: discord.Interaction, button: ui.Button):
        acc_file = get_account(self.guild_id)
        if not acc_file:
            embed = discord.Embed(
                title="Not Logged In",
                description="You are not currently logged in to any account.",
                color=discord.Color.yellow(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title="Confirm Logout",
            description=f"Are you sure you want to log out **{acc_file.stem}**?",
            color=discord.Color.orange(),
        )
        view = LogoutConfirm(self.guild_id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @ui.button(label="⚙️ Settings", style=discord.ButtonStyle.primary)
    async def settings_btn(self, interaction: discord.Interaction, button: ui.Button):
        view = SettingsView(self.guild_id)
        embed = view.build_embed(self.guild_id)
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="❓ Help", style=discord.ButtonStyle.secondary)
    async def help_btn(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="❓ Help Menu",
            description="Choose an option below:",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(
            name="📖 Tutorial",
            value="Step-by-step guide to using the bot",
            inline=False,
        )
        embed.add_field(
            name="📋 Commands",
            value="Full list of available commands",
            inline=False,
        )
        embed.set_footer(text="LanguageNut Hub • Help")
        view = HelpView()
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="❤️ Health", style=discord.ButtonStyle.danger)
    async def health_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)

        acc_file = get_account(self.guild_id)
        if not acc_file:
            embed = discord.Embed(
                title="❤️ Health Check",
                description="❌ **Status: No account logged in**\n\nUse the **Login** button to add your LanguageNut account.",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(text="LanguageNut Hub • Health")
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        username = acc_file.stem
        try:
            content = acc_file.read_text().strip()
            uname, pwd = content.split(":", 1)
            client = LNApiClient(uname, pwd)
            login_ok = await client.login()

            if not login_ok:
                embed = discord.Embed(
                    title="❤️ Health Check",
                    description=(
                        f"❌ **Status: Login Failed**\n"
                        f"Account: **{username}**\n\n"
                        "Your credentials may be invalid or the account may be banned.\n"
                        "Try logging in again with the **Login** button."
                    ),
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow(),
                )
                embed.set_footer(text="LanguageNut Hub • Health")
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            try:
                info = await client.api.get_profile()
            except AttributeError:
                info = {}

            is_banned = False
            ban_reason = None
            ban_time_left = None

            if isinstance(info, dict):
                if info.get("banned") or info.get("isBanned") or info.get("ban"):
                    is_banned = True
                    ban_data = info.get("ban", info)
                    if isinstance(ban_data, dict):
                        ban_reason = ban_data.get("reason") or ban_data.get("reasonText")
                        ban_until = ban_data.get("until") or ban_data.get("expires")
                        if ban_until:
                            try:
                                if isinstance(ban_until, (int, float)):
                                    ban_dt = datetime.fromtimestamp(ban_until / 1000, tz=timezone.utc)
                                else:
                                    ban_dt = datetime.fromisoformat(str(ban_until).replace("Z", "+00:00"))
                                now = datetime.now(timezone.utc)
                                remaining = ban_dt - now
                                if remaining.total_seconds() > 0:
                                    hours, rem = divmod(int(remaining.total_seconds()), 3600)
                                    minutes = rem // 60
                                    ban_time_left = f"{hours}h {minutes}m"
                                else:
                                    ban_time_left = "Expiring soon"
                            except (ValueError, TypeError):
                                ban_time_left = str(ban_until)

            if is_banned:
                reason_text = f"\nReason: {ban_reason}" if ban_reason else ""
                timer_text = f"\nTime remaining: {ban_time_left}" if ban_time_left else ""
                embed = discord.Embed(
                    title="❤️ Health Check",
                    description=(
                        f"🚫 **Status: BANNED**\n"
                        f"Account: **{username}**{reason_text}{timer_text}\n\n"
                        "Contact LanguageNut support or wait for the ban to expire."
                    ),
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow(),
                )
            else:
                embed = discord.Embed(
                    title="❤️ Health Check",
                    description=(
                        f"✅ **Status: Healthy**\n"
                        f"Account: **{username}**\n"
                        f"Token: Valid ✅\n"
                        f"Ban Status: Not banned ✅"
                    ),
                    color=discord.Color.green(),
                    timestamp=discord.utils.utcnow(),
                )

            embed.set_footer(text="LanguageNut Hub • Health")
            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Health check error: {e}")
            embed = discord.Embed(
                title="❤️ Health Check",
                description=f"❌ **Error checking health:** `{e}`",
                color=discord.Color.red(),
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(text="LanguageNut Hub • Health")
            await interaction.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="🔄 Refresh", style=discord.ButtonStyle.secondary)
    async def refresh_btn(self, interaction: discord.Interaction, button: ui.Button):
        embed = build_hub_embed(self.guild_id)
        view = HubView(self.guild_id)
        await interaction.response.edit_message(embed=embed, view=view)


# ─── Cog ─────────────────────────────────────────────────────────────────────

class HubCog(commands.Cog):
    """Cog for the /hub command."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="hub", description="Open the LanguageNut control hub")
    async def hub(self, interaction: discord.Interaction):
        embed = build_hub_embed(interaction.guild_id)
        view = HubView(interaction.guild_id)
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(HubCog(bot))
    logger.info("HubCog loaded")
