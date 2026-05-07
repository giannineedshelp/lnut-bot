import aiohttp
from urllib.parse import urlencode

API_BASE = "https://api.languagenut.com"


class LanguageNutAPI:
    """Complete API wrapper for LanguageNut, reverse-engineered from lnut-client."""

    def __init__(self, session: aiohttp.ClientSession = None):
        self.session = session or aiohttp.ClientSession()
        self.token = None
        self.username = None

    async def _get(self, endpoint, params=None):
        """All LanguageNut API calls are GET with query params."""
        if params is None:
            params = {}
        url = f"{API_BASE}/{endpoint}?{urlencode(params, doseq=True)}"
        async with self.session.get(url) as resp:
            return await resp.json()

    # --- AUTH ---

    async def login(self, username, password):
        """Authenticate and store token."""
        data = await self._get("loginController/attemptLogin", {
            "username": username,
            "pass": password,
        })
        self.token = data.get("newToken")
        self.username = username
        return self.token

    # --- TRANSLATIONS ---

    async def get_module_translations(self):
        """Get module name translations map."""
        data = await self._get("translationController/getUserModuleTranslations", {
            "token": self.token,
        })
        return data.get("translations", {})

    async def get_display_translations(self):
        """Get UI display translations."""
        data = await self._get("publicTranslationController/getTranslations", {})
        return data.get("translations", {})

    # --- HOMEWORK ---

    async def get_homeworks(self):
        """Get all viewable homework assignments."""
        data = await self._get("assignmentController/getViewableAll", {
            "token": self.token,
        })
        return data.get("homework", [])

    # --- ANSWER DATA FETCHERS ---

    async def get_vocab_translations(self, catalog_uid, to_language, from_language="en-US"):
        """Fetch vocabulary translations for a task."""
        data = await self._get("vocabTranslationController/getVocabTranslations", {
            "catalogUid[]": catalog_uid,
            "toLanguage": to_language,
            "fromLanguage": from_language,
            "token": self.token,
        })
        return data.get("vocabTranslations", [])

    async def get_sentence_translations(self, catalog_uid, to_language, from_language="en-US"):
        """Fetch sentence translations."""
        data = await self._get("sentenceTranslationController/getSentenceTranslations", {
            "catalogUid": catalog_uid,
            "toLanguage": to_language,
            "fromLanguage": from_language,
            "token": self.token,
        })
        return data.get("sentenceTranslations", [])

    async def get_verb_translations(self, verb_uid, to_language, from_language="en-US"):
        """Fetch verb translations."""
        data = await self._get("verbTranslationController/getVerbTranslations", {
            "verbUid": verb_uid,
            "toLanguage": to_language,
            "fromLanguage": from_language,
            "token": self.token,
        })
        return data.get("verbTranslations", [])

    async def get_phonics_data(self, phonic_catalog_uid, to_language, from_language="en-US"):
        """Fetch phonics data."""
        data = await self._get("phonicsController/getPhonicsData", {
            "phonicCatalogUid": phonic_catalog_uid,
            "toLanguage": to_language,
            "fromLanguage": from_language,
            "token": self.token,
        })
        return data.get("phonics", [])

    async def get_exam_translations(self, game_uid, exam_uid, to_language, from_language="en-US"):
        """Fetch exam translations (correct answers)."""
        data = await self._get("examTranslationController/getExamTranslationsCorrect", {
            "gameUid": game_uid,
            "examUid": exam_uid,
            "toLanguage": to_language,
            "fromLanguage": from_language,
            "token": self.token,
        })
        return data.get("examTranslations", [])

    # --- TASK TYPE DETECTION ---

    @staticmethod
    def detect_task_type(task):
        """Determine task type from gameLink string.
        
        Returns one of: 'vocabs', 'sentence', 'verbs', 'phonics', 'exam'
        """
        game_link = task.get("gameLink", "")
        if "sentenceCatalog" in game_link:
            return "sentence"
        if "verbUid" in game_link:
            return "verbs"
        if "phonicCatalogUid" in game_link:
            return "phonics"
        if "examUid" in game_link:
            return "exam"
        return "vocabs"

    # --- FETCH ANSWERS FOR ANY TASK ---

    async def fetch_answers(self, task, to_language, from_language="en-US"):
        """Fetch correct answers for a task based on its detected type.
        
        Returns list of vocab/answer objects with 'uid' field.
        """
        mode = self.detect_task_type(task)
        catalog_uid = task.get("catalog_uid", task["base"][-1])
        game_uid = task.get("game_uid")

        if mode == "sentence":
            return await self.get_sentence_translations(catalog_uid, to_language, from_language)
        elif mode == "verbs":
            return await self.get_verb_translations(catalog_uid, to_language, from_language)
        elif mode == "phonics":
            return await self.get_phonics_data(catalog_uid, to_language, from_language)
        elif mode == "exam":
            return await self.get_exam_translations(game_uid, catalog_uid, to_language, from_language)
        else:  # vocabs (default)
            return await self.get_vocab_translations(catalog_uid, to_language, from_language)

    # --- SCORE SUBMISSION ---

    async def submit_score(self, task, answers, to_language, from_language="en-US",
                           dont_store_stats=True, speed=10000):
        """Submit answers as a perfect score for a task.
        
        Args:
            task: Task object from homework
            answers: List of answer objects with 'uid' field
            to_language: IETF language code (e.g., 'fr-FR')
            from_language: Source language (default 'en-US')
            dont_store_stats: If True, prevents stats from being stored
            speed: Base time in ms for timestamp randomization
            
        Returns: API response JSON
        """
        if not answers:
            return None

        mode = self.detect_task_type(task)
        catalog_uid = task.get("catalog_uid", task["base"][0])
        if "catalog_uid" not in task:
            catalog_uid = task["base"][-1]

        import random
        timestamp = int((speed + (random.random() - 0.5) / 10 * speed) * 1000)

        data = {
            "moduleUid": catalog_uid,
            "gameUid": task.get("game_uid"),
            "gameType": task.get("type"),
            "isTest": True,
            "toietf": to_language,
            "fromietf": from_language,
            "score": len(answers) * 200,
            "correctVocabs": ",".join(a["uid"] for a in answers),
            "incorrectVocabs": "",
            "homeworkUid": task["base"][0],
            "isSentence": mode == "sentence",
            "isALevel": False,
            "isVerb": mode == "verbs",
            "verbUid": catalog_uid if mode == "verbs" else "",
            "phonicUid": catalog_uid if mode == "phonics" else "",
            "sentenceScreenUid": 100 if mode == "sentence" else "",
            "sentenceCatalogUid": catalog_uid if mode == "sentence" else "",
            "grammarCatalogUid": catalog_uid,
            "isGrammar": False,
            "isExam": mode == "exam",
            "correctStudentAns": "",
            "incorrectStudentAns": "",
            "timeStamp": timestamp,
            "vocabNumber": len(answers),
            "rel_module_uid": task.get("rel_module_uid", ""),
            "dontStoreStats": dont_store_stats,
            "product": "secondary",
            "token": self.token,
        }

        return await self._get("gameDataController/addGameScore", data)

    # --- HIGH-LEVEL: COMPLETE A SINGLE TASK ---

    async def complete_task(self, task, to_language, from_language="en-US",
                            dont_store_stats=True, speed=10000):
        """Fetch answers and submit perfect score for a single task.
        
        Returns: (answers_list, submission_response)
        """
        answers = await self.fetch_answers(task, to_language, from_language)
        if not answers:
            return [], None
        result = await self.submit_score(task, answers, to_language,
                                         from_language, dont_store_stats, speed)
        return answers, result

    async def close(self):
        await self.session.close()
