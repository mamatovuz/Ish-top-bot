import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Vakansiyalar chop etiladigan ochiq kanal
PUBLIC_CHANNEL_ID = os.getenv("PUBLIC_CHANNEL_ID", "").strip()

# Ishga arizalar (nomzodlar) yuboriladigan maxfiy kanal
PRIVATE_CHANNEL_ID = os.getenv("PRIVATE_CHANNEL_ID", "-1003857564562").strip()

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "data/bot.sqlite3"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "backups"))

# ── DoriKent Test Bot integratsiyasi ────────────────────────────────────────
# 2-bot (bu bot) faqat HTTP/HTTPS API orqali DoriKent Test Bot bilan ishlaydi.
# Hech qachon DoriKent botning DB fayliga to'g'ridan-to'g'ri ulanmaydi.

# DoriKent Test API bazaviy manzili, masalan: https://test.example.uz
DORIKENT_TEST_API_URL = os.getenv("DORIKENT_TEST_API_URL", "").strip().rstrip("/")

# DoriKent API ga so'rov yuborishda ishlatiladigan maxfiy kalit (Bearer token)
DORIKENT_TEST_API_SECRET = os.getenv("DORIKENT_TEST_API_SECRET", "").strip()

# Deep-link yasash uchun DoriKent Test Bot username (masalan: DoriKentTestBot)
DORIKENT_TEST_BOT_USERNAME = os.getenv("DORIKENT_TEST_BOT_USERNAME", "").strip().lstrip("@")

# DoriKent natijani bizga qaytarganda tekshiriladigan maxfiy kalit (Bearer token)
TEST_RESULT_API_SECRET = os.getenv("TEST_RESULT_API_SECRET", "").strip()

# Natija (result) API server tinglaydigan host va port
RESULT_API_HOST = os.getenv("RESULT_API_HOST", "0.0.0.0").strip()
RESULT_API_PORT = int(os.getenv("RESULT_API_PORT", os.getenv("PORT", "8080")) or "8080")

# DoriKent API so'rovlari uchun timeout (soniya)
DORIKENT_TEST_API_TIMEOUT = float(os.getenv("DORIKENT_TEST_API_TIMEOUT", "15") or "15")

# Test natijalari e'lon qilinadigan kanal (bo'sh bo'lsa — maxfiy kanalga tushadi)
TEST_RESULT_CHANNEL_ID = os.getenv("TEST_RESULT_CHANNEL_ID", "").strip() or PRIVATE_CHANNEL_ID


def dorikent_integration_enabled() -> bool:
    """Test integratsiyasi to'liq sozlanganmi (URL + secret bor)."""
    return bool(DORIKENT_TEST_API_URL and DORIKENT_TEST_API_SECRET)


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