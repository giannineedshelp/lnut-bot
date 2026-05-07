# automation/task_handler.py
"""
Task handler - wraps LanguageNutAPI with progress tracking
for Discord command integration.
"""

import asyncio
import logging
import random
from typing import Any, Callable, Dict, List, Optional

from automation.api_direct import LanguageNutAPI

logger = logging.getLogger("lnut_bot.task_handler")


class TaskHandler:
    """
    High-level task handler with progress reporting.
    Manages fetching and submitting all tasks for a user.
    """

    def __init__(self, api: LanguageNutAPI):
        self.api = api
        self._progress_callback: Optional[Callable] = None

    def set_progress_callback(
        self, callback: Optional[Callable]
    ) -> None:
        """Set a callback for progress updates: callback(current, total, task_name)."""
        self._progress_callback = callback

    async def complete_single_task(
        self,
        task: Dict[str, Any],
        speed: float = 10000,
        accuracy_min: int = 100,
        accuracy_max: int = 100,
        dont_store_stats: bool = True,
        product: str = "secondary",
    ) -> Dict[str, Any]:
        """
        Complete a single homework task end-to-end.
        Returns the API response.
        """
        task_name = task.get("name", task.get("uid", "Unknown"))

        logger.info(f"Fetching data for task: {task_name}")
        answers = await self.api.fetch_task_data(task)
        logger.info(
            f"Fetched {len(answers)} items for task: {task_name}"
        )

        if not answers:
            logger.warning(f"No answers found for task: {task_name}")
            return {"score": 0, "status": "no_data"}

        result = await self.api.submit_score(
            task=task,
            answers=answers,
            speed=speed,
            accuracy_min=accuracy_min,
            accuracy_max=accuracy_max,
            dont_store_stats=dont_store_stats,
            product=product,
        )

        return result

    async def complete_all_tasks(
        self,
        speed: float = 10000,
        accuracy_min: int = 100,
        accuracy_max: int = 100,
        concurrency: int = 5,
        dont_store_stats: bool = True,
        product: str = "secondary",
    ) -> List[Dict[str, Any]]:
        """
        Complete all pending homework tasks with concurrency.
        Reports progress via callback.

        Returns list of result dicts.
        """
        if not self.api.homeworks:
            logger.warning("No homeworks loaded — fetching...")
            await self.api.get_homeworks()

        tasks = self._get_pending_tasks()
        total = len(tasks)
        results = []

        if total == 0:
            logger.info("No pending tasks to complete")
            return results

        logger.info(f"Completing {total} tasks with concurrency {concurrency}")

        # Process with semaphore-based concurrency (like JS asyncPool)
        sem = asyncio.Semaphore(concurrency)

        async def _process_one(task: Dict[str, Any], index: int) -> Dict[str, Any]:
            async with sem:
                task_name = task.get("name", task.get("uid", f"Task {index + 1}"))

                if self._progress_callback:
                    report = {
                        "index": index,
                        "total": total,
                        "task_name": task_name,
                        "status": "fetching",
                    }
                    await self._safe_callback(report)

                try:
                    result = await self.complete_single_task(
                        task=task,
                        speed=speed,
                        accuracy_min=accuracy_min,
                        accuracy_max=accuracy_max,
                        dont_store_stats=dont_store_stats,
                        product=product,
                    )

                    score = result.get("score", 0)

                    if self._progress_callback:
                        report = {
                            "index": index,
                            "total": total,
                            "task_name": task_name,
                            "status": "done",
                            "score": score,
                        }
                        await self._safe_callback(report)

                    return {
                        "task": task,
                        "result": result,
                        "score": score,
                        "success": True,
                    }

                except Exception as e:
                    logger.error(
                        f"Failed task {task_name}: {e}"
                    )

                    if self._progress_callback:
                        report = {
                            "index": index,
                            "total": total,
                            "task_name": task_name,
                            "status": "failed",
                            "error": str(e),
                        }
                        await self._safe_callback(report)

                    return {
                        "task": task,
                        "result": None,
                        "score": 0,
                        "success": False,
                        "error": str(e),
                    }

        # Create all tasks and run with semaphore
        coros = [
            _process_one(task, i) for i, task in enumerate(tasks)
        ]

        results = await asyncio.gather(*coros)

        return results

    def _get_pending_tasks(self) -> List[Dict[str, Any]]:
        """Get list of pending/uncompleted homework tasks."""
        if not self.api.homeworks:
            return []

        # The homeworks structure varies — extract all assignments
        raw = self.api.homeworks

        # Try common structures
        if isinstance(raw, list):
            return raw
        elif isinstance(raw, dict):
            # Check for nested arrays
            for key in ("homeworks", "assignments", "tasks", "results"):
                if key in raw and isinstance(raw[key], list):
                    return raw[key]
            # If it has uid/name keys at top, wrap it
            if "uid" in raw or "gameLink" in raw:
                return [raw]

        return []

    async def _safe_callback(self, data: Dict[str, Any]) -> None:
        """Call the progress callback safely."""
        if self._progress_callback:
            try:
                if asyncio.iscoroutinefunction(self._progress_callback):
                    await self._progress_callback(data)
                else:
                    self._progress_callback(data)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")