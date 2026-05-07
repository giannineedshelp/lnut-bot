# automation/task_handler.py
"""Task completer — ported from lnut-client, with customizable speed & accuracy."""

import math
import random

import aiohttp

SPEED_MS = 10000  # default 10s, overridden by settings


class TaskCompleter:
    """Completes LanguageNut homework tasks.
    
    Matches the original JS task_completer class exactly, with added
    speed_ms and accuracy config.
    """

    def __init__(self, token, task, ietf, speed_ms=None, accuracy_min=100, accuracy_max=100):
        self.token = token
        self.task = task
        self.to_language = ietf
        self._session = None
        
        # Speed and accuracy — defaults match JS (10000ms, 100% accuracy)
        self.speed_ms = speed_ms if speed_ms is not None else SPEED_MS
        self.accuracy_min = accuracy_min
        self.accuracy_max = accuracy_max

        # Constructor: parse fields from task object
        self.homework_id = task.get("base", [None])[0]
        self.catalog_uid = task.get("catalog_uid")
        if self.catalog_uid is None:
            base = task.get("base", [])
            self.catalog_uid = base[-1] if base else None
        self.rel_module_uid = task.get("rel_module_uid")
        self.game_uid = task.get("game_uid")
        self.game_type = task.get("type")

        # Determine task mode — matches JS: this.mode = this.get_task_type()
        self.mode = self._get_task_type()

    def _get_task_type(self):
        """Matches JS get_task_type() — checks gameLink for keywords."""
        link = self.task.get("gameLink", "")
        if "sentenceCatalog" in link:
            return "sentence"
        if "verbUid" in link:
            return "verbs"
        if "phonicCatalogUid" in link:
            return "phonics"
        if "examUid" in link:
            return "exam"
        return "vocabs"

    async def call_lnut(self, endpoint, params):
        """Matches JS call_lnut() — GET with URL-encoded params, 15s timeout."""
        timeout = aiohttp.ClientTimeout(total=15)
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=timeout)
        async with self._session.get(
            f"https://api.languagenut.com/{endpoint}",
            params=params
        ) as resp:
            return await resp.json()

    async def get_data(self):
        """Fetch answers based on task type — matches JS get_data()."""
        if self.mode == "sentence":
            return await self._get_sentences()
        elif self.mode == "verbs":
            return await self._get_verbs()
        elif self.mode == "phonics":
            return await self._get_phonics()
        elif self.mode == "exam":
            return await self._get_exam()
        else:
            return await self._get_vocabs()

    async def _get_vocabs(self):
        r = await self.call_lnut("vocabTranslationController/getVocabTranslations", {
            "catalogUid[]": self.catalog_uid,
            "toLanguage": self.to_language,
            "fromLanguage": "en-US",
            "token": self.token,
        })
        return r.get("vocabTranslations", [])

    async def _get_exam(self):
        r = await self.call_lnut("examTranslationController/getExamTranslationsCorrect", {
            "gameUid": self.game_uid,
            "examUid": self.catalog_uid,
            "toLanguage": self.to_language,
            "fromLanguage": "en-US",
            "token": self.token,
        })
        return r.get("examTranslations", [])

    async def _get_sentences(self):
        r = await self.call_lnut("sentenceTranslationController/getSentenceTranslations", {
            "catalogUid": self.catalog_uid,
            "toLanguage": self.to_language,
            "fromLanguage": "en-US",
            "token": self.token,
        })
        return r.get("sentenceTranslations", [])

    async def _get_verbs(self):
        r = await self.call_lnut("verbTranslationController/getVerbTranslations", {
            "verbUid": self.catalog_uid,
            "toLanguage": self.to_language,
            "fromLanguage": "en-US",
            "token": self.token,
        })
        return r.get("verbTranslations", [])

    async def _get_phonics(self):
        r = await self.call_lnut("phonicsController/getPhonicsData", {
            "phonicCatalogUid": self.catalog_uid,
            "toLanguage": self.to_language,
            "fromLanguage": "en-US",
            "token": self.token,
        })
        return r.get("phonics", [])

    async def send_answers(self, vocabs):
        """Submit answers — matches JS send_answers() with added accuracy logic.
        
        Args:
            vocabs: List of vocab objects with 'uid' keys
            
        Returns:
            API response dict with 'score' field
        """
        if not vocabs:
            print("[TaskCompleter] No vocabs, skipping")
            return None

        # ===== TIMESTAMP: matches JS exactly =====
        # JS: Math.floor(speed + ((Math.random() - 0.5) / 10) * speed) * 1000
        speed_val = self.speed_ms / 1000  # convert ms to seconds for JS-style calc
        jitter = (random.random() - 0.5) / 10 * speed_val
        ts = math.floor(speed_val + jitter) * 1000

        # ===== ACCURACY: split vocabs into correct/incorrect =====
        # Pick a random accuracy percentage within [accuracy_min, accuracy_max]
        accuracy_pct = random.uniform(self.accuracy_min, self.accuracy_max) / 100.0
        correct_count = max(1, round(len(vocabs) * accuracy_pct))

        # Shuffle and split
        shuffled = list(vocabs)
        random.shuffle(shuffled)
        correct = shuffled[:correct_count]
        incorrect = shuffled[correct_count:]

        correct_ids = ",".join(str(v.get("uid", "")) for v in correct)
        incorrect_ids = ",".join(str(v.get("uid", "")) for v in incorrect)

        # ===== SCORE: matches JS logic =====
        # JS: score: vocabs.length * 200 (full marks always)
        # With accuracy: score based on correct count
        score = correct_count * 200

        payload = {
            "moduleUid": str(self.catalog_uid or ""),
            "gameUid": str(self.game_uid or ""),
            "gameType": str(self.game_type or ""),
            "isTest": "true",
            "toietf": self.to_language or "",
            "fromietf": "en-US",
            "score": str(score),
            "correctVocabs": correct_ids,
            "incorrectVocabs": incorrect_ids,
            "homeworkUid": str(self.homework_id or ""),
            "isSentence": str(self.mode == "sentence").lower(),
            "isALevel": "false",
            "isVerb": str(self.mode == "verbs").lower(),
            "verbUid": str(self.catalog_uid or "") if self.mode == "verbs" else "",
            "phonicUid": str(self.catalog_uid or "") if self.mode == "phonics" else "",
            "sentenceScreenUid": "100" if self.mode == "sentence" else "",
            "sentenceCatalogUid": str(self.catalog_uid or "") if self.mode == "sentence" else "",
            "grammarCatalogUid": str(self.catalog_uid or ""),
            "isGrammar": "false",
            "isExam": str(self.mode == "exam").lower(),
            "correctStudentAns": "",
            "incorrectStudentAns": "",
            "timeStamp": str(ts),
            "vocabNumber": str(len(vocabs)),
            "rel_module_uid": str(self.rel_module_uid or ""),
            "dontStoreStats": "true",
            "product": "secondary",
            "token": self.token or "",
        }

        return await self.call_lnut("gameDataController/addGameScore", payload)

    async def complete(self):
        """One-shot: fetch answers and submit. Returns result or None."""
        ans = await self.get_data()
        if ans:
            return await self.send_answers(ans)
        return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()