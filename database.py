import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from config import BACKUP_DIR, DATABASE_PATH


DEFAULT_PROFESSIONS = ("Dasturchi", "Operator", "Sotuvchi", "Dizayner")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def days_from_now_iso(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path = DATABASE_PATH) -> None:
        self.path = path
        self.backup_dir = BACKUP_DIR
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")

    def init(self) -> None:
        self.create_backup("startup", keep_last=20)
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER NOT NULL UNIQUE,
                username TEXT,
                full_name TEXT,
                role TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER NOT NULL UNIQUE,
                added_by INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                chat_id TEXT NOT NULL UNIQUE,
                invite_link TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS professions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL UNIQUE,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS seekers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                photo_id TEXT NOT NULL,
                full_name TEXT NOT NULL,
                age INTEGER NOT NULL,
                gender TEXT NOT NULL,
                phone TEXT NOT NULL,
                region TEXT NOT NULL,
                district TEXT,
                profession_id INTEGER,
                profession_title TEXT NOT NULL,
                experience TEXT NOT NULL,
                education TEXT,
                previous_job TEXT NOT NULL,
                salary TEXT NOT NULL,
                extra TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (profession_id) REFERENCES professions(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS employers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                organization TEXT NOT NULL,
                phone TEXT NOT NULL,
                region TEXT NOT NULL,
                district TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS vacancies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employer_tg_id INTEGER NOT NULL,
                full_name TEXT NOT NULL,
                organization TEXT NOT NULL,
                phone TEXT NOT NULL,
                region TEXT NOT NULL,
                district TEXT,
                profession_id INTEGER,
                profession_title TEXT NOT NULL,
                staff_count INTEGER NOT NULL,
                job_type TEXT NOT NULL,
                salary TEXT NOT NULL,
                requirements TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (profession_id) REFERENCES professions(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS interests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vacancy_id INTEGER NOT NULL,
                seeker_id INTEGER NOT NULL,
                employer_tg_id INTEGER NOT NULL,
                seeker_tg_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(vacancy_id, seeker_id),
                FOREIGN KEY (vacancy_id) REFERENCES vacancies(id) ON DELETE CASCADE,
                FOREIGN KEY (seeker_id) REFERENCES seekers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS candidate_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employer_tg_id INTEGER NOT NULL,
                vacancy_id INTEGER NOT NULL,
                seeker_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(employer_tg_id, vacancy_id, seeker_id),
                FOREIGN KEY (vacancy_id) REFERENCES vacancies(id) ON DELETE CASCADE,
                FOREIGN KEY (seeker_id) REFERENCES seekers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_tg_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id INTEGER,
                details TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS moderation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                admin_tg_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(item_type, item_id, admin_tg_id, message_id)
            );
            """
        )
        self.set_setting_default("force_subscription", "0")
        self._migrate_schema()
        self._seed_professions()
        self.conn.commit()

    def create_backup(self, reason: str = "manual", keep_last: int = 20) -> Path | None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return None

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        safe_reason = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in reason).strip("_")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"{self.path.stem}_{safe_reason}_{stamp}.sqlite3"

        backup_conn = sqlite3.connect(backup_path)
        try:
            self.conn.backup(backup_conn)
        finally:
            backup_conn.close()

        self._cleanup_backups(keep_last)
        return backup_path

    def _cleanup_backups(self, keep_last: int) -> None:
        if keep_last <= 0 or not self.backup_dir.exists():
            return
        backups = sorted(
            self.backup_dir.glob(f"{self.path.stem}_*.sqlite3"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for old_backup in backups[keep_last:]:
            try:
                old_backup.unlink()
            except OSError:
                pass

    def _columns(self, table: str) -> set[str]:
        return {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()}

    def _add_column_if_missing(self, table: str, column: str, definition: str) -> None:
        if column not in self._columns(table):
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _migrate_schema(self) -> None:
        self._add_column_if_missing("seekers", "resume_file_id", "TEXT")
        self._add_column_if_missing("seekers", "resume_file_name", "TEXT")
        self._add_column_if_missing("seekers", "birth_date", "TEXT")
        self._add_column_if_missing("seekers", "district", "TEXT")
        self._add_column_if_missing("seekers", "address", "TEXT")
        self._add_column_if_missing("seekers", "job_type", "TEXT")
        self._add_column_if_missing("seekers", "experience_years", "INTEGER")
        self._add_column_if_missing("seekers", "excel_level", "TEXT")
        self._add_column_if_missing("seekers", "word_level", "TEXT")
        self._add_column_if_missing("seekers", "previous_salary", "TEXT")
        self._add_column_if_missing("seekers", "previous_salary_amount", "INTEGER")
        self._add_column_if_missing("seekers", "current_salary", "TEXT")
        self._add_column_if_missing("seekers", "current_salary_amount", "INTEGER")
        self._add_column_if_missing("seekers", "salary_amount", "INTEGER")
        self._add_column_if_missing("seekers", "moderation_status", "TEXT NOT NULL DEFAULT 'pending'")
        self._add_column_if_missing("seekers", "moderation_note", "TEXT")
        self._add_column_if_missing("seekers", "moderated_by", "INTEGER")
        self._add_column_if_missing("seekers", "approved_at", "TEXT")
        self._add_column_if_missing("seekers", "published_at", "TEXT")
        self._add_column_if_missing("seekers", "channel_chat_id", "TEXT")
        self._add_column_if_missing("seekers", "channel_message_id", "INTEGER")

        self._add_column_if_missing("vacancies", "salary_amount", "INTEGER")
        self._add_column_if_missing("vacancies", "district", "TEXT")
        self._add_column_if_missing("vacancies", "min_experience_years", "INTEGER")
        self._add_column_if_missing("vacancies", "moderation_status", "TEXT NOT NULL DEFAULT 'pending'")
        self._add_column_if_missing("vacancies", "moderation_note", "TEXT")
        self._add_column_if_missing("vacancies", "moderated_by", "INTEGER")
        self._add_column_if_missing("vacancies", "approved_at", "TEXT")
        self._add_column_if_missing("vacancies", "published_at", "TEXT")
        self._add_column_if_missing("vacancies", "channel_chat_id", "TEXT")
        self._add_column_if_missing("vacancies", "channel_message_id", "INTEGER")
        self._add_column_if_missing("vacancies", "expires_at", "TEXT")

        self._add_column_if_missing("employers", "district", "TEXT")

        if self.get_setting("migration_moderation_v1", "0") != "1":
            self.conn.execute("UPDATE seekers SET moderation_status = 'approved', approved_at = COALESCE(approved_at, updated_at)")
            self.conn.execute("UPDATE vacancies SET moderation_status = 'approved', approved_at = COALESCE(approved_at, updated_at)")
            self.set_setting("migration_moderation_v1", "1")

        self.conn.execute(
            """
            UPDATE vacancies
            SET moderation_status = 'expired', active = 0
            WHERE active = 1
                AND moderation_status = 'approved'
                AND expires_at IS NOT NULL
                AND expires_at < ?
            """,
            (now_iso(),),
        )

    def _seed_professions(self) -> None:
        count = self.conn.execute("SELECT COUNT(*) FROM professions").fetchone()[0]
        if count:
            return
        for title in DEFAULT_PROFESSIONS:
            self.conn.execute(
                "INSERT INTO professions(title, created_at) VALUES (?, ?)",
                (title, now_iso()),
            )

    def set_setting_default(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
            (key, value),
        )

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO settings(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        self.conn.commit()

    def force_subscription_enabled(self) -> bool:
        return self.get_setting("force_subscription", "0") == "1"

    def is_admin(self, tg_id: int) -> bool:
        try:
            row = self.conn.execute("SELECT 1 FROM admins WHERE tg_id = ?", (tg_id,)).fetchone()
        except sqlite3.OperationalError:
            return False
        return row is not None

    def list_admins(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM admins ORDER BY id").fetchall()

    def add_admin(self, tg_id: int, added_by: int | None = None) -> None:
        self.conn.execute(
            """
            INSERT INTO admins(tg_id, added_by, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(tg_id) DO NOTHING
            """,
            (tg_id, added_by, now_iso()),
        )
        self.conn.commit()

    def delete_admin(self, tg_id: int) -> None:
        self.conn.execute("DELETE FROM admins WHERE tg_id = ?", (tg_id,))
        self.conn.commit()

    def add_admin_log(
        self,
        admin_tg_id: int,
        action: str,
        target_type: str | None = None,
        target_id: int | None = None,
        details: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO admin_logs(admin_tg_id, action, target_type, target_id, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (admin_tg_id, action, target_type, target_id, details, now_iso()),
        )
        self.conn.commit()

    def list_admin_logs(self, limit: int = 30) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM admin_logs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def save_moderation_message(
        self,
        item_type: str,
        item_id: int,
        admin_tg_id: int,
        chat_id: int,
        message_id: int,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO moderation_messages(
                item_type, item_id, admin_tg_id, chat_id, message_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (item_type, item_id, admin_tg_id, chat_id, message_id, now_iso()),
        )
        self.conn.commit()

    def list_moderation_messages(self, item_type: str, item_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT * FROM moderation_messages
            WHERE item_type = ? AND item_id = ?
            ORDER BY id
            """,
            (item_type, item_id),
        ).fetchall()

    def delete_moderation_messages(self, item_type: str, item_id: int) -> None:
        self.conn.execute(
            "DELETE FROM moderation_messages WHERE item_type = ? AND item_id = ?",
            (item_type, item_id),
        )
        self.conn.commit()

    def upsert_user(self, tg_id: int, username: str | None, full_name: str, role: str | None = None) -> None:
        current = self.conn.execute("SELECT role FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
        saved_role = role if role is not None else (current["role"] if current else None)
        stamp = now_iso()
        self.conn.execute(
            """
            INSERT INTO users(tg_id, username, full_name, role, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(tg_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                role = excluded.role,
                updated_at = excluded.updated_at
            """,
            (tg_id, username, full_name, saved_role, stamp, stamp),
        )
        self.conn.commit()

    def set_user_role(self, tg_id: int, role: str) -> None:
        self.conn.execute(
            "UPDATE users SET role = ?, updated_at = ? WHERE tg_id = ?",
            (role, now_iso(), tg_id),
        )
        self.conn.commit()

    def list_channels(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM channels ORDER BY id").fetchall()

    def add_channel(self, title: str, chat_id: str, invite_link: str | None = None) -> None:
        self.conn.execute(
            """
            INSERT INTO channels(title, chat_id, invite_link, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = excluded.title,
                invite_link = excluded.invite_link
            """,
            (title, chat_id, invite_link, now_iso()),
        )
        self.conn.commit()

    def delete_channel(self, channel_id: int) -> None:
        self.conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
        self.conn.commit()

    def list_professions(self, only_active: bool = True) -> list[sqlite3.Row]:
        query = "SELECT * FROM professions"
        if only_active:
            query += " WHERE is_active = 1"
        query += " ORDER BY title COLLATE NOCASE"
        return self.conn.execute(query).fetchall()

    def get_profession(self, profession_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM professions WHERE id = ?", (profession_id,)).fetchone()

    def add_profession(self, title: str) -> None:
        self.conn.execute(
            """
            INSERT INTO professions(title, is_active, created_at)
            VALUES (?, 1, ?)
            ON CONFLICT(title) DO UPDATE SET is_active = 1
            """,
            (title, now_iso()),
        )
        self.conn.commit()

    def update_profession(self, profession_id: int, title: str) -> None:
        old = self.get_profession(profession_id)
        self.conn.execute("UPDATE professions SET title = ? WHERE id = ?", (title, profession_id))
        if old:
            self.conn.execute(
                "UPDATE seekers SET profession_title = ? WHERE profession_id = ?",
                (title, profession_id),
            )
            self.conn.execute(
                "UPDATE vacancies SET profession_title = ? WHERE profession_id = ?",
                (title, profession_id),
            )
        self.conn.commit()

    def delete_profession(self, profession_id: int) -> None:
        self.conn.execute("UPDATE professions SET is_active = 0 WHERE id = ?", (profession_id,))
        self.conn.commit()

    def save_seeker(self, telegram_id: int, data: dict[str, Any]) -> int:
        stamp = now_iso()
        self.conn.execute(
            """
            INSERT INTO seekers(
                telegram_id, photo_id, full_name, age, gender, phone, region, district, address,
                birth_date, profession_id, profession_title, job_type, experience, experience_years,
                education, excel_level, word_level, previous_job,
                previous_salary, previous_salary_amount, current_salary, current_salary_amount,
                salary, salary_amount, extra, resume_file_id, resume_file_name,
                moderation_status, moderation_note, moderated_by, approved_at, published_at,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, NULL, NULL, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                photo_id = excluded.photo_id,
                full_name = excluded.full_name,
                age = excluded.age,
                gender = excluded.gender,
                phone = excluded.phone,
                region = excluded.region,
                district = excluded.district,
                address = excluded.address,
                birth_date = excluded.birth_date,
                profession_id = excluded.profession_id,
                profession_title = excluded.profession_title,
                job_type = excluded.job_type,
                experience = excluded.experience,
                experience_years = excluded.experience_years,
                education = excluded.education,
                excel_level = excluded.excel_level,
                word_level = excluded.word_level,
                previous_job = excluded.previous_job,
                previous_salary = excluded.previous_salary,
                previous_salary_amount = excluded.previous_salary_amount,
                current_salary = excluded.current_salary,
                current_salary_amount = excluded.current_salary_amount,
                salary = excluded.salary,
                extra = excluded.extra,
                resume_file_id = excluded.resume_file_id,
                resume_file_name = excluded.resume_file_name,
                salary_amount = excluded.salary_amount,
                moderation_status = 'pending',
                moderation_note = NULL,
                moderated_by = NULL,
                approved_at = NULL,
                published_at = NULL,
                updated_at = excluded.updated_at
            """,
            (
                telegram_id,
                data["photo_id"],
                data["full_name"],
                int(data["age"]),
                data["gender"],
                data["phone"],
                data["region"],
                data.get("district"),
                data.get("address"),
                data.get("birth_date"),
                data.get("profession_id"),
                data["profession_title"],
                data.get("job_type"),
                data["experience"],
                data.get("experience_years"),
                data.get("education"),
                data.get("excel_level"),
                data.get("word_level"),
                data["previous_job"],
                data.get("previous_salary"),
                data.get("previous_salary_amount"),
                data.get("current_salary"),
                data.get("current_salary_amount"),
                data.get("salary") or data.get("current_salary"),
                data.get("salary_amount") or data.get("current_salary_amount"),
                data.get("extra"),
                data.get("resume_file_id"),
                data.get("resume_file_name"),
                stamp,
                stamp,
            ),
        )
        self.set_user_role(telegram_id, "seeker")
        self.conn.commit()
        row = self.conn.execute("SELECT id FROM seekers WHERE telegram_id = ?", (telegram_id,)).fetchone()
        return int(row["id"])

    def get_seeker(self, seeker_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM seekers WHERE id = ?", (seeker_id,)).fetchone()

    def get_seeker_by_tg(self, telegram_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM seekers WHERE telegram_id = ?", (telegram_id,)).fetchone()

    def update_seeker_field(self, telegram_id: int, field: str, value: Any) -> None:
        allowed = {
            "photo_id",
            "full_name",
            "age",
            "birth_date",
            "gender",
            "phone",
            "region",
            "district",
            "address",
            "profession_id",
            "profession_title",
            "job_type",
            "experience",
            "experience_years",
            "education",
            "excel_level",
            "word_level",
            "previous_job",
            "previous_salary",
            "previous_salary_amount",
            "current_salary",
            "current_salary_amount",
            "salary",
            "salary_amount",
            "extra",
            "resume_file_id",
            "resume_file_name",
        }
        if field not in allowed:
            raise ValueError(f"Unsupported seeker field: {field}")
        self.conn.execute(
            f"""
            UPDATE seekers
            SET {field} = ?,
                moderation_status = 'pending',
                moderation_note = NULL,
                moderated_by = NULL,
                approved_at = NULL,
                published_at = NULL,
                updated_at = ?
            WHERE telegram_id = ?
            """,
            (value, now_iso(), telegram_id),
        )
        self.conn.commit()

    def update_seeker_profession(self, telegram_id: int, profession_id: int, profession_title: str) -> None:
        stamp = now_iso()
        self.conn.execute(
            """
            UPDATE seekers
            SET profession_id = ?,
                profession_title = ?,
                moderation_status = 'pending',
                moderation_note = NULL,
                moderated_by = NULL,
                approved_at = NULL,
                published_at = NULL,
                updated_at = ?
            WHERE telegram_id = ?
            """,
            (profession_id, profession_title, stamp, telegram_id),
        )
        self.conn.commit()

    def set_seeker_moderation_status(
        self,
        seeker_id: int,
        status: str,
        note: str | None = None,
        moderated_by: int | None = None,
    ) -> None:
        stamp = now_iso()
        approved_at = stamp if status == "approved" else None
        self.conn.execute(
            """
            UPDATE seekers
            SET moderation_status = ?,
                moderation_note = ?,
                moderated_by = ?,
                approved_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (status, note, moderated_by, approved_at, stamp, seeker_id),
        )
        self.conn.commit()

    def set_seeker_moderation_status_if_pending(
        self,
        seeker_id: int,
        status: str,
        note: str | None = None,
        moderated_by: int | None = None,
    ) -> bool:
        stamp = now_iso()
        approved_at = stamp if status == "approved" else None
        cur = self.conn.execute(
            """
            UPDATE seekers
            SET moderation_status = ?,
                moderation_note = ?,
                moderated_by = ?,
                approved_at = ?,
                updated_at = ?
            WHERE id = ? AND moderation_status = 'pending'
            """,
            (status, note, moderated_by, approved_at, stamp, seeker_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def mark_seeker_published(
        self,
        seeker_id: int,
        channel_chat_id: str | None = None,
        channel_message_id: int | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE seekers
            SET published_at = ?,
                channel_chat_id = COALESCE(?, channel_chat_id),
                channel_message_id = COALESCE(?, channel_message_id),
                updated_at = ?
            WHERE id = ?
            """,
            (now_iso(), channel_chat_id, channel_message_id, now_iso(), seeker_id),
        )
        self.conn.commit()

    def list_pending_seekers(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM seekers WHERE moderation_status = 'pending' ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def save_employer(self, telegram_id: int, data: dict[str, Any]) -> int:
        stamp = now_iso()
        self.conn.execute(
            """
            INSERT INTO employers(telegram_id, full_name, organization, phone, region, district, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                full_name = excluded.full_name,
                organization = excluded.organization,
                phone = excluded.phone,
                region = excluded.region,
                district = excluded.district,
                updated_at = excluded.updated_at
            """,
            (
                telegram_id,
                data["full_name"],
                data["organization"],
                data["phone"],
                data["region"],
                data.get("district"),
                stamp,
                stamp,
            ),
        )
        self.set_user_role(telegram_id, "employer")
        self.conn.commit()
        row = self.conn.execute("SELECT id FROM employers WHERE telegram_id = ?", (telegram_id,)).fetchone()
        return int(row["id"])

    def save_vacancy(self, employer_tg_id: int, data: dict[str, Any]) -> int:
        stamp = now_iso()
        cur = self.conn.execute(
            """
            INSERT INTO vacancies(
                employer_tg_id, full_name, organization, phone, region, district, profession_id,
                profession_title, staff_count, job_type, salary, salary_amount,
                min_experience_years, requirements, expires_at,
                moderation_status, moderation_note, moderated_by, approved_at, published_at,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', NULL, NULL, NULL, NULL, ?, ?)
            """,
            (
                employer_tg_id,
                data["full_name"],
                data["organization"],
                data["phone"],
                data["region"],
                data.get("district"),
                data.get("profession_id"),
                data["profession_title"],
                int(data["staff_count"]),
                data["job_type"],
                data["salary"],
                data.get("salary_amount"),
                data.get("min_experience_years"),
                data["requirements"],
                data.get("expires_at") or days_from_now_iso(30),
                stamp,
                stamp,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_vacancy(self, vacancy_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM vacancies WHERE id = ?", (vacancy_id,)).fetchone()

    def list_vacancies(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM vacancies ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def list_vacancies_by_employer(self, employer_tg_id: int, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM vacancies WHERE employer_tg_id = ? ORDER BY id DESC LIMIT ?",
            (employer_tg_id, limit),
        ).fetchall()

    def count_vacancies_since(self, employer_tg_id: int, since_iso: str) -> int:
        return int(
            self.conn.execute(
                "SELECT COUNT(*) FROM vacancies WHERE employer_tg_id = ? AND created_at >= ?",
                (employer_tg_id, since_iso),
            ).fetchone()[0]
        )

    def count_seeker_updates_since(self, telegram_id: int, since_iso: str) -> int:
        return int(
            self.conn.execute(
                "SELECT COUNT(*) FROM seekers WHERE telegram_id = ? AND updated_at >= ?",
                (telegram_id, since_iso),
            ).fetchone()[0]
        )

    def delete_vacancy(self, vacancy_id: int) -> None:
        self.conn.execute("DELETE FROM vacancies WHERE id = ?", (vacancy_id,))
        self.conn.commit()

    def update_vacancy_field(self, vacancy_id: int, field: str, value: Any) -> None:
        allowed = {
            "organization",
            "phone",
            "region",
            "district",
            "profession_id",
            "profession_title",
            "staff_count",
            "job_type",
            "salary",
            "salary_amount",
            "min_experience_years",
            "requirements",
            "active",
            "moderation_status",
            "moderation_note",
            "moderated_by",
            "approved_at",
            "published_at",
            "expires_at",
        }
        if field not in allowed:
            raise ValueError(f"Unsupported vacancy field: {field}")
        self.conn.execute(
            f"UPDATE vacancies SET {field} = ?, updated_at = ? WHERE id = ?",
            (value, now_iso(), vacancy_id),
        )
        self.conn.commit()

    def set_vacancy_moderation_status(
        self,
        vacancy_id: int,
        status: str,
        note: str | None = None,
        moderated_by: int | None = None,
    ) -> None:
        stamp = now_iso()
        approved_at = stamp if status == "approved" else None
        self.conn.execute(
            """
            UPDATE vacancies
            SET moderation_status = ?,
                moderation_note = ?,
                moderated_by = ?,
                approved_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (status, note, moderated_by, approved_at, stamp, vacancy_id),
        )
        self.conn.commit()

    def set_vacancy_moderation_status_if_pending(
        self,
        vacancy_id: int,
        status: str,
        note: str | None = None,
        moderated_by: int | None = None,
    ) -> bool:
        stamp = now_iso()
        approved_at = stamp if status == "approved" else None
        cur = self.conn.execute(
            """
            UPDATE vacancies
            SET moderation_status = ?,
                moderation_note = ?,
                moderated_by = ?,
                approved_at = ?,
                updated_at = ?
            WHERE id = ? AND moderation_status = 'pending'
            """,
            (status, note, moderated_by, approved_at, stamp, vacancy_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def mark_vacancy_published(
        self,
        vacancy_id: int,
        channel_chat_id: str | None = None,
        channel_message_id: int | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE vacancies
            SET published_at = ?,
                channel_chat_id = COALESCE(?, channel_chat_id),
                channel_message_id = COALESCE(?, channel_message_id),
                updated_at = ?
            WHERE id = ?
            """,
            (now_iso(), channel_chat_id, channel_message_id, now_iso(), vacancy_id),
        )
        self.conn.commit()

    def list_pending_vacancies(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM vacancies WHERE moderation_status = 'pending' ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def find_seekers_by_profession(self, profession_id: int | None, profession_title: str) -> list[sqlite3.Row]:
        if profession_id is not None:
            rows = self.conn.execute(
                """
                SELECT * FROM seekers
                WHERE profession_id = ? AND moderation_status = 'approved'
                ORDER BY id DESC
                """,
                (profession_id,),
            ).fetchall()
            if rows:
                return rows
        return self.conn.execute(
            """
            SELECT * FROM seekers
            WHERE profession_title = ? AND moderation_status = 'approved'
            ORDER BY id DESC
            """,
            (profession_title,),
        ).fetchall()

    def find_vacancies_by_profession(self, profession_id: int | None, profession_title: str) -> list[sqlite3.Row]:
        if profession_id is not None:
            rows = self.conn.execute(
                """
                SELECT * FROM vacancies
                WHERE profession_id = ?
                    AND moderation_status = 'approved'
                    AND active = 1
                    AND (expires_at IS NULL OR expires_at >= ?)
                ORDER BY id DESC
                """,
                (profession_id, now_iso()),
            ).fetchall()
            if rows:
                return rows
        return self.conn.execute(
            """
            SELECT * FROM vacancies
            WHERE profession_title = ?
                AND moderation_status = 'approved'
                AND active = 1
                AND (expires_at IS NULL OR expires_at >= ?)
            ORDER BY id DESC
            """,
            (profession_title, now_iso()),
        ).fetchall()

    def save_candidate_action(self, employer_tg_id: int, vacancy_id: int, seeker_id: int, status: str) -> None:
        stamp = now_iso()
        self.conn.execute(
            """
            INSERT INTO candidate_actions(employer_tg_id, vacancy_id, seeker_id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(employer_tg_id, vacancy_id, seeker_id) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (employer_tg_id, vacancy_id, seeker_id, status, stamp, stamp),
        )
        self.conn.commit()

    def create_interest(
        self,
        vacancy_id: int,
        seeker_id: int,
        employer_tg_id: int,
        seeker_tg_id: int,
        status: str = "pending",
    ) -> int:
        stamp = now_iso()
        self.conn.execute(
            """
            INSERT INTO interests(vacancy_id, seeker_id, employer_tg_id, seeker_tg_id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(vacancy_id, seeker_id) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (vacancy_id, seeker_id, employer_tg_id, seeker_tg_id, status, stamp, stamp),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM interests WHERE vacancy_id = ? AND seeker_id = ?",
            (vacancy_id, seeker_id),
        ).fetchone()
        return int(row["id"])

    def get_interest(self, interest_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM interests WHERE id = ?", (interest_id,)).fetchone()

    def update_interest_status(self, interest_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE interests SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_iso(), interest_id),
        )
        self.conn.commit()

    def dashboard_counts(self) -> dict[str, int]:
        keys = {
            "seekers": "SELECT COUNT(*) FROM seekers",
            "employers": "SELECT COUNT(*) FROM employers",
            "vacancies": "SELECT COUNT(*) FROM vacancies",
            "interests": "SELECT COUNT(*) FROM interests",
            "users": "SELECT COUNT(*) FROM users",
            "admins": "SELECT COUNT(*) FROM admins",
            "pending_seekers": "SELECT COUNT(*) FROM seekers WHERE moderation_status = 'pending'",
            "pending_vacancies": "SELECT COUNT(*) FROM vacancies WHERE moderation_status = 'pending'",
            "expired_vacancies": "SELECT COUNT(*) FROM vacancies WHERE moderation_status = 'expired'",
        }
        return {key: int(self.conn.execute(query).fetchone()[0]) for key, query in keys.items()}

    def broadcast_users(self, target: str) -> list[int]:
        if target == "seekers":
            rows = self.conn.execute("SELECT telegram_id FROM seekers").fetchall()
            return [int(row["telegram_id"]) for row in rows]
        if target == "employers":
            rows = self.conn.execute("SELECT telegram_id FROM employers").fetchall()
            return [int(row["telegram_id"]) for row in rows]
        rows = self.conn.execute("SELECT tg_id FROM users").fetchall()
        return [int(row["tg_id"]) for row in rows]

    def filter_seekers(self, filters: dict[str, Any] | None = None) -> list[sqlite3.Row]:
        filters = filters or {}
        clauses: list[str] = []
        params: list[Any] = []

        if filters.get("gender"):
            clauses.append("gender = ?")
            params.append(filters["gender"])
        if filters.get("region"):
            clauses.append("region = ?")
            params.append(filters["region"])
        if filters.get("district"):
            clauses.append("district = ?")
            params.append(filters["district"])
        if filters.get("profession_id"):
            clauses.append("profession_id = ?")
            params.append(filters["profession_id"])
        if filters.get("age_min") is not None:
            clauses.append("age >= ?")
            params.append(filters["age_min"])
        if filters.get("age_max") is not None:
            clauses.append("age <= ?")
            params.append(filters["age_max"])
        if filters.get("experience"):
            clauses.append("experience LIKE ?")
            params.append(f"%{filters['experience']}%")
        if filters.get("job_type"):
            clauses.append("(job_type = ? OR job_type = 'Farqi yo''q')")
            params.append(filters["job_type"])
        if filters.get("experience_years_min") is not None:
            clauses.append("experience_years >= ?")
            params.append(filters["experience_years_min"])
        if filters.get("salary_min") is not None:
            clauses.append("salary_amount >= ?")
            params.append(filters["salary_min"])
        if filters.get("salary_max") is not None:
            clauses.append("salary_amount <= ?")
            params.append(filters["salary_max"])
        if filters.get("moderation_status"):
            clauses.append("moderation_status = ?")
            params.append(filters["moderation_status"])

        query = "SELECT * FROM seekers"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY id DESC"
        return self.conn.execute(query, params).fetchall()

    def all_users(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()

    def all_seekers(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM seekers ORDER BY id DESC").fetchall()

    def all_vacancies(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM vacancies ORDER BY id DESC").fetchall()

    def all_employers(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM employers ORDER BY id DESC").fetchall()

    def all_interests(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM interests ORDER BY id DESC").fetchall()

    def all_candidate_actions(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM candidate_actions ORDER BY id DESC").fetchall()

    def search_admin(self, query: str, limit: int = 10) -> dict[str, list[sqlite3.Row]]:
        query = query.strip()
        like = f"%{query}%"
        numeric = int(query) if query.isdigit() else None

        seeker_clauses = ["full_name LIKE ?", "phone LIKE ?", "region LIKE ?", "district LIKE ?", "profession_title LIKE ?"]
        seeker_params: list[Any] = [like, like, like, like, like]
        if numeric is not None:
            seeker_clauses.extend(["id = ?", "telegram_id = ?", "age = ?"])
            seeker_params.extend([numeric, numeric, numeric])

        vacancy_clauses = [
            "organization LIKE ?",
            "full_name LIKE ?",
            "phone LIKE ?",
            "region LIKE ?",
            "district LIKE ?",
            "profession_title LIKE ?",
        ]
        vacancy_params: list[Any] = [like, like, like, like, like, like]
        if numeric is not None:
            vacancy_clauses.extend(["id = ?", "employer_tg_id = ?"])
            vacancy_params.extend([numeric, numeric])

        employer_clauses = ["full_name LIKE ?", "organization LIKE ?", "phone LIKE ?", "region LIKE ?", "district LIKE ?"]
        employer_params: list[Any] = [like, like, like, like, like]
        if numeric is not None:
            employer_clauses.extend(["id = ?", "telegram_id = ?"])
            employer_params.extend([numeric, numeric])

        return {
            "seekers": self.conn.execute(
                f"SELECT * FROM seekers WHERE {' OR '.join(seeker_clauses)} ORDER BY id DESC LIMIT ?",
                (*seeker_params, limit),
            ).fetchall(),
            "vacancies": self.conn.execute(
                f"SELECT * FROM vacancies WHERE {' OR '.join(vacancy_clauses)} ORDER BY id DESC LIMIT ?",
                (*vacancy_params, limit),
            ).fetchall(),
            "employers": self.conn.execute(
                f"SELECT * FROM employers WHERE {' OR '.join(employer_clauses)} ORDER BY id DESC LIMIT ?",
                (*employer_params, limit),
            ).fetchall(),
        }


db = Database()
