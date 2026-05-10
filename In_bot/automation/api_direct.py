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
# These extract the UID value directly from the gameLink query string,
# mirroring JS task_completer.get_task_type() + constructor logic.
_RE_SENTENCE = re.compile(r"sentenceCatalog=([a-zA-Z0-9_-]+)")
_RE_VERB      = re.compile(r"verbUid=([a-zA-Z0-9_-]+)")
_RE_PHONIC    = re.compile(r"phonicCatalogUid=([a-zA-Z0-9_-]+)")
_RE_EXAM      = re.compile(r"examUid=([a-zA-Z0-9_-]+)")


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
    return str(uid) if uid else ""


def _get_homework_uid(task: dict, homework: dict) -> str:
    """
    Mirrors JS: homework_id = task.base[0]
    Falls back to homework dict id if base is absent.
    """
    base = task.get("base", [])
    if base:
        return str(base[0])
    # Fallback: use the homework object's id
    return str(homework.get("id", ""))


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

    # ----- Task-data fetchers (match JS params exactly) -----

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
        return data.get("sentenceTranslations", []) or []

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
        return data.get("verbTranslations", []) or []

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
        return data.get("phonics", []) or []

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
        return data.get("examTranslations", []) or []

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
      
