import logging
from typing import Any

logger = logging.getLogger("lnut_bot.discover")


class HomeworkDiscoverer:
    """
    Handles discovering and resolving homework/task structure from LanguageNut API.
    Mirrors the logic from lnut-client's client_application class.
    """

    # Task type detection patterns
    TASK_PATTERNS = {
        "sentence": "sentenceCatalog",
        "verb": "verbUid",
        "phonic": "phonicCatalogUid",
        "exam": "examUid",
    }

    def __init__(self, api_client):
        """
        Args:
            api_client: LNApiClient instance with an active session
        """
        self.api = api_client
        self.module_translations = {}
        self.display_translations = {}

    async def resolve_task_type(self, task: dict) -> str:
        """
        Determine the type of task by inspecting its gameLink.
        
        Mirrors the JS get_task_type() logic:
        - sentenceCatalog → "sentence"
        - verbUid → "verb"  
        - phonicCatalogUid → "phonic"
        - examUid → "exam"
        - fallback → "vocabs"
        
        Args:
            task: Task dictionary from the API
            
        Returns:
            str: One of "sentence", "verb", "phonic", "exam", "vocabs"
        """
        game_link = task.get("gameLink", "")
        
        for task_type, pattern in self.TASK_PATTERNS.items():
            if pattern in game_link:
                logger.debug(f"Task type resolved: {task_type} (pattern: {pattern})")
                return task_type
        
        logger.debug(f"No pattern matched gameLink '{game_link[:50]}', falling back to 'vocabs'")
        return "vocabs"

    async def get_all_homeworks(self, token: str) -> list[dict]:
        """
        Fetch all viewable homeworks for the logged-in user.
        
        Args:
            token: LanguageNut auth token
            
        Returns:
            list[dict]: List of homework objects
        """
        data = await self.api.call_lnut(
            "assignmentController/getViewableAll",
            {"token": token},
        )
        homeworks = data.get("homework", [])
        homeworks.reverse()  # Match JS behavior: newest first
        logger.info(f"Fetched {len(homeworks)} homeworks")
        return homeworks

    async def get_tasks_by_ids(self, token: str, homework_id: int, task_ids: list[str]) -> list[dict]:
        """
        Get specific tasks by their gameUids for a given homework.
        
        Args:
            token: LanguageNut auth token
            homework_id: Homework ID
            task_ids: List of gameUid strings
            
        Returns:
            list[dict]: Full task objects with metadata
        """
        # First get all homeworks, find the one we need
        all_homeworks = await self.get_all_homeworks(token)
        target_hw = None
        for hw in all_homeworks:
            if hw.get("id") == homework_id:
                target_hw = hw
                break
        
        if not target_hw:
            logger.warning(f"Homework {homework_id} not found")
            return []

        tasks = target_hw.get("tasks", [])
        matched = [t for t in tasks if t.get("gameUid") in task_ids]
        logger.info(f"Found {len(matched)}/{len(task_ids)} requested tasks in homework {homework_id}")
        return matched

    async def get_incomplete_tasks(self, token: str) -> list[tuple[dict, dict]]:
        """
        Get all incomplete tasks across all homeworks.
        
        Returns:
            list[tuple[dict, dict]]: List of (homework, task) tuples for incomplete tasks
        """
        homeworks = await self.get_all_homeworks(token)
        incomplete = []
        
        for hw in homeworks:
            tasks = hw.get("tasks", [])
            for task in tasks:
                game_results = task.get("gameResults")
                if not game_results or game_results.get("percentage", 0) == 0:
                    incomplete.append((hw, task))
        
        logger.info(f"Found {len(incomplete)} incomplete tasks across {len(homeworks)} homeworks")
        return incomplete

    async def get_task_name(self, task: dict, hw: dict | None = None) -> str:
        """
        Resolve the human-readable name for a task.
        
        Mirrors JS get_task_name():
        - If task has verb_name, use it
        - If module_translations exists, look up by first entry
        - If module_translation exists, look it up
        
        Args:
            task: Task dictionary
            hw: Optional homework dictionary for context
            
        Returns:
            str: Human-readable task name
        """
        name = task.get("verb_name", "Unknown Task")

        if not self.module_translations:
            try:
                await self._load_translations()
            except Exception as e:
                logger.warning(f"Could not load module translations: {e}")

        if task.get("module_translations") and self.module_translations:
            key = task["module_translations"][0]
            name = self.module_translations.get(key, name)

        if task.get("module_translation") and self.module_translations:
            key = task["module_translation"]
            name = self.module_translations.get(key, name)

        # Also try display translations
        if task.get("translation") and self.display_translations:
            display = self.display_translations.get(task["translation"])
            if display:
                return f"{display} — {name}"

        return name

    async def _load_translations(self):
        """Load both module and display translations (called lazily)."""
        data = await self.api.call_lnut(
            "translationController/getUserModuleTranslations",
            {"token": self.api.token},
        )
        self.module_translations = data.get("translations", {})

        data2 = await self.api.call_lnut(
            "publicTranslationController/getTranslations",
            {},
        )
        self.display_translations = data2.get("translations", {})
