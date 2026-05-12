"""
Admin API client for LanguageNut.

Provides teacher/admin-level operations (ban/unban students)
using stored encrypted credentials. All operations are
guild-owner restricted at the command level.
"""

import json
import logging
from typing import Optional

import aiohttp

logger = logging.getLogger("lnut_bot.admin_api")


class LNAPIAdminClient:
    """HTTP client for LanguageNut teacher/admin API endpoints."""

    BASE_URL = "https://api.languagenut.com"

    def __init__(
        self,
        session: aiohttp.ClientSession,
        guild_id: int = 0,
    ):
        self.session = session
        self.guild_id = guild_id
        self.token: str = ""
        self.account_uid: str = ""
        self.user_uid: str = ""
        self.person_name: str = ""

    async def call_lnut(self, endpoint: str, params: dict) -> dict:
        """Make a GET request (params in query string) to a LanguageNut API endpoint."""
        url = f"{self.BASE_URL}/{endpoint}"
        logger.debug("Admin API call: %s", endpoint)

        try:
            async with self.session.get(url, params=params) as resp:
                text = await resp.text()
                if resp.status != 200:
                    logger.error(
                        "Admin API error %s on %s: %s",
                        resp.status, endpoint, text[:200],
                    )
                    return {"error": True, "status": resp.status, "body": text[:500]}
                try:
                    result = json.loads(text)
                    new_tok = result.get("newToken")
                    if new_tok and new_tok != self.token:
                        self.token = new_tok
                    return result
                except json.JSONDecodeError:
                    logger.error("Invalid JSON from %s", endpoint)
                    return {"error": True, "body": text[:500]}
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.error("Admin API request failed: %s", exc)
            return {"error": True, "body": str(exc)}

    async def login(self, username: str, password: str) -> Optional[str]:
        """Login with teacher/admin credentials."""
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
            logger.info(
                "Admin login OK: %s (uid=%s, account=%s)",
                self.person_name, self.user_uid, self.account_uid,
            )
        else:
            logger.error("Admin login failed: %s", data.get("msg", data))
        return token

    # ---------------------------------------------------------------
    # STUDENT / CLASS OPERATIONS
    # ---------------------------------------------------------------
    async def delete_student(self, student_uid: str) -> dict:
        """
        Delete (ban) a student from the account.
        Requires teacher/admin token.
        """
        return await self.call_lnut(
            "classController/deleteStudent",
            {"token": self.token, "uid": student_uid},
        )

    async def restore_student(self, student_uid: str) -> dict:
        """
        Restore (unban) a previously deleted student.
        Requires teacher/admin token.
        """
        return await self.call_lnut(
            "classController/restoreStudent",
            {"token": self.token, "uid": student_uid},
        )

    async def get_students(self, account_uid: str = "") -> dict:
        """Get student list. Requires teacher/admin token."""
        uid = account_uid or self.account_uid
        return await self.call_lnut(
            "classController/getStudents",
            {"token": self.token, "accountUid": uid},
        )

    async def get_viewable_classes(self) -> dict:
        """Get list of classes visible to this teacher."""
        return await self.call_lnut(
            "classController/getViewableClasses",
            {"token": self.token, "accountUid": self.account_uid},
        )

    async def create_class(self, name: str) -> dict:
        """Create a new class. Requires teacher/admin token."""
        return await self.call_lnut(
            "classController/createClass",
            {"token": self.token, "name": name, "accountUid": self.account_uid},
        )

    async def delete_class(self, class_uid: str) -> dict:
        """Delete a class. Requires teacher/admin token."""
        return await self.call_lnut(
            "classController/deleteClass",
            {"token": self.token, "uid": class_uid},
        )

    async def remove_user_from_class(self, class_uid: str, user_uid: str) -> dict:
        """Remove a user from a class. Requires teacher/admin token."""
        return await self.call_lnut(
            "classController/removeUser",
            {"token": self.token, "classUid": class_uid, "userUid": user_uid},
        )

    async def get_staff_members(self) -> dict:
        """Get staff list for the account. Requires teacher/admin token."""
        return await self.call_lnut(
            "staffController/getAccountsStaff",
            {"token": self.token, "accountUid": self.account_uid},
        )

    async def verify_token_has_permissions(self) -> str:
        """
        Verify the current token has teacher/admin permissions.
        Returns 'ok', 'denied', or 'error'.
        """
        result = await self.get_staff_members()
        if "denied" in result:
            return "denied"
        if result.get("error"):
            return "error"
        return "ok"
