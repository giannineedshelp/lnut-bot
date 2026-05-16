"""XP Farm commands — Fully integrated with StealthManager v3.0 antiban system

Uses real LanguageNut game data API endpoints:
  - gameDataController/getGameVocab  (GET, token in params)
  - gameDataController/addGameScore  (POST, form-encoded, token in data)

Stealth measures (all handled by automation.stealth.StealthManager):
  - Per-session CV > 0.3 timing jitter
  - Fatigue curves (degrades speed over time)
  - Burst-pause structure (clusters + breaks)
  - Time-of-day modulation (slower at night)
  - Week/weekend differentiation
  - Warmup phase (gradual ramp-up)
  - Realistic accuracy (85-92%, not 100%)
  - Real wrong answer UIDs (not empty lists)
  - Session memory (no repeated patterns)
  - Endpoint diversity (occasional non-task calls)
"""

import asyncio
import json
import math
import random
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from automation.api_direct import LNApiClient
from automation.stealth import StealthManager

logger = logging.getLogger(__name__)

# Curriculum UID → language name (extend as discovered via /languages)
CURRICULUM_LANGUAGES: dict[int, str] = {
    54: "Spanish",
    55: "French",
    56: "German",
    57: "Italian",
    58: "Mandarin",
    59: "Arabic",
    60: "Polish",
    61: "Irish",
    62: "Welsh",
    63: "Latin",
    64: "Japanese",
}

# Game modes and their XP weights
GAME_MODE_XP = {
    "vocab": 10,
    "grammar": 15,
    "reading": 20,
    "listening": 25,
    "speaking": 30,
}

# Default rounds
DEFAULT_ROUNDS = 20
MAX_ROUNDS = 50


def load_config() -> dict:
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"saved_accounts": {}}


def save_config(cfg: dict):
    with open("config.json", "w") as f:
        json.dump(cfg, f, indent=2)


class XPFarmView(discord.ui.View):
    """Interactive view for XP farm session with full stealth integration."""

    def __init__(
        self,
        ctx,
        client: LNApiClient,
        curriculum_uid: int,
        language: str,
        max_rounds: int = DEFAULT_ROUNDS,
        stealth: Optional[StealthManager] = None,
        username: str = "unknown",
    ):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.client = client
        self.curriculum_uid = curriculum_uid
        self.language = language
        self.max_rounds = max_rounds
        self.username = username

        # Stealth engine — the core antiban system
        self.stealth = stealth or StealthManager(
            speed=10.0,
            min_accuracy=85,
            max_accuracy=92,
            min_seconds_per_question=5.0,
            max_seconds_per_question=8.0,
        )
        # Bind the username so session memory works
        self.stealth.username = username

        # Session state
        self.running = False
        self.stopped = False
        self.total_xp = 0
        self.total_correct = 0
        self.total_incorrect = 0
        self.rounds_completed = 0
        self.start_time = None
        self.status_message = None

        # Track wrong answer UIDs for realism
        self._vocab_cache: List[dict] = []

    # ----------------------------------------------------------------
    # Discord UI Buttons
    # ----------------------------------------------------------------

    @discord.ui.button(label="▶ Start XP Farm", style=discord.ButtonStyle.success, emoji="⚡")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.running:
            await interaction.response.send_message("XP Farm is already running!", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        self.running = True
        button.disabled = True
        button.label = "⏳ Farming..."
        await interaction.message.edit(view=self)
        self.start_time = time.time()
        try:
            await self._run_xp_farm(interaction)
        finally:
            self.running = False
            button.disabled = False
            button.label = "▶ Start XP Farm"
            await interaction.message.edit(view=self)

    @discord.ui.button(label="⏹ Stop", style=discord.ButtonStyle.danger, emoji="🛑")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.running = False
        self.stopped = True
        button.disabled = True
        button.label = "✅ Stopped"
        await interaction.response.edit_message(view=self)

    # ----------------------------------------------------------------
    # Core XP Farm Loop
    # ----------------------------------------------------------------

    async def _run_xp_farm(self, interaction: discord.Interaction):
        """Main XP farm loop — fully stealth-integrated."""
        self.status_message = await self.ctx.send(
            f"⚡ **XP Farm** — {self.language}\n"
            f"`[          ]` Connecting..."
        )

        try:
            while self.running and not self.stopped and self.rounds_completed < self.max_rounds:

                # --------------------------------------------------------
                # 1) Endpoint diversity: occasionally hit non-task endpoint
                # --------------------------------------------------------
                if StealthManager.should_hit_non_task_endpoint():
                    logger.debug("Endpoint diversity: fetching stats")
                    try:
                        await self.client.get_stats()
                    except Exception:
                        pass

                # --------------------------------------------------------
                # 2) Fetch real vocabulary from game API
                # --------------------------------------------------------
                vocab_data = await self._fetch_vocab_with_retry()
                if not vocab_data:
                    await asyncio.sleep(random.uniform(2.0, 5.0))
                    continue

                # Parse questions — different possible response shapes
                questions = (
                    vocab_data.get("questions")
                    or vocab_data.get("vocabList")
                    or vocab_data.get("data", [])
                    or []
                )
                if not questions:
                    logger.debug("No questions returned, skipping round")
                    await asyncio.sleep(random.uniform(1.0, 3.0))
                    continue

                # Cache vocabs for wrong-answer generation
                self._vocab_cache = questions

                # --------------------------------------------------------
                # 3) Compute stealth timing for this round
                # --------------------------------------------------------
                # Per-question time * number of questions = total round time
                round_time_ms = self.stealth.compute_timestamp(num_questions=len(questions))

                # --------------------------------------------------------
                # 4) Simulate human-like accuracy
                # --------------------------------------------------------
                correct_indices, incorrect_indices = self.stealth.determine_accuracy(
                    total_items=len(questions)
                )

                # Extract UIDs
                all_uids = [str(q.get("uid", q.get("id", str(uuid.uuid4())))) for q in questions]
                correct_uids = [all_uids[i] for i in correct_indices]
                incorrect_uids = [all_uids[i] for i in incorrect_indices]

                # Generate realistic wrong answers (not empty list!)
                realistic_wrong = self.stealth.generate_wrong_answers(
                    correct_vocabs=[questions[i] for i in correct_indices],
                    incorrect_indices=incorrect_indices,
                    all_vocabs=questions,
                )
                # Use the realistic wrong UIDs if available, else fallback
                wrong_uids = realistic_wrong if realistic_wrong else incorrect_uids

                # --------------------------------------------------------
                # 5) Submit score to game API
                # --------------------------------------------------------
                try:
                    score_result = await self.client.add_game_score(
                        correct_uids=correct_uids,
                        incorrect_uids=wrong_uids,
                        product="secondary",
                    )
                except Exception as e:
                    logger.warning(f"Score submission failed (round {self.rounds_completed}): {e}")
                    await asyncio.sleep(random.uniform(2.0, 4.0))
                    continue

                # --------------------------------------------------------
                # 6) Track XP
                # --------------------------------------------------------
                if score_result:
                    # XP = number of correct answers * XP per vocab question
                    xp_gained = len(correct_uids) * GAME_MODE_XP.get("vocab", 10)
                    self.total_xp += xp_gained
                    self.total_correct += len(correct_uids)
                    self.total_incorrect += len(incorrect_uids)
                    self.rounds_completed += 1

                    logger.info(
                        f"Round {self.rounds_completed}/{self.max_rounds}: "
                        f"{xp_gained} XP ({len(correct_uids)}/{len(questions)} correct)"
                    )

                # --------------------------------------------------------
                # 7) Update live status
                # --------------------------------------------------------
                await self._update_status()

                # --------------------------------------------------------
                # 8) Stealth delay between rounds
                #    Uses burst-pause + TOD + fatigue + warmup
                # --------------------------------------------------------
                delay = self.stealth.delay_between_tasks()
                logger.debug(f"Inter-round delay: {delay:.1f}s")
                await asyncio.sleep(delay)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("XP Farm crashed")
            await self.ctx.send(f"❌ **XP Farm Error:** `{e}`")
        finally:
            # Record session metrics
            self.stealth.end_session({
                "total_xp": self.total_xp,
                "accuracy": (self.total_correct / max(self.total_correct + self.total_incorrect, 1)) * 100,
            })
            # Send final summary
            elapsed = time.time() - self.start_time if self.start_time else 0
            embed = self._build_summary_embed(elapsed)
            await self.ctx.send(embed=embed)

    async def _fetch_vocab_with_retry(self, max_retries: int = 3) -> Optional[dict]:
        """Fetch game vocab with retries and exponential backoff."""
        for attempt in range(max_retries):
            try:
                return await self.client.get_game_vocab(self.curriculum_uid)
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"getGameVocab attempt {attempt+1} failed: {e}, retrying in {wait:.1f}s")
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"getGameVocab failed after {max_retries} attempts: {e}")
                    return None
        return None

    async def _update_status(self):
        """Update the live progress status message."""
        progress = min(self.rounds_completed / self.max_rounds, 1.0)
        bar_len = 10
        filled = int(progress * bar_len)
        bar = "■" * filled + "□" * (bar_len - filled)
        elapsed = time.time() - self.start_time if self.start_time else 0
        remaining = max(0, self.max_rounds - self.rounds_completed)
        eta_secs = remaining * (elapsed / max(self.rounds_completed, 1)) if self.rounds_completed > 0 else 0

        # Stealth stats for debugging (remove in production or keep for user)
        fatigue_pct = self.stealth.fatigue_level * 100
        warmup_status = "Warming up..." if self.stealth.warming_up else "Warm"

        content = (
            f"⚡ **XP Farm** — {self.language} | `{self.username}`\n"
            f"`[{bar}]` {self.rounds_completed}/{self.max_rounds} rounds\n"
            f"💰 **XP:** {self.total_xp}  |  "
            f"✅ {self.total_correct}  ❌ {self.total_incorrect}\n"
            f"⏱ {int(elapsed)}s elapsed  |  ETA: {int(eta_secs)}s\n"
            f"📊 Fatigue: {fatigue_pct:.0f}% | Status: {warmup_status}"
        )

        try:
            await self.status_message.edit(content=content)
        except discord.NotFound:
            self.status_message = await self.ctx.send(content)

    def _build_summary_embed(self, elapsed_secs: float) -> discord.Embed:
        """Build final summary embed with session results."""
        total_answers = self.total_correct + self.total_incorrect
        accuracy = (self.total_correct / total_answers * 100) if total_answers > 0 else 0
        xp_per_min = (self.total_xp / max(elapsed_secs / 60, 0.1)) if elapsed_secs > 0 else 0

        embed = discord.Embed(
            title=f"⚡ XP Farm Complete — {self.language}",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="💰 Total XP Earned", value=str(self.total_xp), inline=True)
        embed.add_field(name="✅ Correct", value=str(self.total_correct), inline=True)
        embed.add_field(name="❌ Incorrect", value=str(self.total_incorrect), inline=True)
        embed.add_field(name="🔄 Rounds", value=str(self.rounds_completed), inline=True)
        embed.add_field(name="⏱ Duration", value=f"{int(elapsed_secs)}s", inline=True)
        embed.add_field(name="📊 Accuracy", value=f"{accuracy:.1f}%", inline=True)
        embed.add_field(name="⚡ XP/min", value=f"{xp_per_min:.0f}", inline=True)
        embed.add_field(name="🌐 Language", value=self.language, inline=True)
        embed.add_field(name="👤 Account", value=f"`{self.username}`", inline=True)
        embed.set_footer(text="LanguageNut XP Bot | Stealth v3.0")
        return embed


class XPFarmCommands(commands.Cog):
    """XP Farm slash commands — fully stealth-integrated."""

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def _get_curriculum_uid(language: str) -> Optional[int]:
        """Map language name → curriculum UID."""
        lang = language.lower().strip()
        # Direct name match
        for uid, name in CURRICULUM_LANGUAGES.items():
            if name.lower() == lang:
                return uid
        # Numeric UID passthrough
        if lang.isdigit():
            return int(lang)
        return None

    @app_commands.command(name="xp-farm", description="Farm XP on LanguageNut")
    @app_commands.describe(
        account="Saved account username",
        language="Language to farm (French, Spanish, etc.)",
        rounds="Number of rounds (1-50, default 20)",
    )
    async def xp_farm(
        self,
        interaction: discord.Interaction,
        account: str,
        language: str,
        rounds: int = DEFAULT_ROUNDS,
    ):
        await interaction.response.defer()

        # ---- 1) Load saved account ----
        config = load_config()
        guild_id = str(interaction.guild_id)
        saved = config.get("saved_accounts", {}).get(guild_id, {})

        if account not in saved:
            await interaction.followup.send(
                f"❌ Account `{account}` not found. Use `/save` first.",
                ephemeral=True,
            )
            return

        creds = saved[account]
        username = creds.get("username", account)
        password = creds.get("password")

        if not password:
            await interaction.followup.send(
                f"❌ No password for `{account}`. Re-save with `/save`.",
                ephemeral=True,
            )
            return

        # ---- 2) Map language → curriculum UID ----
        curriculum_uid = self._get_curriculum_uid(language)
        if not curriculum_uid:
            known = ", ".join(CURRICULUM_LANGUAGES.values())
            await interaction.followup.send(
                f"❌ Unknown language `{language}`. Known: {known}",
                ephemeral=True,
            )
            return

        # ---- 3) Login ----
        client = LNApiClient()
        try:
            login_result = await client.login(username, password)
        except Exception as e:
            await interaction.followup.send(
                f"❌ Login failed for `{username}`: {e}",
                ephemeral=True,
            )
            return

        # ---- 4) Verify user has this curriculum ----
        curriculums = (
            login_result.get("curriculums")
            or login_result.get("user", {}).get("curriculums")
            or []
        )
        user_has = any(str(c.get("uid")) == str(curriculum_uid) for c in curriculums)
        if not user_has:
            await interaction.followup.send(
                f"❌ `{username}` doesn't have `{language}` (UID {curriculum_uid}).\n"
                f"Use `/languages {account}` to see available languages.",
                ephemeral=True,
            )
            return

        # ---- 5) Clamp rounds ----
        rounds = max(1, min(rounds, MAX_ROUNDS))

        # ---- 6) Initialize stealth engine for this session ----
        stealth = StealthManager(
            speed=10.0,
            min_accuracy=85,
            max_accuracy=92,
            min_seconds_per_question=5.0,
            max_seconds_per_question=8.0,
            user_id=interaction.user.id,
            guild_id=interaction.guild_id,
        )
        stealth.username = username

        # ---- 7) Launch XP farm view ----
        embed = discord.Embed(
            title=f"⚡ XP Farm — {language}",
            description=(
                f"**Account:** `{username}`\n"
                f"**Rounds:** {rounds}\n"
                f"**Curriculum UID:** `{curriculum_uid}`\n\n"
                "Press **▶ Start** to begin farming XP.\n"
                "Press **⏹ Stop** to end early.\n\n"
                "🔒 Stealth v3.0 active:\n"
                "• Anti-ban timing & accuracy\n"
                "• Fatigue & burst-pause patterns\n"
                "• Session memory (no repeats)"
            ),
            color=discord.Color.blue(),
        )
        view = XPFarmView(
            ctx=interaction,
            client=client,
            curriculum_uid=curriculum_uid,
            language=language,
            max_rounds=rounds,
            stealth=stealth,
            username=username,
        )
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="languages", description="Show available languages for a saved account")
    @app_commands.describe(account="Saved account username")
    async def languages(self, interaction: discord.Interaction, account: str):
        await interaction.response.defer()

        config = load_config()
        guild_id = str(interaction.guild_id)
        saved = config.get("saved_accounts", {}).get(guild_id, {})

        if account not in saved:
            await interaction.followup.send(f"❌ Account `{account}` not found.", ephemeral=True)
            return

        creds = saved[account]
        username = creds.get("username", account)
        password = creds.get("password")

        if not password:
            await interaction.followup.send("❌ No password saved.", ephemeral=True)
            return

        client = LNApiClient()
        try:
            login_result = await client.login(username, password)
        except Exception as e:
            await interaction.followup.send(f"❌ Login failed: {e}", ephemeral=True)
            return

        curriculums = (
            login_result.get("curriculums")
            or login_result.get("user", {}).get("curriculums")
            or []
        )
        if not curriculums:
            await interaction.followup.send(f"ℹ️ No languages found for `{username}`.", ephemeral=True)
            return

        lines = []
        for c in curriculums:
            uid = c.get("uid", "?")
            name = c.get("language") or c.get("name") or f"UID {uid}"
            known = " ✅" if uid in CURRICULUM_LANGUAGES else ""
            lines.append(f"• **{name}** — UID `{uid}`{known}")

        embed = discord.Embed(
            title=f"🌐 Languages for {username}",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="✅ = mapped in bot, can farm directly")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="xp-status", description="Check active XP farm status")
    async def xp_status(self, interaction: discord.Interaction):
        """Check if any XP farm is running."""
        await interaction.response.send_message(
            "ℹ️ Use `/xp-farm` to start a new session.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(XPFarmCommands(bot))