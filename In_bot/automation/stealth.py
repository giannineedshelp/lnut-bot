import math
import random
import logging
from datetime import datetime, timezone

logger = logging.getLogger("lnut_bot.stealth")


class StealthManager:
    """
    Manages stealth features to mimic human-like behavior and avoid anti-cheat detection.

    Anti-cheat systems typically look for:
    - Impossible completion times (e.g., 50 tasks in 2 seconds)
    - Perfect scores on every task
    - Identical patterns across submissions
    - Missing or invalid timestamps

    This manager addresses all of the above with randomized jitter and configurable accuracy.
    """

    def __init__(self, speed: float = 10.0, min_accuracy: int = 85, max_accuracy: int = 92):
        """
        Args:
            speed: Base completion speed in seconds per task
            min_accuracy: Minimum accuracy percentage
            max_accuracy: Maximum accuracy percentage
        """
        self.speed = speed
        self.min_accuracy = min_accuracy
        self.max_accuracy = max_accuracy

    def compute_timestamp(self) -> int:
        """
        Calculate the fake timeSpent for a task (in milliseconds).
        
        Matches the JS formula from lnut-client exactly:
        Math.floor(speed + ((Math.random() - 0.5) / 10) * speed) * 1000
        
        The jitter formula adds/subtracts up to 5% of the base speed,
        distributing completion times in a realistic bell-like curve.
        
        Returns:
            int: Timestamp in milliseconds
        """
        jitter = (random.random() - 0.5) / 10
        time_spent_seconds = self.speed + (jitter * self.speed)
        time_spent_ms = math.floor(time_spent_seconds) * 1000
        return time_spent_ms

    def apply_accuracy(self, total_items: int) -> tuple[list[int], list[int]]:
        """
        Split items into correct and incorrect groups based on configured accuracy range.
        
        Instead of always hitting exactly min_accuracy, this picks a random target
        within the range [min_accuracy, max_accuracy] to avoid suspicious consistency.
        
        Args:
            total_items: Total number of vocabulary items
            
        Returns:
            tuple: (correct_indices, incorrect_indices)
        """
        if total_items == 0:
            return [], []

        # Pick a random accuracy target within the configured range
        target_accuracy = random.uniform(self.min_accuracy, self.max_accuracy)
        target_correct = max(1, round(total_items * target_accuracy / 100))

        # Clamp: at least 1 correct, at most all items
        correct_count = min(target_correct, total_items - 1) if total_items > 1 else 1
        wrong_count = total_items - correct_count

        indices = list(range(total_items))
        random.shuffle(indices)

        correct_indices = indices[:correct_count]
        incorrect_indices = indices[correct_count:]

        logger.debug(
            f"Accuracy: target={target_accuracy:.1f}%, "
            f"correct={correct_count}/{total_items}, "
            f"wrong={wrong_count}/{total_items}"
        )

        return correct_indices, incorrect_indices

    def delay_between_tasks(self) -> float:
        """
        Generate a human-like delay between tasks.
        
        Real users pause between tasks. This generates delays that look natural:
        - Short tasks: 1-4 second gap
        - The delay includes some randomness proportional to the speed setting
        
        Returns:
            float: Delay in seconds
        """
        base_delay = min(3.0, self.speed * 0.15)
        jitter = random.uniform(-0.5, 1.5)
        return max(0.5, base_delay + jitter)

    def human_typing_delay(self, char_count: int) -> float:
        """
        Simulate the time a human would spend "typing" or reviewing before submitting.
        
        For longer tasks (more vocab items), humans spend slightly longer reviewing.
        
        Args:
            char_count: Length of data being submitted (proxy for task complexity)
            
        Returns:
            float: Delay in seconds
        """
        base = random.uniform(0.3, 1.0)
        per_item_delay = max(0, char_count - 50) * 0.002
        return base + per_item_delay
ement or timeout
        try:
            await page.wait_for_function(
                '() => window.location.href.includes("dashboard") || document.querySelector(\'[class*="dashboard"]\') !== null',
                timeout=20000,
            )
        except Exception:
            pass

        await asyncio.sleep(human_delay(2, 4))

        # Save token if captured
        if captured_token:
            config.data["saved_token"] = captured_token
            config.save()

        # [4/4] Answer questions
        await status_callback(f"🕵️ **Stealth Browser**\n[4/4] Answering questions ({acc*100:.0f}% accuracy)...")

        total = 0
        fails = 0
        max_q = config["max_questions"]
        td_min = config["think_delay_min"]
        td_max = config["think_delay_max"]

        for qnum in range(max_q):
            await asyncio.sleep(human_delay(td_min, td_max))

            found = False

            # Strategy 1: Clickable options (radio buttons, choices)
            for sel in [
                '[class*="option"]', '[class*="choice"]', '[role="radio"]',
                'button:not([disabled])', '[class*="selectable"]', '[class*="answer"]',
                'label:not(:has(input))', '[class*="btn-option"]',
            ]:
                try:
                    opts = await page.query_selector_all(sel)
                except Exception:
                    opts = []
                real = []
                for o in opts:
                    try:
                        t = (await o.text_content() or "").lower().strip()
                    except Exception:
                        t = ""
                    if t and not any(
                        w in t for w in ["login", "sign in", "register", "submit", "dashboard", "logout"]
                    ):
                        real.append(o)
                if len(real) >= 2:
                    idx = 0 if random.random() < acc else random.randint(1, len(real) - 1)
                    idx = min(idx, len(real) - 1)
                    try:
                        await real[idx].click()
                        found = True
                        break
                    except Exception:
                        continue
            if found:
                total += 1
                fails = 0
                if total % 15 == 0:
                    await status_callback(f"🕵️ **Stealth Browser** — Running...\nAnswered: {total}/{max_q}")
                continue

            # Strategy 2: Text inputs
            for sel in ['input[type="text"]', 'textarea', '[contenteditable="true"]']:
                try:
                    inps = await page.query_selector_all(sel)
                except Exception:
                    inps = []
                for inp in inps:
                    try:
                        pid = (await inp.get_attribute("placeholder") or "").lower()
                        if any(w in pid for w in ["user", "pass", "email"]):
                            continue
                        await inp.click()
                        await asyncio.sleep(human_delay(0.1, 0.3))
                        words = ["yes", "no", "hello", "book", "house", "red", "blue",
                                  "one", "two", "three", "big", "small", "hot", "cold",
                                  "good", "bad", "up", "down", "left", "right"]
                        await inp.fill(random.choice(words))
                        found = True
                        break
                    except Exception:
                        continue
                if found:
                    break
            if found:
                total += 1
                fails = 0
                if total % 15 == 0:
                    await status_callback(f"🕵️ **Stealth Browser** — Running...\nAnswered: {total}/{max_q}")
                continue

            # Strategy 3: Navigation buttons
            for txt in ["Next", "Continue", "Submit", "Check", "Done", "Finish", "OK", ">", "→"]:
                for sel in [
                    f'button:has-text("{txt}")',
                    f'[class*="btn"]:has-text("{txt}")',
                    f'a:has-text("{txt}")',
                ]:
                    try:
                        btn = await page.query_selector(sel)
                        if btn:
                            await btn.click()
                            found = True
                            break
                    except Exception:
                        continue
                if found:
                    break
            if found:
                total += 1
                fails = 0
                if total % 15 == 0:
                    await status_callback(f"🕵️ **Stealth Browser** — Running...\nAnswered: {total}/{max_q}")
                continue

            # Nothing found — increment failure counter
            fails += 1
            if fails >= 20:
                break

        await browser.close()

    result = {
        "answered": total,
        "accuracy": round(acc * 100, 1),
        "mode": "stealth",
    }
    await complete_callback(result)
    logger.info(f"[Stealth] User {discord_id} answered {total} questions at {acc*100:.0f}% accuracy")
