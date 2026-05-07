import logging
import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger("core")

class Core(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # =========================
    # PING (TEST COMMAND)
    # =========================

    @app_commands.command(name="ping")
    async def ping(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_message("pong", ephemeral=True)
        except Exception as e:
            print("[PING ERROR]", repr(e))

    # =========================
    # HOMEWORK (SAFE DEBUG VERSION)
    # =========================

    @app_commands.command(name="homework")
    async def homework(self, interaction: discord.Interaction):

        try:
            await interaction.response.defer(ephemeral=True)

            from automation.api_direct import LanguageNutAPI

            api = LanguageNutAPI(self.bot.session)

            data = await api.get_homeworks()
            if not data:
                return await interaction.followup.send("No homework", ephemeral=True)

            await interaction.followup.send(f"Got homework: {len(data)} items", ephemeral=True)

        except Exception as e:
            print("[HOMEWORK ERROR]", repr(e))

            try:
                await interaction.followup.send(f"❌ {e}", ephemeral=True)
            except:
                pass

    # =========================
    # DO (WRAPPED SAFE)
    # =========================

    @app_commands.command(name="do")
    async def do(self, interaction: discord.Interaction, task_id: str):

        try:
            await interaction.response.defer(ephemeral=True)

            from config import get_account, get_decrypted_password
            from automation.api_direct import LanguageNutAPI
            from automation.task_handler import TaskCompleter

            acc = get_account(str(interaction.user.id))
            if not acc:
                return await interaction.followup.send("Not logged in", ephemeral=True)

            pw = get_decrypted_password(str(interaction.user.id))

            api = LanguageNutAPI(self.bot.session)
            ok = await api.login(acc["username"], pw)

            if not ok:
                return await interaction.followup.send("Login failed", ephemeral=True)

            task = {
                "catalog_uid": task_id,
                "game_uid": task_id,
                "type": "homework"
            }

            completer = TaskCompleter(
                token=api.token,
                task=task,
                ietf="fr-FR",
                speed_ms=10000,
                accuracy_min=100,
                accuracy_max=100,
            )

            answers = await completer.get_data()
            if not answers:
                return await interaction.followup.send("No answers found", ephemeral=True)

            result = await completer.send_answers(answers)

            await interaction.followup.send(
                f"Done: {result.get('score', 0)}",
                ephemeral=True
            )

        except Exception as e:
            print("[DO ERROR]", repr(e))

            try:
                await interaction.followup.send(f"❌ {e}", ephemeral=True)
            except:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Core(bot))