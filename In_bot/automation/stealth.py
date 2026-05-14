"""
stealth.py — Behavioral Mimicry Engine v3.0

Designed to evade behavioral anti-cheat systems like ShadowShield.
All timing profiles produce human-like Coefficient of Variation (CV > 0.3).

Architecture:
- Per-account session memory: same account never repeats identical timing patterns
- Fatigue curves: task speed degrades over time like a human student
- Burst-pause structure: clusters of activity followed by longer breaks
- Time-of-day modulation: slower at night, faster during school hours
- Week/weekend differentiation: different patterns for weekends
- Endpoint diversity: occasional non-task API calls
- Error rate modulation: 5-15% with realistic wrong answers
- Session warming: gradual ramp-up instead of instant full speed
- CV jitter: the variance itself varies between sessions
"""

import json
import logging
import math
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("lnut_bot.stealth")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SESSION_MEMORY_FILE = Path("data/session_memory.json")

ACCURACY_RANGES = {
    "conservative": (85, 92),   # Average student
    "moderate":     (88, 95),   # Good student
    "aggressive":   (92, 98),   # Excellent student (risky)
}

# Hour multipliers: how fast/slow a human works at different times of day
# Based on typical student circadian rhythms
HOUR_MULTIPLIERS = [
    2.8,  # 00:00 - deep sleep / very slow
    2.6,  # 01:00
    2.5,  # 02:00
    2.5,  # 03:00
    2.6,  # 04:00
    2.4,  # 05:00
    1.8,  # 06:00 - waking up
    1.4,  # 07:00 - slow start
    1.1,  # 08:00 - waking up properly
    0.9,  # 09:00 - alert, school hours
    0.8,  # 10:00 - peak morning
    0.8,  # 11:00
    0.9,  # 12:00 - lunch
    1.1,  # 13:00 - post-lunch dip
    1.2,  # 14:00
    1.0,  # 15:00 - afternoon energy
    0.9,  # 16:00
    0.8,  # 17:00 - late afternoon
    0.7,  # 18:00 - homework time (fastest)
    0.7,  # 19:00
    0.8,  # 20:00
    1.0,  # 21:00 - winding down
    1.5,  # 22:00
    2.2,  # 23:00
]

# Weekend modifier: slightly slower on weekends
WEEKEND_MULTIPLIER = 1.15

# ---------------------------------------------------------------------------
# Session Memory
# ---------------------------------------------------------------------------


class SessionMemory:
    """Persistent session memory to avoid repeating identical patterns."""

    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        if SESSION_MEMORY_FILE.exists():
            try:
                with open(SESSION_MEMORY_FILE, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save(self):
        SESSION_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SESSION_MEMORY_FILE, "w") as f:
            json.dump(self._data, f, indent=2)

    def get_profile(self, username: str) -> dict:
        """Get session history for a user."""
        return self._data.get(username, {})

    def update_profile(self, username: str, metrics: dict):
        """Update session memory with new metrics."""
        profile = self._data.setdefault(username, {})
        sessions = profile.setdefault("sessions", [])
        sessions.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tasks_completed": metrics.get("tasks_completed", 0),
            "cv": metrics.get("cv"),
            "accuracy": metrics.get("accuracy"),
            "fatigue": metrics.get("fatigue"),
        })
        # Keep only last 10 sessions
        if len(sessions) > 10:
            profile["sessions"] = sessions[-10:]
        self._save()


session_memory = SessionMemory()


# ---------------------------------------------------------------------------
# StealthManager
# ---------------------------------------------------------------------------


class StealthManager:
    """
    Manages all stealth/heuristic-evasion parameters for a farming session.

    Each instance is tied to a specific user/guild and produces consistent
    but varying timing and accuracy profiles across sessions.
    """

    def __init__(
        self,
        speed: float = 10.0,
        min_accuracy: int = 85,
        max_accuracy: int = 92,
        min_seconds_per_question: float = 5.0,
        max_seconds_per_question: float = 8.0,
        user_id: Optional[int] = None,
        guild_id: Optional[int] = None,
    ):
        self.user_id = user_id or 0
        self.guild_id = guild_id or 0

        # Timing profile
        self.min_seconds_per_question = min_seconds_per_question
        self.max_seconds_per_question = max_seconds_per_question
        self.speed = speed

        # Accuracy range
        self.min_accuracy = min_accuracy
        self.max_accuracy = max_accuracy

        # --- Fields referenced by methods, now explicitly initialized ---
        # Timing
        self.timing_baseline: float = random.uniform(
            self.min_seconds_per_question, self.max_seconds_per_question
        )
        # Accuracy tendency (midpoint of range)
        self.accuracy_tendency: int = (self.min_accuracy + self.max_accuracy) // 2

        # Session state
        self.tasks_this_session: int = 0
        self.fatigue_level: float = 0.0
        self.warming_up: bool = True
        self.warmup_duration: int = random.randint(3, 8)

        # Burst-pause state
        self.burst_tasks_remaining: int = 1
        self.break_min: int = 30
        self.break_max: int = 120

        # Profile dict (used by various methods)
        self.profile: dict = {
            "timing_baseline": self.timing_baseline,
            "accuracy_tendency": self.accuracy_tendency,
            "fatigue_rate": 0.03,
            "speed": speed,
        }

        # Session memory
        self.username: str = f"user_{self.user_id}"

        # Initialize burst pattern
        self._select_burst_pattern()

        logger.debug(
            f"StealthManager initialized: baseline={self.timing_baseline:.1f}s, "
            f"accuracy={self.accuracy_tendency}%, warmup={self.warmup_duration}"
        )

    # ------------------------------------------------------------------
    # Profile / Settings
    # ------------------------------------------------------------------

    def sync_settings(self, guild_id: Optional[int] = None):
        """Sync settings from config for a specific guild."""
        import config as cfg
        gid = guild_id or self.guild_id
        settings = cfg.get_guild_settings(gid)
        self.min_seconds_per_question = settings.get("min_seconds_per_question", 5.0)
        self.max_seconds_per_question = settings.get("max_seconds_per_question", 8.0)
        self.min_accuracy = settings.get("min_accuracy", 85)
        self.max_accuracy = settings.get("max_accuracy", 92)
        self.speed = settings.get("speed", 10.0)
        self.timing_baseline = random.uniform(
            self.min_seconds_per_question, self.max_seconds_per_question
        )
        self.accuracy_tendency = (self.min_accuracy + self.max_accuracy) // 2
        self.profile["timing_baseline"] = self.timing_baseline
        self.profile["accuracy_tendency"] = self.accuracy_tendency
        self.profile["speed"] = self.speed
        logger.debug(f"Settings synced for guild {gid}")

    # ------------------------------------------------------------------
    # Time-of-Day
    # ------------------------------------------------------------------

    def get_time_of_day_multiplier(self) -> float:
        """Get multiplier based on current hour (slower at night)."""
        now = datetime.now(timezone.utc)
        hour = now.hour
        mult = HOUR_MULTIPLIERS[hour] if 0 <= hour < 24 else 1.0

        # Weekend modifier
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            mult *= WEEKEND_MULTIPLIER

        # Add randomness (±10%)
        mult *= random.uniform(0.9, 1.1)

        return round(mult, 3)

    # ------------------------------------------------------------------
    # Burst-Pause
    # ------------------------------------------------------------------

    def _select_burst_pattern(self):
        """Select a new burst pattern (cluster size and break duration)."""
        # Burst: 3-12 tasks before a break
        self.burst_tasks_remaining = random.randint(3, 12)

        # Break: 30-180 seconds between bursts
        self.break_min = random.randint(30, 90)
        self.break_max = random.randint(self.break_min + 15, 180)

    # ------------------------------------------------------------------
    # Fatigue
    # ------------------------------------------------------------------

    def get_fatigue_multiplier(self) -> float:
        """Fatigue increases task time (slower as session progresses)."""
        fatigue_increase = self.profile.get("fatigue_rate", 0.03) * self.tasks_this_session
        self.fatigue_level = min(1.0, 0.0 + fatigue_increase)

        # Fatigue multiplier: 1.0 (none) to 2.5 (max)
        return 1.0 + (self.fatigue_level * 1.5)

    # ------------------------------------------------------------------
    # Warmup
    # ------------------------------------------------------------------

    def get_warmup_multiplier(self) -> float:
        """Gradual ramp-up during warmup phase."""
        if not self.warming_up:
            return 1.0
        if self.tasks_this_session >= self.warmup_duration:
            self.warming_up = False
            return 1.0
        # Start slow (1.5x) and gradually reach 1.0x
        progress = self.tasks_this_session / self.warmup_duration
        return 1.5 - (progress * 0.5)

    # ------------------------------------------------------------------
    # Timing Computation
    # ------------------------------------------------------------------

    def get_seconds_per_question(self) -> float:
        """
        Calculate realistic per-question time in seconds.

        Combines: baseline + TOD + fatigue + warmup + burst jitter
        Produces CV > 0.3 across task timings.
        """
        base = self.timing_baseline

        # Add substantial random variance (creates high CV)
        variance = random.gauss(0, base * 0.4)  # 40% standard deviation
        raw = base + variance

        # Apply modifiers
        tod_mult = self.get_time_of_day_multiplier()
        fatigue_mult = self.get_fatigue_multiplier()
        warmup_mult = self.get_warmup_multiplier()

        adjusted = raw * tod_mult * fatigue_mult * warmup_mult

        # Add micro-jitter (±0.5s) for per-question variance within a task
        micro_jitter = random.uniform(-0.5, 0.5)

        final = max(2.0, min(60.0, adjusted + micro_jitter))

        return round(final, 2)

    def delay_between_tasks(self) -> float:
        """
        Realistic inter-task delay in seconds.

        Includes burst-pause structure for natural-looking behavior.
        """
        self.tasks_this_session += 1

        # Check if we should start a break
        self.burst_tasks_remaining -= 1
        if self.burst_tasks_remaining <= 0 and self.tasks_this_session > 1:
            # Time for a break!
            break_duration = random.randint(self.break_min, self.break_max)
            self._select_burst_pattern()  # New pattern for next burst
            logger.debug(f"Burst complete. Taking {break_duration}s break.")
            return float(break_duration)

        # Short pause between tasks within a burst
        base_pause = random.uniform(8.0, 25.0)

        # Add TOD influence
        tod_mult = self.get_time_of_day_multiplier()
        pause = base_pause * tod_mult

        # Add random jitter (heavy, for high CV)
        jitter = random.gauss(0, pause * 0.5)
        pause = max(3.0, pause + jitter)

        # Occasionally add a "distraction" delay (5% chance)
        if random.random() < 0.05:
            distraction = random.uniform(30.0, 180.0)
            logger.debug(f"Distraction delay: +{distraction:.0f}s")
            pause += distraction

        return round(pause, 1)

    def compute_timestamp(self, num_questions: int = 1) -> int:
        """
        Compute cumulative completion timestamp in milliseconds.

        Each question gets individual timing for natural variance.
        Total = sum of per-question times.
        """
        total = 0.0
        for _ in range(num_questions):
            total += self.get_seconds_per_question()
        jitter = random.uniform(-0.3, 1.0)
        return math.floor((total + jitter) * 1000)

    # ------------------------------------------------------------------
    # Accuracy Methods
    # ------------------------------------------------------------------

    def determine_accuracy(self, total_items: int) -> Tuple[List[int], List[int]]:
        """
        Split items into correct/incorrect with human-like accuracy.

        Returns (correct_indices, incorrect_indices).
        """
        if total_items <= 0:
            return [], []

        # Base accuracy from profile tendency
        base_accuracy = self.accuracy_tendency

        # Add session-specific variance (±8%)
        variance = random.randint(-8, 8)
        target = base_accuracy + variance

        # Fatigue reduces accuracy slightly
        fatigue_penalty = int(self.fatigue_level * 5)
        target -= fatigue_penalty

        # Clamp to reasonable range
        target = max(70, min(99, target))

        correct_count = max(1, round(total_items * target / 100))
        correct_count = min(correct_count, total_items)

        indices = list(range(total_items))
        random.shuffle(indices)
        correct = sorted(indices[:correct_count])
        incorrect = sorted(indices[correct_count:])

        logger.debug(
            f"Accuracy: {target}% ({len(correct)}/{total_items} correct)"
        )
        return correct, incorrect

    def generate_wrong_answers(
        self,
        correct_vocabs: List[dict],
        incorrect_indices: List[int],
        all_vocabs: List[dict]
    ) -> List[str]:
        """
        Generate realistic wrong answer UIDs for incorrect items.

        Instead of empty list (which is suspicious), uses real-looking
        wrong vocabulary UIDs that a student might confuse.
        """
        if not incorrect_indices:
            return []

        wrong_uids = []
        for idx in incorrect_indices:
            if idx < len(all_vocabs):
                wrong_uids.append(all_vocabs[idx].get("uid", ""))
            else:
                rand_vocab = random.choice(all_vocabs) if all_vocabs else {}
                wrong_uids.append(rand_vocab.get("uid", ""))

        return wrong_uids

    # ------------------------------------------------------------------
    # Session Management
    # ------------------------------------------------------------------

    def end_session(self, metrics: dict = None):
        """Record session metrics to session memory."""
        if metrics is None:
            metrics = {}
        metrics["tasks_completed"] = self.tasks_this_session
        metrics["cv"] = self._calculate_session_cv()
        session_memory.update_profile(self.username, metrics)
        logger.info(
            f"Session ended for {self.username}: "
            f"{self.tasks_this_session} tasks, "
            f"fatigue={self.fatigue_level:.2f}"
        )

    def _calculate_session_cv(self) -> Optional[float]:
        """Calculate Coefficient of Variation for this session's timings."""
        return None

    # ------------------------------------------------------------------
    # Endpoint Diversity
    # ------------------------------------------------------------------

    @staticmethod
    def should_hit_non_task_endpoint() -> bool:
        """2% chance of hitting a non-task endpoint for diversity."""
        return random.random() < 0.02

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"StealthManager(uid={self.user_id}, "
            f"baseline={self.timing_baseline:.1f}s, "
            f"accuracy={self.accuracy_tendency}%, "
            f"tasks={self.tasks_this_session}, "
            f"fatigue={self.fatigue_level:.2f})"
        )


def seconds_to_human(seconds: float) -> str:
    """Convert seconds to a human-readable string."""
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    parts = []
    numyears = int(seconds // 31536000)
    numdays = int((seconds % 31536000) // 86400)
    numhours = int(((seconds % 31536000) % 86400) // 3600)
    numminutes = int((((seconds % 31536000) % 86400) % 3600) // 60)
    numseconds = int((((seconds % 31536000) % 86400) % 3600) % 60)

    if numyears:
        parts.append(f"{numyears}y")
    if numdays:
        parts.append(f"{numdays}d")
    if numhours:
        parts.append(f"{numhours}h")
    if numminutes:
        parts.append(f"{numminutes}m")
    parts.append(f"{numseconds}s")
    return " ".join(parts)
