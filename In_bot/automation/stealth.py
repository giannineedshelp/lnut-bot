"""
Stealth manager - human-like timing and accuracy helpers for LanguageNut submissions.

Supports two timing modes:
  - Normal mode:     speed = seconds per task (direct value, e.g. 10.0)
  - Fake-time mode:  speed = 10^fake_time_exponent (mirrors JS slider: speed = 10 ** value)
                     This allows very large fake timestamps (e.g. years) like the JS UI does.

Accuracy range:
  - min_accuracy / max_accuracy (0–100 %)
  - A random target between min and max is chosen per task.
  - Mirrors the JS reference: correctVocabs contains the winning subset.
"""

from __future__ import annotations

import logging
import math
import random

logger = logging.getLogger("lnut_bot.stealth")


def seconds_to_human(seconds: float) -> str:
    """
    Convert a seconds value to a human-readable string.
    Mirrors JS secondsToString() exactly.

    Examples
    --------
    >>> seconds_to_human(10000)
    '0 years 0 days 2 hours 46 minutes 40 seconds'
    >>> seconds_to_human(31536000)
    '1 years 0 days 0 hours 0 minutes 0 seconds'
    """
    seconds = int(seconds)
    num_years   = seconds // 31536000
    num_days    = (seconds % 31536000) // 86400
    num_hours   = ((seconds % 31536000) % 86400) // 3600
    num_minutes = (((seconds % 31536000) % 86400) % 3600) // 60
    num_seconds = (((seconds % 31536000) % 86400) % 3600) % 60
    return (
        f"{num_years} years {num_days} days "
        f"{num_hours} hours {num_minutes} minutes {num_seconds} seconds"
    )


class StealthManager:
    """
    Human-like timing + accuracy helper.

    Parameters
    ----------
    speed : float
        Base seconds per task. Used when fake_time_enabled=False.
        Minimum enforced: 3.0 seconds.
    min_accuracy : int
        Minimum accuracy percentage (0–100).
    max_accuracy : int
        Maximum accuracy percentage (0–100).
        If min_accuracy > max_accuracy they are automatically swapped.
    fake_time_enabled : bool
        When True, use fake_time_exponent to compute an inflated timestamp
        (mirrors JS: speed = 10 ** slider_value).
    fake_time_exponent : float
        The exponent x in 10^x seconds. E.g. 4.0 → 10000 seconds (~2.8 hours).
        Valid range: 0.0–7.0  (7.0 ≈ 3.17 years).
    """

    FAKE_TIME_MIN_EXP = 0.0
    FAKE_TIME_MAX_EXP = 7.0

    def __init__(
        self,
        speed: float = 10.0,
        min_accuracy: int = 85,
        max_accuracy: int = 92,
        fake_time_enabled: bool = False,
        fake_time_exponent: float = 4.0,
    ):
        # Clamp individual values first
        min_accuracy = max(0, min(100, int(min_accuracy)))
        max_accuracy = max(0, min(100, int(max_accuracy)))

        # Guard against inverted accuracy range — auto-swap if needed
        if min_accuracy > max_accuracy:
            min_accuracy, max_accuracy = max_accuracy, min_accuracy

        self.speed        = max(3.0, float(speed))
        self.min_accuracy = min_accuracy
        self.max_accuracy = max_accuracy

        self.fake_time_enabled  = bool(fake_time_enabled)
        self.fake_time_exponent = max(
            self.FAKE_TIME_MIN_EXP,
            min(self.FAKE_TIME_MAX_EXP, float(fake_time_exponent)),
        )

    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------

    @property
    def effective_speed(self) -> float:
        """
        Returns the effective seconds-per-task value.
        In fake-time mode this mirrors JS: speed = 10 ** exponent.
        """
        if self.fake_time_enabled:
            return 10 ** self.fake_time_exponent
        return self.speed

    def compute_timestamp(self) -> int:
        """
        Return task completion time in milliseconds with small jitter.

        Mirrors JS exactly:
          Math.floor(speed + ((Math.random() - 0.5) / 10) * speed) * 1000

        The jitter is ±5 % of the base speed, keeping the value realistic.
        """
        s      = self.effective_speed
        jitter = ((random.random() - 0.5) / 10) * s
        return math.floor(s + jitter) * 1000

    def fake_time_display(self) -> str:
        """Human-readable string for the current effective speed."""
        return seconds_to_human(self.effective_speed)

    def speed_display(self) -> str:
        """
        Human-readable speed string regardless of mode.
        Useful for settings embeds.
        """
        return seconds_to_human(self.effective_speed)

    def delay_between_tasks(self) -> float:
        """
        Realistic inter-task delay in seconds.
        Scales with speed, capped at 3 s to avoid excessive waits.
        """
        base_delay = min(3.0, self.speed * 0.15)
        jitter     = random.uniform(-0.5, 1.5)
        return max(0.5, base_delay + jitter)

    def human_typing_delay(self, char_count: int) -> float:
        base  = random.uniform(0.3, 1.0)
        extra = max(0, char_count - 50) * 0.002
        return base + extra

    # ------------------------------------------------------------------
    # Accuracy
    # ------------------------------------------------------------------

    def apply_accuracy(self, total_items: int) -> tuple[list[int], list[int]]:
        """
        Split answer indexes into correct and incorrect groups.

        A random accuracy target is chosen uniformly between min_accuracy
        and max_accuracy for each call, giving natural variation.

        Returns
        -------
        correct_indices : list[int]
        incorrect_indices : list[int]
        """
        if total_items <= 0:
            return [], []

        # Pick a random target within the configured accuracy band
        if self.min_accuracy == self.max_accuracy:
            target_accuracy = float(self.min_accuracy)
        else:
            target_accuracy = random.uniform(self.min_accuracy, self.max_accuracy)

        correct_count = max(1, round(total_items * target_accuracy / 100))
        correct_count = min(correct_count, total_items)

        indices = list(range(total_items))
        random.shuffle(indices)
        correct   = sorted(indices[:correct_count])
        incorrect = sorted(indices[correct_count:])

        logger.debug(
            "Accuracy: target=%.1f%%, correct=%d/%d (range %d%%–%d%%)",
            target_accuracy,
            len(correct),
            total_items,
            self.min_accuracy,
            self.max_accuracy,
        )
        return correct, incorrect

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        mode = (
            f"fake_time(exp={self.fake_time_exponent}, "
            f"≈{self.fake_time_display()})"
            if self.fake_time_enabled
            else f"speed={self.speed}s"
        )
        return (
            f"<StealthManager {mode} "
            f"accuracy={self.min_accuracy}%–{self.max_accuracy}%>"
        )