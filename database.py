"""MongoDB ga asoslangan ma'lumotlar bazasi qatlami.

Eski SQLite versiyasi `database_sqlite_backup.py` faylida saqlangan.
Barcha metod imzolari avvalgidek qoldirilgan, shuning uchun `main.py` o'zgartirilmaydi.
Yozuvlar oddiy `dict` ko'rinishida qaytariladi (avvalgi `sqlite3.Row` o'rniga) —
`row_get()` va `row["..."]` ikkalasi ham ishlaydi.
"""

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument

from config import BACKUP_DIR, MONGO_DB_NAME, MONGO_URI


DEFAULT_PROFESSIONS = ("Dasturchi", "Operator", "Sotuvchi", "Dizayner")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def days_from_now_iso(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds")


def _regex(value: str) -> dict[str, Any]:
    """SQLitedagi `LIKE %x%` ga mos keluvchi, registrga sezgir bo'lmagan regex."""
    return {"$regex": re.escape(value), "$options": "i"}


# Har bir kolleksiya uchun maydonlar va ularning standart qiymatlari.
# Bu SQLite ustunlaridagi NULL larni taqlid qiladi: qaytarilgan dict da
# har doim barcha maydonlar mavjud bo'ladi, shunda `row["field"]` xato bermaydi.
_DEFAULTS: dict[str, dict[str, Any]] = {
    "users": {
        "tg_id": None, "username": None, "full_name": None, "role": None,
        "created_at": None, "updated_at": None,
    },
    "admins": {"tg_id": None, "added_by": None, "created_at": None},
    "channels": {"title": None, "chat_id": None, "invite_link": None, "created_at": None},
    "professions": {"title": None, "is_active": 1, "created_at": None},
    "seekers": {
        "telegram_id": None, "photo_id": None, "full_name": None, "age": None,
        "gender": None, "phone": None, "region": None, "district": None, "address": None,
        "birth_date": None, "profession_id": None, "profession_title": None,
        "job_type": None, "experience": None, "experience_years": None,
        "education": None, "excel_level": None, "word_level": None,
        "previous_job": None, "previous_salary": None, "previous_salary_amount": None,
        "current_salary": None, "current_salary_amount": None, "salary": None,
        "salary_amount": None, "extra": None, "resume_file_id": None,
        "resume_file_name": None, "moderation_status": "pending", "moderation_note": None,
        "moderated_by": None, "approved_at": None, "published_at": None,
        "channel_chat_id": None, "channel_message_id": None,
        "created_at": None, "updated_at": None,
    },
    "employers": {
        "telegram_id": None, "full_name": None, "organization": None, "phone": None,
        "region": None, "district": None, "created_at": None, "updated_at": None,
    },
    "vacancies": {
        "employer_tg_id": None, "full_name": None, "organization": None, "phone": None,
        "region": None, "district": None, "profession_id": None, "profession_title": None,
        "staff_count": None, "job_type": None, "salary": None, "salary_amount": None,
        "min_experience_years": None, "requirements": None, "active": 1,
        "moderation_status": "pending", "moderation_note": None, "moderated_by": None,
        "approved_at": None, "published_at": None, "channel_chat_id": None,
        "channel_message_id": None, "expires_at": None,
        "created_at": None, "updated_at": None,
    },
    "interests": {
        "vacancy_id": None, "seeker_id": None, "employer_tg_id": None,
        "seeker_tg_id": None, "status": "pending", "created_at": None, "updated_at": None,
    },
    "candidate_actions": {
        "employer_tg_id": None, "vacancy_id": None, "seeker_id": None,
        "status": None, "created_at": None, "updated_at": None,
    },
    "admin_logs": {
        "admin_tg_id": None, "action": None, "target_type": None,
        "target_id": None, "details": None, "created_at": None,
    },
    "moderation_messages": {
        "item_type": None, "item_id": None, "admin_tg_id": None,
        "chat_id": None, "message_id": None, "created_at": None,
    },
}

_BACKUP_COLLECTIONS = (
    "settings", "users", "admins", "channels", "professions", "seekers",
    "employers", "vacancies", "interests", "candidate_actions",
    "admin_logs", "moderation_messages", "counters",
)


class Database:
    def __init__(self, uri: str = MONGO_URI, db_name: str = MONGO_DB_NAME) -> None:
        self.backup_dir = BACKUP_DIR
        self.client: MongoClient = MongoClient(uri, serverSelectionTimeoutMS=10000)
        self.db = self.client[db_name]

    # ------------------------------------------------------------------
    # Yordamchi metodlar
    # ------------------------------------------------------------------
    def _clean(self, doc: dict[str, Any] | None, collection: str | None = None) -> dict[str, Any] | None:
        """`_id` ni olib tashlaydi va yetishmayotgan maydonlarni standart qiymat bilan to'ldiradi."""
        if doc is None:
            return None
        doc = dict(doc)
        doc.pop("_id", None)
        if collection and collection in _DEFAULTS:
            for key, default in _DEFAULTS[collection].items():
                doc.setdefault(key, default)
        return doc

    def _clean_list(self, cursor, collection: str | None = None) -> list[dict[str, Any]]:
        return [self._clean(doc, collection) for doc in cursor]

    def _next_id(self, name: str) -> int:
        doc = self.db.counters.find_one_and_update(
            {"_id": name},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int(doc["seq"])

    def _sync_counter(self, name: str) -> None:
        """Mavjud eng katta `id` ga qarab counterni to'g'rilaydi (import qilingandan keyin)."""
        top = self.db[name].find_one(sort=[("id", DESCENDING)])
        max_id = int(top["id"]) if top and top.get("id") is not None else 0
        current = self.db.counters.find_one({"_id": name})
        if not current or int(current.get("seq", 0)) < max_id:
            self.db.counters.update_one({"_id": name}, {"$set": {"seq": max_id}}, upsert=True)

    # ------------------------------------------------------------------
    # Init / indekslar / seed
    # ------------------------------------------------------------------
    def init(self) -> None:
        self.create_backup("startup", keep_last=20)

        self.db.users.create_index([("tg_id", ASCENDING)], unique=True)
        self.db.admins.create_index([("tg_id", ASCENDING)], unique=True)
        self.db.channels.create_index([("chat_id", ASCENDING)], unique=True)
        self.db.professions.create_index([("title", ASCENDING)], unique=True)
        self.db.seekers.create_index([("telegram_id", ASCENDING)], unique=True)
        self.db.employers.create_index([("telegram_id", ASCENDING)], unique=True)
        self.db.interests.create_index([("vacancy_id", ASCENDING), ("seeker_id", ASCENDING)], unique=True)
        self.db.candidate_actions.create_index(
            [("employer_tg_id", ASCENDING), ("vacancy_id", ASCENDING), ("seeker_id", ASCENDING)],
            unique=True,
        )
        self.db.moderation_messages.create_index(
            [("item_type", ASCENDING), ("item_id", ASCENDING),
             ("admin_tg_id", ASCENDING), ("message_id", ASCENDING)],
            unique=True,
        )
        self.db.settings.create_index([("key", ASCENDING)], unique=True)

        self.set_setting_default("force_subscription", "0")
        self._seed_professions()

        # Eski SQLite migratsiyasi MongoDB uchun kerak emas — faqat bayroqni qo'yamiz.
        if self.get_setting("migration_moderation_v1", "0") != "1":
            self.set_setting("migration_moderation_v1", "1")

        # Muddati o'tgan vakansiyalarni yopish.
        self.db.vacancies.update_many(
            {
                "active": 1,
                "moderation_status": "approved",
                "expires_at": {"$ne": None, "$lt": now_iso()},
            },
            {"$set": {"moderation_status": "expired", "active": 0, "updated_at": now_iso()}},
        )

    def _seed_professions(self) -> None:
        if self.db.professions.count_documents({}) > 0:
            return
        for title in DEFAULT_PROFESSIONS:
            self.db.professions.insert_one(
                {"id": self._next_id("professions"), "title": title, "is_active": 1, "created_at": now_iso()}
            )

    # ------------------------------------------------------------------
    # Backup (barcha kolleksiyalarni JSON ga dump qiladi)
    # ------------------------------------------------------------------
    def create_backup(self, reason: str = "manual", keep_last: int = 20) -> Path | None:
        try:
            dump: dict[str, list[dict[str, Any]]] = {}
            total = 0
            for name in _BACKUP_COLLECTIONS:
                docs = []
                for doc in self.db[name].find():
                    doc.pop("_id", None)
                    docs.append(doc)
                dump[name] = docs
                total += len(docs)
            if total == 0:
                return None
        except Exception:
            return None

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        safe_reason = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in reason).strip("_")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"mongo_{safe_reason}_{stamp}.json"
        backup_path.write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
        self._cleanup_backups(keep_last)
        return backup_path

    def _cleanup_backups(self, keep_last: int) -> None:
        if keep_last <= 0 or not self.backup_dir.exists():
            return
        backups = sorted(
            self.backup_dir.glob("mongo_*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for old_backup in backups[keep_last:]:
            try:
                old_backup.unlink()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Sozlamalar (settings)
    # ------------------------------------------------------------------
    def set_setting_default(self, key: str, value: str) -> None:
        self.db.settings.update_one(
            {"key": key},
            {"$setOnInsert": {"key": key, "value": value}},
            upsert=True,
        )

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.db.settings.find_one({"key": key})
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.db.settings.update_one(
            {"key": key},
            {"$set": {"key": key, "value": value}},
            upsert=True,
        )

    def force_subscription_enabled(self) -> bool:
        return self.get_setting("force_subscription", "0") == "1"

    # ------------------------------------------------------------------
    # Adminlar
    # ------------------------------------------------------------------
    def is_admin(self, tg_id: int) -> bool:
        return self.db.admins.find_one({"tg_id": tg_id}) is not None

    def list_admins(self) -> list[dict[str, Any]]:
        return self._clean_list(self.db.admins.find().sort("id", ASCENDING), "admins")

    def add_admin(self, tg_id: int, added_by: int | None = None) -> None:
        if self.db.admins.find_one({"tg_id": tg_id}):
            return
        self.db.admins.insert_one(
            {"id": self._next_id("admins"), "tg_id": tg_id, "added_by": added_by, "created_at": now_iso()}
        )

    def delete_admin(self, tg_id: int) -> None:
        self.db.admins.delete_one({"tg_id": tg_id})

    # ------------------------------------------------------------------
    # Admin loglar
    # ------------------------------------------------------------------
    def add_admin_log(
        self,
        admin_tg_id: int,
        action: str,
        target_type: str | None = None,
        target_id: int | None = None,
        details: str | None = None,
    ) -> None:
        self.db.admin_logs.insert_one(
            {
                "id": self._next_id("admin_logs"),
                "admin_tg_id": admin_tg_id,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "details": details,
                "created_at": now_iso(),
            }
        )

    def list_admin_logs(self, limit: int = 30) -> list[dict[str, Any]]:
        return self._clean_list(self.db.admin_logs.find().sort("id", DESCENDING).limit(limit), "admin_logs")

    # ------------------------------------------------------------------
    # Moderatsiya xabarlari
    # ------------------------------------------------------------------
    def save_moderation_message(
        self,
        item_type: str,
        item_id: int,
        admin_tg_id: int,
        chat_id: int,
        message_id: int,
    ) -> None:
        if self.db.moderation_messages.find_one(
            {"item_type": item_type, "item_id": item_id, "admin_tg_id": admin_tg_id, "message_id": message_id}
        ):
            return
        self.db.moderation_messages.insert_one(
            {
                "id": self._next_id("moderation_messages"),
                "item_type": item_type,
                "item_id": item_id,
                "admin_tg_id": admin_tg_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "created_at": now_iso(),
            }
        )

    def list_moderation_messages(self, item_type: str, item_id: int) -> list[dict[str, Any]]:
        cursor = self.db.moderation_messages.find({"item_type": item_type, "item_id": item_id}).sort("id", ASCENDING)
        return self._clean_list(cursor, "moderation_messages")

    def delete_moderation_messages(self, item_type: str, item_id: int) -> None:
        self.db.moderation_messages.delete_many({"item_type": item_type, "item_id": item_id})

    # ------------------------------------------------------------------
    # Foydalanuvchilar
    # ------------------------------------------------------------------
    def upsert_user(self, tg_id: int, username: str | None, full_name: str, role: str | None = None) -> None:
        current = self.db.users.find_one({"tg_id": tg_id})
        saved_role = role if role is not None else (current.get("role") if current else None)
        stamp = now_iso()
        if current:
            self.db.users.update_one(
                {"tg_id": tg_id},
                {"$set": {"username": username, "full_name": full_name, "role": saved_role, "updated_at": stamp}},
            )
        else:
            self.db.users.insert_one(
                {
                    "id": self._next_id("users"),
                    "tg_id": tg_id,
                    "username": username,
                    "full_name": full_name,
                    "role": saved_role,
                    "created_at": stamp,
                    "updated_at": stamp,
                }
            )

    def set_user_role(self, tg_id: int, role: str) -> None:
        self.db.users.update_one({"tg_id": tg_id}, {"$set": {"role": role, "updated_at": now_iso()}})

    # ------------------------------------------------------------------
    # Kanallar (majburiy obuna)
    # ------------------------------------------------------------------
    def list_channels(self) -> list[dict[str, Any]]:
        return self._clean_list(self.db.channels.find().sort("id", ASCENDING), "channels")

    def add_channel(self, title: str, chat_id: str, invite_link: str | None = None) -> None:
        existing = self.db.channels.find_one({"chat_id": chat_id})
        if existing:
            self.db.channels.update_one(
                {"chat_id": chat_id},
                {"$set": {"title": title, "invite_link": invite_link}},
            )
        else:
            self.db.channels.insert_one(
                {
                    "id": self._next_id("channels"),
                    "title": title,
                    "chat_id": chat_id,
                    "invite_link": invite_link,
                    "created_at": now_iso(),
                }
            )

    def delete_channel(self, channel_id: int) -> None:
        self.db.channels.delete_one({"id": channel_id})

    # ------------------------------------------------------------------
    # Kasblar
    # ------------------------------------------------------------------
    def list_professions(self, only_active: bool = True) -> list[dict[str, Any]]:
        query = {"is_active": 1} if only_active else {}
        rows = self._clean_list(self.db.professions.find(query), "professions")
        rows.sort(key=lambda d: (d.get("title") or "").lower())
        return rows

    def get_profession(self, profession_id: int) -> dict[str, Any] | None:
        return self._clean(self.db.professions.find_one({"id": profession_id}), "professions")

    def add_profession(self, title: str) -> None:
        existing = self.db.professions.find_one({"title": title})
        if existing:
            self.db.professions.update_one({"title": title}, {"$set": {"is_active": 1}})
        else:
            self.db.professions.insert_one(
                {"id": self._next_id("professions"), "title": title, "is_active": 1, "created_at": now_iso()}
            )

    def update_profession(self, profession_id: int, title: str) -> None:
        old = self.get_profession(profession_id)
        self.db.professions.update_one({"id": profession_id}, {"$set": {"title": title}})
        if old:
            self.db.seekers.update_many({"profession_id": profession_id}, {"$set": {"profession_title": title}})
            self.db.vacancies.update_many({"profession_id": profession_id}, {"$set": {"profession_title": title}})

    def delete_profession(self, profession_id: int) -> None:
        self.db.professions.update_one({"id": profession_id}, {"$set": {"is_active": 0}})

    # ------------------------------------------------------------------
    # Nomzodlar (seekers)
    # ------------------------------------------------------------------
    def save_seeker(self, telegram_id: int, data: dict[str, Any]) -> int:
        stamp = now_iso()
        fields = {
            "photo_id": data["photo_id"],
            "full_name": data["full_name"],
            "age": int(data["age"]),
            "gender": data["gender"],
            "phone": data["phone"],
            "region": data["region"],
            "district": data.get("district"),
            "address": data.get("address"),
            "birth_date": data.get("birth_date"),
            "profession_id": data.get("profession_id"),
            "profession_title": data["profession_title"],
            "job_type": data.get("job_type"),
            "experience": data["experience"],
            "experience_years": data.get("experience_years"),
            "education": data.get("education"),
            "excel_level": data.get("excel_level"),
            "word_level": data.get("word_level"),
            "previous_job": data["previous_job"],
            "previous_salary": data.get("previous_salary"),
            "previous_salary_amount": data.get("previous_salary_amount"),
            "current_salary": data.get("current_salary"),
            "current_salary_amount": data.get("current_salary_amount"),
            "salary": data.get("salary") or data.get("current_salary"),
            "salary_amount": data.get("salary_amount") or data.get("current_salary_amount"),
            "extra": data.get("extra"),
            "resume_file_id": data.get("resume_file_id"),
            "resume_file_name": data.get("resume_file_name"),
            "moderation_status": "pending",
            "moderation_note": None,
            "moderated_by": None,
            "approved_at": None,
            "published_at": None,
            "updated_at": stamp,
        }
        existing = self.db.seekers.find_one({"telegram_id": telegram_id})
        if existing:
            self.db.seekers.update_one({"telegram_id": telegram_id}, {"$set": fields})
            seeker_id = int(existing["id"])
        else:
            seeker_id = self._next_id("seekers")
            doc = {"id": seeker_id, "telegram_id": telegram_id, "created_at": stamp, **fields}
            self.db.seekers.insert_one(doc)
        self.set_user_role(telegram_id, "seeker")
        return seeker_id

    def get_seeker(self, seeker_id: int) -> dict[str, Any] | None:
        return self._clean(self.db.seekers.find_one({"id": seeker_id}), "seekers")

    def get_seeker_by_tg(self, telegram_id: int) -> dict[str, Any] | None:
        return self._clean(self.db.seekers.find_one({"telegram_id": telegram_id}), "seekers")

    _SEEKER_EDITABLE = {
        "photo_id", "full_name", "age", "birth_date", "gender", "phone", "region",
        "district", "address", "profession_id", "profession_title", "job_type", "experience",
        "experience_years", "education", "excel_level", "word_level", "previous_job",
        "previous_salary", "previous_salary_amount", "current_salary",
        "current_salary_amount", "salary", "salary_amount", "extra",
        "resume_file_id", "resume_file_name",
    }

    def update_seeker_field(self, telegram_id: int, field: str, value: Any) -> None:
        if field not in self._SEEKER_EDITABLE:
            raise ValueError(f"Unsupported seeker field: {field}")
        self.db.seekers.update_one(
            {"telegram_id": telegram_id},
            {"$set": {
                field: value,
                "moderation_status": "pending",
                "moderation_note": None,
                "moderated_by": None,
                "approved_at": None,
                "published_at": None,
                "updated_at": now_iso(),
            }},
        )

    def update_seeker_profession(self, telegram_id: int, profession_id: int, profession_title: str) -> None:
        self.db.seekers.update_one(
            {"telegram_id": telegram_id},
            {"$set": {
                "profession_id": profession_id,
                "profession_title": profession_title,
                "moderation_status": "pending",
                "moderation_note": None,
                "moderated_by": None,
                "approved_at": None,
                "published_at": None,
                "updated_at": now_iso(),
            }},
        )

    def set_seeker_moderation_status(
        self,
        seeker_id: int,
        status: str,
        note: str | None = None,
        moderated_by: int | None = None,
    ) -> None:
        stamp = now_iso()
        self.db.seekers.update_one(
            {"id": seeker_id},
            {"$set": {
                "moderation_status": status,
                "moderation_note": note,
                "moderated_by": moderated_by,
                "approved_at": stamp if status == "approved" else None,
                "updated_at": stamp,
            }},
        )

    def set_seeker_moderation_status_if_pending(
        self,
        seeker_id: int,
        status: str,
        note: str | None = None,
        moderated_by: int | None = None,
    ) -> bool:
        stamp = now_iso()
        result = self.db.seekers.update_one(
            {"id": seeker_id, "moderation_status": "pending"},
            {"$set": {
                "moderation_status": status,
                "moderation_note": note,
                "moderated_by": moderated_by,
                "approved_at": stamp if status == "approved" else None,
                "updated_at": stamp,
            }},
        )
        return result.modified_count > 0

    def mark_seeker_published(
        self,
        seeker_id: int,
        channel_chat_id: str | None = None,
        channel_message_id: int | None = None,
    ) -> None:
        update: dict[str, Any] = {"published_at": now_iso(), "updated_at": now_iso()}
        if channel_chat_id is not None:
            update["channel_chat_id"] = channel_chat_id
        if channel_message_id is not None:
            update["channel_message_id"] = channel_message_id
        self.db.seekers.update_one({"id": seeker_id}, {"$set": update})

    def list_pending_seekers(self, limit: int = 20) -> list[dict[str, Any]]:
        cursor = self.db.seekers.find({"moderation_status": "pending"}).sort("updated_at", DESCENDING).limit(limit)
        return self._clean_list(cursor, "seekers")

    # ------------------------------------------------------------------
    # Ish beruvchilar (employers)
    # ------------------------------------------------------------------
    def save_employer(self, telegram_id: int, data: dict[str, Any]) -> int:
        stamp = now_iso()
        fields = {
            "full_name": data["full_name"],
            "organization": data["organization"],
            "phone": data["phone"],
            "region": data["region"],
            "district": data.get("district"),
            "updated_at": stamp,
        }
        existing = self.db.employers.find_one({"telegram_id": telegram_id})
        if existing:
            self.db.employers.update_one({"telegram_id": telegram_id}, {"$set": fields})
            employer_id = int(existing["id"])
        else:
            employer_id = self._next_id("employers")
            self.db.employers.insert_one(
                {"id": employer_id, "telegram_id": telegram_id, "created_at": stamp, **fields}
            )
        self.set_user_role(telegram_id, "employer")
        return employer_id

    # ------------------------------------------------------------------
    # Vakansiyalar
    # ------------------------------------------------------------------
    def save_vacancy(self, employer_tg_id: int, data: dict[str, Any]) -> int:
        stamp = now_iso()
        vacancy_id = self._next_id("vacancies")
        self.db.vacancies.insert_one(
            {
                "id": vacancy_id,
                "employer_tg_id": employer_tg_id,
                "full_name": data["full_name"],
                "organization": data["organization"],
                "phone": data["phone"],
                "region": data["region"],
                "district": data.get("district"),
                "profession_id": data.get("profession_id"),
                "profession_title": data["profession_title"],
                "staff_count": int(data["staff_count"]),
                "job_type": data["job_type"],
                "salary": data["salary"],
                "salary_amount": data.get("salary_amount"),
                "min_experience_years": data.get("min_experience_years"),
                "requirements": data["requirements"],
                "active": 1,
                "expires_at": data.get("expires_at") or days_from_now_iso(30),
                "moderation_status": "pending",
                "moderation_note": None,
                "moderated_by": None,
                "approved_at": None,
                "published_at": None,
                "created_at": stamp,
                "updated_at": stamp,
            }
        )
        return vacancy_id

    def get_vacancy(self, vacancy_id: int) -> dict[str, Any] | None:
        return self._clean(self.db.vacancies.find_one({"id": vacancy_id}), "vacancies")

    def list_vacancies(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._clean_list(self.db.vacancies.find().sort("id", DESCENDING).limit(limit), "vacancies")

    def list_vacancies_by_employer(self, employer_tg_id: int, limit: int = 20) -> list[dict[str, Any]]:
        cursor = self.db.vacancies.find({"employer_tg_id": employer_tg_id}).sort("id", DESCENDING).limit(limit)
        return self._clean_list(cursor, "vacancies")

    def count_vacancies_since(self, employer_tg_id: int, since_iso: str) -> int:
        return self.db.vacancies.count_documents({"employer_tg_id": employer_tg_id, "created_at": {"$gte": since_iso}})

    def count_seeker_updates_since(self, telegram_id: int, since_iso: str) -> int:
        return self.db.seekers.count_documents({"telegram_id": telegram_id, "updated_at": {"$gte": since_iso}})

    def delete_vacancy(self, vacancy_id: int) -> None:
        self.db.vacancies.delete_one({"id": vacancy_id})

    _VACANCY_EDITABLE = {
        "organization", "phone", "region", "district", "profession_id", "profession_title",
        "staff_count", "job_type", "salary", "salary_amount", "min_experience_years",
        "requirements", "active", "moderation_status", "moderation_note", "moderated_by",
        "approved_at", "published_at", "expires_at",
    }

    def update_vacancy_field(self, vacancy_id: int, field: str, value: Any) -> None:
        if field not in self._VACANCY_EDITABLE:
            raise ValueError(f"Unsupported vacancy field: {field}")
        self.db.vacancies.update_one({"id": vacancy_id}, {"$set": {field: value, "updated_at": now_iso()}})

    def set_vacancy_moderation_status(
        self,
        vacancy_id: int,
        status: str,
        note: str | None = None,
        moderated_by: int | None = None,
    ) -> None:
        stamp = now_iso()
        self.db.vacancies.update_one(
            {"id": vacancy_id},
            {"$set": {
                "moderation_status": status,
                "moderation_note": note,
                "moderated_by": moderated_by,
                "approved_at": stamp if status == "approved" else None,
                "updated_at": stamp,
            }},
        )

    def set_vacancy_moderation_status_if_pending(
        self,
        vacancy_id: int,
        status: str,
        note: str | None = None,
        moderated_by: int | None = None,
    ) -> bool:
        stamp = now_iso()
        result = self.db.vacancies.update_one(
            {"id": vacancy_id, "moderation_status": "pending"},
            {"$set": {
                "moderation_status": status,
                "moderation_note": note,
                "moderated_by": moderated_by,
                "approved_at": stamp if status == "approved" else None,
                "updated_at": stamp,
            }},
        )
        return result.modified_count > 0

    def mark_vacancy_published(
        self,
        vacancy_id: int,
        channel_chat_id: str | None = None,
        channel_message_id: int | None = None,
    ) -> None:
        update: dict[str, Any] = {"published_at": now_iso(), "updated_at": now_iso()}
        if channel_chat_id is not None:
            update["channel_chat_id"] = channel_chat_id
        if channel_message_id is not None:
            update["channel_message_id"] = channel_message_id
        self.db.vacancies.update_one({"id": vacancy_id}, {"$set": update})

    def list_pending_vacancies(self, limit: int = 20) -> list[dict[str, Any]]:
        cursor = self.db.vacancies.find({"moderation_status": "pending"}).sort("updated_at", DESCENDING).limit(limit)
        return self._clean_list(cursor, "vacancies")

    # ------------------------------------------------------------------
    # Moslashtirish (matching)
    # ------------------------------------------------------------------
    def find_seekers_by_profession(self, profession_id: int | None, profession_title: str) -> list[dict[str, Any]]:
        if profession_id is not None:
            cursor = self.db.seekers.find(
                {"profession_id": profession_id, "moderation_status": "approved"}
            ).sort("id", DESCENDING)
            rows = self._clean_list(cursor, "seekers")
            if rows:
                return rows
        cursor = self.db.seekers.find(
            {"profession_title": profession_title, "moderation_status": "approved"}
        ).sort("id", DESCENDING)
        return self._clean_list(cursor, "seekers")

    def find_vacancies_by_profession(self, profession_id: int | None, profession_title: str) -> list[dict[str, Any]]:
        expires_clause = {"$or": [{"expires_at": None}, {"expires_at": {"$gte": now_iso()}}]}
        if profession_id is not None:
            cursor = self.db.vacancies.find(
                {"profession_id": profession_id, "moderation_status": "approved", "active": 1, **expires_clause}
            ).sort("id", DESCENDING)
            rows = self._clean_list(cursor, "vacancies")
            if rows:
                return rows
        cursor = self.db.vacancies.find(
            {"profession_title": profession_title, "moderation_status": "approved", "active": 1, **expires_clause}
        ).sort("id", DESCENDING)
        return self._clean_list(cursor, "vacancies")

    # ------------------------------------------------------------------
    # Saralashlar va qiziqishlar
    # ------------------------------------------------------------------
    def save_candidate_action(self, employer_tg_id: int, vacancy_id: int, seeker_id: int, status: str) -> None:
        stamp = now_iso()
        existing = self.db.candidate_actions.find_one(
            {"employer_tg_id": employer_tg_id, "vacancy_id": vacancy_id, "seeker_id": seeker_id}
        )
        if existing:
            self.db.candidate_actions.update_one(
                {"_id": existing["_id"]},
                {"$set": {"status": status, "updated_at": stamp}},
            )
        else:
            self.db.candidate_actions.insert_one(
                {
                    "id": self._next_id("candidate_actions"),
                    "employer_tg_id": employer_tg_id,
                    "vacancy_id": vacancy_id,
                    "seeker_id": seeker_id,
                    "status": status,
                    "created_at": stamp,
                    "updated_at": stamp,
                }
            )

    def create_interest(
        self,
        vacancy_id: int,
        seeker_id: int,
        employer_tg_id: int,
        seeker_tg_id: int,
        status: str = "pending",
    ) -> int:
        stamp = now_iso()
        existing = self.db.interests.find_one({"vacancy_id": vacancy_id, "seeker_id": seeker_id})
        if existing:
            self.db.interests.update_one(
                {"_id": existing["_id"]},
                {"$set": {"status": status, "updated_at": stamp}},
            )
            return int(existing["id"])
        interest_id = self._next_id("interests")
        self.db.interests.insert_one(
            {
                "id": interest_id,
                "vacancy_id": vacancy_id,
                "seeker_id": seeker_id,
                "employer_tg_id": employer_tg_id,
                "seeker_tg_id": seeker_tg_id,
                "status": status,
                "created_at": stamp,
                "updated_at": stamp,
            }
        )
        return interest_id

    def get_interest(self, interest_id: int) -> dict[str, Any] | None:
        return self._clean(self.db.interests.find_one({"id": interest_id}), "interests")

    def update_interest_status(self, interest_id: int, status: str) -> None:
        self.db.interests.update_one({"id": interest_id}, {"$set": {"status": status, "updated_at": now_iso()}})

    # ------------------------------------------------------------------
    # Dashboard / eksport / qidiruv
    # ------------------------------------------------------------------
    def dashboard_counts(self) -> dict[str, int]:
        return {
            "seekers": self.db.seekers.count_documents({}),
            "employers": self.db.employers.count_documents({}),
            "vacancies": self.db.vacancies.count_documents({}),
            "interests": self.db.interests.count_documents({}),
            "users": self.db.users.count_documents({}),
            "admins": self.db.admins.count_documents({}),
            "pending_seekers": self.db.seekers.count_documents({"moderation_status": "pending"}),
            "pending_vacancies": self.db.vacancies.count_documents({"moderation_status": "pending"}),
            "expired_vacancies": self.db.vacancies.count_documents({"moderation_status": "expired"}),
        }

    def broadcast_users(self, target: str) -> list[int]:
        if target == "seekers":
            return [int(r["telegram_id"]) for r in self.db.seekers.find({}, {"telegram_id": 1})]
        if target == "employers":
            return [int(r["telegram_id"]) for r in self.db.employers.find({}, {"telegram_id": 1})]
        return [int(r["tg_id"]) for r in self.db.users.find({}, {"tg_id": 1})]

    def filter_seekers(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        query: dict[str, Any] = {}

        if filters.get("gender"):
            query["gender"] = filters["gender"]
        if filters.get("region"):
            query["region"] = filters["region"]
        if filters.get("district"):
            query["district"] = filters["district"]
        if filters.get("profession_id"):
            query["profession_id"] = filters["profession_id"]

        age: dict[str, Any] = {}
        if filters.get("age_min") is not None:
            age["$gte"] = filters["age_min"]
        if filters.get("age_max") is not None:
            age["$lte"] = filters["age_max"]
        if age:
            query["age"] = age

        if filters.get("experience"):
            query["experience"] = _regex(filters["experience"])
        if filters.get("job_type"):
            query["$or"] = [{"job_type": filters["job_type"]}, {"job_type": "Farqi yo'q"}]
        if filters.get("experience_years_min") is not None:
            query["experience_years"] = {"$gte": filters["experience_years_min"]}

        salary: dict[str, Any] = {}
        if filters.get("salary_min") is not None:
            salary["$gte"] = filters["salary_min"]
        if filters.get("salary_max") is not None:
            salary["$lte"] = filters["salary_max"]
        if salary:
            query["salary_amount"] = salary

        if filters.get("moderation_status"):
            query["moderation_status"] = filters["moderation_status"]

        return self._clean_list(self.db.seekers.find(query).sort("id", DESCENDING), "seekers")

    def all_users(self) -> list[dict[str, Any]]:
        return self._clean_list(self.db.users.find().sort("id", DESCENDING), "users")

    def all_seekers(self) -> list[dict[str, Any]]:
        return self._clean_list(self.db.seekers.find().sort("id", DESCENDING), "seekers")

    def all_vacancies(self) -> list[dict[str, Any]]:
        return self._clean_list(self.db.vacancies.find().sort("id", DESCENDING), "vacancies")

    def all_employers(self) -> list[dict[str, Any]]:
        return self._clean_list(self.db.employers.find().sort("id", DESCENDING), "employers")

    def all_interests(self) -> list[dict[str, Any]]:
        return self._clean_list(self.db.interests.find().sort("id", DESCENDING), "interests")

    def all_candidate_actions(self) -> list[dict[str, Any]]:
        return self._clean_list(self.db.candidate_actions.find().sort("id", DESCENDING), "candidate_actions")

    def search_admin(self, query: str, limit: int = 10) -> dict[str, list[dict[str, Any]]]:
        query = query.strip()
        rx = _regex(query)
        numeric = int(query) if query.isdigit() else None

        seeker_or: list[dict[str, Any]] = [
            {"full_name": rx}, {"phone": rx}, {"region": rx}, {"district": rx}, {"profession_title": rx},
        ]
        if numeric is not None:
            seeker_or.extend([{"id": numeric}, {"telegram_id": numeric}, {"age": numeric}])

        vacancy_or: list[dict[str, Any]] = [
            {"organization": rx}, {"full_name": rx}, {"phone": rx},
            {"region": rx}, {"district": rx}, {"profession_title": rx},
        ]
        if numeric is not None:
            vacancy_or.extend([{"id": numeric}, {"employer_tg_id": numeric}])

        employer_or: list[dict[str, Any]] = [
            {"full_name": rx}, {"organization": rx}, {"phone": rx}, {"region": rx}, {"district": rx},
        ]
        if numeric is not None:
            employer_or.extend([{"id": numeric}, {"telegram_id": numeric}])

        return {
            "seekers": self._clean_list(
                self.db.seekers.find({"$or": seeker_or}).sort("id", DESCENDING).limit(limit), "seekers"
            ),
            "vacancies": self._clean_list(
                self.db.vacancies.find({"$or": vacancy_or}).sort("id", DESCENDING).limit(limit), "vacancies"
            ),
            "employers": self._clean_list(
                self.db.employers.find({"$or": employer_or}).sort("id", DESCENDING).limit(limit), "employers"
            ),
        }


db = Database()
