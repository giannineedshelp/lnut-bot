"""
Stealth manager - human-like timing and accuracy helpers for LanguageNut submissions.

Supports one timing mode:
  - Per-question mode: each question/vocab gets a random time in [min_sec, max_sec]
                       Total timestamp = cumulative sum of per-question times.

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
    min_accuracy : int
        Minimum accuracy percentage (0-100).
    max_accuracy : int
        Maximum accuracy percentage (0-100).
        If min_accuracy > max_accuracy they are automatically swapped.
    min_seconds_per_question : float
        Minimum seconds per question/vocab item (default 5.0).
    max_seconds_per_question : float
        Maximum seconds per question/vocab item (default 8.0).
    """

    PER_QUESTION_MIN_SEC = 1.0
    PER_QUESTION_MAX_SEC = 300.0

    def __init__(
        self,
        speed: float = 10.0,
        min_accuracy: int = 85,
        max_accuracy: int = 92,
        min_seconds_per_question: float = 5.0,
        max_seconds_per_question: float = 8.0,
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

        self.min_seconds_per_question = float(min_seconds_per_question)
        self.max_seconds_per_question = float(max_seconds_per_question)
        if self.min_seconds_per_question > self.max_seconds_per_question:
            self.min_seconds_per_question, self.max_seconds_per_question = (
                self.max_seconds_per_question, self.min_seconds_per_question
            )
        self.min_seconds_per_question = max(self.PER_QUESTION_MIN_SEC, self.min_seconds_per_question)
        self.max_seconds_per_question = min(self.PER_QUESTION_MAX_SEC, self.max_seconds_per_question)

    # ------------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------------

    @property
    def effective_speed(self) -> float:
        """Returns average seconds per question."""
        return (self.min_seconds_per_question + self.max_seconds_per_question) / 2.0

    def compute_timestamp(self, num_questions: int = 1) -> int:
        """
        Return cumulative per-question completion time in ms.

        Each question gets a random time in [min_seconds_per_question,
        max_seconds_per_question]. Total = sum of all + small jitter.
        """
        total_s = 0.0
        for _ in range(num_questions):
            total_s += random.uniform(self.min_seconds_per_question, self.max_seconds_per_question)
        jitter = random.uniform(-0.5, 1.5)
        return math.floor((total_s + jitter) * 1000)

    def fake_time_display(self) -> str:
        """Human-readable string for per-question range."""
        return f"{self.min_seconds_per_question}–{self.max_seconds_per_question}s per question"

    def speed_display(self) -> str:
        """Human-readable per-question speed string."""
        return f"{self.min_seconds_per_question}–{self.max_seconds_per_question}s per question"

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
        return (
            f"<StealthManager per-question={self.min_seconds_per_question}–"
            f"{self.max_seconds_per_question}s "
            f"accuracy={self.min_accuracy}%–{self.max_accuracy}%>"
        )