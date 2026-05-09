"""
Homework discovery and metadata resolution.

Mirrors the logic from lnut-client's client_application class.
"""

from __future__ import annotations

import logging
from utils.helper import _pct, _is_done

logger = logging.getLogger("lnut_bot.discover")


class HomeworkDiscoverer:
    """Discover and resolve homework/task structure."""

    TASK_PATTERNS = {
        "sentence": "sentenceCatalog",
        "verb":     "verbUid",
        "phonic":   "phonicCatalogUid",
        "exam":     "examUid",
    }

    def __init__(self, api_client):
        self.api = api_client
        self.module_translations: dict = {}
        self.display_translations: dict = {}

    def resolve_task_type(self, task: dict) -> str:
        """Determine the type of task by inspecting its gameLink."""
        game_link = task.get("gameLink", "")
        for task_type, pattern in self.TASK_PATTERNS.items():
            if pattern in game_link:
                return task_type
        return "vocabs"

    async def get_all_homeworks(self, token: str) -> list[dict]:
        """Fetch all viewable homeworks for the logged-in user."""
        data = await self.api.call_lnut(
            "assignmentController/getViewableAll", {"token": token}
        )
        homeworks = data.get("homework", []) or []
        homeworks.reverse()  # newest first (mirrors JS .reverse())
        logger.info("Fetched %d homeworks", len(homeworks))
        return homeworks

    async def get_tasks_by_ids(
        self, token: str, homework_id: int, task_ids: list[str]
    ) -> list[dict]:
        homeworks = await self.get_all_homeworks(token)
        target = next((h for h in homeworks if h.get("id") == homework_id), None)
        if not target:
            logger.warning("Homework %s not found", homework_id)
            return []
        tasks   = target.get("tasks", [])
        matched = [t for t in tasks if t.get("gameUid") in task_ids]
        logger.info(
            "Found %d/%d tasks in hw %s", len(matched), len(task_ids), homework_id
        )
        return matched

    async def get_incomplete_tasks(self, token: str) -> list[tuple[dict, dict]]:
        """
        Return all (homework, task) pairs where the task is not yet at 100%.

        Fix: previously checked percentage == 0, which missed partially-done tasks.
        Now correctly uses _is_done() which checks >= 100, matching commands.py.
        """
        homeworks = await self.get_all_homeworks(token)
        incomplete: list[tuple[dict, dict]] = []
        for hw in homeworks:
            for task in hw.get("tasks", []):
                if not _is_done(task):
                    incomplete.append((hw, task))
        logger.info(
            "Found %d incomplete tasks across %d homeworks",
            len(incomplete),
            len(homeworks),
        )
        return incomplete

    async def _load_translations(self) -> None:
        """Load module and display translations from the API."""
        data = await self.api.call_lnut(
            "translationController/getUserModuleTranslations",
            {"token": self.api.token},
        )
        self.module_translations = data.get("translations", {}) or {}

        data2 = await self.api.call_lnut(
            "publicTranslationController/getTranslations", {}
        )
        self.display_translations = data2.get("translations", {}) or {}

    async def get_task_name(self, task: dict) -> str:
        """
        Resolve a human-readable task name.

        Mirrors JS get_task_name():
          name = task.verb_name
          if module_translations: name = module_translations[task.module_translations[0]]
          if module_translation:  name = module_translations[task.module_translation]
        Then prepends display_translations[task.translation] if available.
        """
        name = task.get("verb_name", "Unknown Task")

        # Lazy-load translations if not yet fetched
        if not self.module_translations:
            try:
                await self._load_translations()
            except Exception as e:
                logger.warning("Could not load module translations: %s", e)

        # module_translations (list) — use first element as key
        mts = task.get("module_translations")
        if mts and self.module_translations:
            resolved = self.module_translations.get(str(mts[0]))
            if resolved:
                name = resolved

        # module_translation (single key)
        mt = task.get("module_translation")
        if mt and self.module_translations:
            resolved = self.module_translations.get(str(mt))
            if resolved:
                name = resolved

        # Prepend display category name if available
        tr = task.get("translation")
        if tr and self.display_translations:
            disp = self.display_translations.get(str(tr))
            if disp:
                return f"{disp} — {name}"

        return name