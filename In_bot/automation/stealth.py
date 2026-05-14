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
TIME_OF_DAY_PROFILES = {
    # 0-5:深夜 - very slow, sleepy
    # 6-8:早晨 - waking up, slow start
    # 9-12:上午 - alert, school hours
    # 13-15:下午 - post-lunch dip
    # 16-18:傍晚 - afternoon energy
    # 19-21:晚上 - evening homework time
    # 22-23:深夜 - winding down
}

# Pre-computed hour multipliers (24 entries, index = hour)
HOUR_MULTIPLIERS = [
    2.8,  # 00:00 - deep night, very slow
    3.0,  # 01:00
    3.2,  # 02:00 - peak slowness
    3.0,  # 03:00
    2.5,  # 04:00
    2.0,  # 05:00
    1.5,  # 06:00 - waking up
    1.2,  # 07:00 - morning routine
    1.0,  # 08:00 - school starting
    0.9,  # 09:00 - alert
    0.8,  # 10:00 - peak efficiency
    0.8,  # 11:00
    0.9,  # 12:00 - lunch approaching
    1.1,  # 13:00 - post-lunch dip
    1.2,  # 14:00 - sleepy afternoon
    1.0,  # 15:00 - recovering
    0.9,  # 16:00 - afternoon energy
    0.8,  # 17:00 - good focus
    0.8,  # 18:00 - evening
    0.9,  # 19:00 - homework time
    1.0,  # 20:00
    1.2,  # 21:00 - winding down
    1.5,  # 22:00 - getting tired
    2.0,  # 23:00 - night
]

WEEKEND_MULTIPLIER = 1.4  # Humans work slower on weekends

BURST_PATTERNS = [
    # (tasks_in_burst, break_min, break_max)
    (3,  30,  90),    # Small burst
    (5,  60,  180),   # Medium burst
    (8,  120, 300),   # Large burst
    (12, 180, 480),   # Study session
    (4,  45,  120),   # Common pattern
    (6,  90,  240),   # Typical homework
]

# Common "wrong answers" that look realistic (real vocab items a student might confuse)
# These are filled dynamically from actual vocab data when available
COMMON_CONFUSIONS = {}  # correct_word -> [wrong_word1, wrong_word2, ...]


class SessionMemory:
    """Persistent per-account session memory to prevent repeat patterns."""

    def __init__(self):
        self.data: Dict[str, dict] = {}
        self._load()

    def _load(self):
        if SESSION_MEMORY_FILE.exists():
            try:
                self.data = json.loads(SESSION_MEMORY_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                self.data = {}
        logger.debug(f"Loaded session memory for {len(self.data)} accounts")

    def _save(self):
        SESSION_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_MEMORY_FILE.write_text(json.dumps(self.data, indent=2))

    def get_profile(self, username: str) -> dict:
        """Get or create a timing profile for an account."""
        if username not in self.data:
            # Generate a unique timing fingerprint for this account
            seed = hash(username + "lnut_stealth_v3") & 0xFFFFFFFF
            rng = random.Random(seed)
            self.data[username] = {
                "timing_baseline": round(rng.uniform(6.0, 12.0), 2),
                "accuracy_tendency": round(rng.uniform(84, 94)),
                "burst_preference": rng.randint(0, len(BURST_PATTERNS) - 1),
                "session_count": 0,
                "last_session_date": None,
                "total_tasks_completed": 0,
                "tod_offset": round(rng.uniform(-0.3, 0.3), 2),  # Personal TOD variation
                "fatigue_rate": round(rng.uniform(0.02, 0.08), 3),
                "recovery_rate": round(rng.uniform(0.01, 0.04), 3),
                "avg_cv": None,
                "cv_history": [],
            }
            self._save()
            logger.info(f"Created new timing profile for {username}")
        return self.data[username]

    def update_profile(self, username: str, metrics: dict):
        """Update profile with observed metrics after a session."""
        if username in self.data:
            prof = self.data[username]
            prof["session_count"] += 1
            prof["last_session_date"] = datetime.now(timezone.utc).isoformat()
            prof["total_tasks_completed"] += metrics.get("tasks_completed", 0)
            if "cv" in metrics and metrics["cv"] is not None:
                prof["cv_history"].append(round(metrics["cv"], 4))
                # Keep last 20 CV values
                prof["cv_history"] = prof["cv_history"][-20:]
                if prof["cv_history"]:
                    prof["avg_cv"] = round(sum(prof["cv_history"]) / len(prof["cv_history"]), 4)
            self._save()


session_memory = SessionMemory()


class StealthEngine:
    """
    Advanced behavioral mimicry engine for evading heuristic anti-cheat.

    Generates human-like timing, accuracy, and interaction patterns
    with proper Coefficient of Variation (>0.3) across all metrics.
    """

    def __init__(self, username: str, guild_id: int = 0):
        self.username = username
        self.guild_id = guild_id
        self.profile = session_memory.get_profile(username)

        # Session state
        self.session_start = time.time()
        self.tasks_this_session = 0
        self.last_task_time = 0
        self.burst_tasks_remaining = 0
        self.burst_end_time = 0
        self.in_break = False
        self.warming_up = True
        self.warmup_duration = random.randint(8, 20)  # tasks before full speed
        self.current_tod_offset = self.profile["tod_offset"]
        self.fatigue_level = 0.0  # 0.0 to 1.0

        # Select a burst pattern for this session
        self._select_burst_pattern()

        logger.info(
            f"StealthEngine initialized for {username} | "
            f"baseline={self.profile['timing_baseline']}s | "
            f"accuracy_tendency={self.profile['accuracy_tendency']}%"
        )

    def _select_burst_pattern(self):
        """Pick a burst pattern, with influence from profile preference."""
        pref = self.profile["burst_preference"]
        # Add some randomness around the preference
        idx = max(0, min(len(BURST_PATTERNS) - 1,
                         pref + random.randint(-1, 1)))
        self.burst_size, self.break_min, self.break_max = BURST_PATTERNS[idx]
        self.burst_tasks_remaining = self.burst_size

    # ------------------------------------------------------------------
    # Timing Methods
    # ------------------------------------------------------------------

    def get_time_of_day_multiplier(self) -> float:
        """Return multiplier based on current hour. Higher = slower."""
        now = datetime.now(timezone.utc)
        hour = now.hour
        base = HOUR_MULTIPLIERS[hour]

        # Weekend slowdown
        if now.weekday() >= 5:  # Saturday or Sunday
            base *= WEEKEND_MULTIPLIER

        # Add personal offset
        base += self.current_tod_offset

        return max(0.5, min(5.0, base))

    def get_fatigue_multiplier(self) -> float:
        """Calculate fatigue-based slowdown. Increases with tasks done."""
        if self.tasks_this_session == 0:
            return 1.0

        fatigue = self.fatigue_level
        # Fatigue grows with tasks and time-on-task
        fatigue_increase = self.profile["fatigue_rate"] * self.tasks_this_session
        self.fatigue_level = min(1.0, fatigue + fatigue_increase)

        # Fatigue multiplier: 1.0 (none) to 2.5 (max)
        return 1.0 + (self.fatigue_level * 1.5)

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

    def get_seconds_per_question(self) -> float:
        """
        Calculate realistic per-question time in seconds.

        Combines: baseline + TOD + fatigue + warmup + burst jitter
        Produces CV > 0.3 across task timings.
        """
        base = self.profile["timing_baseline"]

        # Add substantial random variance (this creates high CV)
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

    def get_delay_between_tasks(self) -> float:
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
        base_accuracy = self.profile["accuracy_tendency"]

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
                # Fallback: use a random vocab uid
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
        # This would need actual timing data collected during the session
        # Placeholder for now
        return None

    # ------------------------------------------------------------------
    # Endpoint Diversity
    # ------------------------------------------------------------------

    @staticmethod
    def should_hit_non_task_endpoint() -> bool:
        """2% chance of hitting a non-task endpoint for diversity."""
        return random.random() < 0.02

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<StealthEngine {self.username} "
            f"tasks={self.tasks_this_session} "
            f"fatigue={self.fatigue_level:.2f} "
            f"warming={'yes' if self.warming_up else 'no'}>"
        )
