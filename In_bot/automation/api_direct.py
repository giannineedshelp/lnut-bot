"""
Direct API client for LanguageNut.

Handles all HTTP communication with the LN API endpoints.
Mirrors the logic from lnut-client's task_completer class (JS reference).
"""

from __future__ import annotations

import json
import logging
import math
import random
import re
from typing import Any, Optional

import aiohttp

logger = logging.getLogger("lnut_bot.api")

SENSITIVE_PARAM_PARTS = ("pass", "password", "token", "authorization")

# Pre-compiled regexes for task_link parsing
_RE_SENTENCE = re.compile(r"sentenceCatalog=([a-zA-Z0-9-]+)")
_RE_VERB      = re.compile(r"verbUid=([a-zA-Z0-9-]+)")
_RE_PHONIC    = re.compile(r"phonicCatalogUid=([a-zA-Z0-9-]+)")
_RE_EXAM      = re.compile(r"examUid=([a-zA-Z0-9-]+)")


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


def _get_catalog_uid(task: dict) -> str:
    """
    Mirrors JS task_completer constructor logic:
      catalog_uid = task.catalog_uid
      if undefined: catalog_uid = task.base[task.base.length - 1]
    Falls back to game_uid if nothing else is available.
    """
    uid = task.get("catalog_uid") or task.get("catalogUid", "")
    if not uid:
        base = task.get("base", [])
        if base:
            uid = base[-1]
    if not uid:
        uid = task.get("game_uid") or task.get("gameUid", "")
    return uid


def _get_task_mode(game_link: str) -> str:
    """Mirrors JS get_task_type()."""
    if "sentenceCatalog" in game_link:
        return "sentence"
    if "verbUid" in game_link:
        return "verbs"
    if "phonicCatalogUid" in game_link:
        return "phonics"
    if "examUid" in game_link:
        return "exam"
    return "vocabs"


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

    # ----- Task-data fetchers (now match JS params exactly) -----

    async def get_sentences(
        self,
        catalog_uid: str,
        to_language: str,
        from_language: str = "en-US",
    ) -> list[dict]:
        """
        JS: sentenceTranslationController/getSentenceTranslations
            { catalogUid, toLanguage, fromLanguage, token }
        """
        data = await self.call_lnut(
            "sentenceTranslationController/getSentenceTranslations",
            {
                "catalogUid": catalog_uid,
                "toLanguage": to_language,
                "fromLanguage": from_language,
                "token": self.token,
            },
        )
        return data.get("sentenceTranslations", [])

    async def get_verbs(
        self,
        verb_uid: str,
        to_language: str,
        from_language: str = "en-US",
    ) -> list[dict]:
        """
        JS: verbTranslationController/getVerbTranslations
            { verbUid, toLanguage, fromLanguage, token }
        """
        data = await self.call_lnut(
            "verbTranslationController/getVerbTranslations",
            {
                "verbUid": verb_uid,
                "toLanguage": to_language,
                "fromLanguage": from_language,
                "token": self.token,
            },
        )
        return data.get("verbTranslations", [])

    async def get_phonics(
        self,
        phonic_catalog_uid: str,
        to_language: str,
        from_language: str = "en-US",
    ) -> list[dict]:
        """
        JS: phonicsController/getPhonicsData
            { phonicCatalogUid, toLanguage, fromLanguage, token }
        """
        data = await self.call_lnut(
            "phonicsController/getPhonicsData",
            {
                "phonicCatalogUid": phonic_catalog_uid,
                "toLanguage": to_language,
                "fromLanguage": from_language,
                "token": self.token,
            },
        )
        return data.get("phonics", [])

    async def get_exam(
        self,
        game_uid: str,
        exam_uid: str,
        to_language: str,
        from_language: str = "en-US",
    ) -> list[dict]:
        """
        JS: examTranslationController/getExamTranslationsCorrect
            { gameUid, examUid, toLanguage, fromLanguage, token }
        """
        data = await self.call_lnut(
            "examTranslationController/getExamTranslationsCorrect",
            {
                "gameUid": game_uid,
                "examUid": exam_uid,
                "toLanguage": to_language,
                "fromLanguage": from_language,
                "token": self.token,
            },
        )
        return data.get("examTranslations", [])

    async def get_vocabs(
        self,
        catalog_uid: str,
        to_language: str,
        from_language: str = "en-US",
    ) -> list[dict]:
        """
        JS: vocabTranslationController/getVocabTranslations
            { "catalogUid[]": catalog_uid, toLanguage, fromLanguage, token }
        Note: the [] in the key name is REQUIRED by the LN backend.
        """
        data = await self.call_lnut(
            "vocabTranslationController/getVocabTranslations",
            {
                "catalogUid[]": catalog_uid,
                "toLanguage": to_language,
                "fromLanguage": from_language,
                "token": self.token,
            },
        )
        return data.get("vocabTranslations", [])

    async def fetch_task_data(
        self,
        task: dict,
        game_link: str,
        to_language: str,
        from_language: str = "en-US",
    ) -> list[dict]:
        """
        Route task to the correct fetcher based on gameLink pattern.
        Mirrors JS task_completer.get_data() + get_task_type().
        Now correctly passes token + language codes to every fetcher.
        """
        catalog_uid = _get_catalog_uid(task)
        game_uid    = task.get("gameUid") or task.get("game_uid", "")

        if m := _RE_SENTENCE.search(game_link):
            uid = m.group(1) or catalog_uid
            logger.info(f"Fetching sentence data uid={uid[:12]}")
            return await self.get_sentences(uid, to_language, from_language)

        if m := _RE_VERB.search(game_link):
            uid = m.group(1) or catalog_uid
            logger.info(f"Fetching verb data uid={uid[:12]}")
            return await self.get_verbs(uid, to_language, from_language)

        if m := _RE_PHONIC.search(game_link):
            uid = m.group(1) or catalog_uid
            logger.info(f"Fetching phonic data uid={uid[:12]}")
            return await self.get_phonics(uid, to_language, from_language)

        if m := _RE_EXAM.search(game_link):
            uid = m.group(1) or catalog_uid
            logger.info(f"Fetching exam data uid={uid[:12]}")
            return await self.get_exam(game_uid, uid, to_language, from_language)

        if not catalog_uid:
            logger.warning("No catalog_uid in task, cannot fetch vocabs")
            return []

        logger.info(f"Fetching vocab data uid={catalog_uid[:12]}")
        return await self.get_vocabs(catalog_uid, to_language, from_language)

    async def submit_score(
        self,
        task: dict,
        task_data: list[dict],
        homework: dict,
    ) -> dict:
        """
        Submit a completed task score.

        Payload mirrors JS send_answers() exactly:
          moduleUid, gameUid, gameType, isTest, toietf, fromietf,
          score, correctVocabs, incorrectVocabs, homeworkUid,
          isSentence, isALevel, isVerb, verbUid, phonicUid,
          sentenceScreenUid, sentenceCatalogUid, grammarCatalogUid,
          isGrammar, isExam, correctStudentAns, incorrectStudentAns,
          timeStamp, vocabNumber, rel_module_uid, dontStoreStats,
          product, token
        """
        if not task_data:
            logger.warning("No task data to submit")
            return {"error": "No data"}

        game_link   = task.get("gameLink", "")
        mode        = _get_task_mode(game_link)
        catalog_uid = _get_catalog_uid(task)
        game_uid    = task.get("gameUid") or task.get("game_uid", "")
        game_type   = task.get("type", "")
        homework_uid = str(homework.get("id", ""))
        to_language  = homework.get("languageCode", "")
        rel_module_uid = task.get("rel_module_uid", "")

        # Apply stealth accuracy — decide which vocabs are "correct"
        correct_indices, incorrect_indices = self.stealth.apply_accuracy(len(task_data))
        correct_set   = set(correct_indices)
        incorrect_set = set(incorrect_indices)

        correct_vocabs   = [task_data[i].get("uid", "") for i in sorted(correct_set)]
        incorrect_vocabs = [task_data[i].get("uid", "") for i in sorted(incorrect_set)]

        score = len(correct_vocabs) * 200

        # Stealth timestamp (JS: Math.floor(speed + jitter) * 1000)
        timestamp_ms = self.stealth.compute_timestamp()

        payload = {
            # Core identifiers
            "moduleUid":          catalog_uid,
            "gameUid":            game_uid,
            "gameType":           game_type,
            "token":              self.token,
            # Flags (match JS booleans as strings for URLencoded form)
            "isTest":             "true",
            "isALevel":           "false",
            "isGrammar":          "false",
            "isSentence":         "true" if mode == "sentence" else "false",
            "isVerb":             "true" if mode == "verbs"    else "false",
            "isExam":             "true" if mode == "exam"     else "false",
            # Language
            "toietf":             to_language,
            "fromietf":           "en-US",
            # Score
            "score":              str(score),
            "vocabNumber":        str(len(task_data)),
            "correctVocabs":      ",".join(correct_vocabs),
            "incorrectVocabs":    ",".join(incorrect_vocabs),
            # Homework linkage
            "homeworkUid":        homework_uid,
            "rel_module_uid":     rel_module_uid,
            # Mode-specific UIDs (blank when not applicable, mirrors JS ternary)
            "verbUid":            catalog_uid if mode == "verbs"    else "",
            "phonicUid":          catalog_uid if mode == "phonics"  else "",
            "sentenceScreenUid":  "100"       if mode == "sentence" else "",
            "sentenceCatalogUid": catalog_uid if mode == "sentence" else "",
            "grammarCatalogUid":  catalog_uid,
            # Answers (open-ended games — blank for vocab games)
            "correctStudentAns":  "",
            "incorrectStudentAns": "",
            # Timing
            "timeStamp":          str(timestamp_ms),
            # Misc
            "dontStoreStats":     "true",
            "product":            "secondary",
        }

        logger.info(
            f"Submitting score: mode={mode} uid={game_uid[:12]} "
            f"score={score} time={timestamp_ms}ms "
            f"correct={len(correct_vocabs)}/{len(task_data)}"
        )

        response = await self.call_lnut(
            "gameDataController/addGameScore", payload
        )

        if response.get("error"):
            logger.error(f"Score submission failed: {response}")
        else:
            logger.info(f"Score submitted OK: {response.get('score', {})}")

        return response