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
        guild_id: int = 0,
    ):
        self.session = session
        self.stealth = stealth_manager
        self.guild_id = guild_id
        self.token: str = ""
        self.account_uid: str = ""
        self.user_uid: str = ""
        self.person_name: str = ""

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
                    result = json.loads(text)
                    new_tok = result.get("newToken")
                    if new_tok and new_tok != self.token:
                        self.token = new_tok
                        if self.guild_id:
                            import config
                            config.update_token(self.guild_id, new_tok)
                    return result
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
            self.account_uid = data.get("accountUid", "")
            self.user_uid = data.get("uid", "")
            self.person_name = data.get("personName", "")
            if self.guild_id:
                import config
                config.update_token(self.guild_id, token)
            logger.info("Login successful as %s (uid=%s, account=%s)",
                        self.person_name, self.user_uid, self.account_uid)
        else:
            logger.error(f"Login failed: {data}")
        return token

    async def re_login(self) -> bool:
        """Re-authenticate using stored credentials. Returns True on success."""
        if not self.guild_id:
            return False
        import config
        acct = config.get_account(self.guild_id)
        if not acct:
            return False
        from utils.encryption import decrypt_value
        try:
            import importlib
            main_mod = importlib.import_module("main")
            bot = getattr(main_mod, "bot", None)
        except Exception:
            bot = None
        fernet = getattr(bot, "fernet", None) if bot else None
        enc_user = acct.get("username", "")
        enc_pass = acct.get("password", "")
        if not enc_user or not enc_pass:
            return False
        if fernet:
            username = decrypt_value(fernet, enc_user)
            password = decrypt_value(fernet, enc_pass)
        else:
            username = enc_user
            password = enc_pass
        tok = await self.login(username, password)
        return tok is not None

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
        data = await self.call_lnut(
            "vocabTranslationController/getVocabTranslations",
            {
                "catalogUid[]": catalog_uid,
                "toLanguage": to_language,
                "fromLanguage": from_language,
                "token": self.token,
            },
        )
        return data.get("vocabTranslations", []) or []

    # ----- Leaderboard -----
    async def get_leaderboard(self, lb_type: str = "world") -> dict:
        """
        Fetch leaderboard data. The old leaderboardController endpoints are
        defunct (server-side class removed). Replaced by highscoreController.
        """
        if lb_type == "class":
            return await self._get_class_leaderboard()
        elif lb_type == "school":
            return await self._get_school_leaderboard()
        else:
            return await self._get_world_leaderboard()

    async def get_class_leaderboard(self) -> dict:
        return await self._get_class_leaderboard()

    async def get_school_leaderboard(self) -> dict:
        return await self._get_school_leaderboard()

    async def get_world_leaderboard(self) -> dict:
        return await self._get_world_leaderboard()

    async def get_school_rankings(self) -> list[dict]:
        data = await self._get_world_leaderboard()
        return data.get('leaderboard', [])

    async def _get_school_leaderboard(self) -> dict:
        """School-wide leaderboard from highscoreController/studentsAllAccount."""
        data = await self.call_lnut(
            "highscoreController/studentsAllAccount",
            {"token": self.token, "accountUid": self.account_uid},
        )
        student_list = data.get("list") or []
        entries = []
        my_pos = None
        my_score = 0
        for i, student in enumerate(student_list, 1):
            score = int(student.get("score", 0))
            entries.append({
                "rank": i,
                "name": student.get("name", "?"),
                "score": score,
            })
            if student.get("uid") == self.user_uid:
                my_pos = i
                my_score = score
        return {
            "leaderboard": entries,
            "myPosition": my_pos or 0,
            "myScore": my_score,
        }

    async def _get_class_leaderboard(self) -> dict:
        """Find the user's class and return its student leaderboard."""
        data = await self.call_lnut(
            "highscoreController/studentsClassAll",
            {"token": self.token, "accountUid": self.account_uid},
        )
        total_list = data.get("totalList") or []
        my_class = None
        my_class_name = None
        for cls in total_list:
            for student in cls.get("list", []):
                if student.get("name", "").lower() == self.person_name.lower():
                    my_class = cls
                    my_class_name = cls.get("name", "Unknown")
                    break
            if my_class:
                break
        if not my_class:
            my_class = total_list[0] if total_list else {"name": "Unknown", "list": []}
            my_class_name = my_class.get("name", "Unknown")
        entries = []
        my_pos = None
        my_score = 0
        for i, student in enumerate(my_class.get("list", []), 1):
            score = int(student.get("score", 0))
            entries.append({
                "rank": i,
                "name": student.get("name", "?"),
                "score": score,
            })
            if student.get("name", "").lower() == self.person_name.lower():
                my_pos = i
                my_score = score
        return {
            "leaderboard": entries,
            "myPosition": my_pos or 0,
            "myScore": my_score,
            "_className": my_class_name or "Unknown",
        }

    async def _get_world_leaderboard(self) -> dict:
        """Global competition leaderboard from highscoreController."""
        data = await self.call_lnut(
            "highscoreController/getCompetitionInformationLeaderboard",
            {"token": self.token},
        )
        top_ten = data.get("topTen") or []
        your_school = data.get("yourSchool") or []
        if top_ten:
            entries = []
            for i, entry in enumerate(top_ten, 1):
                entries.append({
                    "rank": i,
                    "name": entry.get("name", "?"),
                    "score": int(entry.get("score", 0)),
                })
            return {
                "leaderboard": entries,
                "myPosition": 0,
                "myScore": 0,
                "yourSchool": your_school,
                "_isCompetition": True,
            }
        logger.info("No active competition leaderboard, falling back to school")
        return await self._get_school_leaderboard()

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

        Priority: extract UID directly from gameLink regex match,
        fall back to _get_catalog_uid(task) if regex has no capture.
        """
        catalog_uid = _get_catalog_uid(task)
        game_uid    = task.get("gameUid") or task.get("game_uid", "")

        if m := _RE_SENTENCE.search(game_link):
            uid = m.group(1) or catalog_uid
            logger.info("Fetching sentence data uid=%s", uid[:12] if uid else "?")
            return await self.get_sentences(uid, to_language, from_language)

        if m := _RE_VERB.search(game_link):
            uid = m.group(1) or catalog_uid
            logger.info("Fetching verb data uid=%s", uid[:12] if uid else "?")
            return await self.get_verbs(uid, to_language, from_language)

        if m := _RE_PHONIC.search(game_link):
            uid = m.group(1) or catalog_uid
            logger.info("Fetching phonic data uid=%s", uid[:12] if uid else "?")
            return await self.get_phonics(uid, to_language, from_language)

        if m := _RE_EXAM.search(game_link):
            uid = m.group(1) or catalog_uid
            logger.info("Fetching exam data uid=%s", uid[:12] if uid else "?")
            return await self.get_exam(game_uid, uid, to_language, from_language)

        # Default: vocabs
        if not catalog_uid:
            logger.warning("No catalog_uid in task, cannot fetch vocabs. task keys: %s", list(task.keys()))
            return []

        logger.info("Fetching vocab data uid=%s", catalog_uid[:12] if catalog_uid else "?")
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
          - score = vocabs.length * 200  (ALL vocabs, not just correct ones)
          - correctVocabs = comma-joined UIDs of correct answers
          - incorrectVocabs = [] empty (matches JS behaviour)
          - timeStamp = Math.floor(speed + jitter) * 1000
          - homeworkUid = task.base[0] (mirrors JS: this.homework_id = task.base[0])
        """
        if not task_data:
            logger.warning("No task data to submit")
            return {"error": "No data"}

        # Guard: stealth must be set
        if self.stealth is None:
            logger.error("StealthManager not set on LNApiClient")
            return {"error": "No stealth manager"}

        game_link      = task.get("gameLink", "")
        mode           = _get_task_mode(game_link)
        catalog_uid    = _get_catalog_uid(task)
        game_uid       = task.get("gameUid") or task.get("game_uid", "")
        game_type      = task.get("type", "")
        # Mirrors JS: this.homework_id = task.base[0]
        homework_uid   = _get_homework_uid(task, homework)
        to_language    = homework.get("languageCode", "")
        rel_module_uid = task.get("rel_module_uid", "")

        # Apply stealth accuracy — decide which vocabs are "correct"
        correct_indices, incorrect_indices = self.stealth.apply_accuracy(len(task_data))

        correct_vocabs   = [task_data[i].get("uid", "") for i in sorted(correct_indices) if i < len(task_data)]
        # incorrect_vocabs is intentionally empty like JS (JS sends incorrectVocabs: [])
        incorrect_vocabs: list[str] = []

        # JS: score = vocabs.length * 200  (uses TOTAL count, not just correct)
        score = len(task_data) * 200

        # Stealth timestamp: per-question cumulative sum + jitter
        timestamp_ms = self.stealth.compute_timestamp(len(task_data))

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
            # Score — JS: score = vocabs.length * 200
            "score":              str(score),
            "vocabNumber":        str(len(task_data)),
            "correctVocabs":      ",".join(correct_vocabs),
            "incorrectVocabs":    "",   # JS sends [] which URLencodes to empty
            # Homework linkage — JS: homeworkUid = task.base[0]
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
            "Submitting score: mode=%s uid=%s score=%d time=%dms correct=%d/%d",
            mode,
            (game_uid[:12] if game_uid else "?"),
            score,
            timestamp_ms,
            len(correct_vocabs),
            len(task_data),
        )

        response = await self.call_lnut(
            "gameDataController/addGameScore", payload
        )

        if response.get("error"):
            logger.error("Score submission failed: %s", response)
        else:
            logger.info("Score submitted OK: %s", response.get("score", {}))

        return response