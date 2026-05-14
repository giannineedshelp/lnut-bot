"""
api_direct.py — Direct HTTP client for LanguageNut API with TLS fingerprint spoofing.

Uses curl_cffi to mimic browser TLS/JA3 fingerprints and evade Cloudflare Bot Management.
Falls back to standard requests if curl_cffi is not available.
"""

import logging
import random
import time
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
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
CHROME_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9,de;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Connection": "keep-alive",
    "Cache-Control": "max-age=0",
}

API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.9,de;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Origin": "https://www.languagenut.com",
    "Referer": "https://www.languagenut.com/",
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

    def __init__(self):
        self.session = self._create_session()
        self.token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expiry: Optional[float] = None
        self.username: Optional[str] = None
        self.last_request_time: float = 0

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
            # Set auth header for subsequent requests
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
    # API Methods
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
        """
        Submit a completed task.

        task_data should contain the full task submission payload
        including timing and accuracy data.
        """
        url = urljoin(API_BASE, "/tasks/submit")
        self._throttle()
        try:
            resp = self.session.post(url, json=task_data, timeout=30)
            data = resp.json()
            if resp.status_code == 200:
                return True, data
            elif resp.status_code == 403 and "ACCOUNT_BLOCKED" in str(data):
                return False, "ACCOUNT_BLOCKED"
            else:
                return False, data.get("message", str(data)[:200])
        except Exception as e:
            return False, str(e)

    def get_leaderboard(self) -> Tuple[bool, Any]:
        """Fetch leaderboard data for endpoint diversity."""
        url = urljoin(API_BASE, "/leaderboard")
        self._throttle()
        try:
            resp = self.session.get(url, timeout=30)
            return resp.status_code == 200, resp.json()
        except Exception as e:
            return False, str(e)

    def get_profile(self) -> Tuple[bool, Any]:
        """Fetch user profile for endpoint diversity."""
        url = urljoin(API_BASE, "/auth/me")
        self._throttle()
        try:
            resp = self.session.get(url, timeout=30)
            return resp.status_code == 200, resp.json()
        except Exception as e:
            return False, str(e)

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
