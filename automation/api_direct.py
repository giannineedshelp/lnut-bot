# automation/api_direct.py
"""
Direct API client for LanguageNut.
Matches the JS lnut-client's task_completer class exactly.

Endpoints and payload structures reverse-engineered from:
  https://github.com/smellyelephant/lnut-client
"""

import asyncio
import json
import logging
import math
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger("lnut_bot.automation")

BASE_URL = "https://www.languagenut.com"


class LanguageNutAPI:
    """Direct API client matching lnut-client's task_completer."""

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.token: Optional[str] = None
        self.username: Optional[str] = None
        self.user_info: Optional[Dict[str, Any]] = None
        self.homeworks: Optional[List[Dict[str, Any]]] = None
        self.display_translations: Optional[List[Dict[str, Any]]] = None
        self.module_translations: Optional[List[Dict[str, Any]]] = None

    # =========================
    # AUTH
    # =========================

    async def login(self, username: str, password: str) -> bool:
        """Authenticate and store session token."""
        self.username = username

        payload = {
            "username": username,
            "password": password,
            "rememberMe": True,
        }

        try:
            result = await self._call_lnut(
                "loginController/performLogin",
                payload,
            )

            if "token" in result:
                self.token = result["token"]
                self.user_info = result
                logger.info(f"Login successful for {username}")
                return True

            logger.warning(f"Login failed for {username}: no token in response")
            return False

        except Exception as e:
            logger.error(f"Login error for {username}: {e}")
            return False

    # =========================
    # DATA FETCHING
    # =========================

    async def get_display_translations(self) -> List[Dict[str, Any]]:
        """Fetch display/UI translations."""
        result = await self._call_lnut(
            "publicTranslationController/getTranslations",
            {},
        )
        self.display_translations = result.get("translations", [])
        return self.display_translations

    async def get_module_translations(self) -> List[Dict[str, Any]]:
        """Fetch user's module translations."""
        result = await self._call_lnut(
            "translationController/getUserModuleTranslations",
            {"token": self.token},
        )
        self.module_translations = result.get("translations", [])
        return self.module_translations

    async def get_homeworks(self) -> Dict[str, Any]:
        """Fetch all viewable homework assignments."""
        result = await self._call_lnut(
            "assignmentController/getViewableAll",
            {"token": self.token},
        )
        self.homeworks = result
        return result

    async def fetch_task_data(
        self,
        task: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Fetch vocab/verb/phonic/sentence/exam data for a single task.
        Returns list of answer items, each with a 'uid' and metadata.

        Matches JS: task_completer.get_data(id)
        """
        task_type = self._get_task_type(task)
        game_link = task.get("gameLink", "")

        if task_type == "sentence":
            return await self._get_sentences(game_link)
        elif task_type == "verbs":
            return await self._get_verbs(game_link)
        elif task_type == "phonics":
            return await self._get_phonics(game_link)
        elif task_type == "exam":
            return await self._get_exam(game_link)
        else:
            return await self._get_vocabs(game_link)

    # =========================
    # TASK TYPE DETECTION
    # =========================

    @staticmethod
    def _get_task_type(task: Dict[str, Any]) -> str:
        """
        Determine task type from gameLink.
        Matches JS: task_completer.get_task_type()
        """
        game_link = task.get("gameLink", "")

        if "sentenceCatalog" in game_link:
            return "sentence"
        elif "verbUid" in game_link:
            return "verbs"
        elif "phonicCatalogUid" in game_link:
            return "phonics"
        elif "examUid" in game_link:
            return "exam"
        else:
            return "vocabs"

    # =========================
    # TYPE-SPECIFIC FETCHERS
    # =========================

    async def _get_sentences(self, game_link: str) -> List[Dict[str, Any]]:
        """Fetch sentence-based task data."""
        # Parse sentenceCatalog from gameLink
        catalog_uid = self._extract_param(game_link, "sentenceCatalog")
        result = await self._call_lnut(
            "sentenceTranslationController/getSentenceTranslations",
            {"catalogUid": catalog_uid, "token": self.token},
        )
        return result.get("sentences", [])

    async def _get_verbs(self, game_link: str) -> List[Dict[str, Any]]:
        """Fetch verb conjugation task data."""
        verb_uid = self._extract_param(game_link, "verbUid")
        result = await self._call_lnut(
            "verbTranslationController/getVerbTranslations",
            {"verbUid": verb_uid, "token": self.token},
        )
        verbs = result.get("verbs", [])
        # Flatten: each verb has tenses array
        items = []
        for verb in verbs:
            for tense in verb.get("tenses", []):
                items.append(tense)
        return items

    async def _get_phonics(self, game_link: str) -> List[Dict[str, Any]]:
        """Fetch phonics task data."""
        catalog_uid = self._extract_param(game_link, "phonicCatalogUid")
        result = await self._call_lnut(
            "phonicsController/getPhonicsData",
            {"catalogUid": catalog_uid, "token": self.token},
        )
        return result.get("phonics", [])

    async def _get_exam(self, game_link: str) -> List[Dict[str, Any]]:
        """Fetch exam task data."""
        exam_uid = self._extract_param(game_link, "examUid")
        result = await self._call_lnut(
            "examTranslationController/getExamTranslationsCorrect",
            {"examUid": exam_uid, "token": self.token},
        )
        return result.get("questions", [])

    async def _get_vocabs(self, game_link: str) -> List[Dict[str, Any]]:
        """Fetch vocabulary task data (default type)."""
        # Parse catalogUid[] params
        catalog_uids = self._extract_array_param(game_link, "catalogUid")
        if not catalog_uids:
            catalog_uids = [self._extract_param(game_link, "catalogUid")]

        # Build params with bracket notation like JS does
        params: Dict[str, Any] = {"token": self.token}
        for i, uid in enumerate(catalog_uids):
            if uid:
                params[f"catalogUid[{i}]"] = uid

        result = await self._call_lnut(
            "vocabTranslationController/getVocabTranslations",
            params,
        )
        return result.get("vocabs", [])

    # =========================
    # ANSWER SUBMISSION
    # =========================

    async def submit_score(
        self,
        task: Dict[str, Any],
        answers: List[Dict[str, Any]],
        speed: float = 10000,
        accuracy_min: int = 100,
        accuracy_max: int = 100,
        dont_store_stats: bool = True,
        product: str = "secondary",
    ) -> Dict[str, Any]:
        """
        Submit answers for a task.
        Matches JS: task_completer.send_answers()

        Args:
            task: The homework task dict
            answers: List of answer items (each with a 'uid')
            speed: Base time in ms (default 10000 = 10s)
            accuracy_min: Minimum accuracy % (0-100)
            accuracy_max: Maximum accuracy % (0-100)
            dont_store_stats: Whether to prevent stat storage
            product: Product type ("secondary" or "primary")

        Returns:
            API response dict with 'score' field
        """
        # Determine which UIDs to mark correct vs incorrect
        correct, incorrect = self._select_accuracy(
            answers, accuracy_min, accuracy_max
        )

        correct_vocabs = ",".join(correct)
        incorrect_vocabs = ",".join(incorrect)

        # Calculate score: all correct items × 200 (matching JS)
        score = len(correct) * 200

        # Calculate timestamp matching JS formula:
        # Math.floor(speed + ((Math.random() - 0.5)/10) * speed) * 1000
        jitter = (random.random() - 0.5) / 10 * speed
        timestamp = math.floor(speed + jitter) * 1000

        task_type = self._get_task_type(task)
        game_link = task.get("gameLink", "")

        payload = {
            "correctVocabs": correct_vocabs,
            "incorrectVocabs": incorrect_vocabs,
            "score": score,
            "timeStamp": timestamp,
            "isTest": True,
            "homeworkUid": task.get("uid", ""),
            "moduleUid": task.get("moduleUid", ""),
            "dontStoreStats": dont_store_stats,
            "product": product,
        }

        # Type-specific booleans
        payload["isSentence"] = task_type == "sentence"
        payload["isVerb"] = task_type == "verbs"
        payload["isPhonics"] = task_type == "phonics"
        payload["isExam"] = task_type == "exam"
        payload["isGrammar"] = "grammarUid" in game_link

        # Add type-specific UIDs
        if task_type == "sentence":
            payload["sentenceCatalogUid"] = self._extract_param(
                game_link, "sentenceCatalog"
            )
        elif task_type == "verbs":
            payload["verbUid"] = self._extract_param(game_link, "verbUid")
        elif task_type == "phonics":
            payload["phonicCatalogUid"] = self._extract_param(
                game_link, "phonicCatalogUid"
            )
        elif task_type == "exam":
            payload["examUid"] = self._extract_param(game_link, "examUid")
        else:
            # Vocabulary: add catalogUid[]
            catalog_uids = self._extract_array_param(
                game_link, "catalogUid"
            )
            if not catalog_uids:
                catalog_uids = [
                    self._extract_param(game_link, "catalogUid")
                ]
            for i, uid in enumerate(catalog_uids):
                if uid:
                    payload[f"catalogUid[{i}]"] = uid

        # Send to the completion endpoint
        result = await self._call_lnut(
            "assignmentController/completeHomework",
            payload,
        )

        return result

    # =========================
    # ACCURACY SELECTION
    # =========================

    @staticmethod
    def _select_accuracy(
        answers: List[Dict[str, Any]],
        accuracy_min: int,
        accuracy_max: int,
    ) -> Tuple[List[str], List[str]]:
        """
        Randomly select which items are correct vs incorrect
        based on the target accuracy range.

        Returns (correct_uids, incorrect_uids)
        """
        if not answers:
            return [], []

        uids = [a.get("uid", "") for a in answers if a.get("uid")]
        if not uids:
            return [], []

        # Pick a random accuracy within range
        accuracy = random.randint(accuracy_min, accuracy_max)
        accuracy = max(0, min(100, accuracy))

        num_correct = max(1, round(len(uids) * accuracy / 100))
        num_correct = min(num_correct, len(uids))

        # Shuffle and split
        random.shuffle(uids)
        correct = uids[:num_correct]
        incorrect = uids[num_correct:]

        return correct, incorrect

    # =========================
    # UTILITY
    # =========================

    @staticmethod
    def _extract_param(url: str, param: str) -> Optional[str]:
        """Extract a single query parameter from a URL."""
        if "?" in url:
            query = url.split("?", 1)[1]
            for part in query.split("&"):
                if part.startswith(f"{param}="):
                    return part.split("=", 1)[1]
        return None

    @staticmethod
    def _extract_array_param(url: str, param: str) -> List[str]:
        """Extract array-style query params (e.g., catalogUid[0]=...)."""
        values = []
        if "?" in url:
            query = url.split("?", 1)[1]
            for part in query.split("&"):
                if part.startswith(f"{param}[") and "=" in part:
                    values.append(part.split("=", 1)[1])
        return values

    async def _call_lnut(
        self,
        endpoint: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Make an API call to LanguageNut.
        Matches JS: task_completer.call_lnut()
        """
        url = f"{BASE_URL}/{endpoint}"

        # JS client sends as form-urlencoded
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13; SM-S908B) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Mobile Safari/537.36"
            ),
            "Origin": "https://www.languagenut.com",
            "Referer": "https://www.languagenut.com/",
        }

        # Add token to headers if we have one (JS sends it in payload too)
        if self.token and "token" not in payload:
            payload["token"] = self.token

        for attempt in range(3):
            try:
                async with self.session.post(
                    url,
                    data=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    text = await resp.text()
                    if not text:
                        logger.warning(
                            f"Empty response from {endpoint} "
                            f"(attempt {attempt + 1})"
                        )
                        await asyncio.sleep(1)
                        continue

                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        logger.error(
                            f"Invalid JSON from {endpoint}: {text[:200]}"
                        )
                        await asyncio.sleep(1)
                        continue

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning(
                    f"Request failed for {endpoint} "
                    f"(attempt {attempt + 1}): {e}"
                )
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)

        raise RuntimeError(f"Failed to call {endpoint} after 3 attempts")