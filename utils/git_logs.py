from git import Repo
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
repo = Repo(BASE_DIR)

def get_recent_commits(limit=10):
    commits = list(repo.iter_commits("main", max_count=limit))

    logs = []

    for c in commits:
        logs.append({
            "message": c.message.strip(),
            "author": c.author.name,
            "date": datetime.fromtimestamp(c.committed_date),
            "hash": c.hexsha[:7],
        })

    return logs