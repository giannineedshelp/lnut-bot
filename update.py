"""
One-click update grabber for LanguageNut Bot.

Run this to pull the latest code from GitHub and reinstall deps:
    python update.py

Works on Windows, Termux (Android / phone), Mac, Linux.
"""

import os
import subprocess
import sys
from pathlib import Path


def main():
    FILE_DIR = Path(__file__).resolve().parent
    os.chdir(str(FILE_DIR))

    print("=" * 50)
    print("  LanguageNut Bot - Updater")
    print("=" * 50)

    # 1. Git pull
    print("\n[1/2] Pulling latest code from GitHub...")
    try:
        result = subprocess.run(
            ["git", "pull"],
            capture_output=True, text=True, timeout=30,
        )
        print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip())
        if result.returncode == 0:
            print("  ✓ Update complete!")
        else:
            print("  ! Git pull had warnings (non-fatal)")
    except FileNotFoundError:
        print("  ! git not found - install git or download manually")
        print("    https://github.com/giannineedshelp/lnut-bot")
    except subprocess.TimeoutExpired:
        print("  ! git pull timed out - check your connection")

    # 2. Install deps
    print("\n[2/2] Installing Python dependencies...")
    pip = "pip" if sys.platform != "linux" or "termux" not in str(FILE_DIR).lower() else "pip"
    try:
        result = subprocess.run(
            [pip, "install", "-r", "requirements.txt", "--quiet"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            print("  ✓ Dependencies installed")
        else:
            print(f"  ! pip had issues:\n{result.stderr.strip()[:500]}")
    except FileNotFoundError:
        try:
            subprocess.run(
                ["pip3", "install", "-r", "requirements.txt", "--quiet"],
                capture_output=True, text=True, timeout=60,
            )
            print("  ✓ Dependencies installed (via pip3)")
        except FileNotFoundError:
            print("  ! pip not found - install Python first")

    print("\n" + "=" * 50)
    print("  Done! Run the bot with:")
    print("    Windows: double-click run.bat")
    print("    Phone:   bash run.sh")
    print("=" * 50)


if __name__ == "__main__":
    main()

