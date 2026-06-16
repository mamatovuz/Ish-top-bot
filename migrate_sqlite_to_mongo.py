"""Eski SQLite bazasidagi ma'lumotlarni MongoDB ga bir martalik ko'chirish skripti.

Ishlatish:
    python migrate_sqlite_to_mongo.py

Bu skript SQLite (data/bot.sqlite3) dagi barcha jadvallarni o'qib,
MongoDB ga (config.py dagi MONGO_URI) ko'chiradi. `id` qiymatlari saqlanadi
va counterlar to'g'rilanadi. Mavjud yozuvlar `id` bo'yicha ustiga yoziladi.
"""

import sqlite3
import sys
from pathlib import Path

from config import DATABASE_PATH
from database import db

TABLES = [
    "settings", "users", "admins", "channels", "professions", "seekers",
    "employers", "vacancies", "interests", "candidate_actions",
    "admin_logs", "moderation_messages",
]


def main() -> None:
    if not Path(DATABASE_PATH).exists():
        print(f"SQLite fayl topilmadi: {DATABASE_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row

    existing = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    total = 0
    for table in TABLES:
        if table not in existing:
            print(f"  - {table}: jadval yo'q, o'tkazib yuborildi")
            continue

        rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]
        if not rows:
            print(f"  - {table}: 0 ta yozuv")
            continue

        coll = db.db[table]
        moved = 0
        for row in rows:
            if table == "settings":
                # settings da id yo'q, key bo'yicha upsert
                db.set_setting(row["key"], row["value"])
                moved += 1
                continue
            row_id = row.get("id")
            if row_id is None:
                coll.insert_one(row)
            else:
                coll.replace_one({"id": row_id}, row, upsert=True)
            moved += 1
        total += moved
        print(f"  - {table}: {moved} ta yozuv ko'chirildi")

        # counterni to'g'rilash
        if table != "settings":
            db._sync_counter(table)

    conn.close()
    print(f"\n✅ Migratsiya tugadi. Jami {total} ta yozuv MongoDB ga ko'chirildi.")
    print("Dashboard:", db.dashboard_counts())


if __name__ == "__main__":
    main()
