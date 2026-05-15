"""Homework discovery and metadata resolution."""

from __future__ import annotations
import logging
from utils.helper import _pct, _is_done

logger = logging.getLogger("lnut_bot.discover")

class HomeworkDiscoverer:
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
        game_link = task.get("gameLink", "")
        for task_type, pattern in self.TASK_PATTERNS.items():
            if pattern in game_link:
                return task_type
        return "vocabs"

    def get_all_homeworks(self, token: str) -> list[dict]:
        data = self.api.call_lnut("assignmentController/getViewableAll", {"token": token})
        homeworks = data.get("homework", []) or []
        homeworks.reverse()
        logger.info("Fetched %d homeworks", len(homeworks))
        return homeworks

    def get_tasks_by_ids(self, token: str, homework_id: int, task_ids: list[str]) -> list[dict]:
        homeworks = self.get_all_homeworks(token)
        target = next((h for h in homeworks if h.get("id") == homework_id), None)
        if not target:
            logger.warning("Homework %s not found", homework_id)
            return []
        tasks = target.get("tasks", [])
        matched = [t for t in tasks if t.get("gameUid") in task_ids]
        logger.info("Found %d/%d tasks in hw %s", len(matched), len(task_ids), homework_id)
        return matched

    def get_incomplete_tasks(self, token: str) -> list[tuple[dict, dict]]:
        homeworks = self.get_all_homeworks(token)
        incomplete: list[tuple[dict, dict]] = []
        for hw in homeworks:
            for task in hw.get("tasks", []):
                if not _is_done(task):
                    incomplete.append((hw, task))
        logger.info("Found %d incomplete tasks across %d homeworks", len(incomplete), len(homeworks))
        return incomplete

    def _load_translations(self) -> None:
        data = self.api.call_lnut("translationController/getUserModuleTranslations", {"token": self.api.token})
        self.module_translations = data.get("translations", {}) or {}
        data2 = self.api.call_lnut("publicTranslationController/getTranslations", {})
        self.display_translations = data2.get("translations", {}) or {}

    def get_task_name(self, task: dict) -> str:
        name = task.get("verb_name", "Unknown Task")
        if not self.module_translations:
            try:
                self._load_translations()
            except Exception as e:
                logger.warning("Could not load module translations: %s", e)
        mts = task.get("module_translations")
        if mts and self.module_translations:
            resolved = self.module_translations.get(str(mts[0]))
            if resolved:
                name = resolved
        mt = task.get("module_translation")
        if mt and self.module_translations:
            resolved = self.module_translations.get(str(mt))
            if resolved:
                name = resolved
        tr = task.get("translation")
        if tr and self.display_translations:
            disp = self.display_translations.get(str(tr))
            if disp:
                return f"{disp} \u2014 {name}"
        return name
