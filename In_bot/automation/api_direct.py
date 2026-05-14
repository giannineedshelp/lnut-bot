"""
api_direct.py — Direct HTTP client for LanguageNut API with TLS fingerprint spoofing.

Uses curl_cffi to mimic browser TLS/JA3 fingerprints and evade Cloudflare Bot Management.
Falls back to standard requests if curl_cffi is not available.
"""

import logging
import random
import time
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urljoin

logger = logging.getLogger("lnut_bot.api_direct")

# Try to use curl_cffi for TLS fingerprint impersonation
try:
    import curl_cffi.requests as curl_requests
    HAS_CURL_CFFI = True
    logger.info("Using curl_cffi for TLS fingerprint impersonation")
except ImportError:
    import requests as curl_requests
    HAS_CURL_CFFI = False
    logger.warning("curl_cffi not available, using standard requests (weak TLS fingerprint)")

# API Base URLs
API_BASE = "https://api.languagenut.com"
LIVE_BASE = "https://live.languagenut.com"

# Realistic browser headers
API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Origin": "https://www.languagenut.com",
    "Referer": "https://www.languagenut.com/",
    "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


class LanguagenutClient:
    """
    HTTP client for LanguageNut API with browser fingerprint mimicry.

    Handles authentication, session management, and API requests
    with realistic browser-like behavior.
    """

    def __init__(self, stealth=None, guild_id: int = 0):
        self.session = self._create_session()
        self.token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expiry: Optional[float] = None
        self.username: Optional[str] = None
        self.last_request_time: float = 0
        self.stealth = stealth
        self.guild_id = guild_id

    def _create_session(self):
        """Create an HTTP session with browser-like configuration."""
        if HAS_CURL_CFFI:
            session = curl_requests.Session(impersonate="chrome125")
        else:
            session = curl_requests.Session()
        return session

    def _rotate_user_agent(self):
        """Rotate user agent periodically to avoid fingerprinting."""
        ua = random.choice(USER_AGENTS)
        self.session.headers.update({"User-Agent": ua})

    def _apply_headers(self, headers: dict):
        """Apply headers to the session."""
        for key, value in headers.items():
            self.session.headers[key] = value

    def _throttle(self):
        """Ensure minimum gap between requests (human-like pacing)."""
        now = time.time()
        gap = now - self.last_request_time
        min_gap = random.uniform(0.5, 2.0)
        if gap < min_gap:
            time.sleep(min_gap - gap)
        self.last_request_time = time.time()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self, username: str, password: str) -> Tuple[bool, Optional[str]]:
        """
        Authenticate with LanguageNut.

        Returns (success, error_message).
        """
        self.username = username
        self._rotate_user_agent()
        self._apply_headers(API_HEADERS)

        url = urljoin(API_BASE, "/auth/login")
        payload = {
            "username": username,
            "password": password,
        }

        self._throttle()

        try:
            resp = self.session.post(url, json=payload, timeout=30)
            data = resp.json()
        except Exception as e:
            return False, f"Connection error: {str(e)[:100]}"

        if resp.status_code == 200 and data.get("token"):
            self.token = data["token"]
            self.refresh_token = data.get("refreshToken")
            self.session.headers["Authorization"] = f"Bearer {self.token}"
            logger.info(f"Successfully logged in as {username}")
            return True, None
        elif resp.status_code == 403 or "ACCOUNT_BLOCKED" in str(data):
            return False, "ACCOUNT_BLOCKED"
        else:
            return False, f"Login failed: {data.get('message', str(data)[:200])}"

    def refresh_auth(self) -> bool:
        """Refresh the authentication token."""
        if not self.refresh_token:
            return False
        url = urljoin(API_BASE, "/auth/refresh")
        payload = {"refreshToken": self.refresh_token}
        try:
            resp = self.session.post(url, json=payload, timeout=30)
            data = resp.json()
            if resp.status_code == 200 and data.get("token"):
                self.token = data["token"]
                self.session.headers["Authorization"] = f"Bearer {self.token}"
                return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # API Methods (sync — used by commands.py/discover.py)
    # ------------------------------------------------------------------

    def call_lnut(self, endpoint: str, params: dict = None) -> dict:
        """
        Generic API call to LanguageNut.

        endpoint: e.g. "assignmentController/getViewableAll"
        params: dict of query/post parameters, must include "token" if needed
        """
        if params is None:
            params = {}

        url = urljoin(API_BASE, f"/{endpoint}")
        self._throttle()

        token = params.pop("token", self.token)
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            resp = self.session.post(url, json=params, headers=headers, timeout=30)
            data = resp.json()
            if resp.status_code == 200:
                return data
            else:
                return {"error": True, "status": resp.status_code, "body": data}
        except Exception as e:
            return {"error": True, "body": str(e)}

    def fetch_task_data(self, task: dict, game_link: str = "", to_lang: str = "") -> Optional[list]:
        """
        Fetch vocab data for a task.

        Returns list of vocab items or None on failure.
        """
        task_type = self._resolve_task_type(task)
        uid = task.get("gameUid", "") or task.get("uid", "")

        common_params = {
            "token": self.token,
        }

        if task_type == "sentence":
            common_params["sentenceCatalogUid"] = uid
            endpoint = "sentenceCatalogController/getSentence"
        elif task_type == "verb":
            common_params["verbUid"] = uid
            endpoint = "verbController/getVerb"
        elif task_type == "phonic":
            common_params["phonicCatalogUid"] = uid
            endpoint = "phonicCatalogController/getPhonic"
        elif task_type == "exam":
            common_params["examUid"] = uid
            endpoint = "examController/getExam"
        else:
            # Default: vocab task
            common_params["gameUid"] = uid
            common_params["toLanguage"] = to_lang or "en"
            endpoint = "gameDataController/getGameVocab"

        data = self.call_lnut(endpoint, common_params)
        if data.get("error"):
            logger.warning(f"fetch_task_data failed for {uid}: {data.get('body', '')[:100]}")
            return None

        # Extract vocab list from response
        vocabs = data.get("vocabs", data.get("sentences", data.get("items", [])))
        if not vocabs:
            vocabs = [data] if isinstance(data, dict) and data.get("uid") else []
        return vocabs if vocabs else None

    def submit_score(self, task_data: dict) -> dict:
        """
        Submit a completed task score.

        task_data should be the full submission payload.
        Returns the API response dict.
        """
        url = urljoin(API_BASE, "/tasks/submit")
        self._throttle()
        try:
            resp = self.session.post(
                url, json=task_data,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30
            )
            data = resp.json()
            if resp.status_code == 200:
                return data
            else:
                return {"error": True, "status": resp.status_code, "body": data}
        except Exception as e:
            return {"error": True, "body": str(e)}

    # ------------------------------------------------------------------
    # Legacy sync submit (used by commands.py)
    # ------------------------------------------------------------------

    def submit_score_legacy(self, token: str, task: dict) -> dict:
        """Legacy submit wrapper (used by old dashboard commands)."""
        payload = {
            "token": token,
            "taskUid": task.get("gameUid", ""),
            "gameLink": task.get("gameLink", ""),
            "percentage": 100,
            "timeSpent": random.randint(30000, 120000),
        }
        return self.call_lnut("assignmentController/submitTask", payload)

    # ------------------------------------------------------------------
    # Assignment Methods
    # ------------------------------------------------------------------

    def get_assignments(self) -> Tuple[bool, Any]:
        """Fetch available assignments."""
        url = urljoin(API_BASE, "/assignments")
        self._throttle()
        try:
            resp = self.session.get(url, timeout=30)
            return resp.status_code == 200, resp.json()
        except Exception as e:
            return False, str(e)

    def get_assignment_tasks(self, assignment_id: str) -> Tuple[bool, Any]:
        """Fetch tasks for a specific assignment."""
        url = urljoin(API_BASE, f"/assignments/{assignment_id}/tasks")
        self._throttle()
        try:
            resp = self.session.get(url, timeout=30)
            return resp.status_code == 200, resp.json()
        except Exception as e:
            return False, str(e)

    def submit_task(self, task_data: dict) -> Tuple[bool, Any]:
        """Submit a completed task (returns tuple for backward compat)."""
        result = self.submit_score(task_data)
        if result.get("error"):
            return False, result.get("body", "Unknown error")
        return True, result

    def get_leaderboard(self) -> Tuple[bool, Any]:
        """Fetch leaderboard data."""
        url = urljoin(API_BASE, "/leaderboard")
        self._throttle()
        try:
            resp = self.session.get(url, timeout=30)
            return resp.status_code == 200, resp.json()
        except Exception as e:
            return False, str(e)

    def get_profile(self) -> Tuple[bool, Any]:
        """Fetch user profile."""
        url = urljoin(API_BASE, "/auth/me")
        self._throttle()
        try:
            resp = self.session.get(url, timeout=30)
            return resp.status_code == 200, resp.json()
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------
    # Task Type Resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_task_type(task: dict) -> str:
        """Determine task type from gameLink."""
        game_link = task.get("gameLink", "")
        patterns = {
            "sentence": "sentenceCatalog",
            "verb": "verbUid",
            "phonic": "phonicCatalogUid",
            "exam": "examUid",
        }
        for task_type, pattern in patterns.items():
            if pattern in game_link:
                return task_type
        return "vocabs"

    # ------------------------------------------------------------------
    # Session Management
    # ------------------------------------------------------------------

    def logout(self):
        """Clean up session."""
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass
        self.token = None
        self.refresh_token = None
        self.username = None


# ======================================================================
# ALIAS for backward compatibility with files importing LNApiClient
# ======================================================================
LNApiClient = LanguagenutClient
