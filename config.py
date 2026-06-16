import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Vakansiyalar chop etiladigan ochiq kanal
PUBLIC_CHANNEL_ID = os.getenv("PUBLIC_CHANNEL_ID", "").strip()

# Ishga arizalar (nomzodlar) yuboriladigan maxfiy kanal
PRIVATE_CHANNEL_ID = os.getenv("PRIVATE_CHANNEL_ID", "-1004372898211").strip()

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/bot.sqlite3"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "backups"))


def _parse_admin_ids(raw: str) -> set[int]:
    result: set[int] = set()
    for item in raw.replace(";", ",").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.add(int(item))
        except ValueError:
            continue
    return result


ADMIN_IDS = _parse_admin_ids(os.getenv("ADMIN_IDS", ""))


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS