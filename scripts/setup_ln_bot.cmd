@echo off
title LanguageNut Bot — Auto Setup
cd /d "C:\Users\Saturated\OneDrive - St Ambrose College\code\ln_bot"

echo ============================================
echo   LanguageNut Bot — Auto Setup
echo ============================================
echo.

REM ========== CREATE FOLDER STRUCTURE ==========
echo [1/8] Creating folder structure...
mkdir data 2>nul
mkdir data\users 2>nul
mkdir logs 2>nul
mkdir utils 2>nul
mkdir automation 2>nul
mkdir commands 2>nul

REM ========== CREATE EMPTY __init__.py FILES ==========
echo [2/8] Creating __init__.py files...
echo. > utils\__init__.py
echo. > automation\__init__.py
echo. > commands\__init__.py

REM ========== CREATE .env.example ==========
echo [3/8] Creating .env.example...
(
echo # Discord Bot Token
echo DISCORD_TOKEN=your_token_here
echo.
echo # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
echo ENCRYPTION_KEY=
echo.
echo # Bot owner Discord ID
echo OWNER_ID=
echo.
echo # Optional logging channel
echo LOG_CHANNEL_ID=0
) > .env.example

REM ========== CREATE .gitignore ==========
echo [4/8] Creating .gitignore...
(
echo # Environment
echo .env
echo.
echo # Data files
echo data/users/*.json
echo data/discovered_endpoints.json
echo data/settings.json
echo.
echo # Python
echo __pycache__/
echo *.pyc
echo *.pyo
echo *.egg-info/
echo dist/
echo build/
echo *.egg
echo.
echo # Logs
echo logs/
echo *.log
echo.
echo # Playwright browsers
echo ms-playwright/
echo playwright-browsers/
echo.
echo # IDE
echo .vscode/
echo .idea/
echo.
echo # OS
echo .DS_Store
echo Thumbs.db
) > .gitignore

REM ========== CREATE requirements.txt ==========
echo [5/8] Creating requirements.txt...
(
echo discord.py==2.4.0
echo playwright==1.51.0
echo playwright-stealth==1.0.6
echo requests==2.32.3
echo python-dotenv==1.1.0
echo cryptography==44.0.2
echo aiofiles==24.1.0
) > requirements.txt

REM ========== CREATE config.py ==========
echo [6/8] Creating config.py...
(
echo import os
echo import json
echo from pathlib import Path
echo from dotenv import load_dotenv
echo from cryptography.fernet import Fernet
echo.
echo load_dotenv()
echo.
echo BASE_DIR = Path(__file__).parent
echo DATA_DIR = BASE_DIR / "data"
echo USERS_DIR = DATA_DIR / "users"
echo LOGS_DIR = BASE_DIR / "logs"
echo.
echo for d in [DATA_DIR, USERS_DIR, LOGS_DIR]:
echo     d.mkdir(parents=True, exist_ok=True)
echo.
echo DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
echo ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
echo OWNER_ID = os.getenv("OWNER_ID", "")
echo LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))
echo.
echo DEFAULT_USER_SETTINGS = {
echo     "username": "",
echo     "password_encrypted": "",
echo     "region": "en-gb",
echo     "accuracy_min": 0.82,
echo     "accuracy_max": 0.95,
echo     "think_delay_min": 0.8,
echo     "think_delay_max": 4.0,
echo     "type_speed_min": 45,
echo     "type_speed_max": 150,
echo     "activity_delay_min": 1.5,
echo     "activity_delay_max": 5.0,
echo     "fake_time_enabled": True,
echo     "fake_timezone": "Europe/London",
echo     "fake_time_mode": "realistic",
echo     "fake_geolocation_enabled": True,
echo     "fake_latitude": 51.5074,
echo     "fake_longitude": -0.1278,
echo     "fake_locale": "en-GB",
echo     "viewport_width": 1400,
echo     "viewport_height": 900,
echo     "user_agent": (
echo         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
echo         "AppleWebKit/537.36 (KHTML, like Gecko) "
echo         "Chrome/131.0.0.0 Safari/537.36"
echo     ),
echo     "headless": True,
echo     "max_questions": 500,
echo     "max_assignments": 20,
echo     "last_used": "",
echo     "created_at": "",
echo }
echo.
echo.
echo class UserConfig:
echo     def __init__(self, discord_id: str):
echo         self.discord_id = str(discord_id)
echo         self.filepath = USERS_DIR / f"{self.discord_id}.json"
echo         self.data = dict(DEFAULT_USER_SETTINGS)
echo         self._load()
echo.
echo     def _load(self):
echo         if self.filepath.exists():
echo             try:
echo                 with open(self.filepath) as f:
echo                     saved = json.load(f)
echo                 for k, v in saved.items():
echo                     if k in self.data:
echo                         self.data[k] = v
echo             except Exception:
echo                 pass
echo.
echo     def save(self):
echo         with open(self.filepath, "w") as f:
echo             json.dump(self.data, f, indent=2)
echo.
echo     def __getitem__(self, key):
echo         if key == "password" and self.data.get("password_encrypted"):
echo             return self._decrypt_password()
echo         return self.data.get(key, DEFAULT_USER_SETTINGS.get(key))
echo.
echo     def __setitem__(self, key, value):
echo         if key == "password":
echo             self.data["password_encrypted"] = self._encrypt_password(value)
echo         else:
echo             self.data[key] = value
echo         self.save()
echo.
echo     def _encrypt_password(self, password: str) -> str:
echo         if not ENCRYPTION_KEY:
echo             return password
echo         try:
echo             f = Fernet(ENCRYPTION_KEY.encode())
echo             return f.encrypt(password.encode()).decode()
echo         except Exception:
echo             return password
echo.
echo     def _decrypt_password(self) -> str:
echo         if not ENCRYPTION_KEY:
echo             return self.data.get("password_encrypted", "")
echo         try:
echo             f = Fernet(ENCRYPTION_KEY.encode())
echo             return f.decrypt(self.data["password_encrypted"].encode()).decode()
echo         except Exception:
echo             return self.data.get("password_encrypted", "")
echo.
echo     @property
echo     def region(self):
echo         return self.data.get("region", "en-gb")
echo.
echo     @property
echo     def login_url(self):
echo         r = self.region
echo         if r == "en-au":
echo             return "https://asia.languagenut.com/resources/#/LoginScreen"
echo         return f"https://resources.languagenut.com/resources/{r}/index.html#/LoginScreen"
echo.
echo     @property
echo     def has_credentials(self):
echo         return bool(self["username"] and self.__getitem__("password"))
echo.
echo     def delete(self):
echo         if self.filepath.exists():
echo             self.filepath.unlink()
echo.
echo     def to_dict(self, show_password=False):
echo         d = dict(self.data)
echo         if show_password:
echo             d["password"] = self.__getitem__("password")
echo         else:
echo             d.pop("password_encrypted", None)
echo         return d
echo.
echo.
echo def get_config(discord_id: str) -> UserConfig:
echo     return UserConfig(discord_id)
) > config.py

REM ========== CREATE ALL UTILS FILES ==========
echo [7/8] Creating utility and module files...

REM utils\logger.py
(
echo import logging
echo import sys
echo from config import LOGS_DIR
echo.
echo LOG_FILE = LOGS_DIR / "bot.log"
echo.
echo def setup_logger(name: str = "ln_bot") -^> logging.Logger:
echo     logger = logging.getLogger(name)
echo     logger.setLevel(logging.INFO)
echo.
echo     fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
echo     fh.setLevel(logging.INFO)
echo     fh.setFormatter(logging.Formatter(
echo         "%%(asctime)s | %%(levelname)-8s | %%(message)s",
echo         datefmt="%%Y-%%m-%%d %%H:%%M:%%S"
echo     ))
echo     logger.addHandler(fh)
echo.
echo     ch = logging.StreamHandler(sys.stdout)
echo     ch.setLevel(logging.INFO)
echo     ch.setFormatter(logging.Formatter(
echo         "%%(asctime)s | %%(levelname)-8s | %%(message)s",
echo         datefmt="%%H:%%M:%%S"
echo     ))
echo     logger.addHandler(ch)
echo.
echo     return logger
echo.
echo logger = setup_logger()
) > utils\logger.py

REM utils\encryption.py
(
echo from cryptography.fernet import Fernet
echo from config import ENCRYPTION_KEY
echo.
echo def generate_key() -^> str:
echo     return Fernet.generate_key().decode()
echo.
echo def encrypt(text: str) -^> str:
echo     if not ENCRYPTION_KEY:
echo         return text
echo     try:
echo         f = Fernet(ENCRYPTION_KEY.encode())
echo         return f.encrypt(text.encode()).decode()
echo     except Exception:
echo         return text
echo.
echo def decrypt(token: str) -^> str:
echo     if not ENCRYPTION_KEY or not token:
echo         return token
echo     try:
echo         f = Fernet(ENCRYPTION_KEY.encode())
echo         return f.decrypt(token.encode()).decode()
echo     except Exception:
echo         return token
) > utils\encryption.py

REM utils\helpers.py
(
echo import random
echo import json
echo from pathlib import Path
echo from datetime import datetime
echo from config import BASE_DIR
echo.
echo def accuracy_for_run(acc_min: float, acc_max: float) -^> float:
echo     return random.uniform(acc_min, acc_max)
echo.
echo def human_delay(min_s: float = 0.3, max_s: float = 2.0) -^> float:
echo     return random.uniform(min_s, max_s)
echo.
echo def random_viewport():
echo     w = random.choice([1366, 1440, 1536, 1600, 1680, 1920])
echo     h = random.choice([768, 900, 864, 1024, 1080])
echo     return {"width": w, "height": h}
echo.
echo def timestamp() -^> str:
echo     return datetime.now().isoformat()
echo.
echo def load_json(path: Path):
echo     if path.exists():
echo         try:
echo             with open(path) as f:
echo                 return json.load(f)
echo         except Exception:
echo             return {}
echo     return {}
echo.
echo def save_json(path: Path, data):
echo     path.parent.mkdir(parents=True, exist_ok=True)
echo     with open(path, "w") as f:
echo         json.dump(data, f, indent=2)
) > utils\helpers.py

REM automation\__init__.py
(
echo from .stealth import run_stealth
echo from .discover import run_discover
echo from .api_direct import run_api
) > automation\__init__.py

REM automation\stealth.py
(
echo import asyncio
echo import random
echo from config import get_config
echo from utils.logger import logger
echo from utils.helpers import accuracy_for_run, human_delay, random_viewport
echo.
echo async def run_stealth(discord_id, status_callback, complete_callback, bot=None):
echo     config = get_config(discord_id)
echo     if not config.has_credentials:
echo         await status_callback("Credentialion not set! Use /set username and /set password")
echo         return
echo.
echo     try:
echo         from playwright.async_api import async_playwright
echo         from playwright_stealth import Stealth
echo     except ImportError:
echo         await status_callback("Playwright not installed! Run: pip install playwright playwright-stealth ^&^& playwright install chromium")
echo         return
echo.
echo     acc = accuracy_for_run(config["accuracy_min"], config["accuracy_max"])
echo     await status_callback(f"Stealth Browser - Starting (acc: {acc*100:.0f}%)")
echo.
echo     async with async_playwright() as p:
echo         vp = random_viewport()
echo         ua = config["user_agent"]
echo         browser = await p.chromium.launch(headless=config["headless"], args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"])
echo         ctx = await browser.new_context(viewport=vp, user_agent=ua, locale=config["fake_locale"], timezone_id=config["fake_timezone"] if config["fake_time_enabled"] else None, geolocation={"latitude": config["fake_latitude"], "longitude": config["fake_longitude"]} if config["fake_geolocation_enabled"] else None, permissions=["geolocation"] if config["fake_geolocation_enabled"] else None)
echo         await Stealth().use_async(ctx)
echo         page = await ctx.new_page()
echo.
echo         captured_token = None
echo         async def intercept(req):
echo             nonlocal captured_token
echo             auth = req.headers.get("authorization", "")
echo             if auth.startswith("Bearer ") and not captured_token:
echo                 captured_token = auth[7:]
echo         page.on("request", intercept)
echo.
echo         await page.goto(config.login_url, wait_until="domcontentloaded", timeout=60000)
echo         await asyncio.sleep(human_delay(1.5, 3.5))
echo.
echo         await status_callback(f"Stealth - Logging in as {config['username']}")
echo         u_el = await page.query_selector('input[type="text"]')
echo         if u_el: await u_el.click(); await asyncio.sleep(human_delay(0.1, 0.3)); await u_el.fill(config["username"])
echo         await asyncio.sleep(human_delay(0.3, 0.8))
echo         p_el = await page.query_selector('input[type="password"]')
echo         if p_el: await p_el.click(); await asyncio.sleep(human_delay(0.1, 0.3)); await p_el.fill(config["password"])
echo         await asyncio.sleep(human_delay(0.5, 1.5))
echo         btn = await page.query_selector('button:has-text("Login"), button[type="submit"]')
echo         if btn: await btn.click()
echo         else: await page.keyboard.press("Enter")
echo.
echo         try: await page.wait_for_load_state("networkidle", timeout=30000)
echo         except: pass
echo         await asyncio.sleep(human_delay(2, 4))
echo.
echo         if captured_token:
echo             config.data["saved_token"] = captured_token
echo             config.save()
echo.
echo         total = 0
echo         fails = 0
echo         max_q = config["max_questions"]
echo         for qnum in range(max_q):
echo             await asyncio.sleep(human_delay(config["think_delay_min"], config["think_delay_max"]))
echo             found = False
echo             for sel in ['[class*="option"]', '[class*="choice"]', '[role="radio"]', 'button:not([disabled])', '[class*="selectable"]', '[class*="answer"]', 'label:not(:has(input))', '[class*="btn-option"]']:
echo                 try: opts = await page.query_selector_all(sel)
echo                 except: opts = []
echo                 real = [o for o in opts if (await o.text_content() or "").strip().lower() and not any(w in (await o.text_content() or "").lower() for w in ["login","sign in","register","submit","dashboard","logout"])]
echo                 if len(real) >= 2:
echo                     idx = 0 if random.random() < acc else random.randint(1, len(real)-1)
echo                     idx = min(idx, len(real)-1)
echo                     try: await real[idx].click(); found = True; break
echo                     except: continue
echo             if found:
echo                 total += 1; fails = 0
echo                 if total % 15 == 0: await status_callback(f"Stealth - Answered: {total}/{max_q}")
echo                 continue
echo             for sel in ['input[type="text"]', 'textarea', '[contenteditable="true"]']:
echo                 try: inps = await page.query_selector_all(sel)
echo                 except: inps = []
echo                 for inp in inps:
echo                     try:
echo                         pid = (await inp.get_attribute("placeholder") or "").lower()
echo                         if any(w in pid for w in ["user","pass","email"]): continue
echo                         await inp.click(); await asyncio.sleep(human_delay(0.1,0.3))
echo                         await inp.fill(random.choice(["yes","no","hello","book","house","red","blue","one","two","three","big","small","hot","cold","good","bad","up","down","left","right"]))
echo                         found = True; break
echo                     except: continue
echo                 if found: break
echo             if found:
echo                 total += 1; fails = 0
echo                 if total % 15 == 0: await status_callback(f"Stealth - Answered: {total}/{max_q}")
echo                 continue
echo             for txt in ["Next","Continue","Submit","Check","Done","Finish","OK"]:
echo                 for sel in [f'button:has-text("{txt}")', f'[class*="btn"]:has-text("{txt}")', f'a:has-text("{txt}")']:
echo                     try: btn = await page.query_selector(sel)
echo                     except: btn = None
echo                     if btn: await btn.click(); found = True; break
echo                 if found: break
echo             if found:
echo                 total += 1; fails = 0
echo                 if total % 15 == 0: await status_callback(f"Stealth - Answered: {total}/{max_q}")
echo                 continue
echo             fails += 1
echo             if fails >= 20: break
echo.
echo         await browser.close()
echo     await complete_callback({"answered": total, "accuracy": round(acc*100, 1), "mode": "stealth"})
echo     logger.info(f"[Stealth] User {discord_id} answered {total} questions")
) > automation\stealth.py

REM automation\discover.py
(
echo import asyncio
echo import json
echo from datetime import datetime
echo from config import get_config, DATA_DIR
echo from utils.logger import logger
echo from utils.helpers import human_delay
echo.
echo DISCOVERED_FILE = DATA_DIR / "discovered_endpoints.json"
echo.
echo async def run_discover(discord_id, status_callback, complete_callback):
echo     config = get_config(discord_id)
echo     try:
echo         from playwright.async_api import async_playwright
echo         from playwright_stealth import Stealth
echo     except ImportError:
echo         await status_callback("Playwright not installed!")
echo         return
echo.
echo     await status_callback("Discover - Launching browser...")
echo     async with async_playwright() as p:
echo         browser = await p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
echo         ctx = await browser.new_context(viewport={"width": 1400, "height": 900})
echo         await Stealth().use_async(ctx)
echo         page = await ctx.new_page()
echo.
echo         captured = {"endpoints": set(), "token": None}
echo         async def intercept(req):
echo             url = req.url
echo             if "languagenut.com" in url: captured["endpoints"].add(url.split("?")[0])
echo             auth = req.headers.get("authorization", "")
echo             if auth.startswith("Bearer ") and not captured["token"]: captured["token"] = auth[7:]
echo         page.on("request", intercept)
echo.
echo         await page.goto(config.login_url, wait_until="domcontentloaded", timeout=60000)
echo         await asyncio.sleep(human_delay(1, 2))
echo.
echo         if config.has_credentials:
echo             u_el = await page.query_selector('input[type="text"]')
echo             if u_el: await u_el.fill(config["username"])
echo             await asyncio.sleep(human_delay(0.3, 0.8))
echo             p_el = await page.query_selector('input[type="password"]')
echo             if p_el: await p_el.fill(config["password"])
echo             await asyncio.sleep(human_delay(0.5, 1.5))
echo             btn = await page.query_selector('button:has-text("Login"), button[type="submit"]')
echo             if btn: await btn.click()
echo             else: await page.keyboard.press("Enter")
echo             await asyncio.sleep(3)
echo.
echo         for sel in ['a:has-text("Assignments")', 'a:has-text("Activities")', 'a:has-text("Homework")', 'a:has-text("To Do")']:
echo             try: el = await page.query_selector(sel)
echo             except: el = None
echo             if el: await el.click(); await asyncio.sleep(human_delay(2, 4)); break
echo.
echo         for i in range(10):
echo             await asyncio.sleep(1)
echo             if (i+1) % 3 == 0: await status_callback(f"Discover - Capturing... ({i+1}/10s, {len(captured['endpoints'])} endpoints)")
echo.
echo         endpoints = sorted(captured["endpoints"])
echo         out = {"endpoints": endpoints, "token": captured.get("token",""), "base_url": config.login_url, "region": config.region, "captured_at": datetime.now().isoformat()}
echo         with open(DISCOVERED_FILE, "w") as f: json.dump(out, f, indent=2)
echo         await browser.close()
echo.
echo     await status_callback(f"Discover Complete! Endpoints: {len(endpoints)}, Token: {'Yes' if captured['token'] else 'No'}")
echo     await complete_callback({"endpoints": len(endpoints), "token_found": bool(captured['token']), "mode": "discover"})
echo     logger.info(f"[Discover] User {discord_id} found {len(endpoints)} endpoints")
) > automation\discover.py

REM automation\api_direct.py
(
echo import asyncio
echo import json
echo import random
echo import requests as req
echo from config import get_config, DATA_DIR
echo from utils.logger import logger
echo from utils.helpers import accuracy_for_run, human_delay
echo.
echo DISCOVERED_FILE = DATA_DIR / "discovered_endpoints.json"
echo.
echo async def run_api(discord_id, status_callback, complete_callback):
echo     config = get_config(discord_id)
echo     if not config.has_credentials:
echo         await status_callback("Credentials not set!")
echo         return
echo.
echo     acc = accuracy_for_run(config["accuracy_min"], config["accuracy_max"])
echo     await status_callback(f"API Direct - Authenticating...")
echo.
echo     session = req.Session()
echo     session.headers.update({"User-Agent": config["user_agent"], "Accept": "application/json, text/plain, */*", "Accept-Language": config["fake_locale"].replace("_","-"), "Connection": "keep-alive"})
echo.
echo     token = None
echo     if DISCOVERED_FILE.exists():
echo         with open(DISCOVERED_FILE) as f: token = json.load(f).get("token", "")
echo.
echo     for base in ["https://api.languagenut.com"]:
echo         for path in ["/auth/login", "/api/v1/auth/login"]:
echo             try:
echo                 resp = session.post(f"{base}{path}", json={"username": config["username"], "password": config["password"]}, timeout=15)
echo                 if resp.status_code == 200:
echo                     data = resp.json()
echo                     for k in ["token","accessToken","access_token","jwt","idToken"]:
echo                         if k in data: token = data[k]; break
echo                     if not token and "data" in data and isinstance(data["data"], dict):
echo                         for k in ["token","accessToken","jwt"]:
echo                             if k in data["data"]: token = data["data"][k]; break
echo                     if token: break
echo             except: continue
echo         if token: break
echo.
echo     if not token:
echo         await status_callback("API Direct - Login failed. Try /discover or /stealth.")
echo         return
echo.
echo     session.headers.update({"Authorization": f"Bearer {token}"})
echo     total = 0
echo.
echo     for base in ["https://api.languagenut.com"]:
echo         for path in ["/activities", "/api/v1/activities", "/questions", "/api/v1/questions"]:
echo             try:
echo                 resp = session.get(f"{base}{path}", timeout=15)
echo                 if resp.status_code != 200: continue
echo                 questions = resp.json()
echo                 if isinstance(questions, dict):
echo                     for k in ["data","questions","activities","items","results"]:
echo                         if k in questions and isinstance(questions[k], list): questions = questions[k]; break
echo                 if not isinstance(questions, list) or not questions: continue
echo.
echo                 for i, q in enumerate(questions[:config["max_questions"]]):
echo                     qid = q.get("id") or q.get("questionId") or q.get("_id") or str(i)
echo                     correct = random.random() < acc
echo                     payload = {"questionId": qid, "answer": "correct" if correct else "wrong", "correct": correct, "timeSpent": random.randint(int(config["think_delay_min"]*1000), int(config["think_delay_max"]*1000))}
echo                     for ep in [f"{base}{path}/submit", f"{base}{path}/answer", f"{base}/{qid}/submit"]:
echo                         try:
echo                             sr = session.post(ep, json=payload, timeout=10)
echo                             if sr.status_code in (200, 201, 204): total += 1; break
echo                         except: continue
echo                     if (i+1) % 25 == 0: await status_callback(f"API Direct - {i+1}/{len(questions)}... ({total} submitted)")
echo                     await asyncio.sleep(human_delay(0.2, 0.8))
echo.
echo                 if total > 0:
echo                     await status_callback(f"API Direct Complete! Answered: {total}")
echo                     await complete_callback({"answered": total, "accuracy": round(acc*100, 1), "mode": "api"})
echo                     logger.info(f"[API] User {discord_id} answered {total} questions")
echo                     return
echo             except: continue
echo.
echo     await status_callback("API Direct - No questions found. Try /stealth.")
) > automation\api_direct.py

REM commands\__init__.py
(
echo from .core import setup_core_commands
echo from .settings import setup_settings_commands
echo from .profiles import setup_profile_commands
echo from .backup import setup_backup_commands
) > commands\__init__.py

REM commands\core.py
(
echo import asyncio
echo import discord
echo from discord import app_commands, ui, ButtonStyle, Interaction
echo from discord.ext import commands
echo from config import OWNER_ID, LOG_CHANNEL_ID
echo from utils.logger import logger
echo from automation import run_stealth, run_discover, run_api
echo.
echo def has_permission(interaction: Interaction) -^> bool:
echo     if not OWNER_ID: return True
echo     return str(interaction.user.id) == OWNER_ID
echo.
echo class ModeSelectView(ui.View):
echo     def __init__(self): super().__init__(timeout=300)
echo.
echo     @ui.button(label="Stealth Browser", style=ButtonStyle.primary, row=0)
echo     async def stealth_btn(self, interaction: Interaction, btn: ui.Button):
echo         if not has_permission(interaction): await interaction.response.send_message("No permission.", ephemeral=True); return
echo         await interaction.response.send_message("Starting Stealth Browser mode...", ephemeral=True)
echo         asyncio.create_task(_run_stealth_for(interaction))
echo.
echo     @ui.button(label="API Direct", style=ButtonStyle.success, row=0)
echo     async def api_btn(self, interaction: Interaction, btn: ui.Button):
echo         if not has_permission(interaction): await interaction.response.send_message("No permission.", ephemeral=True); return
echo         await interaction.response.send_message("Starting API Direct mode...", ephemeral=True)
echo         asyncio.create_task(_run_api_for(interaction))
echo.
echo     @ui.button(label="Discover", style=ButtonStyle.secondary, row=0)
echo     async def discover_btn(self, interaction: Interaction, btn: ui.Button):
echo         if not has_permission(interaction): await interaction.response.send_message("No permission.", ephemeral=True); return
echo         await interaction.response.send_message("Starting Discover mode...", ephemeral=True)
echo         asyncio.create_task(_run_discover_for(interaction))
echo.
echo     @ui.button(label="Settings", style=ButtonStyle.gray, row=1)
echo     async def settings_btn(self, interaction: Interaction, btn: ui.Button):
echo         if not has_permission(interaction): await interaction.response.send_message("No permission.", ephemeral=True); return
echo         from commands.settings import SettingsCategoryView
echo         await interaction.response.send_message(embed=discord.Embed(title="Settings", description="Choose a category:"), view=SettingsCategoryView(), ephemeral=True)
echo.
echo     @ui.button(label="Status", style=ButtonStyle.green, row=1)
echo     async def status_btn(self, interaction: Interaction, btn: ui.Button):
echo         if not has_permission(interaction): await interaction.response.send_message("No permission.", ephemeral=True); return
echo         config = get_config(str(interaction.user.id))
echo         embed = discord.Embed(title="Your Status", description=f"Username: {config['username'] or 'Not set'} | Has password: {'Yes' if config.has_credentials else 'No'}", color=0x4488ff)
echo         embed.add_field(name="Accuracy", value=f"{config['accuracy_min']*100:.0f}% - {config['accuracy_max']*100:.0f}%")
echo         embed.add_field(name="Think Delay", value=f"{config['think_delay_min']}s - {config['think_delay_max']}s")
echo         await interaction.response.send_message(embed=embed, ephemeral=True)
echo.
echo async def _run_stealth_for(interaction):
echo     msg = await interaction.original_response()
echo     async def scb(t):
echo         try: await msg.edit(content=t)
echo         except: pass
echo     async def ccb(r):
echo         embed = discord.Embed(title="Run Complete", description=f"Mode: Stealth | Answered: {r['answered']} | Accuracy: {r['accuracy']}%", color=0x00ff88)
echo         try: await msg.edit(content=None, embed=embed)
echo         except: pass
echo     await run_stealth(str(interaction.user.id), scb, ccb)
echo.
echo async def _run_api_for(interaction):
echo     msg = await interaction.original_response()
echo     async def scb(t):
echo         try: await msg.edit(content=t)
echo         except: pass
echo     async def ccb(r):
echo         embed = discord.Embed(title="Run Complete", description=f"Mode: API | Answered: {r['answered']} | Accuracy: {r['accuracy']}%", color=0x00ff88)
echo         try: await msg.edit(content=None, embed=embed)
echo         except: pass
echo     await run_api(str(interaction.user.id), scb, ccb)
echo.
echo async def _run_discover_for(interaction):
echo     msg = await interaction.original_response()
echo     async def scb(t):
echo         try: await msg.edit(content=t)
echo         except: pass
echo     async def ccb(r):
echo         embed = discord.Embed(title="Discover Complete", description=f"Endpoints: {r['endpoints']} | Token: {'Captured' if r['token_found'] else 'Not found'}", color=0x4488ff)
echo         try: await msg.edit(content=None, embed=embed)
echo         except: pass
echo     await run_discover(str(interaction.user.id), scb, ccb)
echo.
echo def setup_core_commands(bot):
echo     @bot.tree.command(name="start", description="Open the main control panel")
echo     async def start_cmd(interaction: Interaction):
echo         if not has_permission(interaction): await interaction.response.send_message("No permission.", ephemeral=True); return
echo         await interaction.response.send_message(embed=discord.Embed(title="LanguageNut Bot", description="Choose a mode:"), view=ModeSelectView())
echo.
echo     @bot.tree.command(name="stealth", description="Run Stealth Browser mode")
echo     async def stealth_cmd(interaction: Interaction):
echo         if not has_permission(interaction): await interaction.response.send_message("No permission.", ephemeral=True); return
echo         await interaction.response.send_message("Starting Stealth mode...", ephemeral=True)
echo         asyncio.create_task(_run_stealth_for(interaction))
echo.
echo     @bot.tree.command(name="api", description="Run API Direct mode")
echo     async def api_cmd(interaction: Interaction):
echo         if not has_permission(interaction): await interaction.response.send_message("No permission.", ephemeral=True); return
echo         await interaction.response.send_message("Starting API Direct mode...", ephemeral=True)
echo         asyncio.create_task(_run_api_for(interaction))
echo.
echo     @bot.tree.command(name="discover", description="Map API endpoints")
echo     async def discover_cmd(interaction: Interaction):
echo         if not has_permission(interaction): await interaction.response.send_message("No permission.", ephemeral=True); return
echo         await interaction.response.send_message("Starting Discover...", ephemeral=True)
echo         asyncio.create_task(_run_discover_for(interaction))
echo     logger.info("Core commands registered")
) > commands\core.py

REM commands\settings.py
(
echo import discord
echo from discord import ui, ButtonStyle, Interaction
echo from discord.ext import commands
echo from config import get_config
echo from utils.logger import logger
echo.
echo VALID_KEYS = ["username","password","region","accuracy_min","accuracy_max","think_delay_min","think_delay_max","type_speed_min","type_speed_max","activity_delay_min","activity_delay_max","fake_time_enabled","fake_timezone","fake_time_mode","fake_geolocation_enabled","fake_latitude","fake_longitude","fake_locale","viewport_width","viewport_height","user_agent","headless","max_questions","max_assignments"]
echo.
echo class SettingsCategoryView(ui.View):
echo     def __init__(self): super().__init__(timeout=120)
echo.
echo     @ui.button(label="Account", style=ButtonStyle.blurple, row=0)
echo     async def acct_btn(self, interaction, btn):
echo         c = get_config(str(interaction.user.id))
echo         await interaction.response.edit_message(embed=discord.Embed(title="Account", description=f"Username: {c['username'] or 'Not set'}\nRegion: {c.region}", color=0x4488ff), view=BackView())
echo.
echo     @ui.button(label="Accuracy", style=ButtonStyle.success, row=0)
echo     async def acc_btn(self, interaction, btn):
echo         c = get_config(str(interaction.user.id))
echo         await interaction.response.edit_message(embed=discord.Embed(title="Accuracy", description=f"Range: {c['accuracy_min']*100:.0f}% - {c['accuracy_max']*100:.0f}%", color=0x00ff88), view=BackView())
echo.
echo     @ui.button(label="Timing", style=ButtonStyle.gold, row=0)
echo     async def time_btn(self, interaction, btn):
echo         c = get_config(str(interaction.user.id))
echo         await interaction.response.edit_message(embed=discord.Embed(title="Timing", description=f"Think: {c['think_delay_min']}s - {c['think_delay_max']}s\nType: {c['type_speed_min']}ms - {c['type_speed_max']}ms", color=0x00ff88), view=BackView())
echo.
echo     @ui.button(label="Anti-Detect", style=ButtonStyle.gray, row=1)
echo     async def anti_btn(self, interaction, btn):
echo         c = get_config(str(interaction.user.id))
echo         await interaction.response.edit_message(embed=discord.Embed(title="Anti-Detect", description=f"Fake time: {'ON' if c['fake_time_enabled'] else 'OFF'}\nGeo: {'ON' if c['fake_geolocation_enabled'] else 'OFF'}\nLocale: {c['fake_locale']}", color=0x4488ff), view=BackView())
echo.
echo     @ui.button(label="Browser", style=ButtonStyle.secondary, row=1)
echo     async def browser_btn(self, interaction, btn):
echo         c = get_config(str(interaction.user.id))
echo         await interaction.response.edit_message(embed=discord.Embed(title="Browser", description=f"Headless: {c['headless']}\nViewport: {c['viewport_width']}x{c['viewport_height']}\nMax Q: {c['max_questions']}", color=0x4488ff), view=BackView())
echo.
echo class BackView(ui.View):
echo     def __init__(self): super().__init__(timeout=120)
echo     @ui.button(label="Back", style=ButtonStyle.gray)
echo     async def back_btn(self, interaction, btn):
echo         await interaction.response.edit_message(embed=discord.Embed(title="Settings", description="Choose a category:"), view=SettingsCategoryView())
echo.
echo def setup_settings_commands(bot):
echo     from discord import app_commands
echo.
echo     @bot.tree.command(name="set", description="Set a configuration value")
echo     @app_commands.describe(key="Setting key", value="Value to set")
echo     async def set_cmd(interaction: Interaction, key: str, value: str):
echo         key = key.lower()
echo         if key not in VALID_KEYS:
echo             await interaction.response.send_message(f"Invalid key. Valid: {', '.join(VALID_KEYS)}", ephemeral=True)
echo             return
echo         config = get_config(str(interaction.user.id))
echo         if key in ("accuracy_min","accuracy_max","think_delay_min","think_delay_max","activity_delay_min","activity_delay_max","fake_latitude","fake_longitude"):
echo             try: value = float(value)
echo             except: await interaction.response.send_message("Must be a number.", ephemeral=True); return
echo         elif key in ("viewport_width","viewport_height","type_speed_min","type_speed_max","max_questions","max_assignments"):
echo             try: value = int(value)
echo             except: await interaction.response.send_message("Must be an integer.", ephemeral=True); return
echo         elif key in ("fake_time_enabled","fake_geolocation_enabled","headless"):
echo             v = value.lower()
echo             if v in ("true","1","yes","on"): value = True
echo             elif v in ("false","0","no","off"): value = False
echo             else: await interaction.response.send_message("Must be true/false.", ephemeral=True); return
echo         config[key] = value
echo         await interaction.response.send_message(embed=discord.Embed(title="Updated", description=f"{key} = {config[key]}", color=0x00ff88), ephemeral=True)
echo.
echo     @bot.tree.command(name="status", description="View your configuration")
echo     async def status_cmd(interaction: Interaction):
echo         config = get_config(str(interaction.user.id))
echo         embed = discord.Embed(title="Your Config", description=f"Username: {config['username'] or 'Not set'}\nRegion: {config.region}\nPassword: {'Yes' if config.has_credentials else 'No'}", color=0x4488ff)
echo         embed.add_field(name="Accuracy", value=f"{config['accuracy_min']*100:.0f}% - {config['accuracy_max']*100:.0f}%")
echo         embed.add_field(name="Think Delay", value=f"{config['think_delay_min']}s - {config['think_delay_max']}s")
echo         embed.add_field(name="Anti-Detect", value=f"Time: {'ON' if config['fake_time_enabled'] else 'OFF'}\nGeo: {'ON' if config['fake_geolocation_enabled'] else 'OFF'}")
echo         await interaction.response.send_message(embed=embed, ephemeral=True)
echo.
echo     @bot.tree.command(name="reset", description="Reset all settings")
echo     async def reset_cmd(interaction: Interaction):
echo         get_config(str(interaction.user.id)).delete()
echo         await interaction.response.send_message(embed=discord.Embed(title="Reset", description="Settings reset to defaults.", color=0xffaa00), ephemeral=True)
echo     logger.info("Settings commands registered")
) > commands\settings.py

REM commands\profiles.py
(
echo import discord
echo from discord import ui, ButtonStyle, Interaction
echo from discord.ext import commands
echo from config import get_config
echo from utils.logger import logger
echo.
echo class ProfileSelectView(ui.View):
echo     def __init__(self): super().__init__(timeout=120)
echo.
echo     @ui.button(label="New Profile", style=ButtonStyle.success, row=0)
echo     async def new_btn(self, interaction, btn):
echo         config = get_config(str(interaction.user.id))
echo         config["username"] = ""; config["password_encrypted"] = ""
echo         config["created_at"] = __import__("datetime").datetime.now().isoformat()
echo         config.save()
echo         await interaction.response.edit_message(embed=discord.Embed(title="Profile Created", description="Set credentials with /set username and /set password", color=0x00ff88), view=None)
echo.
echo     @ui.button(label="View Profile", style=ButtonStyle.blurple, row=0)
echo     async def view_btn(self, interaction, btn):
echo         config = get_config(str(interaction.user.id))
echo         embed = discord.Embed(title="Your Profile", description=f"Username: {config['username'] or 'Not set'}\nRegion: {config.region}", color=0x4488ff)
echo         embed.add_field(name="Accuracy", value=f"{config['accuracy_min']*100:.0f}% - {config['accuracy_max']*100:.0f}%")
echo         embed.add_field(name="Anti-Detect", value=f"Time: {'ON' if config['fake_time_enabled'] else 'OFF'}\nGeo: {'ON' if config['fake_geolocation_enabled'] else 'OFF'}")
echo         await interaction.response.edit_message(embed=embed, view=self)
echo.
echo     @ui.button(label="Delete Profile", style=ButtonStyle.danger, row=1)
echo     async def del_btn(self, interaction, btn):
echo         get_config(str(interaction.user.id)).delete()
echo         await interaction.response.edit_message(embed=discord.Embed(title="Deleted", description="Profile removed.", color=0xff4444), view=None)
echo.
echo def setup_profile_commands(bot):
echo     @bot.tree.command(name="profile", description="Manage your profile")
echo     async def profile_cmd(interaction: Interaction):
echo         await interaction.response.send_message(embed=discord.Embed(title="Profile", description="Manage your settings:"), view=ProfileSelectView(), ephemeral=True)
echo.
echo     @bot.tree.command(name="deleteprofile", description="Delete your profile")
echo     async def deleteprofile_cmd(interaction: Interaction):
echo         get_config(str(interaction.user.id)).delete()
echo         await interaction.response.send_message(embed=discord.Embed(title="Deleted", description="Profile removed.", color=0xff4444), ephemeral=True)
echo     logger.info("Profile commands registered")
) > commands\profiles.py

REM commands\backup.py
(
echo import json
echo import base64
echo import io
echo from datetime import datetime
echo import discord
echo from discord import app_commands, ui, ButtonStyle, Interaction
echo from discord.ext import commands
echo from config import get_config
echo from utils.logger import logger
echo.
echo def setup_backup_commands(bot):
echo     @bot.tree.command(name="backup", description="Create a backup of your data")
echo     async def backup_cmd(interaction: Interaction):
echo         config = get_config(str(interaction.user.id))
echo         data = {"discord_id": str(interaction.user.id), "username": config["username"], "backup_date": datetime.now().isoformat(), "settings": dict(config.data)}
echo         b64 = base64.b64encode(json.dumps(data).encode()).decode()
echo         await interaction.response.send_message(embed=discord.Embed(title="Backup Created", description=f"User: {data['username'] or 'Not set'}", color=0x4488ff), ephemeral=True)
echo         await interaction.followup.send(f"Backup data:\n{b64[:1900]}", ephemeral=True)
echo.
echo     @bot.tree.command(name="loadbackup", description="Restore from backup")
echo     @app_commands.describe(backup_data="The backup string")
echo     async def loadbackup_cmd(interaction: Interaction, backup_data: str):
echo         try:
echo             decoded = base64.b64decode(backup_data).decode()
echo             data = json.loads(decoded)
echo         except:
echo             await interaction.response.send_message("Invalid backup data.", ephemeral=True); return
echo         if data.get("discord_id") != str(interaction.user.id):
echo             await interaction.response.send_message("This backup belongs to another user.", ephemeral=True); return
echo         config = get_config(str(interaction.user.id))
echo         for k, v in data.get("settings", {}).items():
echo             if k in config.data: config.data[k] = v
echo         config.save()
echo         await interaction.response.send_message(embed=discord.Embed(title="Restored", description="Backup loaded.", color=0x00ff88), ephemeral=True)
echo.
echo     @bot.tree.command(name="export", description="Export settings as JSON")
echo     async def export_cmd(interaction: Interaction):
echo         config = get_config(str(interaction.user.id))
echo         export = {"discord_id": str(interaction.user.id), "export_date": datetime.now().isoformat(), "username": config["username"], "settings": config.to_dict(show_password=True)}
echo         await interaction.response.send_message(content="Settings Export", file=discord.File(io.BytesIO(json.dumps(export, indent=2).encode()), filename=f"ln_bot_backup_{interaction.user.id}.json"), ephemeral=True)
echo.
echo     @bot.tree.command(name="import", description="Import settings from JSON")
echo     async def import_cmd(interaction: Interaction, attachment: discord.Attachment):
echo         if not attachment.filename.endswith(".json"):
echo             await interaction.response.send_message("Upload a .json file.", ephemeral=True); return
echo         try: data = json.loads((await attachment.read()).decode())
echo         except: await interaction.response.send_message("Invalid JSON.", ephemeral=True); return
echo         config = get_config(str(interaction.user.id))
echo         settings = data.get("settings", data)
echo         count = 0
echo         for k, v in settings.items():
echo             if k in config.data and k not in ("discord_id","created_at"): config.data[k] = v; count += 1
echo         config.save()
echo         await interaction.response.send_message(embed=discord.Embed(title="Imported", description=f"Imported {count} settings.", color=0x00ff88), ephemeral=True)
echo     logger.info("Backup commands registered")
) > commands\backup.py

REM ========== CREATE main.py ==========
(
echo #!/usr/bin/env python3
echo import asyncio
echo import sys
echo import discord
echo from discord.ext import commands
echo from config import DISCORD_TOKEN, OWNER_ID
echo from utils.logger import logger
echo from commands.core import setup_core_commands
echo from commands.settings import setup_settings_commands
echo from commands.profiles import setup_profile_commands
echo from commands.backup import setup_backup_commands
echo.
echo class LanguageNutBot(commands.Bot):
echo     def __init__(self):
echo         intents = discord.Intents.default()
echo         intents.message_content = True
echo         super().__init__(command_prefix="ln!", intents=intents, application_id=1500541510440190043)
echo.
echo     async def setup_hook(self):
echo         logger.info("Registering commands...")
echo         setup_core_commands(self)
echo         setup_settings_commands(self)
echo         setup_profile_commands(self)
echo         setup_backup_commands(self)
echo         try:
echo             synced = await self.tree.sync()
echo             logger.info(f"Synced {len(synced)} commands: {[c.name for c in synced]}")
echo         except Exception as e:
echo             logger.error(f"Sync failed: {e}")
echo.
echo     async def on_ready(self):
echo         logger.info(f"Bot online as {self.user}")
echo         await self.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name="/start | LN Bot"))
echo.
echo async def main():
echo     if not DISCORD_TOKEN:
echo         logger.error("DISCORD_TOKEN not set! Create .env file.")
echo         sys.exit(1)
echo     bot = LanguageNutBot()
echo     try: await bot.start(DISCORD_TOKEN)
echo     except discord.errors.LoginFailure:
echo         logger.error("Invalid token! Reset at https://discord.com/developers/applications")
echo         sys.exit(1)
echo     except KeyboardInterrupt: logger.info("Shutting down...")
echo     finally:
echo         if not bot.is_closed(): await bot.close()
echo.
echo if __name__ == "__main__":
echo     asyncio.run(main())
) > main.py

REM ========== INSTALL DEPENDENCIES ==========
echo [8/8] Installing Python dependencies...
python -m pip install -r requirements.txt

echo.
echo ============================================
echo   Setup Complete!
echo ============================================
echo.
echo Next steps:
echo   1. Edit .env - set your DISCORD_TOKEN and ENCRYPTION_KEY
echo   2. Generate key: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
echo   3. Run bot: python main.py
echo.
pause