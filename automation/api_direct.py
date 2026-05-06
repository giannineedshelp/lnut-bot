from email.mime import text
import json
import logging
import math
import random
import time
from typing import Any

logger = logging.getLogger("lnut_bot.api")


class LNApiClient:
    """
    Direct API client for LanguageNut.
    
    Handles all HTTP communication with the LN API endpoints.
    Mirrors the logic from lnut-client's task_completer class.
    """

    BASE_URL = "https://api.languagenut.com"

    def __init__(self, session, stealth_manager=None):
        """
        Args:
            session: aiohttp.ClientSession
            stealth_manager: Optional StealthManager instance
        """
        self.session = session
        self.stealth = stealth_manager
        self.token = ""

    async def call_lnut(self, endpoint: str, params: dict) -> dict:
        """
        Make a request to the LanguageNut API.
        
        Mirrors the JS call_lnut() pattern:
        fetch(`https://api.languagenut.com/{endpoint}?{URLSearchParams}`)
        
        Args:
            endpoint: API endpoint path (e.g. "loginController/attemptLogin")
            params: Query parameters as dict
            
        Returns:
            dict: Parsed JSON response
        """
        url = f"{self.BASE_URL}/{endpoint}"
        logger.debug(f"API call: {endpoint} params={ {k: v[:20] if isinstance(v, str) else v for k, v in params.items()} }")
        
        async with self.session.get(url, params=params) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"API error {resp.status} on {endpoint}: {text[:200]}")
                return {"error": True, "status": resp.status, "body": text[:500]}
            
            text = await resp.text()

        try:
            return json.loads(text)
        except Exception:
            logger.error(f"Non-JSON response from {endpoint}: {text[:200]}")
            return {"error": True, "body": text}

    async def login(self, username: str, password: str) -> str | None:
        """
        Authenticate with LanguageNut.
        
        Endpoint: loginController/attemptLogin
        Params: username, pass
        
        Returns:
            str | None: Authentication token, or None on failure
        """
        data = await self.call_lnut("loginController/attemptLogin", {
            "username": username,
            "pass": password,
        })
        
        token = data.get("newToken")
        if token:
            self.token = token
            logger.info(f"Login successful, token: {token[:20]}...")
        else:
            logger.error(f"Login failed: {data}")
        
        return token

    async def get_sentences(self, game_uid: str, catalog_uid: str) -> list[dict]:
        """
        Fetch sentence data for sentence-type tasks.
        
        Endpoint: sentenceTranslationController/getSentenceTranslations
        Params: gameUid, sentenceCatalogUid
        
        Args:
            game_uid: The gameUid from the task
            catalog_uid: The sentenceCatalogUid from gameLink
            
        Returns:
            list[dict]: Sentence translation data
        """
        data = await self.call_lnut(
            "sentenceTranslationController/getSentenceTranslations",
            {
                "gameUid": game_uid,
                "sentenceCatalogUid": catalog_uid,
            },
        )
        return data.get("sentenceTranslations", [])

    async def get_verbs(self, game_uid: str, verb_uid: str) -> list[dict]:
        """
        Fetch verb conjugation data.
        
        Endpoint: verbTranslationController/getVerbTranslations
        Params: gameUid, verbUid
        
        Args:
            game_uid: The gameUid from the task
            verb_uid: The verbUid from gameLink
            
        Returns:
            list[dict]: Verb translation data
        """
        data = await self.call_lnut(
            "verbTranslationController/getVerbTranslations",
            {
                "gameUid": game_uid,
                "verbUid": verb_uid,
            },
        )
        return data.get("verbTranslations", [])

    async def get_phonics(self, game_uid: str, phonic_uid: str) -> list[dict]:
        """
        Fetch phonics data.
        
        Endpoint: phonicTranslationController/getPhonicTranslations
        Params: gameUid, phonicCatalogUid
        
        Args:
            game_uid: The gameUid from the task
            phonic_uid: The phonicCatalogUid from gameLink
            
        Returns:
            list[dict]: Phonic translation data
        """
        data = await self.call_lnut(
            "phonicTranslationController/getPhonicTranslations",
            {
                "gameUid": game_uid,
                "phonicCatalogUid": phonic_uid,
            },
        )
        return data.get("phonicTranslations", [])

    async def get_exam(self, game_uid: str, exam_uid: str) -> list[dict]:
        """
        Fetch exam data.
        
        Endpoint: examTranslationController/getExamTranslationsCorrect
        Params: gameUid, examUid (alias of catalog_uid)
        
        Args:
            game_uid: The gameUid from the task
            exam_uid: The examUid from gameLink (acts as catalog_uid)
            
        Returns:
            list[dict]: Exam translation data
        """
        data = await self.call_lnut(
            "examTranslationController/getExamTranslationsCorrect",
            {
                "gameUid": game_uid,
                "examUid": exam_uid,
            },
        )
        return data.get("examTranslations", [])

    async def get_vocabs(self, game_uid: str, catalog_uid: str) -> list[dict]:
        """
        Fetch vocabulary data.
        
        ENDPOINT: vocabTranslationController/getVocabTranslations
        PARAMS: gameUid, catalogUid[] (array notation — critical!)
        
        The JS uses URLSearchParams which handles array notation.
        We replicate this by passing catalogUid as a string value.
        
        THE [] IN THE PARAMETER NAME IS REQUIRED — the API specifically
        expects "catalogUid[]" not "catalogUid".
        
        Args:
            game_uid: The gameUid from the task
            catalog_uid: The catalog_uid from the task
            
        Returns:
            list[dict]: Vocab translation data
        """
        data = await self.call_lnut(
            "vocabTranslationController/getVocabTranslations",
            {
                "gameUid": game_uid,
                "catalogUid[]": catalog_uid,
            },
        )
        return data.get("vocabTranslations", [])

    async def fetch_task_data(self, task: dict, game_link: str) -> list[dict]:
        """
        Fetch the correct data for a task based on its type.
        
        This is the router method — it inspects the gameLink patterns
        and dispatches to the appropriate fetch method.
        
        Args:
            task: Full task dictionary from homework
            game_link: The gameLink string from the task
            
        Returns:
            list[dict]: The fetched task data (translations/vocabs/etc)
        """
        game_uid = task.get("gameUid", "")
        
        import re
        
        # Extract UIDs from gameLink patterns
        sentence_match = re.search(r"sentenceCatalog=([a-zA-Z0-9-]+)", game_link)
        verb_match = re.search(r"verbUid=([a-zA-Z0-9-]+)", game_link)
        phonic_match = re.search(r"phonicCatalogUid=([a-zA-Z0-9-]+)", game_link)
        exam_match = re.search(r"examUid=([a-zA-Z0-9-]+)", game_link)
        
        if sentence_match:
            catalog_uid = sentence_match.group(1)
            logger.info(f"Fetching sentence data: gameUid={game_uid[:12]}..., catalog={catalog_uid[:12]}...")
            return await self.get_sentences(game_uid, catalog_uid)
        
        elif verb_match:
            verb_uid = verb_match.group(1)
            logger.info(f"Fetching verb data: gameUid={game_uid[:12]}..., verbUid={verb_uid[:12]}...")
            return await self.get_verbs(game_uid, verb_uid)
        
        elif phonic_match:
            phonic_uid = phonic_match.group(1)
            logger.info(f"Fetching phonic data: gameUid={game_uid[:12]}..., phonicUid={phonic_uid[:12]}...")
            return await self.get_phonics(game_uid, phonic_uid)
        
        elif exam_match:
            exam_uid = exam_match.group(1)
            logger.info(f"Fetching exam data: gameUid={game_uid[:12]}..., examUid={exam_uid[:12]}...")
            return await self.get_exam(game_uid, exam_uid)
        
        else:
            # Fallback: use catalog_uid directly from task data
            catalog_uid = task.get("catalog_uid", "")
            if not catalog_uid:
                logger.warning(f"No catalog_uid found in task, cannot fetch vocabs")
                return []
            logger.info(f"Fetching vocab data: gameUid={game_uid[:12]}..., catalog={catalog_uid[:12]}...")
            return await self.get_vocabs(game_uid, catalog_uid)

    async def submit_score(self, task: dict, task_data: list[dict]) -> dict:
        """
        Submit a score for a task with stealth timing and accuracy.
        
        MIRRORS THE JS send_answers() EXACTLY:
        
        Payload structure:
        {
            "gameUid": task.gameUid,
            "translation": task.translation,
            "token": this.token,
            "score": correctVocabs.length * 200,
            "timeStamp": Math.floor(speed + ((Math.random() - 0.5) / 10) * speed) * 1000,
            "scorePercentage": Math.round(Math.random() * (max - min) + min),
            "results": [{"vocabUid": v.uid, "correct": true/false}, ...],
            "dontStoreStats": true,
            "product": "secondary"
        }
        
        ENDPOINT: gameDataController/addGameScore
        
        Args:
            task: Task dictionary from homework
            task_data: List of vocab/translation items to submit
            
        Returns:
            dict: API response
        """
        if not task_data:
            logger.warning("No task data to submit")
            return {"error": "No data"}

        game_uid = task.get("gameUid", "")
        
        # Apply accuracy splitting
        correct_indices, incorrect_indices = self.stealth.apply_accuracy(len(task_data))
        
        # Build results array
        results = []
        correct_count = 0
        for i, item in enumerate(task_data):
            vocab_uid = item.get("uid", "")
            is_correct = i in correct_indices
            if is_correct:
                correct_count += 1
            results.append({
                "vocabUid": vocab_uid,
                "correct": is_correct,
            })

        # Calculate score: 200 points per correct answer (matches JS)
        score = correct_count * 200
        
        # Calculate fake timestamp with jitter (matches JS formula exactly)
        timestamp_ms = self.stealth.compute_timestamp()
        
        # Pick accuracy within range (matches JS)
        score_pct = round(random.uniform(self.stealth.min_accuracy, self.stealth.max_accuracy))
        
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
            f"Submitting score for task {game_uid[:12]}...: "
            f"score={score}, pct={score_pct}%, time={timestamp_ms}ms, "
            f"correct={correct_count}/{len(task_data)}"
        )

        response = await self.call_lnut("gameDataController/addGameScore", payload)
        
        if response.get("error"):
            logger.error(f"Score submission failed: {response}")
        else:
            score_data = response.get("score", {})
            logger.info(f"Score submitted successfully: {score_data}")
        
        return response
