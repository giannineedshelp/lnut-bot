@echo off
cd /d "%~dp0In_bot"
echo Installing/checking dependencies...
pip install -r requirements.txt --quiet
echo Starting LanguageNut bot...
python main.py
pause
