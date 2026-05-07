"""
Direct API client for LanguageNut.

Handles all HTTP communication with the LN API endpoints.
Mirrors the logic from lnut-client's task_completer class.
"""

from __future__ import annotations

import json
import logging
import random
import re
from typing import Any, Optional

import aiohttp

logger = logging.getLogger("lnut_bot.api")

SENSITIVE_PARAM_PARTS = ("pass", "password", "token", "authorization")

# Pre-compiled regexes for task_link parsing (perf)
_RE_SENTENCE = re.compile(r"sentenceCatalog=([a-zA-Z0-9-]+)")
_RE_VERB = re.compile(r"verbUid=([a-zA-Z0-9-]+)")
_RE_PHONIC = re.compile(r"phonicCatalogUid=([a-zA-Z0-9-]+)")
_RE_EXAM = re.compile(r"examUid=([a-zA-Z0-9-]+)")


def _safe_params(params: dict) -> dict:
    safe = {}
    for key, value in params.items():
        if any(part in key.lower() for part in SENSITIVE_PARAM_PARTS):
            safe[key] = "***"
        elif isinstance(value, str):
            safe[key] = value[:20]
        else:
            safe[key] = value
    return safe


class LNApiClient:
    """Direct HTTP client for LanguageNut API endpoints."""

    BASE_URL = "https://api.languagenut.com"

    def __init__(
        self,
        session: aiohttp.ClientSession,
        stealth_manager: Optional[Any] = None,
    ):
        self.session = session
        self.stealth = stealth_manager
        self.token: str = ""

    async def call_lnut(self, endpoint: str, params: dict) -> dict:
        """Make a GET request to a LanguageNut API endpoint."""
        url = f"{self.BASE_URL}/{endpoint}"
        logger.debug("API call: %s params=%s", endpoint, _safe_params(params))

        try:
            async with self.session.get(url, params=params) as resp:
                text = await resp.text()
                if resp.status != 200:
                    logger.error(
                        "API error %s on %s: %s",
                        resp.status,
                        endpoint,
                        text[:200],
                    )
                    return {
                        "error": True,
                        "status": resp.status,
                        "body": text[:500],
                    }
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    logger.error(
                        "Invalid JSON from %s: %s", endpoint, text[:200]
                    )
                    return {
                        "error": True,
                        "status": resp.status,
                        "body": text[:500],
                    }
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.error("API request failed for %s: %s", endpoint, exc)
            return {
                "error": True,
                "status": "request_failed",
                "body": str(exc),
            }

    async def login(self, username: str, password: str) -> Optional[str]:
        data = await self.call_lnut(
            "loginController/attemptLogin",
            {"username": username, "pass": password},
        )
        token = data.get("newToken")
        if token:
            self.token = token
            logger.info("Login successful")
        else:
            logger.error(f"Login failed: {data}")
        return token

    # ----- Task-data fetchers -----
    async def get_sentences(self, game_uid: str, catalog_uid: str) -> list[dict]:
        data = await self.call_lnut(
            "sentenceTranslationController/getSentenceTranslations",
            {"gameUid": game_uid, "sentenceCatalogUid": catalog_uid},
        )
        return data.get("sentenceTranslations", [])

    async def get_verbs(self, game_uid: str, verb_uid: str) -> list[dict]:
        data = await self.call_lnut(
            "verbTranslationController/getVerbTranslations",
            {"gameUid": game_uid, "verbUid": verb_uid},
        )
        return data.get("verbTranslations", [])

    async def get_phonics(self, game_uid: str, phonic_uid: str) -> list[dict]:
        data = await self.call_lnut(
            "phonicTranslationController/getPhonicTranslations",
            {"gameUid": game_uid, "phonicCatalogUid": phonic_uid},
        )
        return data.get("phonicTranslations", [])

    async def get_exam(self, game_uid: str, exam_uid: str) -> list[dict]:
        data = await self.call_lnut(
            "examTranslationController/getExamTranslationsCorrect",
            {"gameUid": game_uid, "examUid": exam_uid},
        )
        return data.get("examTranslations", [])

    async def get_vocabs(self, game_uid: str, catalog_uid: str) -> list[dict]:
        # The [] in the name is REQUIRED by the LN backend.
        data = await self.call_lnut(
            "vocabTranslationController/getVocabTranslations",
            {"gameUid": game_uid, "catalogUid[]": catalog_uid},
        )
        return data.get("vocabTranslations", [])

    async def fetch_task_data(self, task: dict, game_link: str) -> list[dict]:
        """Route task to the correct fetcher based on gameLink pattern."""
        game_uid = task.get("gameUid", "")

        if m := _RE_SENTENCE.search(game_link):
            logger.info(f"Fetching sentence data for {game_uid[:12]}")
            return await self.get_sentences(game_uid, m.group(1))
        if m := _RE_VERB.search(game_link):
            logger.info(f"Fetching verb data for {game_uid[:12]}")
            return await self.get_verbs(game_uid, m.group(1))
        if m := _RE_PHONIC.search(game_link):
            logger.info(f"Fetching phonic data for {game_uid[:12]}")
            return await self.get_phonics(game_uid, m.group(1))
        if m := _RE_EXAM.search(game_link):
            logger.info(f"Fetching exam data for {game_uid[:12]}")
            return await self.get_exam(game_uid, m.group(1))

        catalog_uid = task.get("catalog_uid", "")
        if not catalog_uid:
            logger.warning("No catalog_uid in task, cannot fetch vocabs")
            return []
        logger.info(f"Fetching vocab data for {game_uid[:12]}")
        return await self.get_vocabs(game_uid, catalog_uid)

    async def submit_score(self, task: dict, task_data: list[dict]) -> dict:
        """Submit a score with stealth timing + accuracy."""
        if not task_data:
            logger.warning("No task data to submit")
            return {"error": "No data"}

        game_uid = task.get("gameUid", "")
        correct_indices, _ = self.stealth.apply_accuracy(len(task_data))
        correct_set = set(correct_indices)

        results = []
        correct_count = 0
        for i, item in enumerate(task_data):
            is_correct = i in correct_set
            if is_correct:
                correct_count += 1
            results.append(
                {"vocabUid": item.get("uid", ""), "correct": is_correct}
            )

        score = correct_count * 200
        timestamp_ms = self.stealth.compute_timestamp()
        score_pct = round(
            random.uniform(self.stealth.min_accuracy, self.stealth.max_accuracy)
        )

        payload = {
            "gameUid": game_uid,
            "translation": task.get("translation", ""),
            "token": self.token,
            "score": str(score),
            "timeStamp": str(timestamp_ms),
            "scorePercentage": str(score_pct),
            "results": json.dumps(results),
            "dontStoreStats": "true",
            "product": "secondary",
        }

        logger.info(
            f"Submitting score for {game_uid[:12]}: "
            f"score={score}, pct={score_pct}%, "
            f"time={timestamp_ms}ms, "
            f"correct={correct_count}/{len(task_data)}"
        )

        response = await self.call_lnut(
            "gameDataController/addGameScore", payload
        )

        if response.get("error"):
            logger.error(f"Score submission failed: {response}")
        else:
            logger.info(
                f"Score submitted: {response.get('score', {})}"
            )
        return response