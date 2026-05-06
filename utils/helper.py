import math
import random
from datetime import datetime, timedelta, timezone


def extract_task_id(task) -> str:
    """Extract a readable identifier for a task."""
    uid = task.get("gameUid", "") or task.get("uid", "") or ""
    return uid[:12] + "..." if len(uid) > 12 else uid


def format_homework_list(homeworks: list) -> str:
    """Format homeworks into a Discord-friendly string."""
    if not homeworks:
        return "No homeworks found."

    lines = []
    for hw in homeworks:
        name = hw.get("name", "Unnamed")
        hw_id = hw.get("id", "?")
        due = hw.get("dueDate", "")
        tasks = hw.get("tasks", [])
        completed = sum(1 for t in tasks if t.get("gameResults"))
        total = len(tasks)
        lines.append(f"**{name}** (ID: {hw_id})")
        if due:
            lines.append(f"  Due: {due}")
        lines.append(f"  Progress: {completed}/{total} tasks")
        for i, task in enumerate(tasks):
            task_name = task.get("translation", "Unknown")
            pct = task.get("gameResults", {}).get("percentage", "-") if task.get("gameResults") else "—"
            lines.append(f"  `[{i}]` {task_name} — {pct}%")
        lines.append("")
    return "\n".join(lines)


def seconds_to_string(seconds: float) -> str:
    """Convert seconds to a human-readable duration string."""
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


def cooldown_timestamp(seconds: float) -> str:
    """Return a Discord relative timestamp for when cooldown ends."""
    dt = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    timestamp = int(dt.timestamp())
    return f"<t:{timestamp}:R>"


def random_delay_ms(min_ms: float, max_ms: float) -> float:
    """Generate a random delay in milliseconds within range."""
    return random.uniform(min_ms, max_ms)