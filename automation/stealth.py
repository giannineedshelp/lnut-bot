import math
import random
import logging

logger = logging.getLogger("lnut_bot.stealth")


class StealthManager:
    def __init__(self, speed: float = 10.0, min_accuracy: int = 85, max_accuracy: int = 92):
        self.speed = speed
        self.min_accuracy = min_accuracy
        self.max_accuracy = max_accuracy

    def compute_timestamp(self) -> int:
        jitter = (random.random() - 0.5) / 10
        time_spent_seconds = self.speed + (jitter * self.speed)
        return math.floor(time_spent_seconds) * 1000

    def apply_accuracy(self, total_items: int):
        if total_items <= 0:
            return [], []

        target_accuracy = random.uniform(self.min_accuracy, self.max_accuracy)
        correct_count = max(1, round(total_items * target_accuracy / 100))
        correct_count = min(correct_count, total_items)

        indices = list(range(total_items))
        random.shuffle(indices)

        correct = indices[:correct_count]
        wrong = indices[correct_count:]

        return correct, wrong

    def delay_between_tasks(self) -> float:
        base_delay = min(3.0, self.speed * 0.15)
        jitter = random.uniform(-0.5, 1.5)
        return max(0.5, base_delay + jitter)

    def human_typing_delay(self, char_count: int) -> float:
        base = random.uniform(0.3, 1.0)
        extra = max(0, char_count - 50) * 0.002
        return base + extra