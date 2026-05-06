import discord
from discord import ui, ButtonStyle
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


def setup_settings_commands(bot: commands.Bot):

    @bot.tree.command(name="settings", description="Open settings panel")
    async def settings(interaction: discord.Interaction):
        await interaction.response.send_message(
            "⚙️ Settings Panel",
            view=SettingsView(),
            ephemeral=True
        )