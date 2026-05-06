import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import time


# =========================
# PERMISSION CHECK
# =========================
def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator


# =========================
# CORE COG
# =========================
class Core(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()

    # =========================
    # BOT STATUS
    # =========================
    @app_commands.command(
        name="status",
        description="Show bot status"
    )
    async def status(self, interaction: discord.Interaction):

        uptime = int(time.time() - self.start_time)

        embed = discord.Embed(
            title="🟢 Bot Status Panel",
            color=discord.Color.green()
        )

        embed.add_field(
            name="Latency",
            value=f"{round(self.bot.latency * 1000)}ms",
            inline=True
        )

        embed.add_field(
            name="Uptime",
            value=f"{uptime}s",
            inline=True
        )

        embed.add_field(
            name="Servers",
            value=str(len(self.bot.guilds)),
            inline=True
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

        # auto delete after 20s
        await asyncio.sleep(20)
        try:
            await interaction.delete_original_response()
        except:
            pass

    # =========================
    # CLEAR CHANNEL
    # =========================
    @app_commands.command(
        name="clear",
        description="Clear messages in a channel (admin only)"
    )
    async def clear(self, interaction: discord.Interaction, amount: int = 10):

        if not is_admin(interaction):
            return await interaction.response.send_message(
                "❌ You need admin permissions.",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        deleted = await interaction.channel.purge(limit=amount)

        msg = await interaction.followup.send(
            f"🧹 Deleted **{len(deleted)} messages**",
            ephemeral=True
        )

        await asyncio.sleep(10)

        try:
            await msg.delete()
        except:
            pass

    # =========================
    # RESTART BOT
    # =========================
    @app_commands.command(
        name="restart",
        description="Restart the bot (admin only)"
    )
    async def restart(self, interaction: discord.Interaction):

        if not is_admin(interaction):
            return await interaction.response.send_message(
                "❌ You need admin permissions.",
                ephemeral=True
            )

        await interaction.response.send_message(
            "♻️ Restarting bot...",
            ephemeral=True
        )

        await self.bot.close()

    # =========================
    # SYNC COMMANDS
    # =========================
    @app_commands.command(
        name="sync",
        description="Sync slash commands (admin only)"
    )
    async def sync(self, interaction: discord.Interaction):

        if not is_admin(interaction):
            return await interaction.response.send_message(
                "❌ You need admin permissions.",
                ephemeral=True
            )

        await self.bot.tree.sync()

        msg = await interaction.response.send_message(
            "✅ Commands synced!",
            ephemeral=True
        )

        await asyncio.sleep(10)

        try:
            await interaction.delete_original_response()
        except:
            pass

    # =========================
    # PING TEST
    # =========================
    @app_commands.command(
        name="ping",
        description="Check bot latency"
    )
    async def ping(self, interaction: discord.Interaction):

        await interaction.response.send_message(
            f"🏓 Pong: {round(self.bot.latency * 1000)}ms",
            ephemeral=True
        )

        await asyncio.sleep(15)

        try:
            await interaction.delete_original_response()
        except:
            pass


# =========================
# SETUP FUNCTION
# =========================
async def setup(bot: commands.Bot):
    await bot.add_cog(Core(bot))