"""
Stealth manager - human-like timing and accuracy helpers for LanguageNut submissions.
"""

from __future__ import annotations

import logging
import math
import random

logger = logging.getLogger("lnut_bot.stealth")


class StealthManager:
    """Human-like timing + accuracy helper."""

    def __init__(
        self,
        speed: float = 10.0,
        min_accuracy: int = 85,
        max_accuracy: int = 92,
    ):
        # Guard against inverted ranges
        if min_accuracy > max_accuracy:
            min_accuracy, max_accuracy = max_accuracy, min_accuracy
        self.speed = max(3.0, float(speed))
        self.min_accuracy = max(0, min(100, int(min_accuracy)))
        self.max_accuracy = max(self.min_accuracy, min(100, int(max_accuracy)))

    def compute_timestamp(self) -> int:
        """Return task completion time in milliseconds with small jitter."""
        jitter = (random.random() - 0.5) / 10
        time_spent_seconds = self.speed + (jitter * self.speed)
        return math.floor(time_spent_seconds) * 1000

    def apply_accuracy(self, total_items: int) -> tuple[list[int], list[int]]:
        """Split answer indexes into correct and incorrect groups."""
        if total_items <= 0:
            return [], []

        target_accuracy = random.uniform(self.min_accuracy, self.max_accuracy)
        correct_count = max(1, round(total_items * target_accuracy / 100))
        correct_count = min(correct_count, total_items)

        indices = list(range(total_items))
        random.shuffle(indices)
        correct = indices[:correct_count]
        incorrect = indices[correct_count:]

        logger.debug(
            "Accuracy: target=%.1f%%, correct=%d/%d",
            target_accuracy,
            len(correct),
            total_items,
        )
        return correct, incorrect

    def delay_between_tasks(self) -> float:
        base_delay = min(3.0, self.speed * 0.15)
        jitter = random.uniform(-0.5, 1.5)
        return max(0.5, base_delay + jitter)

    def human_typing_delay(self, char_count: int) -> float:
        base = random.uniform(0.3, 1.0)
        extra = max(0, char_count - 50) * 0.002
        return base + extra