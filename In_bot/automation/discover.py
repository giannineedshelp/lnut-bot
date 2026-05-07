"""
Homework discovery and metadata resolution.

Mirrors the logic from lnut-client's client_application class.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("lnut_bot.discover")


class HomeworkDiscoverer:
    """Discover and resolve homework/task structure."""

    TASK_PATTERNS = {
        "sentence": "sentenceCatalog",
        "verb": "verbUid",
        "phonic": "phonicCatalogUid",
        "exam": "examUid",
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
        homeworks.reverse()  # newest first
        logger.info(f"Fetched {len(homeworks)} homeworks")
        return homeworks

    async def get_tasks_by_ids(
        self, token: str, homework_id: int, task_ids: list[str]
    ) -> list[dict]:
        homeworks = await self.get_all_homeworks(token)
        target = next((h for h in homeworks if h.get("id") == homework_id), None)
        if not target:
            logger.warning(f"Homework {homework_id} not found")
            return []
        tasks = target.get("tasks", [])
        matched = [t for t in tasks if t.get("gameUid") in task_ids]
        logger.info(
            f"Found {len(matched)}/{len(task_ids)} tasks in hw {homework_id}"
        )
        return matched

    async def get_incomplete_tasks(self, token: str) -> list[tuple[dict, dict]]:
        homeworks = await self.get_all_homeworks(token)
        incomplete: list[tuple[dict, dict]] = []
        for hw in homeworks:
            for task in hw.get("tasks", []):
                gr = task.get("gameResults") or {}
                if not gr or gr.get("percentage", 0) == 0:
                    incomplete.append((hw, task))
        logger.info(
            f"Found {len(incomplete)} incomplete tasks across "
            f"{len(homeworks)} homeworks"
        )
        return incomplete

    async def _load_translations(self) -> None:
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
        name = task.get("verb_name", "Unknown Task")

        if not self.module_translations:
            try:
                await self._load_translations()
            except Exception as e:
                logger.warning(f"Could not load module translations: {e}")

        mts = task.get("module_translations")
        if mts and self.module_translations:
            name = self.module_translations.get(mts[0], name)

        mt = task.get("module_translation")
        if mt and self.module_translations:
            name = self.module_translations.get(mt, name)

        tr = task.get("translation")
        if tr and self.display_translations:
            disp = self.display_translations.get(tr)
            if disp:
                return f"{disp} — {name}"
        return name