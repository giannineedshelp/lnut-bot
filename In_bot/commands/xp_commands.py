"""
LanguageNut Bot - XP Grind & Account Management Cog

Commands:
  /xp-grind       Grind XP with live DM progress bar
  /save-account   Save a LanguageNut account (max 3)
  /switch-account Switch to a saved account
  /delete-account Delete a saved account
  /list-accounts  List your saved accounts
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import discord
from discord import Interaction, app_commands
from discord.ext import commands

import config
from automation.api_direct import LNApiClient
from automation.stealth import StealthManager, seconds_to_human
from utils.encryption import decrypt_value, encrypt_value
from utils.helper import _is_done
from utils.logger import log_homework_action, log_user_command

logger = logging.getLogger("lnut_bot.xp_commands")


# ============================================================
# XP GRIND EXECUTOR with live DM progress bar
# ============================================================
async def execute_jobs_xp(
    followup: Any,
    jobs: list[tuple[dict, dict]],
    cog: commands.Cog,
    guild_id: int,
    user_id: int = 0,
    xp_target: int = 5000,
    dm_channel: Any = None,
) -> None:
    """Run jobs with live DM progress bar tracking XP earned."""
    client = await cog._get_api_client(guild_id)  # type: ignore
    if not client:
        try:
            await followup.send("Not logged in.", ephemeral=True)
        except Exception:
            pass
        return

    settings = config.get_guild_settings(guild_id)
    concurrency = max(1, min(settings["concurrency"], 8))
    sem = asyncio.Semaphore(concurrency)

    total_xp = 0
    completed = 0
    failed = 0
    dm_msg = None

    async def update_dm():
        nonlocal dm_msg
        if not dm_channel:
            return
        pct = min(100, int(total_xp / xp_target * 100)) if xp_target else 0
        bar_len = 20
        filled = round(pct / (100 / bar_len))
        bar = chr(0x2588) * filled + chr(0x2591) * (bar_len - filled)
        remaining = max(0, xp_target - total_xp)
        text = (
            "**XP Grind Progress**\n"
            f"`{bar}` **{pct}%**\n"
            f"{chr(0x2705)} {completed} tasks | {chr(0x274C)} {failed} failed\n"
            f"{chr(0x1F4CA)} **{total_xp:,}** / {xp_target:,} XP\n"
            f"{chr(0x23F3)} ~{remaining:,} XP remaining"
        )
        try:
            if dm_msg is None:
                dm_msg = await dm_channel.send(text)
            else:
                await dm_msg.edit(content=text)
        except Exception:
            pass

    async def run_one(hw: dict, t_obj: dict):
        nonlocal total_xp, completed, failed
        hw_name = hw.get("name", "Unnamed")
        task_name = t_obj.get("translation", "Unknown")
        game_link = t_obj.get("gameLink", "")
        to_lang = hw.get("languageCode", "")

        async with sem:
            client.stealth.sync_settings(guild_id)
            attempt = 0
            while True:
                attempt += 1
                try:
                    data = await client.fetch_task_data(t_obj, game_link, to_lang)
                    if not data:
                        ls = config.get_guild_settings(guild_id)
                        retries = ls["retry_attempts"] if ls["auto_retry"] else 0
                        if attempt <= retries:
                            await asyncio.sleep(1.5 * attempt)
                            continue
                        failed += 1
                        return hw_name, task_name, False, "No data", 0

                    result = await client.submit_score(t_obj, data, hw)

                    if result.get("error"):
                        if result.get("status") in (401, 403) and attempt == 1:
                            try:
                                re_ok = await client.re_login()
                                if re_ok:
                                    continue
                            except Exception:
                                pass
                        ls = config.get_guild_settings(guild_id)
                        retries = ls["retry_attempts"] if ls["auto_retry"] else 0
                        if attempt <= retries:
                            await asyncio.sleep(1.5 * attempt)
                            continue
                        failed += 1
                        return hw_name, task_name, False, str(result.get("body", ""))[:120], 0

                    xp_this = len(data) * 200
                    total_xp += xp_this
                    completed += 1
                    if (completed + failed) % 3 == 0 or total_xp >= xp_target:
                        await update_dm()
                    return hw_name, task_name, True, "", xp_this

                except Exception as e:
                    ls = config.get_guild_settings(guild_id)
                    retries = ls["retry_attempts"] if ls["auto_retry"] else 0
                    if attempt <= retries:
                        await asyncio.sleep(1.5 * attempt)
                        continue
                    failed += 1
                    return hw_name, task_name, False, str(e)[:120], 0

    async def _staggered(hw: dict, t_obj: dict, delay: float):
        if delay > 0:
            await asyncio.sleep(delay)
        return await run_one(hw, t_obj)

    tasks = []
    for i, (hw, t) in enumerate(jobs):
        d = client.stealth.delay_between_tasks() if i > 0 else 0
        tasks.append(_staggered(hw, t, d))
    results = await asyncio.gather(*tasks)
    ok = [r for r in results if r[2]]
    bad = [r for r in results if not r[2]]

    await update_dm()

    if user_id and jobs:
        for (hw, t_obj), (_, tname, success, _, xpval) in zip(jobs, results):
            log_homework_action(
                user_id, str(hw.get("id", "?")), tname,
                100 if success else 0, 0, xpval if success else 0,
            )

    embed = discord.Embed(
        title="\u2705 XP Grind Complete \U0001F3C6" if not bad else "\u26A0\uFE0F XP Grind Finished",
        description=f"**{completed}/{len(results)}** tasks done | **{total_xp:,}** / {xp_target:,} XP earned",
        color=discord.Color.green() if not bad else discord.Color.orange(),
    )
    if ok:
        lst = [f"{chr(0x2705)} **{name}** ({xp:,} XP)" for _, name, _, _, xp in ok[:10]]
        if len(ok) > 10:
            lst.append(f"...and {len(ok) - 10} more")
        embed.add_field(name=f"{chr(0x2705)} Completed ({len(ok)})", value="\n".join(lst), inline=False)
    if bad:
        lst = [f"{chr(0x274C)} **{name}**" for _, name, _, _, _ in bad[:5]]
        embed.add_field(name=f"{chr(0x274C)} Failed ({len(bad)})", value="\n".join(lst), inline=False)
    embed.set_footer(text=f"Total XP earned: {total_xp:,}")

    cog._hw_cache.pop(guild_id, None)  # type: ignore
    try:
        await followup.send(embed=embed, ephemeral=True)
    except Exception:
        try:
            await followup.send(f"Grind done: {completed}/{len(results)} tasks, {total_xp:,} XP.", ephemeral=True)
        except Exception:
            pass

    if dm_channel and dm_msg:
        try:
            await dm_msg.edit(
                content=(
                    "**XP Grind Complete**\n"
                    f"{chr(0x1F3C6)} **{total_xp:,}** XP earned\n"
                    f"{chr(0x2705)} {completed} tasks | {chr(0x274C)} {failed} failed\n"
                    f"Target: {xp_target:,} XP"
                )
            )
        except Exception:
            pass


# ============================================================
# COG
# ============================================================
class XpCommands(commands.Cog):
    """XP Grind and Account Management commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._hw_cache: dict[int, tuple[float, list[dict]]] = {}

    async def _get_api_client(self, guild_id: int) -> Optional[LNApiClient]:
        """Get the LN API client for a guild, or None."""
        account = config.get_account(guild_id)
       
