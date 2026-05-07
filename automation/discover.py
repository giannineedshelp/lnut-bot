import logging

logger = logging.getLogger("lnut_bot.discover")


class HomeworkDiscoverer:
    """
    Discovers and resolves homework/task structure from LanguageNut.

    Mirrors the JS client_application class from lnut-client:
        - get_hwks()        → get_all_homeworks()
        - get_task_name()   → get_task_name()
        - get_hwks() processes assignmentController/getViewableAll
    """

    def __init__(self, api_client: "LNApiClient"):
        """
        Args:
            api_client: An authenticated LNApiClient instance
        """
        self.api = api_client
        self.module_translations = {}
        self.display_translations = {}
        self.homeworks = []

    async def get_all_homeworks(self) -> list[dict]:
        """
        Fetch all homeworks for the logged-in user.

        Mirrors JS: assignmentController/getViewableAll with token.

        The API returns:
            {
                "homework": [
                    {
                        "id": int,
                        "name": str,
                        "languageCode": str (ietf like "fr-FR"),
                        "tasks": [
                            {
                                "gameUid": str,
                                "translation": str,
                                "gameLink": str,
                                "type": str,
                                "catalog_uid": str,
                                "base": list,
                                "rel_module_uid": str,
                                "module_translation": str,
                                "module_translations": list[str],
                                "verb_name": str,
                                "gameResults": {...} or None,
                                ...
                            }
                        ]
                    }
                ]
            }

        Returns:
            list[dict]: List of homework objects (reversed, newest first)
        """
        data = await self.api.call_lnut("assignmentController/getViewableAll", {
            "token": self.api.token,
        })

        self.homeworks = data.get("homework", [])
        # Reverse so newest is first (matching JS: this.homeworks.reverse())
        self.homeworks.reverse()

        logger.info(f"Fetched {len(self.homeworks)} homeworks")
        return self.homeworks

    async def get_task_name(self, task: dict) -> str:
        """
        Resolve the human-readable name for a task.

        Mirrors JS get_task_name() exactly:
            1. Try task.verb_name
            2. Try task.module_translations[0] looked up in module_translations
            3. Try task.module_translation looked up in module_translations

        Args:
            task: Task dictionary from homework

        Returns:
            str: Human-readable task name
        """
        name = task.get("verb_name", "")

        if not name and task.get("module_translations"):
            key = task["module_translations"][0]
            name = self.module_translations.get(key, "")

        if not name and task.get("module_translation"):
            name = self.module_translations.get(task["module_translation"], "")

        return name or "Unknown Task"

    async def load_translations(self) -> None:
        """
        Pre-fetch display and module translations for task naming.

        Call this once after login to populate translation maps.
        """
        self.display_translations = await self.api.get_display_translations()
        self.module_translations = await self.api.get_module_translations()
        logger.debug(
            f"Loaded {len(self.display_translations)} display translations "
            f"and {len(self.module_translations)} module translations"
        )

    async def complete_task(self, homework_id: int, task_index: int) -> dict:
        """
        Complete a single task by fetching its data and submitting scores.

        Args:
            homework_id: The homework ID
            task_index:  Index of the task within the homework's task list

        Returns:
            dict: Response from score submission, or error dict
        """
        # Find the homework
        target = next((h for h in self.homeworks if h.get("id") == homework_id), None)
        if not target:
            return {"error": f"Homework {homework_id} not found"}

        tasks = target.get("tasks", [])
        if task_index < 0 or task_index >= len(tasks):
            return {"error": f"Task index {task_index} out of range"}

        task = tasks[task_index]

        # Set the language code on the API client
        self.api.language_code = target.get("languageCode", "")

        # Fetch task data
        vocabs = await self.api.fetch_task_data(task)
        if not vocabs:
            return {"error": "No vocabs fetched for this task"}

        # Submit score
        result = await self.api.submit_score(task, vocabs, homework_id)
        return result

    async def complete_all_tasks(self, homework_id: int = None) -> list[dict]:
        """
        Complete all tasks across all homeworks, or a specific homework.

        Args:
            homework_id: Optional — if set, only complete tasks in this homework

        Returns:
            list[dict]: Results from each completed task
        """
        results = []

        for hw in self.homeworks:
            if homework_id is not None and hw.get("id") != homework_id:
                continue

            for idx in range(len(hw.get("tasks", []))):
                result = await self.complete_task(hw["id"], idx)
                results.append({
                    "homework_id": hw["id"],
                    "task_index": idx,
                    "result": result,
                })

        return results