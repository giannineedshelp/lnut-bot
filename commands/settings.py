import discord
from discord import ui, app_commands
from discord.ext import commands


class SettingsView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)

        self.add_item(ui.Button(label="⚙️ Core", style=discord.ButtonStyle.primary))
        self.add_item(ui.Button(label="👤 Profile", style=discord.ButtonStyle.secondary))
        self.add_item(ui.Button(label="❌ Close", style=discord.ButtonStyle.danger))

    @ui.button(label="❌ Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.message.delete()
        except:
            pass


class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="settings")
    async def settings(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚙️ Settings Panel",
            description="Click buttons below",
            color=discord.Color.green()
        )

        await interaction.response.send_message(
            embed=embed,
            view=SettingsView(),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Settings(bot))