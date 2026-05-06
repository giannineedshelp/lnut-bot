import discord
from discord import ui, ButtonStyle
from discord.ext import commands


class SettingsView(ui.View):
    @ui.button(label="⏱️ Timing", style=ButtonStyle.secondary, row=0)
    async def timing(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("Timing settings opened ⚙️", ephemeral=True)

    @ui.button(label="👤 Profile", style=ButtonStyle.primary, row=0)
    async def profile(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("Profile settings opened 👤", ephemeral=True)

    @ui.button(label="⚙️ General", style=ButtonStyle.secondary, row=1)
    async def general(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("General settings opened ⚙️", ephemeral=True)


class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @discord.app_commands.command(
        name="settings",
        description="Open settings panel"
    )
    async def settings_command(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Settings menu:",
            view=SettingsView(),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Settings(bot))