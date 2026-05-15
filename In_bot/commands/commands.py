"""
commands.py — LanguageNut Command Centre (FULLY WORKING)
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import platform
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord import Interaction, app_commands, ui
from discord.ext import commands

import config
from automation.stealth import StealthManager
from utils.logger import setup_logging

logger = setup_logging()

# ─── Constants ─────────────────────────────────────────────────────────────
OWNER_ID = 1453752725324955656
GREEN = discord.Colour(0x00FF88)
RED = discord.Colour(0xFF0044)
BLUE = discord.Colour(0x0088FF)
AMBER = discord.Colour(0xFFAA00)
PURPLE = discord.Colour(0x8844FF)
API_BASE = "https://api.languagenut.com"
SAVED_FILE = Path("data/saved_accounts.json")
SAVED_TTL = 10
MAX_SAVED = 3

# Languages (25 max) — NO subdivision flags, only simple country flags
LANGUAGES = {
    "fr": "French", "es": "Spanish", "de": "German", "it": "Italian",
    "en": "English", "cy": "Welsh", "zh": "Mandarin", "ar": "Arabic",
    "ja": "Japanese", "ko": "Korean", "pt": "Portuguese", "ru": "Russian",
    "nl": "Dutch", "pl": "Polish", "sv": "Swedish", "tr": "Turkish",
    "vi": "Vietnamese", "el": "Greek", "he": "Hebrew", "hi": "Hindi",
    "th": "Thai", "ro": "Romanian", "hu": "Hungarian", "cs": "Czech",
    "ga": "Irish",
}

# Safe flag emojis — only standard 2-letter region indicators that DISCORD SUPPORTS
# NO subdivision flags (Wales, Scotland, England) will break Discord select menus
_FLAG_MAP = {
    "fr": "\U0001F1EB\U0001F1F7", "es": "\U0001F1EA\U0001F1F8",
    "de": "\U0001F1E9\U0001F1EA", "it": "\U0001F1EE\U0001F1F9",
    "en": "\U0001F1EC\U0001F1E7", "cy": "\U0001F1FF\U0001F1F2",
    "zh": "\U0001F1E8\U0001F1F3", "ar": "\U0001F1E6\U0001F1F7",
    "ja": "\U0001F1EF\U0001F1F5", "ko": "\U0001F1F0\U0001F1F7",
    "pt": "\U0001F1E7\U0001F1F7", "ru": "\U0001F1F7\U0001F1FA",
    "nl": "\U0001F1F3\U0001F1F1", "pl": "\U0001F1F5\U0001F1F1",
    "sv": "\U0001F1F8\U0001F1EA", "tr": "\U0001F1F9\U0001F1F7",
    "vi": "\U0001F1FB\U0001F1F3", "el": "\U0001F1EC\U0001F1F7",
    "he": "\U0001F1EF\U0001F1F2", "hi": "\U0001F1EE\U0001F1F3",
    "th": "\U0001F1F9\U0001F1ED", "ro": "\U0001F1F7\U0001F1F4",
    "hu": "\U0001F1ED\U0001F1FA", "cs": "\U0001F1E8\U0001F1FF",
    "ga": "\u2618\uFE0F",
}

XP_QUICK = [500, 1000, 2500, 5000, 10000, 25000, 50000]

# ─── Stores ────────────────────────────────────────────────────────────────
sessions: Dict[int, Dict[str, Any]] = {}
settings_cache: Dict[int, Dict[str, Any]] = {}

DEFAULT_SETTINGS = {
    "speed": 10.0,
    "min_accuracy": 85,
    "max_accuracy": 92,
    "concurrency": 3,
    "min_seconds_per_question": 5.0,
    "max_seconds_per_question": 8.0,
    "show_completed_tasks": False,
}


def get_session(uid: int) -> dict:
    if uid not in sessions:
        sessions[uid] = {"token": None, "username": None}
    return sessions[uid]


def get_settings(uid: int) -> dict:
    if uid not in settings_cache:
        settings_cache[uid] = dict(DEFAULT_SETTINGS)
    return settings_cache[uid]


# ─── Saved Accounts ────────────────────────────────────────────────────────
def _load_saved() -> dict:
    if not SAVED_FILE.exists():
        SAVED_FILE.parent.mkdir(parents=True, exist_ok=True)
        return {}
    try:
        with open(SAVED_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_saved(data: dict):
    SAVED_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SAVED_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.replace(SAVED_FILE)


def get_saved(uid: int) -> list:
    all_a = _load_saved()
    now = datetime.now(timezone.utc)
    valid = []
    for a in all_a.get(str(uid), []):
        try:
            saved_ts = datetime.fromisoformat(a.get("saved_at", now.isoformat()))
        except Exception:
            saved_ts = now
        if (now - saved_ts).days < SAVED_TTL:
            valid.append(a)
    if len(valid) != len(all_a.get(str(uid), [])):
        all_a[str(uid)] = valid
        _save_saved(all_a)
    return valid


def save_account(uid: int, user: str, pwd: str) -> Tuple[bool, str]:
    all_a = _load_saved()
    now = datetime.now(timezone.utc)
    accs = []
    for a in all_a.get(str(uid), []):
        try:
            saved_ts = datetime.fromisoformat(a.get("saved_at", now.isoformat()))
        except Exception:
            saved_ts = now
        if (now - saved_ts).days < SAVED_TTL:
            accs.append(a)
    for a in accs:
        if a["username"].lower() == user.lower():
            a["password"] = pwd
            a["saved_at"] = now.isoformat()
            _save_saved(all_a)
            return True, "Account updated."
    if len(accs) >= MAX_SAVED:
        accs.pop(0)
    accs.append({"username": user, "password": pwd, "saved_at": now.isoformat()})
    all_a[str(uid)] = accs
    _save_saved(all_a)
    left = MAX_SAVED - len(accs)
    warn = (f"\n⚠️ Auto-deletes after {SAVED_TTL} days." if left == 0
            else f"\n💾 {left} slot{'s' if left != 1 else ''} left.")
    return True, f"Saved **{user}**!{warn}"


def delete_saved(uid: int, user: str) -> bool:
    all_a = _load_saved()
    before = len(all_a.get(str(uid), []))
    all_a[str(uid)] = [a for a in all_a.get(str(uid), [])
                       if a["username"].lower() != user.lower()]
    if len(all_a[str(uid)]) < before:
        _save_saved(all_a)
        return True
    return False


# ─── Sync API ──────────────────────────────────────────────────────────────
def _lnut(endpoint: str, payload: dict) -> dict:
    try:
        import curl_cffi.requests as cr
    except ImportError:
        import requests as cr
    url = f"{API_BASE}/{endpoint}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.languagenut.com",
        "Referer": "https://www.languagenut.com/",
    }
    try:
        resp = cr.post(url, json=payload, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        return {"error": True, "status": resp.status_code, "body": resp.text[:500]}
    except Exception as e:
        return {"error": True, "body": f"Error: {type(e).__name__}: {str(e)[:200]}"}


def _lnut_auth(endpoint: str, token: str, extra: dict = None) -> dict:
    try:
        import curl_cffi.requests as cr
    except ImportError:
        import requests as cr
    url = f"{API_BASE}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    try:
        resp = cr.get(url, headers=headers, params=extra or {}, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        return {"error": True, "status": resp.status_code, "body": resp.text[:500]}
    except Exception as e:
        return {"error": True, "body": str(e)[:200]}


# ─── Login ─────────────────────────────────────────────────────────────────
def do_login(username: str, password: str) -> Tuple[bool, str]:
    result = _lnut("loginController/attemptLogin",
                   {"username": username, "pass": password})
    if isinstance(result, dict) and not result.get("error"):
        token = result.get("newToken")
        if token:
            return True, token
        return False, f"No token: {json.dumps(result)[:200]}"
    status = result.get("status", 0)
    body = str(result.get("body", ""))[:300]
    if status in (401, 403):
        if any(k in body.lower() for k in ["banned", "suspended", "locked"]):
            return False, f"BANNED: {body}"
        return False, "Invalid credentials"
    return False, f"HTTP {status}: {body}"


# ─── API Data ──────────────────────────────────────────────────────────────
def get_homeworks(token: str) -> list:
    data = _lnut_auth("assignmentController/getViewableAll", token)
    if isinstance(data, dict) and not data.get("error"):
        hws = data.get("homework", []) or []
        hws.reverse()
        return hws
    return []


def get_stats(token: str) -> dict:
    data = _lnut_auth("stats/get", token)
    if isinstance(data, dict) and not data.get("error"):
        return data
    return {}


def get_profile(token: str) -> dict:
    data = _lnut_auth("profile/get", token)
    if isinstance(data, dict) and not data.get("error"):
        return data
    return {}


def get_leaderboard_data(token: str) -> list:
    data = _lnut_auth("leaderboard", token)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and not data.get("error"):
        return data.get("leaderboard", data.get("users", []))
    return []


# ─── Task Fetch / Submit ──────────────────────────────────────────────────
_RE_S = re.compile(r"sentenceCatalog=([a-zA-Z0-9-]+)")
_RE_V = re.compile(r"verbUid=([a-zA-Z0-9-]+)")
_RE_P = re.compile(r"phonicCatalogUid=([a-zA-Z0-9-]+)")
_RE_E = re.compile(r"examUid=([a-zA-Z0-9-]+)")


def fetch_vocabs(token: str, task: dict, lang_code: str = "en") -> Optional[list]:
    gu = task.get("gameUid", "")
    gl = task.get("gameLink", "")
    if m := _RE_S.search(gl):
        ep = (f"sentenceTranslationController/getSentenceTranslations"
              f"?gameUid={gu}&sentenceCatalogUid={m.group(1)}")
        d = _lnut_auth(ep, token)
        return (d.get("sentenceTranslations", d.get("sentences", []))
                if not d.get("error") else None)
    elif m := _RE_V.search(gl):
        ep = (f"verbTranslationController/getVerbTranslations"
              f"?gameUid={gu}&verbUid={m.group(1)}")
        d = _lnut_auth(ep, token)
        return d.get("verbTranslations", []) if not d.get("error") else None
    elif m := _RE_P.search(gl):
        ep = (f"phonicTranslationController/getPhonicTranslations"
              f"?gameUid={gu}&phonicCatalogUid={m.group(1)}")
        d = _lnut_auth(ep, token)
        return d.get("phonicTranslations", []) if not d.get("error") else None
    elif m := _RE_E.search(gl):
        ep = (f"examTranslationController/getExamTranslationsCorrect"
              f"?gameUid={gu}&examUid={m.group(1)}")
        d = _lnut_auth(ep, token)
        return d.get("examTranslations", []) if not d.get("error") else None
    else:
        cu = task.get("catalog_uid", "")
        if cu:
            ep = (f"vocabTranslationController/getVocabTranslations"
                  f"?gameUid={gu}&catalogUid[]={cu}")
            d = _lnut_auth(ep, token)
            return d.get("vocabTranslations", []) if not d.get("error") else None
        ep = f"gameDataController/getGameVocab?gameUid={gu}&toLanguage={lang_code}"
        d = _lnut_auth(ep, token)
        return d.get("vocabs", []) if not d.get("error") else None


def submit_score(token: str, task: dict, vocabs: list) -> dict:
    gu = task.get("gameUid", "")
    stealth = StealthManager()
    n = len(vocabs)
    ci, ii = stealth.apply_accuracy(n)
    ts = stealth.compute_timestamp()
    pct = round(len(ci) / n * 100) if n else 0
    payload = {
        "token": token, "taskUid": gu, "gameLink": task.get("gameLink", ""),
        "percentage": pct, "timeSpent": ts,
        "correctVocabUids": [vocabs[i].get("uid", "") for i in ci],
        "incorrectVocabUids": [vocabs[i].get("uid", "") for i in ii if i < len(vocabs)],
    }
    result = _lnut("tasks/submit", payload)
    if not result.get("error"):
        return result
    score_val = len(ci) * 200
    rl = [{"vocabUid": v.get("uid", ""), "correct": i in ci}
          for i, v in enumerate(vocabs)]
    return _lnut("gameDataController/addGameScore", {
        "gameUid": gu, "translation": task.get("translation", ""),
        "token": token, "score": str(score_val), "timeStamp": str(ts),
        "scorePercentage": str(pct),
        "results": json.dumps(rl), "dontStoreStats": "true", "product": "secondary",
    })


# ─── Health Check ──────────────────────────────────────────────────────────
def check_health(token: str) -> dict:
    res = {"status": "unknown", "banned": False, "msg": None,
           "unban_in": None, "unban_ts": None, "stats": {}}
    data = _lnut_auth("assignmentController/getViewableAll", token)
    if data.get("error"):
        sc = data.get("status", 0)
        b = str(data.get("body", ""))[:500]
        if sc in (401, 403):
            if any(k in b.lower() for k in ["banned", "suspended", "disabled",
                                             "terminated", "locked"]):
                res["status"] = "banned"
                res["banned"] = True
                res["msg"] = b
                try:
                    bd = json.loads(b) if isinstance(b, str) else b
                    if isinstance(bd, dict):
                        for k in ("unbanAt", "unban_at", "suspendedUntil",
                                  "reactivateAt", "bannedUntil"):
                            v = bd.get(k)
                            if v:
                                try:
                                    if isinstance(v, (int, float)):
                                        ts = datetime.fromtimestamp(v, tz=timezone.utc)
                                    else:
                                        ts = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
                                    res["unban_ts"] = ts
                                    rem = ts - datetime.now(timezone.utc)
                                    if rem.total_seconds() > 0:
                                        d2, r2 = rem.days, rem.seconds
                                        h, m2 = divmod(r2, 3600)
                                        mn, _ = divmod(m2, 60)
                                        parts = []
                                        if d2 > 0: parts.append(f"{d2}d")
                                        if h > 0: parts.append(f"{h}h")
                                        if mn > 0: parts.append(f"{mn}m")
                                        res["unban_in"] = " ".join(parts) if parts else "<1m"
                                    else:
                                        res["unban_in"] = "Any minute now"
                                except Exception:
                                    pass
                            break
                except Exception:
                    pass
            else:
                res["status"] = "invalid_token"
                res["msg"] = "Token expired"
        elif sc == 429:
            res["status"] = "rate_limited"
            res["msg"] = "Rate limited"
        else:
            res["status"] = "error"
            res["msg"] = b[:200]
        return res
    s = get_stats(token)
    if s:
        res["stats"] = s
        res["status"] = "active"
    else:
        res["status"] = "degraded"
    return res


# ─── Helpers ───────────────────────────────────────────────────────────────
def _pct(task: dict) -> int:
    gr = task.get("gameResults")
    if not gr:
        return 0
    try:
        return int(float(gr.get("percentage", 0)))
    except Exception:
        return 0


def _done(task: dict) -> bool:
    return _pct(task) >= 100


def _flag(lc: str) -> str:
    return _FLAG_MAP.get(lc, "\U0001F310")


def _flag_opt(lc: str) -> Optional[str]:
    """Return flag ONLY if it's a safe 2-letter region indicator."""
    f = _FLAG_MAP.get(lc)
    if f and len(f) == 4:  # 2 Unicode scalars = 4 bytes (e.g. \U0001F1EB\U0001F1F7)
        return f
    return None  # No emoji for subdivision flags to avoid Discord 400 error


# ═══════════════════════════════════════════════════════════════════════════
#  OWNER CHECK
# ═══════════════════════════════════════════════════════════════════════════
def owner_only():
    async def predicate(interaction: Interaction) -> bool:
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "🚫 Owner only command.", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)


# ═══════════════════════════════════════════════════════════════════════════
#  FARM EXECUTION
# ═══════════════════════════════════════════════════════════════════════════

async def _execute_farm(ctx, uid: int, lang: str, topic: str,
                        target: int, followup):
    s = get_session(uid)
    token = s.get("token")
    if not token:
        return await followup.send(
            embed=discord.Embed(title="Not Logged In", colour=RED),
            ephemeral=True)

    dm = None
    try:
        dm = ctx.user.dm_channel or await ctx.user.create_dm()
    except Exception:
        pass

    h = check_health(token)
    if h["banned"]:
        e = discord.Embed(title="❌ Banned", colour=RED,
                          description=h.get("msg", ""))
        if h.get("unban_in"):
            e.add_field(name="⏳ Unban", value=h["unban_in"])
        return await followup.send(embed=e, ephemeral=True)
    if h["status"] == "invalid_token":
        return await followup.send(
            embed=discord.Embed(title="Token Expired",
                                description="/login again", colour=RED),
            ephemeral=True)

    hws = get_homeworks(token)
    lh = [hw for hw in hws
          if hw.get("languageCode", "").lower() == lang.lower()]
    if not lh:
        return await followup.send(
            embed=discord.Embed(title="No Homeworks", colour=AMBER),
            ephemeral=True)

    tasks = [(hw, t) for hw in lh for t in hw.get("tasks", []) if not _done(t)]
    if not tasks:
        return await followup.send(
            embed=discord.Embed(title="All Done!", colour=GREEN),
            ephemeral=True)
    if topic.lower() != "all":
        tl = topic.lower()
        ft = [(hw, t) for hw, t in tasks
              if tl in (hw.get("name") or "").lower()
              or tl in (t.get("translation") or "").lower()]
        if ft:
            tasks = ft
    if not tasks:
        return await followup.send(
            embed=discord.Embed(title="No Matching", colour=AMBER),
            ephemeral=True)

    total = len(tasks)
    done = 0
    failed = 0
    xp = 0
    stealth = StealthManager()
    ld = LANGUAGES.get(lang, lang.upper())
    e = discord.Embed(
        title=f"{_flag(lang)} Farming {ld}",
        description=f"Target: **{target:,} XP** | Tasks: **{total}**",
        colour=AMBER)
    msg = await followup.send(embed=e, ephemeral=True)
    if dm:
        try:
            await dm.send(
                f"🌾 **Farming** {_flag(lang)} {ld} | "
                f"Target: {target:,} XP | {total} tasks")
        except Exception:
            pass

    for i, (hw, t) in enumerate(tasks):
        if xp >= target:
            break
        try:
            voc = fetch_vocabs(token, t, hw.get("languageCode", "en"))
            if not voc:
                failed += 1
                continue
            r = submit_score(token, t, voc)
            if r.get("error"):
                if r.get("status") in (401, 403):
                    await msg.edit(
                        embed=discord.Embed(title="❌ Session Expired", colour=RED))
                    return
                failed += 1
            else:
                done += 1
                xp += len(voc) * 200
        except Exception:
            failed += 1

        if (i + 1) % 3 == 0 or i == total - 1 or xp >= target:
            p = min(100, int(xp / target * 100)) if target else 0
            e.description = (f"Progress: `{done}/{total}` tasks\n"
                             f"XP: `{xp:,}/{target:,}`\nFailed: `{failed}`")
            e.set_footer(text=f"{p}%")
            await msg.edit(embed=e)
            if dm and (i + 1) % 5 == 0:
                try:
                    await dm.send(
                        f"📊 **Farm:** `{done}/{total}` tasks | "
                        f"`{xp:,}/{target:,}` XP ({p}%)")
                except Exception:
                    pass
        time.sleep(stealth.delay_between_tasks())

    e.colour = GREEN if xp >= target else AMBER
    e.description = (f"**Done!** `{done}/{total}` tasks\n"
                     f"XP: **{xp:,}** / {target:,}\n{_flag(lang)} {ld}")
    if failed:
        e.description += f"\nFailed: `{failed}`"
    await msg.edit(embed=e)
    if dm:
        try:
            await dm.send(
                f"✅ **Farm done!** `{xp:,}` XP (`{done}/{total}` tasks)")
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
#  HOMEWORK VIEWS
# ═══════════════════════════════════════════════════════════════════════════

def _fmt_sub(hw: dict, sc: bool) -> str:
    name = hw.get("name", "?")
    due = hw.get("dueDate", "?")
    tasks = hw.get("tasks", [])
    d = sum(1 for t in tasks if _done(t))
    total = len(tasks)
    p = round(d / total * 100) if total else 0
    lines = [f"**{name}**", f"📅 Due: {due}", f"📊 **{d}/{total}** ({p}%)", ""]
    for t in tasks:
        pct = _pct(t)
        dn = _done(t)
        if dn and not sc:
            continue
        lines.append(f"{'✅' if dn else '⬜'} `{t.get('translation','?')}` — {pct}%")
    if not lines[3:]:
        lines.append("All done! 🎉")
    return "\n".join(lines)


async def _show_hws(i: Interaction, uid: int, sc: bool):
    s = get_session(uid)
    token = s.get("token")
    if not token:
        return
    hws = get_homeworks(token)
    if not hws:
        return
    tt = sum(len(h.get("tasks", [])) for h in hws)
    td = sum(sum(1 for t in h.get("tasks", []) if _done(t)) for h in hws)
    e = discord.Embed(title="📋 Homeworks",
                      description=f"**{len(hws)}** homeworks — **{td}/{tt}** done",
                      colour=BLUE)
    for h in hws[:5]:
        ts2 = h.get("tasks", [])
        d2 = sum(1 for t in ts2 if _done(t))
        t2 = len(ts2)
        p2 = round(d2 / t2 * 100) if t2 else 0
        e.add_field(
            name=f"{'✅' if p2 == 100 else '📋'} {h.get('name','?')}",
            value=f"Due: {h.get('dueDate','?')} — `{d2}/{t2}` ({p2}%)",
            inline=False)
    v = ui.View(timeout=120)
    v.add_item(HwSelect(uid, hws, sc))
    v.add_item(DoAllHwBtn(uid, hws))
    if not i.response.is_done():
        await i.response.send_message(embed=e, view=v, ephemeral=True)
    else:
        await i.edit_original_response(embed=e, view=v)


class HwSelect(ui.Select):
    def __init__(self, uid: int, hws: list, sc: bool):
        self._uid = uid
        self._hws = hws
        self._sc = sc
        opts = []
        for h in hws:
            n = (h.get("name") or "?")[:90]
            ts = h.get("tasks", [])
            d = sum(1 for t in ts if _done(t))
            total = len(ts)
            p = round(d / total * 100) if total else 0
            opts.append(discord.SelectOption(
                label=f"{n} ({p}% — {d}/{total})",
                value=str(h.get("id", "")),
                description=f"Due: {h.get('dueDate','?')}",
                emoji="✅" if p == 100 else "📋"))
        super().__init__(placeholder="Select a homework...",
                         min_values=1, max_values=1,
                         options=opts[:25])

    async def callback(self, i: Interaction):
        h = next((h for h in self._hws
                  if str(h.get("id", "")) == self.values[0]), None)
        if not h:
            return
        text = _fmt_sub(h, self._sc)
        if len(text) > 1900:
            text = text[:1900] + "\n*(trunc)*"
        v = ui.View(timeout=120)
        v.add_item(DoSubBtn(self._uid, h))
        v.add_item(BackBtn(self._uid, self._sc))
        await i.response.edit_message(
            embed=discord.Embed(title=f"📋 {h.get('name','?')}",
                                description=text, colour=BLUE),
            view=v)


class DoSubBtn(ui.Button):
    def __init__(self, uid: int, hw: dict):
        super().__init__(style=discord.ButtonStyle.success,
                         label="✅ Do All Tasks", row=1)
        self.uid = uid
        self.hw = hw

    async def callback(self, i: Interaction):
        s = get_session(self.uid)
        token = s.get("token")
        if not token:
            return await i.response.send_message("Not logged in.", ephemeral=True)
        tasks = [t for t in self.hw.get("tasks", []) if not _done(t)]
        if not tasks:
            return await i.response.send_message("All done!", ephemeral=True)
        await i.response.defer(ephemeral=True)
        stealth = StealthManager()
        done = 0
        failed = 0
        xp = 0
        total = len(tasks)
        e = discord.Embed(title="Doing Tasks",
                          description=f"Completing {total}...",
                          colour=AMBER)
        msg = await i.followup.send(embed=e, ephemeral=True)
        for t in tasks:
            try:
                voc = fetch_vocabs(token, t, self.hw.get("languageCode", "en"))
                if not voc:
                    failed += 1
                    continue
                r = submit_score(token, t, voc)
                if r.get("error"):
                    failed += 1
                else:
                    done += 1
                    xp += len(voc) * 200
            except Exception:
                failed += 1
            e.description = (f"Progress: `{done}/{total}` | "
                             f"XP: `{xp:,}` | Failed: `{failed}`")
            await msg.edit(embed=e)
            time.sleep(stealth.delay_between_tasks())
        e.colour = GREEN if not failed else AMBER
        e.description = f"**Done!** `{done}/{total}`\nXP: `{xp:,}`"
        if failed:
            e.description += f"\nFailed: `{failed}`"
        await msg.edit(embed=e)


class BackBtn(ui.Button):
    def __init__(self, uid: int, sc: bool):
        super().__init__(style=discord.ButtonStyle.secondary,
                         label="◀ Back", row=2)
        self.uid = uid
        self._sc = sc

    async def callback(self, i: Interaction):
        await _show_hws(i, self.uid, self._sc)


class DoAllHwBtn(ui.Button):
    def __init__(self, uid: int, hws: list):
        super().__init__(style=discord.ButtonStyle.success,
                         label="✅ Do All Homeworks", row=2)
        self.uid = uid
        self.hws = hws

    async def callback(self, i: Interaction):
        s = get_session(self.uid)
        token = s.get("token")
        if not token:
            return await i.response.send_message("Not logged in.", ephemeral=True)
        tasks = [(h, t) for h in self.hws
                 for t in h.get("tasks", []) if not _done(t)]
        if not tasks:
            return await i.response.send_message("All done!", ephemeral=True)
        await i.response.defer(ephemeral=True)
        stealth = StealthManager()
        done = 0
        failed = 0
        xp = 0
        total = len(tasks)
        e = discord.Embed(title="Doing All",
                          description=f"{total} tasks across {len(self.hws)} homeworks...",
                          colour=AMBER)
        msg = await i.followup.send(embed=e, ephemeral=True)
        for hw, t in tasks:
            try:
                voc = fetch_vocabs(token, t, hw.get("languageCode", "en"))
                if not voc:
                    failed += 1
                    continue
                r = submit_score(token, t, voc)
                if r.get("error"):
                    failed += 1
                else:
                    done += 1
                    xp += len(voc) * 200
            except Exception:
                failed += 1
            if (done + failed) % 3 == 0 or (done + failed) == total:
                e.description = (f"Progress: `{done}/{total}` | "
                                 f"XP: `{xp:,}` | Failed: `{failed}`")
                e.set_footer(text=f"{round((done+failed)/total*100)}%")
                await msg.edit(embed=e)
            time.sleep(stealth.delay_between_tasks())
        e.colour = GREEN if not failed else AMBER
        e.description = f"**Done!** `{done}/{total}`\nXP: `{xp:,}`"
        if failed:
            e.description += f"\nFailed: `{failed}`"
        await msg.edit(embed=e)


# ═══════════════════════════════════════════════════════════════════════════
#  HUB & BUTTONS
# ═══════════════════════════════════════════════════════════════════════════

def build_hub_embed(uid: int) -> discord.Embed:
    s = get_session(uid)
    logged = s.get("token") is not None
    e = discord.Embed(title="LanguageNut Command Centre",
                      colour=PURPLE if logged else BLUE)
    if logged:
        e.description = f"Logged in as **{s.get('username','?')}**"
        e.add_field(name="Status", value="✅ Logged in", inline=True)
    else:
        e.description = "Click **Login** to get started"
        e.add_field(name="Status", value="❌ Not logged in", inline=True)
    e.set_footer(text="Buttons time out after 5 min • 📌 Pin Hub to keep panel")
    return e


class HubView(ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=300)
        self.uid = uid
        self._build()

    def _build(self):
        s = get_session(self.uid)
        logged = s.get("token") is not None

        if logged:
            self.add_item(LoginBtn(self.uid, True))
            self.add_item(LogoutBtn(self.uid))
        else:
            self.add_item(LoginBtn(self.uid, False))

        if logged:
            self.add_item(FarmBtn(self.uid))
            self.add_item(HwBtn(self.uid))
            self.add_item(LbBtn(self.uid))
            self.add_item(StatusBtn(self.uid))
            self.add_item(SettingsBtn(self.uid))
            self.add_item(SavedBtn(self.uid))
            self.add_item(HealthBtn(self.uid))

        self.add_item(HelpBtn(self.uid))
        self.add_item(PinBtn(self.uid))

        if self.uid == OWNER_ID:
            self.add_item(AdminBtn(self.uid))


class LoginBtn(ui.Button):
    def __init__(self, uid: int, logged: bool):
        super().__init__(
            style=discord.ButtonStyle.success if logged else discord.ButtonStyle.primary,
            label="Logged In ✅" if logged else "Login",
            disabled=logged)
        self.uid = uid

    async def callback(self, i: Interaction):
        await i.response.send_modal(LoginModal(self.uid))


class LogoutBtn(ui.Button):
    def __init__(self, uid: int):
        super().__init__(style=discord.ButtonStyle.danger, label="Logout")
        self.uid = uid

    async def callback(self, i: Interaction):
        s = get_session(self.uid)
        s["token"] = None
        s["username"] = None
        await i.response.send_message(
            embed=discord.Embed(title="Logged Out", colour=RED),
            ephemeral=True)


class FarmBtn(ui.Button):
    def __init__(self, uid: int):
        super().__init__(style=discord.ButtonStyle.success, label="🌾 Farm XP", row=1)
        self.uid = uid

    async def callback(self, i: Interaction):
        s = get_session(self.uid)
        token = s.get("token")
        if not token:
            return await i.response.send_message(
                embed=discord.Embed(title="Not Logged In", colour=RED),
                ephemeral=True)
        h = check_health(token)
        if h["banned"]:
            e = discord.Embed(title="❌ Banned", colour=RED, description=h.get("msg",""))
            if h.get("unban_in"):
                e.add_field(name="⏳", value=h["unban_in"])
            return await i.response.send_message(embed=e, ephemeral=True)
        v = FarmLangView(self.uid)
        await i.response.send_message(
            embed=discord.Embed(title="🌾 Farm XP",
                                description="Select a language:",
                                colour=AMBER),
            view=v, ephemeral=True)


class FarmLangView(ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=120)
        opts = []
        for code, name in sorted(LANGUAGES.items(), key=lambda x: x[1]):
            ef = _flag_opt(code)
            opts.append(discord.SelectOption(label=name, value=code, emoji=ef))
        self.add_item(FarmLangSelect(uid, opts))


class FarmLangSelect(ui.Select):
    def __init__(self, uid: int, opts: list):
        self._uid = uid
        super().__init__(placeholder="Choose language...",
                         min_values=1, max_values=1, options=opts)

    async def callback(self, i: Interaction):
        lang = self.values[0]
        s = get_session(self._uid)
        token = s.get("token")
        topics = ["All"]
        if token:
            for hw in get_homeworks(token):
                if hw.get("languageCode", "").lower() == lang.lower():
                    n = hw.get("name", "").strip()
                    if n and n not in topics:
                        topics.append(n)
                    for t in hw.get("tasks", []):
                        tn = t.get("translation", "").strip()
                        if tn and tn not in topics:
                            topics.append(tn)
                    topics = topics[:25]
        opts2 = []
        for t in topics[:25]:
            opts2.append(discord.SelectOption(
                label=t[:100], value=t,
                emoji="\U0001F4CB" if t == "All" else "\U0001F4D6"))
        v = ui.View(timeout=120)
        v.add_item(FarmTopicSelect(self._uid, lang, opts2))
        await i.response.edit_message(
            embed=discord.Embed(
                title=f"{_flag(lang)} {LANGUAGES.get(lang, lang)}",
                description="Select topic:", colour=BLUE),
            view=v)


class FarmTopicSelect(ui.Select):
    def __init__(self, uid: int, lang: str, opts: list):
        self._uid = uid
        self._lang = lang
        super().__init__(placeholder="Choose topic...",
                         min_values=1, max_values=1, options=opts)

    async def callback(self, i: Interaction):
        topic = self.values[0]
        opts3 = [discord.SelectOption(label="Custom", value="custom", emoji="\u270F\uFE0F")]
        for x in XP_QUICK:
            opts3.append(discord.SelectOption(label=f"{x:,} XP", value=str(x), emoji="\u2B50"))
        v = ui.View(timeout=120)
        v.add_item(FarmXPSelect(self._uid, self._lang, topic, opts3))
        await i.response.edit_message(
            embed=discord.Embed(title="Target XP", description="Select XP target:", colour=AMBER),
            view=v)


class FarmXPSelect(ui.Select):
    def __init__(self, uid: int, lang: str, topic: str, opts: list):
        self._uid = uid
        self._lang = lang
        self._topic = topic
        super().__init__(placeholder="Choose XP...",
                         min_values=1, max_values=1, options=opts)

    async def callback(self, i: Interaction):
        v = self.values[0]
        if v == "custom":
            await i.response.send_modal(XPModal(self._uid, self._lang, self._topic))
        else:
            await i.response.defer(ephemeral=True)
            await _execute_farm(i, self._uid, self._lang, self._topic, int(v), i.followup)


class HwBtn(ui.Button):
    def __init__(self, uid: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="📋 Homeworks", row=1)
        self.uid = uid

    async def callback(self, i: Interaction):
        s = get_session(self.uid)
        if not s.get("token"):
            return await i.response.send_message(
                embed=discord.Embed(title="Not Logged In", colour=RED),
                ephemeral=True)
        sc = get_settings(self.uid).get("show_completed_tasks", False)
        await i.response.defer(ephemeral=True)
        await _show_hws(i, self.uid, sc)


class LbBtn(ui.Button):
    def __init__(self, uid: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="🏆 Leaderboard", row=1)
        self.uid = uid

    async def callback(self, i: Interaction):
        s = get_session(self.uid)
        token = s.get("token")
        if not token:
            return await i.response.send_message("Not logged in.", ephemeral=True)
        await i.response.defer(ephemeral=True)
        entries = get_leaderboard_data(token)
        e = discord.Embed(title="Leaderboard", colour=AMBER)
        if entries:
            for idx, ent in enumerate(entries[:15]):
                name = ent.get("name", ent.get("username", f"P{idx+1}"))
                pts = int(ent.get("points", ent.get("xp", 0)))
                medal = ["🥇", "🥈", "🥉"][idx] if idx < 3 else f"`#{idx+1}`"
                e.add_field(name=f"{medal} {name}", value=f"{pts:,} pts", inline=False)
        else:
            e.description = "No data."
        await i.followup.send(embed=e, ephemeral=True)


class StatusBtn(ui.Button):
    def __init__(self, uid: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="📊 Status", row=2)
        self.uid = uid

    async def callback(self, i: Interaction):
        s = get_session(self.uid)
        token = s.get("token")
        if not token:
            return await i.response.send_message("Not logged in.", ephemeral=True)
        await i.response.defer(ephemeral=True)
        stats = get_stats(token)
        e = discord.Embed(title="📊 Status", colour=BLUE)
        e.add_field(name="Username", value=s.get("username", "?"), inline=True)
        e.add_field(name="Tasks", value=str(stats.get("tasks", "?")), inline=True)
        e.add_field(name="Points", value=f"{stats.get('points', 0):,}", inline=True)
        await i.followup.send(embed=e, ephemeral=True)


class SettingsBtn(ui.Button):
    def __init__(self, uid: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="⚙️ Settings", row=2)
        self.uid = uid

    async def callback(self, i: Interaction):
        v = SettingsView(self.uid)
        await i.response.send_message(embed=v.build_embed(), view=v, ephemeral=True)


class SavedBtn(ui.Button):
    def __init__(self, uid: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="💾 Saved Accounts", row=2)
        self.uid = uid

    async def callback(self, i: Interaction):
        v = SavedView(self.uid)
        await i.response.send_message(embed=v.build_embed(), view=v, ephemeral=True)


class HealthBtn(ui.Button):
    def __init__(self, uid: int):
        super().__init__(style=discord.ButtonStyle.danger, label="❤️ Account Health", row=3)
        self.uid = uid

    async def callback(self, i: Interaction):
        s = get_session(self.uid)
        token = s.get("token")
        if not token:
            return await i.response.send_message("Not logged in.", ephemeral=True)
        await i.response.defer(ephemeral=True)
        h = check_health(token)
        if h["banned"]:
            e = discord.Embed(title="❌ Banned", colour=RED)
            e.description = h.get("msg", "Unknown")
            if h["unban_in"]:
                e.add_field(name="⏳ Unban", value=f"**{h['unban_in']}**", inline=False)
            if h["unban_ts"]:
                e.add_field(name="ETA", value=f"<t:{int(h['unban_ts'].timestamp())}:F>", inline=False)
        elif h["status"] == "invalid_token":
            e = discord.Embed(title="Session Expired", description="/login again", colour=RED)
        else:
            stats = h.get("stats", {})
            if not stats:
                stats = get_stats(token)
            prof = get_profile(token)
            e = discord.Embed(title="❤️ Healthy ✅", colour=GREEN)
            e.add_field(name="Tasks", value=str(stats.get("tasks", "?")), inline=True)
            e.add_field(name="Points", value=f"{stats.get('points',0):,}", inline=True)
            e.add_field(name="Streak", value=f"{prof.get('streak',0)} days", inline=True)
            e.add_field(name="Accuracy", value=f"{stats.get('accuracy',0)}%", inline=True)
        e.set_footer(text=s.get("username", "?"))
        await i.followup.send(embed=e, ephemeral=True)


class HelpBtn(ui.Button):
    def __init__(self, uid: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="❓ Help", row=3)
        self.uid = uid

    async def callback(self, i: Interaction):
        e = discord.Embed(title="Help", colour=BLUE)
        e.add_field(name="Getting Started",
                    value=("1. **Login** → enter credentials\n"
                           "2. **Homeworks** → view with due dates & %\n"
                           "3. **Farm XP** → language → topic → XP target (DMs progress!)\n"
                           "4. **Account Health** → ban check with unban timer\n"
                           "5. **Saved Accounts** → save up to 3 (auto-delete 10 days)"),
                    inline=False)
        e.add_field(name="Homeworks",
                    value=("Select a homework → see subtasks (✅ done, ⬜ pending)\n"
                           "**Do All Tasks** for individual homework\n"
                           "**Do All Homeworks** for everything\n"
                           "Settings: toggle Show Completed to hide done tasks"),
                    inline=False)
        e.add_field(name="Farm XP",
                    value=("3 steps: Language → Topic → XP Target\n"
                           "Bot DMs you progress every 5 tasks!\n"
                           "Stops when target reached or tasks run out"),
                    inline=False)
        e.add_field(name="Saved Accounts",
                    value=("Save up to 3 accounts per Discord user\n"
                           "Auto-delete after 10 days to save storage\n"
                           "Login instantly from saved accounts"),
                    inline=False)
        e.add_field(name="Commands",
                    value=("`/hub` — Dashboard\n`/login` — Login\n"
                           "`/logout` — Logout\n`/farm` — Farm\n"
                           "`/homeworks` — View homeworks\n"
                           "`/status` — Stats\n"
                           "`/account-health` — Ban check\n"
                           "`/leaderboard` — Rankings"),
                    inline=False)
        await i.response.send_message(embed=e, ephemeral=True)


class PinBtn(ui.Button):
    def __init__(self, uid: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="📌 Pin Hub", row=3)
        self.uid = uid

    async def callback(self, i: Interaction):
        e = build_hub_embed(self.uid)
        v = HubView(self.uid)
        await i.response.send_message(embed=e, view=v)
        await i.followup.send("✅ Hub pinned!", ephemeral=True)


class AdminBtn(ui.Button):
    def __init__(self, uid: int):
        super().__init__(style=discord.ButtonStyle.danger, label="🛠️ Admin Panel", row=4)
        self.uid = uid

    async def callback(self, i: Interaction):
        if i.user.id != OWNER_ID:
            return await i.response.send_message("🚫 Owner only.", ephemeral=True)
        v = AdminView()
        e = discord.Embed(title="🛠️ Admin Panel", colour=RED)
        e.description = "Owner-only bot administration commands."
        await i.response.send_message(embed=e, view=v, ephemeral=True)


# ═══════════════════════════════════════════════════════════════════════════
#  MODALS
# ═══════════════════════════════════════════════════════════════════════════

class LoginModal(ui.Modal, title="LanguageNut Login (UK)"):
    username = ui.TextInput(label="Username", placeholder="Enter your LanguageNut username")
    password = ui.TextInput(label="Password", placeholder="Enter password",
                            style=discord.TextStyle.short)

    def __init__(self, uid: int):
        super().__init__()
        self.uid = uid

    async def on_submit(self, i: Interaction):
        await i.response.defer(ephemeral=True)
        ok, token_or_err = do_login(self.username.value, self.password.value)
        if ok:
            s = get_session(self.uid)
            s["token"] = token_or_err
            s["username"] = self.username.value
            await i.followup.send(
                embed=discord.Embed(title="Login Successful",
                                    description=f"Logged in as **{self.username.value}**",
                                    colour=GREEN),
                ephemeral=True)
        else:
            await i.followup.send(
                embed=discord.Embed(title="Login Failed",
                                    description=f"```{token_or_err}```",
                                    colour=RED),
                ephemeral=True)


class XPModal(ui.Modal, title="Custom XP Target"):
    xp = ui.TextInput(label="XP Target", placeholder="Enter amount (min 100)",
                      default="5000", max_length=8)

    def __init__(self, uid: int, lang: str, topic: str):
        super().__init__()
        self.uid = uid
        self.lang = lang
        self.topic = topic

    async def on_submit(self, i: Interaction):
        try:
            v = int(self.xp.value.strip())
            if v < 100 or v > 999999:
                raise ValueError
        except ValueError:
            return await i.response.send_message(
                embed=discord.Embed(title="Invalid", description="Enter 100–999,999",
                                    colour=RED),
                ephemeral=True)
        await i.response.defer(ephemeral=True)
        await _execute_farm(i, self.uid, self.lang, self.topic, v, i.followup)


# ═══════════════════════════════════════════════════════════════════════════
#  SETTINGS VIEW
# ═══════════════════════════════════════════════════════════════════════════

SETTINGS_KEYS = {
    "speed": ("Speed", "1-20", 1, 20),
    "min_accuracy": ("Min Accuracy %", "50-99", 50, 99),
    "max_accuracy": ("Max Accuracy %", "51-100", 51, 100),
    "concurrency": ("Concurrency", "1-10", 1, 10),
    "min_seconds_per_question": ("Min Sec/Q", "1-15", 1, 15),
    "max_seconds_per_question": ("Max Sec/Q", "2-20", 2, 20),
    "show_completed_tasks": ("Show Completed", "0=hide, 1=show", 0, 1),
}


class SettingsView(ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=120)
        self.uid = uid
        self._build()

    def _build(self):
        settings = get_settings(self.uid)
        for key, (label, desc, mn, mx) in SETTINGS_KEYS.items():
            val = settings.get(key, DEFAULT_SETTINGS.get(key, 0))
            self.add_item(SettingsBtn2(self.uid, key, label,
                                       f"{label}: {val}", mn, mx))

    def build_embed(self) -> discord.Embed:
        settings = get_settings(self.uid)
        e = discord.Embed(title="⚙️ Settings", colour=BLUE)
        for key, (label, desc, _, _) in SETTINGS_KEYS.items():
            val = settings.get(key, DEFAULT_SETTINGS.get(key, 0))
            e.add_field(name=label, value=f"`{val}`", inline=True)
        e.set_footer(text="Click a button to change • Show Completed: 0=hide done, 1=show all")
        return e


class SettingsBtn2(ui.Button):
    def __init__(self, uid: int, key: str, label: str, display: str, mn, mx):
        super().__init__(style=discord.ButtonStyle.secondary, label=display,
                         row=min(hash(key) % 5, 4))
        self.uid = uid
        self.skey = key
        self.slabel = label
        self.mn = mn
        self.mx = mx

    async def callback(self, i: Interaction):
        modal = SettingModal(self.uid, self.skey, self.slabel, self.mn, self.mx)
        await i.response.send_modal(modal)


class SettingModal(ui.Modal):
    def __init__(self, uid: int, key: str, label: str, mn, mx):
        super().__init__(title=f"Set {label}")
        self.uid = uid
        self.skey = key
        self.mn = mn
        self.mx = mx
        settings = get_settings(uid)
        cur = settings.get(key, DEFAULT_SETTINGS.get(key, ""))
        self.inp = ui.TextInput(label=f"{label} ({mn}-{mx})",
                                default=str(cur), max_length=10)
        self.add_item(self.inp)

    async def on_submit(self, i: Interaction):
        raw = self.inp.value.strip()
        try:
            val = int(raw)
            if val < self.mn or val > self.mx:
                raise ValueError
        except ValueError:
            return await i.response.send_message(
                embed=discord.Embed(title="Invalid",
                                    description=f"Must be {self.mn}-{self.mx}",
                                    colour=RED),
                ephemeral=True)
        if self.uid in settings_cache:
            settings_cache[self.uid][self.skey] = val
        await i.response.send_message(
            embed=discord.Embed(title="✅ Updated", description=f"`{val}`", colour=GREEN),
            ephemeral=True)


# ═══════════════════════════════════════════════════════════════════════════
#  SAVED ACCOUNTS VIEW
# ═══════════════════════════════════════════════════════════════════════════

class SavedView(ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=120)
        self.uid = uid
        self._build()

    def _build(self):
        self.add_item(SaveNowBtn(self.uid))
        accs = get_saved(self.uid)
        if accs:
            self.add_item(LoginSavedSelect(self.uid, accs))
            self.add_item(DeleteSavedSelect(self.uid, accs))

    def build_embed(self) -> discord.Embed:
        accs = get_saved(self.uid)
        e = discord.Embed(title="💾 Saved Accounts", colour=BLUE)
        if not accs:
            e.description = "No saved accounts.\nUse **Save Current** to save."
        else:
            for i, a in enumerate(accs):
                e.add_field(name=f"`#{i+1}` {a['username']}",
                            value=f"Saved: {a.get('saved_at','?')[:10]}",
                            inline=False)
        e.set_footer(text=f"Max {MAX_SAVED} • Auto-delete {SAVED_TTL} days • Per Discord user")
        return e


class SaveNowBtn(ui.Button):
    def __init__(self, uid: int):
        super().__init__(style=discord.ButtonStyle.primary, label="💾 Save Current Account")

    async def callback(self, i: Interaction):
        s = get_session(i.user.id)
        if not s.get("token") or not s.get("username"):
            return await i.response.send_message(
                embed=discord.Embed(title="Not Logged In", colour=RED),
                ephemeral=True)
        await i.response.send_modal(SavePwdModal(i.user.id))


class SavePwdModal(ui.Modal, title="Save Account"):
    pwd = ui.TextInput(label="Password", placeholder="Enter LN password",
                       style=discord.TextStyle.short)

    def __init__(self, uid: int):
        super().__init__()
        self.uid = uid

    async def on_submit(self, i: Interaction):
        s = get_session(self.uid)
        ok, msg = save_account(self.uid, s.get("username", "?"), self.pwd.value)
        await i.response.send_message(
            embed=discord.Embed(title="✅ Saved" if ok else "❌ Failed",
                                description=msg, colour=GREEN if ok else RED),
            ephemeral=True)


class LoginSavedSelect(ui.Select):
    def __init__(self, uid: int, accs: list):
        self._uid = uid
        opts = [discord.SelectOption(label=a["username"], value=str(i))
                for i, a in enumerate(accs)]
        super().__init__(placeholder="Login from saved...",
                         min_values=1, max_values=1, options=opts)

    async def callback(self, i: Interaction):
        idx = int(self.values[0])
        accs = get_saved(self._uid)
        if idx >= len(accs):
            return
        a = accs[idx]
        await i.response.defer(ephemeral=True)
        ok, tok = do_login(a["username"], a["password"])
        if ok:
            s = get_session(self._uid)
            s["token"] = tok
            s["username"] = a["username"]
            await i.followup.send(
                embed=discord.Embed(title="Logged In",
                                    description=f"**{a['username']}**",
                                    colour=GREEN),
                ephemeral=True)
        else:
            await i.followup.send(
                embed=discord.Embed(title="Failed",
                                    description=f"```{tok}```",
                                    colour=RED),
                ephemeral=True)


class DeleteSavedSelect(ui.Select):
    def __init__(self, uid: int, accs: list):
        self._uid = uid
        opts = [discord.SelectOption(label=a["username"], value=str(i))
                for i, a in enumerate(accs)]
        super().__init__(placeholder="Delete saved...",
                         min_values=1, max_values=1, options=opts)

    async def callback(self, i: Interaction):
        idx = int(self.values[0])
        accs = get_saved(self._uid)
        if idx >= len(accs):
            return
        a = accs[idx]
        delete_saved(self._uid, a["username"])
        await i.response.send_message(
            embed=discord.Embed(title="Deleted",
                                description=f"**{a['username']}** removed.",
                                colour=AMBER),
            ephemeral=True)


# ═══════════════════════════════════════════════════════════════════════════
#  ADMIN VIEW
# ═══════════════════════════════════════════════════════════════════════════

class AdminView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(AdminButton("♻️ Restart", "restart", discord.ButtonStyle.danger, 0))
        self.add_item(AdminButton("🛑 Shutdown", "shutdown", discord.ButtonStyle.danger, 0))
        self.add_item(AdminButton("🔄 Sync Cmds", "sync", discord.ButtonStyle.primary, 0))
        self.add_item(AdminButton("📥 Git Pull", "update", discord.ButtonStyle.primary, 0))
        self.add_item(AdminButton("🗑️ Clear Msgs", "clear", discord.ButtonStyle.secondary, 1))
        self.add_item(AdminButton("📄 Logs", "logs", discord.ButtonStyle.secondary, 1))
        self.add_item(AdminButton("🔄 Reload Cog", "reload", discord.ButtonStyle.secondary, 1))
        self.add_item(AdminButton("⚡ Eval", "eval", discord.ButtonStyle.danger, 2))
        self.add_item(AdminButton("🟢 Online", "online", discord.ButtonStyle.success, 2))
        self.add_item(AdminButton("🔴 Offline", "offline", discord.ButtonStyle.danger, 2))


class AdminButton(ui.Button):
    def __init__(self, label: str, cmd: str, style: discord.ButtonStyle, row: int):
        super().__init__(style=style, label=label, row=row, custom_id=f"admin_{cmd}")
        self.cmd = cmd

    async def callback(self, i: Interaction):
        if i.user.id != OWNER_ID:
            return await i.response.send_message("🚫 Owner only.", ephemeral=True)
        method = getattr(self, f"_do_{self.cmd}", None)
        if method:
            await method(i)

    async def _do_restart(self, i: Interaction):
        await i.response.send_message("♻️ Restarting bot...", ephemeral=True)
        await i.client.close()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    async def _do_shutdown(self, i: Interaction):
        await i.response.send_message("🛑 Shutting down...", ephemeral=True)
        await i.client.close()

    async def _do_sync(self, i: Interaction):
        await i.response.defer(ephemeral=True)
        try:
            synced_g = []
            if i.guild:
                synced_g = await i.client.tree.sync(guild=i.guild)
            synced_global = await i.client.tree.sync()
            await i.followup.send(
                f"✅ Synced {len(synced_g)} guild + {len(synced_global)} global commands",
                ephemeral=True)
        except Exception as e:
            await i.followup.send(f"❌ Sync failed: {e}", ephemeral=True)

    async def _do_update(self, i: Interaction):
        await i.response.defer(ephemeral=True)
        try:
            result = subprocess.run(["git", "pull"], capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return await i.followup.send("❌ git pull timed out", ephemeral=True)
        output = (result.stdout or "") + (result.stderr or "")
        await i.followup.send(f"```{output[:1800] or '(no output)'}```", ephemeral=True)
        if result.returncode != 0:
            return
        await asyncio.sleep(2)
        await i.client.close()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    async def _do_clear(self, i: Interaction):
        await i.response.send_modal(ClearModal())

    async def _do_logs(self, i: Interaction):
        log_paths = ["logs/bot.log", "bot.log"]
        log_file = next((p for p in log_paths if os.path.exists(p)), None)
        if not log_file:
            return await i.response.send_message("❌ No log file found.", ephemeral=True)
        await i.response.defer(ephemeral=True)
        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-20:]
            content = "".join(lines)
            if len(content) > 1800:
                content = content[-1800:]
            await i.followup.send(f"```{content}```", ephemeral=True)
        except OSError as e:
            await i.followup.send(f"❌ Read failed: {e}", ephemeral=True)

    async def _do_reload(self, i: Interaction):
        await i.response.send_modal(ReloadModal())

    async def _do_eval(self, i: Interaction):
        await i.response.send_modal(EvalModal())

    async def _do_online(self, i: Interaction):
        await i.response.send_message("@everyone BOT IS ONLINE 🟢")

    async def _do_offline(self, i: Interaction):
        await i.response.send_message("@everyone BOT IS OFFLINE 🔴")


class ClearModal(ui.Modal, title="Clear Messages"):
    amount = ui.TextInput(label="Number of messages (1-100)", default="10", max_length=3)

    async def on_submit(self, i: Interaction):
        try:
            amt = min(100, max(1, int(self.amount.value.strip())))
        except ValueError:
            return await i.response.send_message("Invalid number.", ephemeral=True)
        channel = i.channel
        if not isinstance(channel, discord.TextChannel):
            return await i.response.send_message("Text channels only.", ephemeral=True)
        await i.response.defer(ephemeral=True)
        try:
            deleted = await channel.purge(limit=amt)
            await i.followup.send(f"🗑️ Deleted {len(deleted)} messages", ephemeral=True)
        except discord.Forbidden:
            await i.followup.send("❌ No permission to delete messages.", ephemeral=True)


class ReloadModal(ui.Modal, title="Reload Cog"):
    cog = ui.TextInput(label="Cog name", placeholder="e.g. commands.commands",
                       default="commands.commands")

    async def on_submit(self, i: Interaction):
        await i.response.defer(ephemeral=True)
        candidates = [self.cog.value]
        if "." not in self.cog.value:
            candidates.append(f"commands.{self.cog.value}")
        last_err = None
        for name in candidates:
            try:
                await i.client.reload_extension(name)
                return await i.followup.send(f"✅ Reloaded `{name}`", ephemeral=True)
            except Exception as e:
                last_err = e
                continue
        await i.followup.send(f"❌ Reload failed: {last_err}", ephemeral=True)


class EvalModal(ui.Modal, title="Python Eval"):
    code = ui.TextInput(label="Code",
                        placeholder="await interaction.followup.send('hi')",
                        style=discord.TextStyle.long,
                        default="await interaction.followup.send('Hello from eval!')")

    async def on_submit(self, i: Interaction):
        await i.response.defer(ephemeral=True)
        env: Dict[str, Any] = {
            "bot": i.client,
            "discord": discord,
            "interaction": i,
            "asyncio": asyncio,
            "os": os,
            "sys": sys,
        }
        try:
            lines = self.code.value.strip().split("\n")
            body = "\n".join(f"    {line}" for line in lines)
            exec(f"async def __ex():\n{body}", env)
            result = await env["__ex"]()
            await i.followup.send(f"```\n{str(result)[:1900]}\n```", ephemeral=True)
        except Exception as e:
            await i.followup.send(f"❌ {type(e).__name__}: {e}", ephemeral=True)


# ═══════════════════════════════════════════════════════════════════════════
#  COG — SLASH COMMANDS
# ═══════════════════════════════════════════════════════════════════════════

class LanguageBotCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="hub", description="Open the LanguageNut control hub dashboard")
    async def hub(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        uid = interaction.guild_id or interaction.user.id
        await interaction.followup.send(embed=build_hub_embed(uid),
                                        view=HubView(uid), ephemeral=True)

    @app_commands.command(name="login", description="Login to LanguageNut (UK)")
    async def login(self, interaction: Interaction):
        uid = interaction.guild_id or interaction.user.id
        await interaction.response.send_modal(LoginModal(uid))

    @app_commands.command(name="logout", description="Logout and clear session")
    async def logout(self, interaction: Interaction):
        uid = interaction.guild_id or interaction.user.id
        s = get_session(uid)
        s["token"] = None
        s["username"] = None
        await interaction.response.send_message(
            embed=discord.Embed(title="Logged Out", colour=RED), ephemeral=True)

    @app_commands.command(name="homeworks", description="View and manage homeworks")
    async def homeworks(self, interaction: Interaction):
        uid = interaction.guild_id or interaction.user.id
        s = get_session(uid)
        if not s.get("token"):
            return await interaction.response.send_message(
                embed=discord.Embed(title="Not Logged In", colour=RED), ephemeral=True)
        sc = get_settings(uid).get("show_completed_tasks", False)
        await interaction.response.defer(ephemeral=True)
        await _show_hws(interaction, uid, sc)

    @app_commands.command(name="farm", description="Farm XP: language → topic → XP target")
    async def farm(self, interaction: Interaction):
        uid = interaction.guild_id or interaction.user.id
        s = get_session(uid)
        if not s.get("token"):
            return await interaction.response.send_message(
                embed=discord.Embed(title="Not Logged In", colour=RED), ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        h = check_health(s["token"])
        if h["banned"]:
            e = discord.Embed(title="❌ Account Banned", colour=RED, description=h.get("msg",""))
            if h.get("unban_in"):
                e.add_field(name="⏳ Unban In", value=h["unban_in"])
            return await interaction.followup.send(embed=e, ephemeral=True)
        await interaction.followup.send(
            embed=discord.Embed(title="🌾 Farm XP", description="Select a language:", colour=AMBER),
            view=FarmLangView(uid), ephemeral=True)

    @app_commands.command(name="leaderboard", description="View school leaderboard")
    async def leaderboard(self, interaction: Interaction):
        uid = interaction.guild_id or interaction.user.id
        s = get_session(uid)
        if not s.get("token"):
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        entries = get_leaderboard_data(s["token"])
        e = discord.Embed(title="🏆 Leaderboard", colour=AMBER)
        if entries:
            for idx, ent in enumerate(entries[:15]):
                name = ent.get("name", ent.get("username", f"P{idx+1}"))
                pts = int(ent.get("points", ent.get("xp", 0)))
                medal = ["🥇", "🥈", "🥉"][idx] if idx < 3 else f"`#{idx+1}`"
                e.add_field(name=f"{medal} {name}", value=f"{pts:,} pts", inline=False)
        else:
            e.description = "No data available."
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="status", description="Show account stats")
    async def status(self, interaction: Interaction):
        uid = interaction.guild_id or interaction.user.id
        s = get_session(uid)
        if not s.get("token"):
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        stats = get_stats(s["token"])
        e = discord.Embed(title="📊 Account Status", colour=BLUE)
        e.add_field(name="Username", value=s.get("username", "?"), inline=True)
        e.add_field(name="Tasks", value=str(stats.get("tasks", "?")), inline=True)
        e.add_field(name="Points", value=f"{stats.get('points', 0):,}", inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="account-health", description="Check if account is banned or healthy")
    async def account_health(self, interaction: Interaction):
        uid = interaction.guild_id or interaction.user.id
        s = get_session(uid)
        if not s.get("token"):
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        h = check_health(s["token"])
        if h["banned"]:
            e = discord.Embed(title="❌ Account Banned", colour=RED)
            e.description = h.get("msg", "Unknown reason")
            if h["unban_in"]:
                e.add_field(name="⏳ Unban In", value=f"**{h['unban_in']}**", inline=False)
            if h["unban_ts"]:
                e.add_field(name="📅 ETA", value=f"<t:{int(h['unban_ts'].timestamp())}:R>", inline=False)
        elif h["status"] == "invalid_token":
            e = discord.Embed(title="Session Expired", description="Run `/login` again.", colour=RED)
        else:
            stats = h.get("stats", {})
            if not stats:
                stats = get_stats(s["token"])
            prof = get_profile(s["token"])
            e = discord.Embed(title="❤️ Account Healthy ✅", colour=GREEN)
            e.add_field(name="Tasks", value=str(stats.get("tasks", "?")), inline=True)
            e.add_field(name="Points", value=f"{stats.get('points',0):,}", inline=True)
            e.add_field(name="Streak", value=f"{prof.get('streak',0)} days", inline=True)
            e.add_field(name="Accuracy", value=f"{stats.get('accuracy',0)}%", inline=True)
        e.set_footer(text=s.get("username", "?"))
        await interaction.followup.send(embed=e, ephemeral=True)

    @app_commands.command(name="settings", description="Configure bot behaviour")
    async def settings(self, interaction: Interaction):
        uid = interaction.guild_id or interaction.user.id
        await interaction.response.send_message(
            embed=SettingsView(uid).build_embed(), view=SettingsView(uid), ephemeral=True)

    @app_commands.command(name="saved", description="Manage saved accounts (max 3, auto-delete 10 days)")
    async def saved(self, interaction: Interaction):
        uid = interaction.user.id
        await interaction.response.send_message(
            embed=SavedView(uid).build_embed(), view=SavedView(uid), ephemeral=True)

    @app_commands.command(name="pin-hub", description="Pin hub panel to channel (non-ephemeral)")
    async def pin_hub(self, interaction: Interaction):
        uid = interaction.guild_id or interaction.user.id
        await interaction.response.send_message(embed=build_hub_embed(uid), view=HubView(uid))
        await interaction.followup.send("📌 Hub pinned!", ephemeral=True)

    # Admin commands
    @app_commands.command(name="admin-restart", description="[OWNER] Restart the bot")
    @owner_only()
    async def admin_restart(self, interaction: Interaction):
        await interaction.response.send_message("♻️ Restarting bot...", ephemeral=True)
        await self.bot.close()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @app_commands.command(name="admin-shutdown", description="[OWNER] Stop the bot")
    @owner_only()
    async def admin_shutdown(self, interaction: Interaction):
        await interaction.response.send_message("🛑 Shutting down...", ephemeral=True)
        await self.bot.close()

    @app_commands.command(name="admin-sync", description="[OWNER] Force sync slash commands")
    @owner_only()
    async def admin_sync(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            synced_g = []
            if interaction.guild:
                self.bot.tree.clear_commands(guild=interaction.guild)
                synced_g = await self.bot.tree.sync(guild=interaction.guild)
            synced_global = await self.bot.tree.sync()
            await interaction.followup.send(
                f"✅ Synced {len(synced_g)} guild + {len(synced_global)} global commands",
                ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Sync failed: {e}", ephemeral=True)

    @app_commands.command(name="admin-update", description="[OWNER] Git pull + restart")
    @owner_only()
    async def admin_update(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            result = subprocess.run(["git", "pull"], capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return await interaction.followup.send("❌ git pull timed out", ephemeral=True)
        output = (result.stdout or "") + (result.stderr or "")
        await interaction.followup.send(f"```{output[:1800] or '(no output)'}```", ephemeral=True)
        if result.returncode != 0:
            return
        await asyncio.sleep(2)
        await self.bot.close()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @app_commands.command(name="admin-clear", description="[OWNER] Delete recent messages")
    @owner_only()
    @app_commands.describe(amount="Number of messages (1-100)")
    async def admin_clear(self, interaction: Interaction, amount: int = 10):
        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("❌ Text channels only.", ephemeral=True)
        amount = max(1, min(100, amount))
        await interaction.response.defer(ephemeral=True)
        try:
            deleted = await interaction.channel.purge(limit=amount)
            await interaction.followup.send(f"🗑️ Deleted {len(deleted)} messages", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ No permission to delete messages.", ephemeral=True)

    @app_commands.command(name="admin-logs", description="[OWNER] Show last 20 log lines")
    @owner_only()
    async def admin_logs(self, interaction: Interaction):
        log_paths = ["logs/bot.log", "bot.log"]
        log_file = next((p for p in log_paths if os.path.exists(p)), None)
        if not log_file:
            return await interaction.response.send_message("❌ No log file found.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()[-20:]
            content = "".join(lines)
            if len(content) > 1800:
                content = content[-1800:]
            await interaction.followup.send(f"```{content}```", ephemeral=True)
        except OSError as e:
            await interaction.followup.send(f"❌ Read failed: {e}", ephemeral=True)

    @app_commands.command(name="admin-reload", description="[OWNER] Reload a cog")
    @owner_only()
    @app_commands.describe(cog="Cog path (e.g. 'commands.commands')")
    async def admin_reload(self, interaction: Interaction, cog: str = "commands.commands"):
        await interaction.response.defer(ephemeral=True)
        candidates = [cog]
        if "." not in cog:
            candidates.append(f"commands.{cog}")
        last_err = None
        for name in candidates:
            try:
                await self.bot.reload_extension(name)
                return await interaction.followup.send(f"✅ Reloaded `{name}`", ephemeral=True)
            except Exception as e:
                last_err = e
                continue
        await interaction.followup.send(f"❌ Reload failed: {last_err}", ephemeral=True)

    @app_commands.command(name="admin-eval", description="[OWNER] Execute Python code")
    @owner_only()
    @app_commands.describe(code="Python code to execute")
    async def admin_eval(self, interaction: Interaction,
                         code: str = "await interaction.followup.send('Hello from eval!')"):
        await interaction.response.defer(ephemeral=True)
        env = {"bot": self.bot, "discord": discord, "interaction": interaction,
               "asyncio": asyncio, "os": os, "sys": sys}
        try:
            lines = code.strip().split("\n")
            body = "\n".join(f"    {line}" for line in lines)
            exec(f"async def __ex():\n{body}", env)
            result = await env["__ex"]()
            await interaction.followup.send(f"```\n{str(result)[:1900]}\n```", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ {type(e).__name__}: {e}", ephemeral=True)

    @app_commands.command(name="admin-online", description="[OWNER] Announce BOT ONLINE")
    @owner_only()
    async def admin_online(self, interaction: Interaction):
        await interaction.response.send_message("@everyone BOT IS ONLINE 🟢")

    @app_commands.command(name="admin-offline", description="[OWNER] Announce BOT OFFLINE")
    @owner_only()
    async def admin_offline(self, interaction: Interaction):
        await interaction.response.send_message("@everyone BOT IS OFFLINE 🔴")

    @app_commands.command(name="admin-students", description="[OWNER] List school students + stats")
    @owner_only()
    async def admin_students(self, interaction: Interaction):
        uid = interaction.guild_id or interaction.user.id
        s = get_session(uid)
        if not s.get("token"):
            return await interaction.response.send_message("Not logged in.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        data = _lnut_auth("highscoreController/studentsAllAccount", s["token"], {"accountUid": ""})
        students = data.get("list", []) if isinstance(data, dict) else []
        if not students:
            return await interaction.followup.send(
                embed=discord.Embed(title="No Students", colour=AMBER), ephemeral=True)
        e = discord.Embed(title="👥 School Students", colour=BLUE)
        for i, stu in enumerate(students[:20]):
            name = stu.get("name", stu.get("username", f"S{i+1}"))
            pts = int(stu.get("score", stu.get("points", 0)))
            e.add_field(name=f"`#{i+1}` {name}", value=f"{pts:,} pts", inline=False)
        await interaction.followup.send(embed=e, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LanguageBotCog(bot))
    logger.info("✅ CommandCentre loaded")