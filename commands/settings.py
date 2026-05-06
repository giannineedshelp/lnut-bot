import discord
from discord import ui, ButtonStyle, app_commands
from discord.ext import commands


class SettingsView(ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @ui.button(label="⏱️ Timing", style=ButtonStyle.primary)
    async def timing(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("Timing settings opened", ephemeral=True)

    @ui.button(label="👤 Profile", style=ButtonStyle.secondary)
    async def profile(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("Profile settings opened", ephemeral=True)

    @ui.button(label="🔧 Core", style=ButtonStyle.success)
    async def core(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("Core settings opened", ephemeral=True)

    @ui.button(label="❌ Close", style=ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.message.delete()


class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="settings", description="Open settings panel")
    async def settings(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "⚙️ Settings Panel",
            view=SettingsView(),
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))