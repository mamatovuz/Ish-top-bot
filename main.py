import asyncio
import html
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMIN_IDS, BOT_TOKEN, PUBLIC_CHANNEL_ID, is_admin as is_env_admin
from database import db
from keyboards import (
    CANCEL,
    SKIP,
    admin_export_keyboard,
    admin_moderation_keyboard,
    admin_menu,
    admin_professions_keyboard,
    admin_subscription_keyboard,
    admin_users_keyboard,
    broadcast_preview_keyboard,
    broadcast_target_keyboard,
    candidate_filter_keyboard,
    candidate_offer_keyboard,
    cancel_menu,
    contact_menu,
    districts_menu,
    education_keyboard,
    employer_candidate_keyboard,
    gender_menu,
    job_type_keyboard,
    main_menu,
    matched_vacancy_keyboard,
    my_vacancy_keyboard,
    profession_keyboard,
    regions_menu,
    seeker_confirm_keyboard,
    seeker_edit_job_type_keyboard,
    seeker_job_type_keyboard,
    seeker_edit_fields_keyboard,
    seeker_moderation_keyboard,
    seeker_profile_keyboard,
    skill_level_keyboard,
    skip_menu,
    skip_inline_keyboard,
    subscription_keyboard,
    vacancy_admin_keyboard,
    vacancy_confirm_keyboard,
    vacancy_edit_fields_keyboard,
    vacancy_moderation_keyboard,
    employer_candidate_request_keyboard,
)
from locations import DISTRICTS, REGIONS


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    return is_env_admin(user_id) or db.is_admin(user_id)


def menu_for(user_id: int):
    return main_menu(is_admin=is_admin(user_id))


class SeekerForm(StatesGroup):
    photo = State()
    full_name = State()
    birth_date = State()
    gender = State()
    phone = State()
    region = State()
    district = State()
    profession = State()
    job_type = State()
    experience = State()
    education = State()
    excel_level = State()
    word_level = State()
    previous_job = State()
    previous_salary = State()
    current_salary = State()
    extra = State()
    resume = State()
    confirm = State()


class VacancyForm(StatesGroup):
    full_name = State()
    organization = State()
    phone = State()
    region = State()
    district = State()
    profession = State()
    staff_count = State()
    job_type = State()
    salary = State()
    requirements = State()
    confirm = State()


class AdminChannelForm(StatesGroup):
    channel = State()


class AdminProfessionForm(StatesGroup):
    add_title = State()
    edit_title = State()


class AdminUserForm(StatesGroup):
    add_id = State()


class BroadcastForm(StatesGroup):
    message = State()


class AdminCandidateFilter(StatesGroup):
    menu = State()
    gender = State()
    age = State()
    region = State()
    district = State()
    experience = State()
    profession = State()
    job_type = State()
    salary = State()


class AdminVacancyEdit(StatesGroup):
    value = State()
    profession = State()


class SeekerEditForm(StatesGroup):
    value = State()
    district = State()
    profession = State()
    resume = State()


class AdminModerationReason(StatesGroup):
    seeker_reason = State()
    vacancy_reason = State()


class AdminSearchForm(StatesGroup):
    query = State()


def clean_text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    value = str(value).strip()
    return value if value else default


def esc(value: Any, default: str = "-") -> str:
    return html.escape(clean_text(value, default))


def row_get(row: Any, key: str, default: Any = "") -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        value = row[key]
    except (KeyError, IndexError):
        return default
    return default if value is None else value


def is_valid_region(value: Any) -> bool:
    return clean_text(value, "") in REGIONS


def is_valid_district(region: Any, district: Any) -> bool:
    region_text = clean_text(region, "")
    district_text = clean_text(district, "")
    return district_text in DISTRICTS.get(region_text, [])


def location_text(row: Any) -> str:
    region = clean_text(row_get(row, "region"), "")
    district = clean_text(row_get(row, "district"), "")
    if region and district:
        return f"{region}, {district}"
    return region or district or "-"


def location_from_data(data: dict[str, Any]) -> str:
    region = clean_text(data.get("region"), "")
    district = clean_text(data.get("district"), "")
    if region and district:
        return f"{region}, {district}"
    return region or district or "-"


def parse_positive_int(text: str, *, minimum: int = 1, maximum: int = 1000) -> int | None:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return None
    value = int(digits)
    if minimum <= value <= maximum:
        return value
    return None


def extract_phone(message: Message) -> str:
    return clean_text(message.text)


def normalize_phone(text: Any) -> str | None:
    raw = clean_text(text, "")
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("998") and len(digits) == 12:
        return "+" + digits
    if len(digits) == 9:
        return "+998" + digits
    if 10 <= len(digits) <= 13:
        return "+" + digits
    return None


def parse_money_amount(text: Any) -> int | None:
    digits = re.sub(r"\D", "", clean_text(text, ""))
    if not digits:
        return None
    amount = int(digits)
    return amount if amount > 0 else None


def parse_experience_years(text: Any) -> int:
    value = first_number(text)
    return value if value is not None else 0


def day_start_iso() -> str:
    now = datetime.now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def parse_birth_date(text: Any) -> tuple[str, int] | None:
    raw = clean_text(text, "")
    match = re.fullmatch(r"\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})\s*", raw)
    if not match:
        return None
    day, month, year = map(int, match.groups())
    try:
        birth = datetime(year, month, day)
    except ValueError:
        return None
    today = datetime.now()
    age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
    if age < 14 or age > 90:
        return None
    return birth.strftime("%d.%m.%Y"), age


def public_channel_id() -> str:
    return db.get_setting("public_channel_id", "") or PUBLIC_CHANNEL_ID


def all_admin_ids() -> set[int]:
    return set(ADMIN_IDS) | {int(row["tg_id"]) for row in db.list_admins()}


def moderation_status_text(status: str) -> str:
    return {
        "pending": "⏳ Admin tekshiruvida",
        "approved": "✅ Tasdiqlangan",
        "rejected": "❌ Rad etilgan",
        "needs_edit": "✏️ Tuzatish kerak",
        "archived": "📦 Arxivlangan",
        "expired": "⏰ Muddati tugagan",
    }.get(status, status or "-")


def vacancy_active_text(active: Any) -> str:
    return "🟢 Aktiv" if int(active or 0) == 1 else "🔴 Yopilgan"


def first_number(text: Any) -> int | None:
    numbers = re.findall(r"\d+", clean_text(text, ""))
    return int("".join(numbers)) if numbers else None


def salary_number(text: Any) -> int | None:
    return first_number(str(text).replace(" ", ""))


def match_score(seeker: Any, vacancy: Any) -> int:
    score = 0
    seeker_prof_id = row_get(seeker, "profession_id", None)
    vacancy_prof_id = row_get(vacancy, "profession_id", None)
    seeker_prof = clean_text(row_get(seeker, "profession_title"), "").lower()
    vacancy_prof = clean_text(row_get(vacancy, "profession_title"), "").lower()
    requirements = clean_text(row_get(vacancy, "requirements"), "").lower()

    if seeker_prof_id and vacancy_prof_id and seeker_prof_id == vacancy_prof_id:
        score += 35
    elif seeker_prof and (seeker_prof == vacancy_prof or seeker_prof in requirements):
        score += 25

    if clean_text(row_get(seeker, "region"), "").lower() == clean_text(row_get(vacancy, "region"), "").lower():
        score += 15
    seeker_district = clean_text(row_get(seeker, "district"), "").lower()
    vacancy_district = clean_text(row_get(vacancy, "district"), "").lower()
    if seeker_district and vacancy_district and seeker_district == vacancy_district:
        score += 10

    seeker_job_type = clean_text(row_get(seeker, "job_type"), "").lower()
    vacancy_job_type = clean_text(row_get(vacancy, "job_type"), "").lower()
    if seeker_job_type == "farqi yo'q":
        score += 8
    elif seeker_job_type and vacancy_job_type and seeker_job_type == vacancy_job_type:
        score += 12

    seeker_exp = row_get(seeker, "experience_years", None)
    required_exp = row_get(vacancy, "min_experience_years", None)
    if seeker_exp is None:
        seeker_exp = first_number(row_get(seeker, "experience"))
    if required_exp is None:
        required_exp = first_number(requirements)
    if required_exp is None and clean_text(row_get(seeker, "experience"), ""):
        score += 15
    elif seeker_exp is not None and required_exp is not None and seeker_exp >= required_exp:
        score += 15
    elif seeker_exp is not None:
        score += 8

    seeker_salary = row_get(seeker, "salary_amount", None) or salary_number(row_get(seeker, "salary"))
    vacancy_salary = row_get(vacancy, "salary_amount", None) or salary_number(row_get(vacancy, "salary"))
    if seeker_salary and vacancy_salary and seeker_salary <= vacancy_salary:
        score += 10
    elif vacancy_salary:
        score += 5

    education = clean_text(row_get(seeker, "education"), "").lower()
    if education and education != "farqi yo'q" and education in requirements:
        score += 5

    if row_get(seeker, "resume_file_id"):
        score += 8

    return min(score, 100)


def seeker_card(seeker: Any, *, hide_phone: bool = True) -> str:
    phone = "yashirilgan" if hide_phone else row_get(seeker, "phone")
    resume = "bor" if row_get(seeker, "resume_file_id") else "yo'q"
    note = row_get(seeker, "moderation_note", "")
    birth_date = row_get(seeker, "birth_date", "")
    return (
        f"📄 <b>Nomzod #{row_get(seeker, 'id')}</b>\n"
        f"👤 {esc(row_get(seeker, 'full_name'))}\n"
        f"🎂 Tug'ilgan sana: {esc(birth_date or '-')}"
        f"{' (' + esc(row_get(seeker, 'age')) + ' yosh)' if row_get(seeker, 'age') else ''}\n"
        f"🚻 {esc(row_get(seeker, 'gender'))}\n"
        f"📍 {esc(location_text(seeker))}\n"
        f"💼 {esc(row_get(seeker, 'profession_title'))}\n"
        f"🧭 Ish turi: {esc(row_get(seeker, 'job_type', 'Ko‘rsatilmagan'))}\n"
        f"📈 Tajriba: {esc(row_get(seeker, 'experience'))}\n"
        f"🔢 Tajriba yili: {esc(row_get(seeker, 'experience_years', 0))}\n"
        f"🎓 Ma'lumot: {esc(row_get(seeker, 'education', 'Ko‘rsatilmagan'))}\n"
        f"📊 Excel: {esc(row_get(seeker, 'excel_level', '-'))}\n"
        f"📝 Word: {esc(row_get(seeker, 'word_level', '-'))}\n"
        f"💸 Oldingi oylik: {esc(row_get(seeker, 'previous_salary', '-'))}\n"
        f"💰 Hozirgi kutayotgan oylik: {esc(row_get(seeker, 'current_salary', row_get(seeker, 'salary')))}\n"
        f"📞 Telefon: {esc(phone)}\n"
        f"📎 Rezyume: {esc(resume)}\n"
        f"🛂 Holat: {moderation_status_text(clean_text(row_get(seeker, 'moderation_status'), 'pending'))}\n"
        f"{'📝 Izoh: ' + esc(note) + chr(10) if note else ''}"
        f"ℹ️ Qo'shimcha: {esc(row_get(seeker, 'extra', 'Yo‘q'))}"
    )


def public_seeker_card(seeker: Any) -> str:
    resume = "bor" if row_get(seeker, "resume_file_id") else "yo'q"
    birth = row_get(seeker, "birth_date", "-")
    age = row_get(seeker, "age", "")
    birth_line = f"{esc(birth)}"
    if age:
        birth_line += f" ({esc(age)} yosh)"
    return (
        f"🆕 <b>Ish qidiruvchi</b>\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"📄 <b>Nomzod #{row_get(seeker, 'id')}</b>\n"
        f"👤 <b>{esc(row_get(seeker, 'full_name'))}</b>\n"
        f"🎂 Tug'ilgan sana: {birth_line}\n"
        f"🚻 Jins: {esc(row_get(seeker, 'gender'))}\n"
        f"📍 Hudud: {esc(location_text(seeker))}\n"
        f"💼 Kasb: {esc(row_get(seeker, 'profession_title'))}\n"
        f"🧭 Ish turi: {esc(row_get(seeker, 'job_type', '-'))}\n\n"
        f"📈 Tajriba: {esc(row_get(seeker, 'experience'))}\n"
        f"🎓 Ma'lumot: {esc(row_get(seeker, 'education', '-'))}\n"
        f"📊 Excel: {esc(row_get(seeker, 'excel_level', '-'))}\n"
        f"📝 Word: {esc(row_get(seeker, 'word_level', '-'))}\n\n"
        f"💸 Oldingi oylik: {esc(row_get(seeker, 'previous_salary', '-'))}\n"
        f"💰 Hozirgi kutayotgan oylik: {esc(row_get(seeker, 'current_salary', row_get(seeker, 'salary')))}\n"
        f"📞 Aloqa: {esc(row_get(seeker, 'phone'))}\n"
        f"📎 Rezyume: {esc(resume)}\n\n"
        f"ℹ️ Qo'shimcha: {esc(row_get(seeker, 'extra', 'Yo‘q'))}"
    )


def seeker_match_card(seeker: Any) -> str:
    birth = row_get(seeker, "birth_date", "-")
    age = row_get(seeker, "age", "")
    birth_line = f"{esc(birth)}"
    if age:
        birth_line += f" ({esc(age)} yosh)"
    return (
        f"📄 <b>Nomzod #{row_get(seeker, 'id')}</b>\n"
        f"👤 <b>{esc(row_get(seeker, 'full_name'))}</b>\n"
        f"🎂 Tug'ilgan sana: {birth_line}\n"
        f"📍 Hudud: {esc(location_text(seeker))}\n"
        f"💼 Kasb: {esc(row_get(seeker, 'profession_title'))}\n"
        f"🧭 Ish turi: {esc(row_get(seeker, 'job_type', '-'))}\n"
        f"📈 Tajriba: {esc(row_get(seeker, 'experience'))}\n"
        f"🎓 Ma'lumot: {esc(row_get(seeker, 'education', '-'))}\n"
        f"📊 Excel: {esc(row_get(seeker, 'excel_level', '-'))}\n"
        f"📝 Word: {esc(row_get(seeker, 'word_level', '-'))}\n"
        f"📞 Telefon: yashirilgan"
    )


def vacancy_card(vacancy: Any) -> str:
    note = row_get(vacancy, "moderation_note", "")
    return (
        f"🏢 <b>Vakansiya #{row_get(vacancy, 'id')}</b>\n"
        f"👤 Mas'ul: {esc(row_get(vacancy, 'full_name'))}\n"
        f"🏢 Tashkilot: {esc(row_get(vacancy, 'organization'))}\n"
        f"📞 Telefon: {esc(row_get(vacancy, 'phone'))}\n"
        f"📍 Hudud: {esc(location_text(vacancy))}\n"
        f"💼 Mutaxassislik: {esc(row_get(vacancy, 'profession_title'))}\n"
        f"👥 Xodim soni: {esc(row_get(vacancy, 'staff_count'))}\n"
        f"🧭 Ish turi: {esc(row_get(vacancy, 'job_type'))}\n"
        f"💰 Maosh: {esc(row_get(vacancy, 'salary'))}\n"
        f"🔢 Minimal tajriba: {esc(row_get(vacancy, 'min_experience_years', 0))} yil\n"
        f"📌 Holat: {vacancy_active_text(row_get(vacancy, 'active'))}\n"
        f"🛂 Moderatsiya: {moderation_status_text(clean_text(row_get(vacancy, 'moderation_status'), 'pending'))}\n"
        f"⏰ Muddati: {esc(row_get(vacancy, 'expires_at', '30 kun'))}\n"
        f"{'📝 Izoh: ' + esc(note) + chr(10) if note else ''}"
        f"📌 Talablar: {esc(row_get(vacancy, 'requirements'))}"
    )


def public_vacancy_card(vacancy: Any) -> str:
    organization = clean_text(row_get(vacancy, "organization"), "Ko'rsatilmagan")
    return (
        f"🆕 <b>Vakansiya</b>\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"📌 <b>Vakansiya #{row_get(vacancy, 'id')}</b>\n"
        f"🏢 Tashkilot: <b>{esc(organization)}</b>\n"
        f"👤 Mas'ul: {esc(row_get(vacancy, 'full_name'))}\n"
        f"📍 Hudud: {esc(location_text(vacancy))}\n"
        f"💼 Mutaxassislik: {esc(row_get(vacancy, 'profession_title'))}\n"
        f"👥 Kerakli xodim: {esc(row_get(vacancy, 'staff_count'))}\n"
        f"🧭 Ish turi: {esc(row_get(vacancy, 'job_type'))}\n\n"
        f"💰 Maosh: {esc(row_get(vacancy, 'salary'))}\n"
        f"📈 Minimal tajriba: {esc(row_get(vacancy, 'min_experience_years', 0))} yil\n"
        f"📞 Aloqa: {esc(row_get(vacancy, 'phone'))}\n\n"
        f"📋 Talablar:\n{esc(row_get(vacancy, 'requirements'))}"
    )


def seeker_summary(data: dict[str, Any]) -> str:
    return (
        "📋 <b>Arizani tekshiring</b>\n\n"
        f"👤 Ism familiya: {esc(data.get('full_name'))}\n"
        f"🎂 Tug'ilgan sana: {esc(data.get('birth_date'))} ({esc(data.get('age'))} yosh)\n"
        f"🚻 Jins: {esc(data.get('gender'))}\n"
        f"📞 Telefon: {esc(data.get('phone'))}\n"
        f"📍 Hudud: {esc(location_from_data(data))}\n"
        f"💼 Kasb: {esc(data.get('profession_title'))}\n"
        f"🧭 Ish turi: {esc(data.get('job_type'))}\n"
        f"📈 Tajriba: {esc(data.get('experience'))}\n"
        f"🔢 Tajriba yili: {esc(data.get('experience_years'))}\n"
        f"🎓 Ma'lumot: {esc(data.get('education'))}\n"
        f"📊 Excel: {esc(data.get('excel_level'))}\n"
        f"📝 Word: {esc(data.get('word_level'))}\n"
        f"🏢 Oldingi ish joyi: {esc(data.get('previous_job'))}\n"
        f"💸 Oldingi ish joyidagi oylik: {esc(data.get('previous_salary'))}\n"
        f"💰 Hozir olayotgan oylik: {esc(data.get('current_salary'))}\n"
        f"📎 Rezyume: {'bor' if data.get('resume_file_id') else 'yo‘q'}\n"
        f"ℹ️ Qo'shimcha: {esc(data.get('extra'))}"
    )


def vacancy_summary(data: dict[str, Any]) -> str:
    return (
        "📋 <b>Vakansiyani tekshiring</b>\n\n"
        f"👤 Ism familiya: {esc(data.get('full_name'))}\n"
        f"🏢 Tashkilot: {esc(data.get('organization'))}\n"
        f"📞 Telefon: {esc(data.get('phone'))}\n"
        f"📍 Hudud: {esc(location_from_data(data))}\n"
        f"💼 Mutaxassislik: {esc(data.get('profession_title'))}\n"
        f"👥 Kerakli xodim: {esc(data.get('staff_count'))}\n"
        f"🧭 Ish turi: {esc(data.get('job_type'))}\n"
        f"💰 Maosh: {esc(data.get('salary'))}\n"
        f"🔢 Minimal tajriba: {esc(data.get('min_experience_years', 0))} yil\n"
        f"📌 Talablar: {esc(data.get('requirements'))}"
    )


async def check_user_subscription(bot: Bot, user_id: int) -> bool:
    channels = db.list_channels()
    if not channels:
        return True
    for channel in channels:
        try:
            member = await bot.get_chat_member(channel["chat_id"], user_id)
        except Exception as exc:
            logger.warning("Subscription check failed for %s: %s", channel["chat_id"], exc)
            return False
        if member.status not in {"creator", "administrator", "member"}:
            return False
    return True


async def send_subscription_prompt(message: Message) -> None:
    channels = db.list_channels()
    if not channels:
        await message.answer(
            "🔐 Majburiy obuna yoqilgan, ammo admin hali kanal qo'shmagan.\n\n"
            "Iltimos, admin bilan bog'laning."
        )
        return
    await message.answer(
        "🔐 <b>Majburiy obuna</b>\n\n"
        "Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling.\n"
        "Obuna bo'lgach, <b>✅ Tekshirish</b> tugmasini bosing.",
        reply_markup=subscription_keyboard(channels),
    )


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if not user or is_admin(user.id):
            return await handler(event, data)

        if isinstance(event, Message):
            if event.text and event.text.startswith("/start"):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            if event.data == "check_sub":
                return await handler(event, data)

        if db.force_subscription_enabled() and not await check_user_subscription(data["bot"], user.id):
            if isinstance(event, Message):
                await send_subscription_prompt(event)
            elif isinstance(event, CallbackQuery):
                await event.answer("Avval kanallarga obuna bo'ling.", show_alert=True)
                if event.message:
                    await send_subscription_prompt(event.message)
            return None

        return await handler(event, data)


async def publish_seeker(bot: Bot, seeker: Any) -> None:
    channel_id = public_channel_id()
    if not channel_id:
        return
    try:
        caption = public_seeker_card(seeker)
        message_id = row_get(seeker, "channel_message_id", None)
        chat_id = row_get(seeker, "channel_chat_id", None) or channel_id
        if message_id:
            try:
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=int(message_id),
                    caption=caption,
                )
                db.mark_seeker_published(int(row_get(seeker, "id")), str(chat_id), int(message_id))
            except Exception as exc:
                logger.warning("Failed to edit seeker post, sending new: %s", exc)
                sent = await bot.send_photo(chat_id=channel_id, photo=row_get(seeker, "photo_id"), caption=caption)
                db.mark_seeker_published(int(row_get(seeker, "id")), str(channel_id), sent.message_id)
        else:
            sent = await bot.send_photo(chat_id=channel_id, photo=row_get(seeker, "photo_id"), caption=caption)
            db.mark_seeker_published(int(row_get(seeker, "id")), str(channel_id), sent.message_id)
        if row_get(seeker, "resume_file_id"):
            await bot.send_document(
                chat_id=channel_id,
                document=row_get(seeker, "resume_file_id"),
                caption=f"📎 Nomzod #{row_get(seeker, 'id')} rezyumesi",
            )
    except Exception as exc:
        logger.warning("Failed to publish seeker: %s", exc)


async def publish_vacancy(bot: Bot, vacancy: Any) -> None:
    channel_id = public_channel_id()
    if not channel_id:
        return
    try:
        text = public_vacancy_card(vacancy)
        message_id = row_get(vacancy, "channel_message_id", None)
        chat_id = row_get(vacancy, "channel_chat_id", None) or channel_id
        if message_id:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=int(message_id),
                    text=text,
                )
                db.mark_vacancy_published(int(row_get(vacancy, "id")), str(chat_id), int(message_id))
            except Exception as exc:
                logger.warning("Failed to edit vacancy post, sending new: %s", exc)
                sent = await bot.send_message(chat_id=channel_id, text=text)
                db.mark_vacancy_published(int(row_get(vacancy, "id")), str(channel_id), sent.message_id)
        else:
            sent = await bot.send_message(chat_id=channel_id, text=text)
            db.mark_vacancy_published(int(row_get(vacancy, "id")), str(channel_id), sent.message_id)
    except Exception as exc:
        logger.warning("Failed to publish vacancy: %s", exc)


async def send_to_admins(bot: Bot, text: str, **kwargs) -> None:
    for admin_id in all_admin_ids():
        try:
            await bot.send_message(admin_id, text, **kwargs)
        except Exception as exc:
            logger.warning("Failed to send admin message to %s: %s", admin_id, exc)


async def send_seeker_moderation_to_admins(bot: Bot, seeker: Any) -> None:
    for admin_id in all_admin_ids():
        try:
            sent = await bot.send_photo(
                admin_id,
                photo=row_get(seeker, "photo_id"),
                caption="🛂 <b>Yangi ariza moderatsiyada</b>\n\n" + seeker_card(seeker, hide_phone=False),
                reply_markup=seeker_moderation_keyboard(int(row_get(seeker, "id"))),
            )
            db.save_moderation_message(
                "seeker",
                int(row_get(seeker, "id")),
                admin_id,
                sent.chat.id,
                sent.message_id,
            )
            if row_get(seeker, "resume_file_id"):
                doc = await bot.send_document(
                    admin_id,
                    document=row_get(seeker, "resume_file_id"),
                    caption=f"📎 Nomzod #{row_get(seeker, 'id')} rezyumesi",
                )
                db.save_moderation_message(
                    "seeker",
                    int(row_get(seeker, "id")),
                    admin_id,
                    doc.chat.id,
                    doc.message_id,
                )
        except Exception as exc:
            logger.warning("Failed to send seeker moderation to %s: %s", admin_id, exc)


async def send_vacancy_moderation_to_admins(bot: Bot, vacancy: Any) -> None:
    for admin_id in all_admin_ids():
        try:
            sent = await bot.send_message(
                admin_id,
                "🛂 <b>Yangi vakansiya moderatsiyada</b>\n\n" + vacancy_card(vacancy),
                reply_markup=vacancy_moderation_keyboard(int(row_get(vacancy, "id"))),
            )
            db.save_moderation_message(
                "vacancy",
                int(row_get(vacancy, "id")),
                admin_id,
                sent.chat.id,
                sent.message_id,
            )
        except Exception as exc:
            logger.warning("Failed to send vacancy moderation to %s: %s", admin_id, exc)


async def safe_clear_reply_markup(message: Message | None) -> None:
    if not message:
        return
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception as exc:
        logger.warning("Failed to clear reply markup: %s", exc)


async def cleanup_moderation_requests(
    bot: Bot,
    item_type: str,
    item_id: int,
    handled_by: int,
    current_message: Message | None = None,
) -> None:
    messages = db.list_moderation_messages(item_type, item_id)
    for item in messages:
        chat_id = int(row_get(item, "chat_id"))
        message_id = int(row_get(item, "message_id"))
        admin_tg_id = int(row_get(item, "admin_tg_id"))

        if current_message and chat_id == current_message.chat.id and message_id == current_message.message_id:
            await safe_clear_reply_markup(current_message)
            continue

        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as exc:
            if admin_tg_id == handled_by:
                try:
                    await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
                except Exception:
                    pass
            logger.warning("Failed to delete moderation message %s/%s: %s", chat_id, message_id, exc)

    db.delete_moderation_messages(item_type, item_id)


async def send_matches_to_employer(bot: Bot, vacancy: Any) -> None:
    if clean_text(row_get(vacancy, "moderation_status"), "pending") != "approved":
        await bot.send_message(int(row_get(vacancy, "employer_tg_id")), "Vakansiya hali admin tasdig'idan o'tmagan.")
        return
    if int(row_get(vacancy, "active", 0)) != 1:
        await bot.send_message(int(row_get(vacancy, "employer_tg_id")), "Bu vakansiya yopilgan. Avval uni faollashtiring.")
        return
    matches = db.find_seekers_by_profession(
        row_get(vacancy, "profession_id", None),
        row_get(vacancy, "profession_title"),
    )
    employer_tg_id = int(row_get(vacancy, "employer_tg_id"))
    if not matches:
        await bot.send_message(
            employer_tg_id,
            "Hozircha shu kasb bo'yicha mos nomzod topilmadi. Yangi nomzodlar qo'shilganda admin panel orqali ko'rish mumkin.",
        )
        return

    await bot.send_message(employer_tg_id, f"🔎 {len(matches)} ta mos nomzod topildi.")
    for seeker in matches:
        markup = employer_candidate_keyboard(int(row_get(vacancy, "id")), int(row_get(seeker, "id")))
        score = match_score(seeker, vacancy)
        caption = f"🎯 <b>Moslik: {score}%</b>\n\n" + seeker_match_card(seeker)
        try:
            await bot.send_photo(
                employer_tg_id,
                photo=row_get(seeker, "photo_id"),
                caption=caption,
                reply_markup=markup,
            )
        except Exception:
            await bot.send_message(
                employer_tg_id,
                caption,
                reply_markup=markup,
            )


async def send_matched_vacancies_to_seeker(bot: Bot, seeker: Any, *, limit: int = 10) -> None:
    if clean_text(row_get(seeker, "moderation_status"), "pending") != "approved":
        await bot.send_message(int(row_get(seeker, "telegram_id")), "Arizangiz hali admin tasdig'idan o'tmagan.")
        return
    vacancies = db.find_vacancies_by_profession(
        row_get(seeker, "profession_id", None),
        row_get(seeker, "profession_title"),
    )
    seeker_tg_id = int(row_get(seeker, "telegram_id"))
    if not vacancies:
        await bot.send_message(seeker_tg_id, "Hozircha sizga mos aktiv vakansiya topilmadi.")
        return
    await bot.send_message(seeker_tg_id, f"💼 Sizga mos {min(len(vacancies), limit)} ta vakansiya topildi.")
    for vacancy in sorted(vacancies, key=lambda item: match_score(seeker, item), reverse=True)[:limit]:
        score = match_score(seeker, vacancy)
        await bot.send_message(
            seeker_tg_id,
            f"🎯 <b>Moslik: {score}%</b>\n\n" + public_vacancy_card(vacancy),
            reply_markup=matched_vacancy_keyboard(int(row_get(vacancy, "id"))),
        )


async def notify_seekers_about_new_vacancy(bot: Bot, vacancy: Any, *, limit: int = 20) -> None:
    matches = db.find_seekers_by_profession(
        row_get(vacancy, "profession_id", None),
        row_get(vacancy, "profession_title"),
    )
    for seeker in sorted(matches, key=lambda item: match_score(item, vacancy), reverse=True)[:limit]:
        try:
            await bot.send_message(
                int(row_get(seeker, "telegram_id")),
                "💼 <b>Sizga mos yangi vakansiya topildi</b>\n\n"
                f"🎯 Moslik: {match_score(seeker, vacancy)}%\n\n"
                + public_vacancy_card(vacancy),
                reply_markup=matched_vacancy_keyboard(int(row_get(vacancy, "id"))),
            )
            await asyncio.sleep(0.03)
        except Exception as exc:
            logger.warning("Failed to notify seeker %s: %s", row_get(seeker, "telegram_id"), exc)


async def notify_candidate_about_interest(bot: Bot, interest_id: int, vacancy: Any, seeker: Any) -> None:
    text = (
        "Sizning profilingiz bilan qiziqqan ish beruvchi topildi.\n\n"
        f"🏢 {esc(row_get(vacancy, 'organization'))}\n"
        f"💼 {esc(row_get(vacancy, 'profession_title'))}\n"
        f"💰 {esc(row_get(vacancy, 'salary'))} so'm\n"
        f"📍 {esc(location_text(vacancy))}"
    )
    await bot.send_message(
        int(row_get(seeker, "telegram_id")),
        text,
        reply_markup=candidate_offer_keyboard(interest_id),
    )


def filter_status_text(filters: dict[str, Any]) -> str:
    parts = []
    if filters.get("gender"):
        parts.append(f"🚻 Jins: {filters['gender']}")
    if filters.get("age_min") is not None or filters.get("age_max") is not None:
        parts.append(f"🎂 Yosh: {filters.get('age_min', '')}-{filters.get('age_max', '')}")
    if filters.get("region"):
        parts.append(f"📍 Hudud: {filters['region']}")
    if filters.get("district"):
        parts.append(f"🏙 Tuman: {filters['district']}")
    if filters.get("profession_title"):
        parts.append(f"💼 Kasb: {filters['profession_title']}")
    if filters.get("experience"):
        parts.append(f"📈 Tajriba: {filters['experience']}")
    if filters.get("job_type"):
        parts.append(f"🧭 Ish turi: {filters['job_type']}")
    if filters.get("salary_min") is not None or filters.get("salary_max") is not None:
        parts.append(f"💰 Oylik: {filters.get('salary_min', '')}-{filters.get('salary_max', '')}")
    current = "\n".join(f"• {esc(part)}" for part in parts) if parts else "Filtr tanlanmagan."
    return "👥 <b>Nomzodlar filtri</b>\n\n" + current


async def show_candidate_filter_menu(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    filters = data.get("filters", {})
    await message.answer(filter_status_text(filters), reply_markup=candidate_filter_keyboard())


def export_seekers_to_excel(rows, filename: str = "nomzodlar.xlsx") -> Path:
    from openpyxl import Workbook

    output_dir = Path("generated")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    wb = Workbook()
    ws = wb.active
    ws.title = "Nomzodlar"
    ws.append(
        [
            "ID",
            "Telegram ID",
            "Ism familiya",
            "Tug'ilgan sana",
            "Yosh",
            "Jins",
            "Telefon",
            "Hudud",
            "Tuman",
            "Kasb",
            "Ish turi",
            "Tajriba",
            "Tajriba yili",
            "Ma'lumot",
            "Excel",
            "Word",
            "Oldingi ish joyi",
            "Oldingi oylik",
            "Oldingi oylik raqam",
            "Hozirgi oylik",
            "Hozirgi oylik raqam",
            "Rezyume",
            "Moderatsiya",
            "Qo'shimcha",
            "Yaratilgan",
        ]
    )
    for seeker in rows:
        ws.append(
            [
                row_get(seeker, "id"),
                row_get(seeker, "telegram_id"),
                row_get(seeker, "full_name"),
                row_get(seeker, "birth_date"),
                row_get(seeker, "age"),
                row_get(seeker, "gender"),
                row_get(seeker, "phone"),
                row_get(seeker, "region"),
                row_get(seeker, "district"),
                row_get(seeker, "profession_title"),
                row_get(seeker, "job_type"),
                row_get(seeker, "experience"),
                row_get(seeker, "experience_years"),
                row_get(seeker, "education"),
                row_get(seeker, "excel_level"),
                row_get(seeker, "word_level"),
                row_get(seeker, "previous_job"),
                row_get(seeker, "previous_salary"),
                row_get(seeker, "previous_salary_amount"),
                row_get(seeker, "current_salary"),
                row_get(seeker, "current_salary_amount"),
                "bor" if row_get(seeker, "resume_file_id") else "yo'q",
                row_get(seeker, "moderation_status"),
                row_get(seeker, "extra"),
                row_get(seeker, "created_at"),
            ]
        )
    for column in ws.columns:
        max_length = max(len(str(cell.value or "")) for cell in column)
        ws.column_dimensions[column[0].column_letter].width = min(max(max_length + 2, 12), 40)
    wb.save(path)
    return path


def export_rows_to_excel(rows, headers: list[tuple[str, str]], filename: str, title: str) -> Path:
    from openpyxl import Workbook

    output_dir = Path("generated")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append([label for label, _ in headers])
    for row in rows:
        ws.append([row_get(row, key) for _, key in headers])
    for column in ws.columns:
        max_length = max(len(str(cell.value or "")) for cell in column)
        ws.column_dimensions[column[0].column_letter].width = min(max(max_length + 2, 12), 45)
    wb.save(path)
    return path


def export_dataset(kind: str) -> tuple[Path, int]:
    if kind == "seekers":
        rows = db.all_seekers()
        return export_seekers_to_excel(rows, "nomzodlar.xlsx"), len(rows)
    if kind == "vacancies":
        rows = db.all_vacancies()
        headers = [
            ("ID", "id"),
            ("Employer TG", "employer_tg_id"),
            ("Mas'ul", "full_name"),
            ("Tashkilot", "organization"),
            ("Telefon", "phone"),
            ("Hudud", "region"),
            ("Tuman", "district"),
            ("Kasb", "profession_title"),
            ("Xodim soni", "staff_count"),
            ("Ish turi", "job_type"),
            ("Maosh", "salary"),
            ("Maosh raqam", "salary_amount"),
            ("Min tajriba", "min_experience_years"),
            ("Holat", "active"),
            ("Moderatsiya", "moderation_status"),
            ("Muddati", "expires_at"),
            ("Yaratilgan", "created_at"),
        ]
        return export_rows_to_excel(rows, headers, "vakansiyalar.xlsx", "Vakansiyalar"), len(rows)
    if kind == "employers":
        rows = db.all_employers()
        headers = [
            ("ID", "id"),
            ("Telegram ID", "telegram_id"),
            ("Ism familiya", "full_name"),
            ("Tashkilot", "organization"),
            ("Telefon", "phone"),
            ("Hudud", "region"),
            ("Tuman", "district"),
            ("Yaratilgan", "created_at"),
        ]
        return export_rows_to_excel(rows, headers, "ish_beruvchilar.xlsx", "Ish beruvchilar"), len(rows)
    if kind == "interests":
        rows = db.all_interests()
        headers = [
            ("ID", "id"),
            ("Vakansiya ID", "vacancy_id"),
            ("Nomzod ID", "seeker_id"),
            ("Employer TG", "employer_tg_id"),
            ("Seeker TG", "seeker_tg_id"),
            ("Status", "status"),
            ("Yaratilgan", "created_at"),
        ]
        return export_rows_to_excel(rows, headers, "qiziqishlar.xlsx", "Qiziqishlar"), len(rows)
    if kind == "candidate_actions":
        rows = db.all_candidate_actions()
        headers = [
            ("ID", "id"),
            ("Employer TG", "employer_tg_id"),
            ("Vakansiya ID", "vacancy_id"),
            ("Nomzod ID", "seeker_id"),
            ("Status", "status"),
            ("Yaratilgan", "created_at"),
        ]
        return export_rows_to_excel(rows, headers, "saralashlar.xlsx", "Saralashlar"), len(rows)
    rows = db.list_admin_logs(limit=1000)
    headers = [
        ("ID", "id"),
        ("Admin TG", "admin_tg_id"),
        ("Action", "action"),
        ("Target type", "target_type"),
        ("Target ID", "target_id"),
        ("Details", "details"),
        ("Yaratilgan", "created_at"),
    ]
    return export_rows_to_excel(rows, headers, "admin_log.xlsx", "Admin log"), len(rows)


async def send_admin_subscription_menu(message: Message) -> None:
    enabled = db.force_subscription_enabled()
    channels = db.list_channels()
    status = "🟢 Yoqilgan" if enabled else "🔴 O'chirilgan"
    channel_text = "\n".join(f"• {esc(ch['title'])} ({esc(ch['chat_id'])})" for ch in channels) or "Kanal yo'q."
    await message.answer(
        f"🔐 <b>Majburiy obuna</b>\n\n"
        f"Holat: <b>{status}</b>\n\n"
        f"📣 <b>Kanallar</b>\n{channel_text}",
        reply_markup=admin_subscription_keyboard(enabled, channels),
    )


async def send_professions_menu(message: Message) -> None:
    professions = db.list_professions()
    text = "🧰 <b>Kasblar boshqaruvi</b>\n\n" + (
        "\n".join(f"• {esc(item['title'])}" for item in professions) if professions else "Kasb yo'q."
    )
    await message.answer(text, reply_markup=admin_professions_keyboard(professions))


async def send_admin_users_menu(message: Message) -> None:
    dynamic_admins = db.list_admins()
    env_text = "\n".join(f"• <code>{admin_id}</code>  🔒 .env" for admin_id in sorted(ADMIN_IDS))
    db_text = "\n".join(f"• <code>{admin['tg_id']}</code>" for admin in dynamic_admins)
    if not env_text:
        env_text = "• .env orqali admin kiritilmagan."
    if not db_text:
        db_text = "• Paneldan qo'shilgan admin yo'q."
    await message.answer(
        "👑 <b>Adminlar</b>\n\n"
        "🔒 <b>Asosiy adminlar</b>\n"
        f"{env_text}\n\n"
        "🛠 <b>Paneldan qo'shilgan adminlar</b>\n"
        f"{db_text}\n\n"
        "Admin qo'shish uchun Telegram ID raqamini kiriting.",
        reply_markup=admin_users_keyboard(dynamic_admins),
    )


@router.message(CommandStart(), StateFilter("*"))
async def start(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    db.upsert_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name,
    )
    if (
        not is_admin(message.from_user.id)
        and db.force_subscription_enabled()
        and not await check_user_subscription(bot, message.from_user.id)
    ):
        await send_subscription_prompt(message)
        return
    await message.answer(
        "👋 <b>Assalomu alaykum!</b>\n\n"
        "Ish topish va ishchi topish platformasiga xush kelibsiz.\n"
        "Quyidagi menyudan kerakli yo'nalishni tanlang.",
        reply_markup=menu_for(message.from_user.id),
    )


@router.callback_query(F.data == "check_sub")
async def check_subscription(callback: CallbackQuery, bot: Bot) -> None:
    if await check_user_subscription(bot, callback.from_user.id):
        await callback.answer("Obuna tasdiqlandi.")
        await callback.message.answer(
            "✅ Obuna tasdiqlandi.\n\nEndi botdan foydalanishingiz mumkin.",
            reply_markup=menu_for(callback.from_user.id),
        )
    else:
        await callback.answer("Hali barcha kanallarga obuna bo'lmagansiz.", show_alert=True)


@router.message(Command("admin"), StateFilter("*"))
@router.message(F.text == "🛠 Admin panel", StateFilter("*"))
async def admin_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not is_admin(message.from_user.id):
        await message.answer("Bu bo'lim faqat adminlar uchun.")
        return
    await message.answer(
        "🛠 <b>Admin panel</b>\n\nKerakli bo'limni tanlang.",
        reply_markup=admin_menu(),
    )


@router.message(F.text == "🏠 Asosiy menyu", StateFilter("*"))
async def back_to_main(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🏠 Asosiy menyu", reply_markup=menu_for(message.from_user.id))


@router.message(F.text == "📊 Dashboard", StateFilter("*"))
async def admin_dashboard(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    counts = db.dashboard_counts()
    await message.answer(
        "📊 <b>Dashboard</b>\n\n"
        f"👥 Foydalanuvchilar: {counts['users']}\n"
        f"👑 Panel adminlari: {counts['admins']}\n"
        f"👨‍💼 Ish qidiruvchilar: {counts['seekers']}\n"
        f"🏢 Ish beruvchilar: {counts['employers']}\n"
        f"📌 Vakansiyalar: {counts['vacancies']}\n"
        f"❤️ Qiziqishlar: {counts['interests']}\n\n"
        f"⏳ Kutilayotgan arizalar: {counts['pending_seekers']}\n"
        f"⏳ Kutilayotgan vakansiyalar: {counts['pending_vacancies']}\n"
        f"⏰ Muddati tugagan vakansiyalar: {counts['expired_vacancies']}",
        reply_markup=admin_menu(),
    )


@router.message(F.text == "🔎 Qidiruv", StateFilter("*"))
async def admin_search_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AdminSearchForm.query)
    await message.answer(
        "🔎 <b>Admin qidiruv</b>\n\n"
        "Nomzod ID, telefon, ism, vakansiya ID yoki tashkilot nomini kiriting.",
        reply_markup=cancel_menu(),
    )


@router.message(AdminSearchForm.query)
async def admin_search_run(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    query = clean_text(message.text)
    results = db.search_admin(query)
    db.add_admin_log(message.from_user.id, "search", "query", None, query)
    await state.clear()
    await message.answer(
        "🔎 <b>Qidiruv natijalari</b>\n\n"
        f"👨‍💼 Nomzodlar: {len(results['seekers'])}\n"
        f"🏢 Vakansiyalar: {len(results['vacancies'])}\n"
        f"👔 Ish beruvchilar: {len(results['employers'])}",
        reply_markup=admin_menu(),
    )
    for seeker in results["seekers"][:5]:
        await message.answer(seeker_card(seeker, hide_phone=False))
    for vacancy in results["vacancies"][:5]:
        await message.answer(vacancy_card(vacancy), reply_markup=vacancy_admin_keyboard(int(row_get(vacancy, "id"))))
    for employer in results["employers"][:5]:
        await message.answer(
            "👔 <b>Ish beruvchi</b>\n\n"
            f"ID: {esc(row_get(employer, 'id'))}\n"
            f"Telegram ID: <code>{esc(row_get(employer, 'telegram_id'))}</code>\n"
            f"👤 {esc(row_get(employer, 'full_name'))}\n"
            f"🏢 {esc(row_get(employer, 'organization'))}\n"
            f"📞 {esc(row_get(employer, 'phone'))}\n"
            f"📍 {esc(location_text(employer))}"
        )


@router.message(F.text == "📤 Excel eksport", StateFilter("*"))
async def admin_export_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    await message.answer("📤 Qaysi ma'lumot Excel qilinsin?", reply_markup=admin_export_keyboard())


@router.callback_query(F.data.startswith("export:"))
async def admin_export_callback(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    kind = callback.data.split(":")[1]
    path, count = export_dataset(kind)
    db.add_admin_log(callback.from_user.id, "export", kind, None, f"{count} rows")
    await callback.message.answer_document(FSInputFile(path), caption=f"📤 {count} ta yozuv eksport qilindi.")
    await callback.answer()


@router.message(F.text == "💾 Backup", StateFilter("*"))
async def admin_database_backup(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    path = db.create_backup("admin", keep_last=20)
    if path is None:
        await message.answer("Hozircha backup olinadigan baza fayli yo'q.", reply_markup=admin_menu())
        return
    db.add_admin_log(message.from_user.id, "database_backup", "database", None, str(path))
    await message.answer_document(
        FSInputFile(path),
        caption="💾 SQLite backup tayyor.\n\nBu faylni xavfsiz joyda saqlab qo'ying.",
        reply_markup=admin_menu(),
    )


@router.message(F.text == "🧾 Admin log", StateFilter("*"))
async def admin_logs(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    logs = db.list_admin_logs(limit=20)
    if not logs:
        await message.answer("🧾 Admin log hozircha bo'sh.", reply_markup=admin_menu())
        return
    text = "🧾 <b>So'nggi admin amallari</b>\n\n"
    for log in logs:
        text += (
            f"#{esc(row_get(log, 'id'))} "
            f"<code>{esc(row_get(log, 'admin_tg_id'))}</code> "
            f"{esc(row_get(log, 'action'))} "
            f"{esc(row_get(log, 'target_type'))}:{esc(row_get(log, 'target_id'))}\n"
        )
    await message.answer(text, reply_markup=admin_menu())


@router.message(F.text == "👑 Adminlar", StateFilter("*"))
async def admin_users(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    await send_admin_users_menu(message)


@router.callback_query(F.data == "admin_user:add")
async def admin_user_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    await state.set_state(AdminUserForm.add_id)
    await callback.message.answer(
        "➕ <b>Admin qo'shish</b>\n\n"
        "Yangi adminning Telegram ID raqamini yuboring.\n"
        "Misol: <code>123456789</code>",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


@router.message(AdminUserForm.add_id)
async def admin_user_save(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    admin_id = parse_positive_int(clean_text(message.text), minimum=1, maximum=999999999999999)
    if admin_id is None:
        await message.answer("Telegram ID faqat raqam bo'lishi kerak. Misol: <code>123456789</code>")
        return
    if is_env_admin(admin_id):
        await state.clear()
        await message.answer("Bu foydalanuvchi allaqachon .env orqali asosiy admin.", reply_markup=admin_menu())
        await send_admin_users_menu(message)
        return
    db.add_admin(admin_id, added_by=message.from_user.id)
    db.add_admin_log(message.from_user.id, "add_admin", "admin", admin_id)
    await state.clear()
    await message.answer(f"✅ <code>{admin_id}</code> admin qilib qo'shildi.", reply_markup=admin_menu())
    await send_admin_users_menu(message)


@router.callback_query(F.data.startswith("admin_user:delete:"))
async def admin_user_delete(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    admin_id = int(callback.data.split(":")[2])
    if is_env_admin(admin_id):
        await callback.answer(".env adminini paneldan o'chirib bo'lmaydi.", show_alert=True)
        return
    if admin_id == callback.from_user.id and not ADMIN_IDS:
        await callback.answer("O'zingizni o'chirishdan oldin kamida bitta asosiy admin qoldiring.", show_alert=True)
        return
    db.delete_admin(admin_id)
    db.add_admin_log(callback.from_user.id, "delete_admin", "admin", admin_id)
    await callback.answer("Admin o'chirildi.")
    await callback.message.delete()
    await send_admin_users_menu(callback.message)


@router.message(F.text == "🛂 Moderatsiya", StateFilter("*"))
async def admin_moderation(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    counts = db.dashboard_counts()
    await message.answer(
        "🛂 <b>Moderatsiya</b>\n\n"
        f"⏳ Kutilayotgan arizalar: {counts['pending_seekers']}\n"
        f"⏳ Kutilayotgan vakansiyalar: {counts['pending_vacancies']}",
        reply_markup=admin_moderation_keyboard(),
    )


@router.callback_query(F.data == "moderation:seekers")
async def admin_pending_seekers(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    seekers = db.list_pending_seekers(limit=20)
    if not seekers:
        await callback.message.answer("⏳ Kutilayotgan ariza yo'q.")
        await callback.answer()
        return
    await callback.message.answer(f"👨‍💼 Kutilayotgan arizalar: {len(seekers)}")
    for seeker in seekers:
        try:
            sent = await callback.message.answer_photo(
                photo=row_get(seeker, "photo_id"),
                caption=seeker_card(seeker, hide_phone=False),
                reply_markup=seeker_moderation_keyboard(int(row_get(seeker, "id"))),
            )
        except Exception:
            sent = await callback.message.answer(
                seeker_card(seeker, hide_phone=False),
                reply_markup=seeker_moderation_keyboard(int(row_get(seeker, "id"))),
            )
        db.save_moderation_message(
            "seeker",
            int(row_get(seeker, "id")),
            callback.from_user.id,
            sent.chat.id,
            sent.message_id,
        )
        if row_get(seeker, "resume_file_id"):
            doc = await callback.message.answer_document(
                document=row_get(seeker, "resume_file_id"),
                caption=f"📎 Nomzod #{row_get(seeker, 'id')} rezyumesi",
            )
            db.save_moderation_message(
                "seeker",
                int(row_get(seeker, "id")),
                callback.from_user.id,
                doc.chat.id,
                doc.message_id,
            )
    await callback.answer()


@router.callback_query(F.data == "moderation:vacancies")
async def admin_pending_vacancies(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    vacancies = db.list_pending_vacancies(limit=20)
    if not vacancies:
        await callback.message.answer("⏳ Kutilayotgan vakansiya yo'q.")
        await callback.answer()
        return
    await callback.message.answer(f"🏢 Kutilayotgan vakansiyalar: {len(vacancies)}")
    for vacancy in vacancies:
        sent = await callback.message.answer(
            vacancy_card(vacancy),
            reply_markup=vacancy_moderation_keyboard(int(row_get(vacancy, "id"))),
        )
        db.save_moderation_message(
            "vacancy",
            int(row_get(vacancy, "id")),
            callback.from_user.id,
            sent.chat.id,
            sent.message_id,
        )
    await callback.answer()


@router.callback_query(F.data.startswith("mod_seeker:"))
async def admin_moderate_seeker(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    _, action, seeker_id_raw = callback.data.split(":")
    seeker_id = int(seeker_id_raw)
    seeker = db.get_seeker(seeker_id)
    if not seeker:
        await callback.answer("Ariza topilmadi.", show_alert=True)
        return
    if clean_text(row_get(seeker, "moderation_status"), "pending") != "pending":
        await safe_clear_reply_markup(callback.message)
        await callback.answer("Bu arizaga boshqa admin allaqachon ishlov bergan.", show_alert=True)
        return
    if action == "approve":
        if not db.set_seeker_moderation_status_if_pending(
            seeker_id,
            "approved",
            moderated_by=callback.from_user.id,
        ):
            await safe_clear_reply_markup(callback.message)
            await callback.answer("Bu arizaga boshqa admin allaqachon ishlov bergan.", show_alert=True)
            return
        db.add_admin_log(callback.from_user.id, "approve_seeker", "seeker", seeker_id)
        seeker = db.get_seeker(seeker_id)
        await cleanup_moderation_requests(bot, "seeker", seeker_id, callback.from_user.id, callback.message)
        await publish_seeker(bot, seeker)
        await bot.send_message(
            int(row_get(seeker, "telegram_id")),
            "✅ Arizangiz admin tomonidan tasdiqlandi.\n\nEndi mos vakansiyalar sizga yuboriladi.",
            reply_markup=menu_for(int(row_get(seeker, "telegram_id"))),
        )
        await send_matched_vacancies_to_seeker(bot, seeker)
        await callback.message.answer("✅ Ariza tasdiqlandi va kanalga yuborildi.")
    else:
        await cleanup_moderation_requests(bot, "seeker", seeker_id, callback.from_user.id, callback.message)
        await state.set_state(AdminModerationReason.seeker_reason)
        await state.update_data(seeker_id=seeker_id, moderation_message_id=callback.message.message_id)
        await callback.message.answer(
            "📝 Arizani rad etish sababini yozing.\n\n"
            "Misol: <code>Telefon raqam noto'g'ri kiritilgan</code>",
            reply_markup=cancel_menu(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("mod_vacancy:"))
async def admin_moderate_vacancy(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    _, action, vacancy_id_raw = callback.data.split(":")
    vacancy_id = int(vacancy_id_raw)
    vacancy = db.get_vacancy(vacancy_id)
    if not vacancy:
        await callback.answer("Vakansiya topilmadi.", show_alert=True)
        return
    if clean_text(row_get(vacancy, "moderation_status"), "pending") != "pending":
        await safe_clear_reply_markup(callback.message)
        await callback.answer("Bu vakansiyaga boshqa admin allaqachon ishlov bergan.", show_alert=True)
        return
    if action == "approve":
        if not db.set_vacancy_moderation_status_if_pending(
            vacancy_id,
            "approved",
            moderated_by=callback.from_user.id,
        ):
            await safe_clear_reply_markup(callback.message)
            await callback.answer("Bu vakansiyaga boshqa admin allaqachon ishlov bergan.", show_alert=True)
            return
        db.add_admin_log(callback.from_user.id, "approve_vacancy", "vacancy", vacancy_id)
        vacancy = db.get_vacancy(vacancy_id)
        await cleanup_moderation_requests(bot, "vacancy", vacancy_id, callback.from_user.id, callback.message)
        await publish_vacancy(bot, vacancy)
        await bot.send_message(
            int(row_get(vacancy, "employer_tg_id")),
            "✅ Vakansiyangiz admin tomonidan tasdiqlandi.\n\nMos nomzodlar avtomatik yuboriladi.",
            reply_markup=menu_for(int(row_get(vacancy, "employer_tg_id"))),
        )
        await send_matches_to_employer(bot, vacancy)
        await notify_seekers_about_new_vacancy(bot, vacancy)
        await callback.message.answer("✅ Vakansiya tasdiqlandi va kanalga yuborildi.")
    else:
        await cleanup_moderation_requests(bot, "vacancy", vacancy_id, callback.from_user.id, callback.message)
        await state.set_state(AdminModerationReason.vacancy_reason)
        await state.update_data(vacancy_id=vacancy_id, moderation_message_id=callback.message.message_id)
        await callback.message.answer(
            "📝 Vakansiyani rad etish sababini yozing.\n\n"
            "Misol: <code>Maosh yoki talablar aniq yozilmagan</code>",
            reply_markup=cancel_menu(),
        )
    await callback.answer()


@router.message(AdminModerationReason.seeker_reason)
async def admin_seeker_reject_reason(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    seeker_id = int(data["seeker_id"])
    reason = clean_text(message.text)
    seeker = db.get_seeker(seeker_id)
    if not seeker:
        await state.clear()
        await message.answer("Ariza topilmadi.", reply_markup=admin_menu())
        return
    if not db.set_seeker_moderation_status_if_pending(
        seeker_id,
        "needs_edit",
        reason,
        moderated_by=message.from_user.id,
    ):
        await state.clear()
        await message.answer("Bu arizaga boshqa admin allaqachon ishlov bergan.", reply_markup=admin_menu())
        return
    db.add_admin_log(message.from_user.id, "reject_seeker", "seeker", seeker_id, reason)
    await bot.send_message(
        int(row_get(seeker, "telegram_id")),
        "✏️ <b>Arizangizga tuzatish kerak</b>\n\n"
        f"Sabab: {esc(reason)}\n\n"
        "📄 Mening arizam bo'limidan ma'lumotlarni tahrirlab qayta yuboring.",
        reply_markup=menu_for(int(row_get(seeker, "telegram_id"))),
    )
    await state.clear()
    await message.answer("✅ Sabab yuborildi, ariza tuzatishga qaytarildi.", reply_markup=admin_menu())


@router.message(AdminModerationReason.vacancy_reason)
async def admin_vacancy_reject_reason(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    vacancy_id = int(data["vacancy_id"])
    reason = clean_text(message.text)
    vacancy = db.get_vacancy(vacancy_id)
    if not vacancy:
        await state.clear()
        await message.answer("Vakansiya topilmadi.", reply_markup=admin_menu())
        return
    if not db.set_vacancy_moderation_status_if_pending(
        vacancy_id,
        "needs_edit",
        reason,
        moderated_by=message.from_user.id,
    ):
        await state.clear()
        await message.answer("Bu vakansiyaga boshqa admin allaqachon ishlov bergan.", reply_markup=admin_menu())
        return
    db.add_admin_log(message.from_user.id, "reject_vacancy", "vacancy", vacancy_id, reason)
    await bot.send_message(
        int(row_get(vacancy, "employer_tg_id")),
        "✏️ <b>Vakansiyangizga tuzatish kerak</b>\n\n"
        f"Sabab: {esc(reason)}\n\n"
        "📌 Mening vakansiyalarim bo'limidan ma'lumotlarni ko'rib, kerak bo'lsa yangi vakansiya yarating.",
        reply_markup=menu_for(int(row_get(vacancy, "employer_tg_id"))),
    )
    await state.clear()
    await message.answer("✅ Sabab yuborildi, vakansiya tuzatishga qaytarildi.", reply_markup=admin_menu())


@router.message(F.text == CANCEL, StateFilter("*"))
async def cancel_any(message: Message, state: FSMContext) -> None:
    await state.clear()
    if is_admin(message.from_user.id):
        await message.answer("Bekor qilindi.", reply_markup=admin_menu())
    else:
        await message.answer("Bekor qilindi.", reply_markup=menu_for(message.from_user.id))


@router.message(F.text == "🔐 Majburiy obuna", StateFilter("*"))
async def admin_subscription(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    await send_admin_subscription_menu(message)


@router.callback_query(F.data.startswith("admin_sub:"))
async def admin_toggle_subscription(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    action = callback.data.split(":")[1]
    db.set_setting("force_subscription", "1" if action == "enable" else "0")
    db.add_admin_log(callback.from_user.id, f"force_subscription_{action}", "settings", None)
    await callback.answer("Saqlandi.")
    await callback.message.delete()
    await send_admin_subscription_menu(callback.message)


@router.callback_query(F.data == "admin_channel:add")
async def admin_channel_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    await state.set_state(AdminChannelForm.channel)
    await callback.message.answer(
        "Kanal username yoki ID kiriting.\n\n"
        "Misol: <code>@kanal_username</code>\n"
        "Yopiq kanal uchun: <code>-1001234567890 | Kanal nomi | https://t.me/+invite</code>\n\n"
        "Bot kanalga admin qilingan bo'lishi kerak.",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


@router.message(AdminChannelForm.channel)
async def admin_channel_save(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return
    parts = [part.strip() for part in clean_text(message.text).split("|")]
    chat_id = parts[0]
    title = parts[1] if len(parts) > 1 and parts[1] else chat_id
    invite_link = parts[2] if len(parts) > 2 and parts[2] else None
    try:
        chat = await bot.get_chat(chat_id)
        title = title if title != chat_id else clean_text(chat.title or chat.username or chat_id)
        invite_link = invite_link or getattr(chat, "invite_link", None)
    except Exception as exc:
        logger.warning("Could not fetch channel info: %s", exc)
    db.add_channel(title, chat_id, invite_link)
    db.add_admin_log(message.from_user.id, "add_channel", "channel", None, chat_id)
    await state.clear()
    await message.answer("Kanal saqlandi.", reply_markup=admin_menu())
    await send_admin_subscription_menu(message)


@router.callback_query(F.data.startswith("admin_channel:delete:"))
async def admin_channel_delete(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    channel_id = int(callback.data.split(":")[2])
    db.delete_channel(channel_id)
    db.add_admin_log(callback.from_user.id, "delete_channel", "channel", channel_id)
    await callback.answer("Kanal o'chirildi.")
    await callback.message.delete()
    await send_admin_subscription_menu(callback.message)


@router.message(F.text == "🧰 Kasblar", StateFilter("*"))
async def admin_professions(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    await send_professions_menu(message)


@router.callback_query(F.data == "admin_prof:add")
async def admin_profession_add(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    await state.set_state(AdminProfessionForm.add_title)
    await callback.message.answer("Yangi kasb nomini kiriting.", reply_markup=cancel_menu())
    await callback.answer()


@router.message(AdminProfessionForm.add_title)
async def admin_profession_save(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    title = clean_text(message.text)
    if title == "-":
        await message.answer("Kasb nomini matn ko'rinishida kiriting.")
        return
    db.add_profession(title)
    db.add_admin_log(message.from_user.id, "add_profession", "profession", None, title)
    await state.clear()
    await message.answer("Kasb qo'shildi.", reply_markup=admin_menu())
    await send_professions_menu(message)


@router.callback_query(F.data.startswith("admin_prof:edit:"))
async def admin_profession_edit(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    profession_id = int(callback.data.split(":")[2])
    profession = db.get_profession(profession_id)
    if not profession:
        await callback.answer("Kasb topilmadi.", show_alert=True)
        return
    await state.set_state(AdminProfessionForm.edit_title)
    await state.update_data(profession_id=profession_id)
    await callback.message.answer(f"Yangi nom kiriting: {esc(profession['title'])}", reply_markup=cancel_menu())
    await callback.answer()


@router.message(AdminProfessionForm.edit_title)
async def admin_profession_update(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    db.update_profession(int(data["profession_id"]), clean_text(message.text))
    db.add_admin_log(message.from_user.id, "edit_profession", "profession", int(data["profession_id"]))
    await state.clear()
    await message.answer("Kasb tahrirlandi.", reply_markup=admin_menu())
    await send_professions_menu(message)


@router.callback_query(F.data.startswith("admin_prof:delete:"))
async def admin_profession_delete(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    profession_id = int(callback.data.split(":")[2])
    db.delete_profession(profession_id)
    db.add_admin_log(callback.from_user.id, "delete_profession", "profession", profession_id)
    await callback.answer("Kasb o'chirildi.")
    await callback.message.delete()
    await send_professions_menu(callback.message)


@router.message(F.text == "📣 Ommaviy xabar", StateFilter("*"))
async def admin_broadcast(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    await message.answer("Kimlarga yuborilsin?", reply_markup=broadcast_target_keyboard())


@router.callback_query(F.data.startswith("broadcast:"))
async def admin_broadcast_target(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    target = callback.data.split(":")[1]
    await state.set_state(BroadcastForm.message)
    await state.update_data(target=target)
    await callback.message.answer("Yuboriladigan xabarni matn, rasm yoki fayl ko'rinishida yuboring.", reply_markup=cancel_menu())
    await callback.answer()


@router.message(BroadcastForm.message)
async def admin_broadcast_preview(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.update_data(
        target=data.get("target", "all"),
        source_chat_id=message.chat.id,
        source_message_id=message.message_id,
    )
    await message.answer("👁 <b>Xabar ko'rinishi</b>\n\nPastda yuboriladigan xabar nusxasi:")
    await bot.copy_message(message.chat.id, message.chat.id, message.message_id)
    await message.answer(
        "Ushbu xabarni tanlangan foydalanuvchilarga yuboraymi?",
        reply_markup=broadcast_preview_keyboard(),
    )


@router.callback_query(F.data.startswith("broadcast_confirm:"))
async def admin_broadcast_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    action = callback.data.split(":")[1]
    data = await state.get_data()
    if action == "no":
        await state.clear()
        await callback.message.answer("❌ Ommaviy xabar rad etildi. Hech kimga yuborilmadi.", reply_markup=admin_menu())
        await callback.answer()
        return
    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")
    if not source_chat_id or not source_message_id:
        await callback.answer("Xabar topilmadi. Qaytadan yuboring.", show_alert=True)
        return
    users = db.broadcast_users(data.get("target", "all"))
    sent = 0
    failed = 0
    for user_id in users:
        try:
            await bot.copy_message(user_id, source_chat_id, source_message_id)
            sent += 1
            await asyncio.sleep(0.03)
        except Exception:
            failed += 1
    await state.clear()
    db.add_admin_log(callback.from_user.id, "broadcast", data.get("target", "all"), None, f"sent={sent}; failed={failed}")
    await callback.message.answer(
        f"Ommaviy xabar yakunlandi.\n\nYuborildi: {sent}\nXatolik: {failed}",
        reply_markup=admin_menu(),
    )
    await callback.answer()


@router.message(F.text == "👥 Nomzodlar", StateFilter("*"))
async def admin_candidates(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminCandidateFilter.menu)
    await state.update_data(filters={})
    await show_candidate_filter_menu(message, state)


@router.callback_query(F.data.startswith("filter:"))
async def admin_candidate_filter_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    action = callback.data.split(":")[1]
    data = await state.get_data()
    filters = data.get("filters", {})

    if action == "gender":
        await state.set_state(AdminCandidateFilter.gender)
        await callback.message.answer("Jinsni tanlang.", reply_markup=gender_menu())
    elif action == "age":
        await state.set_state(AdminCandidateFilter.age)
        await callback.message.answer("Yosh oralig'ini kiriting. Masalan: <code>18-30</code>", reply_markup=cancel_menu())
    elif action == "region":
        await state.set_state(AdminCandidateFilter.region)
        await callback.message.answer("Hududni tanlang.", reply_markup=regions_menu())
    elif action == "profession":
        await state.set_state(AdminCandidateFilter.profession)
        await callback.message.answer("Kasbni tanlang.", reply_markup=profession_keyboard(db.list_professions(), "filter_prof"))
    elif action == "experience":
        await state.set_state(AdminCandidateFilter.experience)
        await callback.message.answer("Tajriba bo'yicha qidiruv so'zini kiriting. Masalan: <code>2 yil</code>", reply_markup=cancel_menu())
    elif action == "job_type":
        await state.set_state(AdminCandidateFilter.job_type)
        await callback.message.answer("Ish turini tanlang.", reply_markup=seeker_job_type_keyboard())
    elif action == "salary":
        await state.set_state(AdminCandidateFilter.salary)
        await callback.message.answer("Maosh oralig'ini kiriting. Masalan: <code>3000000-7000000</code>", reply_markup=cancel_menu())
    elif action == "clear":
        await state.set_state(AdminCandidateFilter.menu)
        await state.update_data(filters={})
        await callback.message.answer("Filtrlar tozalandi.", reply_markup=admin_menu())
        await show_candidate_filter_menu(callback.message, state)
    elif action == "show":
        rows = db.filter_seekers(filters)
        await callback.message.answer(f"{len(rows)} ta nomzod topildi.", reply_markup=admin_menu())
        for seeker in rows[:10]:
            await callback.message.answer(seeker_card(seeker, hide_phone=False))
        if len(rows) > 10:
            await callback.message.answer("Faqat birinchi 10 ta nomzod ko'rsatildi. To'liq ro'yxat uchun Excel eksportdan foydalaning.")
    elif action == "excel":
        rows = db.filter_seekers(filters)
        path = export_seekers_to_excel(rows)
        await callback.message.answer_document(FSInputFile(path), caption=f"{len(rows)} ta nomzod eksport qilindi.")
    await callback.answer()


@router.message(AdminCandidateFilter.gender)
async def admin_filter_gender(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    if message.text not in {"Erkak", "Ayol"}:
        await message.answer("Jinsni tugmadan tanlang.", reply_markup=gender_menu())
        return
    data = await state.get_data()
    filters = data.get("filters", {})
    filters["gender"] = message.text
    await state.update_data(filters=filters)
    await state.set_state(AdminCandidateFilter.menu)
    await message.answer("Jins filtri saqlandi.", reply_markup=admin_menu())
    await show_candidate_filter_menu(message, state)


@router.message(AdminCandidateFilter.age)
async def admin_filter_age(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    numbers = [int(item) for item in re.findall(r"\d+", clean_text(message.text))]
    if not numbers:
        await message.answer("Yoshni <code>18-30</code> ko'rinishida kiriting.")
        return
    age_min = numbers[0]
    age_max = numbers[1] if len(numbers) > 1 else numbers[0]
    if age_min > age_max:
        age_min, age_max = age_max, age_min
    data = await state.get_data()
    filters = data.get("filters", {})
    filters["age_min"] = age_min
    filters["age_max"] = age_max
    await state.update_data(filters=filters)
    await state.set_state(AdminCandidateFilter.menu)
    await message.answer("Yosh filtri saqlandi.", reply_markup=admin_menu())
    await show_candidate_filter_menu(message, state)


@router.message(AdminCandidateFilter.region)
async def admin_filter_region(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    filters = data.get("filters", {})
    filters["region"] = clean_text(message.text)
    await state.update_data(filters=filters)
    await state.set_state(AdminCandidateFilter.menu)
    await message.answer("Hudud filtri saqlandi.", reply_markup=admin_menu())
    await show_candidate_filter_menu(message, state)


@router.callback_query(F.data.startswith("filter_prof:"))
async def admin_filter_profession(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    profession_id = int(callback.data.split(":")[1])
    profession = db.get_profession(profession_id)
    if not profession:
        await callback.answer("Kasb topilmadi.", show_alert=True)
        return
    data = await state.get_data()
    filters = data.get("filters", {})
    filters["profession_id"] = profession_id
    filters["profession_title"] = profession["title"]
    await state.update_data(filters=filters)
    await state.set_state(AdminCandidateFilter.menu)
    await callback.message.answer("Kasb filtri saqlandi.", reply_markup=admin_menu())
    await show_candidate_filter_menu(callback.message, state)
    await callback.answer()


@router.message(AdminCandidateFilter.experience)
async def admin_filter_experience(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    filters = data.get("filters", {})
    filters["experience"] = clean_text(message.text)
    await state.update_data(filters=filters)
    await state.set_state(AdminCandidateFilter.menu)
    await message.answer("Tajriba filtri saqlandi.", reply_markup=admin_menu())
    await show_candidate_filter_menu(message, state)


@router.callback_query(AdminCandidateFilter.job_type, F.data.startswith("seeker_job_type:"))
async def admin_filter_job_type(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    data = await state.get_data()
    filters = data.get("filters", {})
    filters["job_type"] = callback.data.split(":", 1)[1]
    await state.update_data(filters=filters)
    await state.set_state(AdminCandidateFilter.menu)
    await callback.message.answer("Ish turi filtri saqlandi.", reply_markup=admin_menu())
    await show_candidate_filter_menu(callback.message, state)
    await callback.answer()


@router.message(AdminCandidateFilter.salary)
async def admin_filter_salary(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    numbers = [int("".join(re.findall(r"\d+", item))) for item in re.split(r"[-–]", clean_text(message.text)) if re.findall(r"\d+", item)]
    if not numbers:
        await message.answer("Maosh oralig'ini <code>3000000-7000000</code> ko'rinishida kiriting.")
        return
    salary_min = numbers[0]
    salary_max = numbers[1] if len(numbers) > 1 else numbers[0]
    if salary_min > salary_max:
        salary_min, salary_max = salary_max, salary_min
    data = await state.get_data()
    filters = data.get("filters", {})
    filters["salary_min"] = salary_min
    filters["salary_max"] = salary_max
    await state.update_data(filters=filters)
    await state.set_state(AdminCandidateFilter.menu)
    await message.answer("Maosh filtri saqlandi.", reply_markup=admin_menu())
    await show_candidate_filter_menu(message, state)


@router.message(F.text == "🏢 Vakansiyalar", StateFilter("*"))
async def admin_vacancies(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not is_admin(message.from_user.id):
        return
    vacancies = db.list_vacancies(limit=20)
    if not vacancies:
        await message.answer("Vakansiya yo'q.", reply_markup=admin_menu())
        return
    await message.answer(f"So'nggi {len(vacancies)} ta vakansiya:", reply_markup=admin_menu())
    for vacancy in vacancies:
        await message.answer(vacancy_card(vacancy), reply_markup=vacancy_admin_keyboard(int(vacancy["id"])))


@router.callback_query(F.data.startswith("vac_admin:delete:"))
async def admin_vacancy_delete(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    vacancy_id = int(callback.data.split(":")[2])
    db.delete_vacancy(vacancy_id)
    db.add_admin_log(callback.from_user.id, "delete_vacancy", "vacancy", vacancy_id)
    await callback.message.edit_text("Vakansiya o'chirildi.")
    await callback.answer()


@router.callback_query(F.data.startswith("vac_admin:edit:"))
async def admin_vacancy_edit(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    vacancy_id = int(callback.data.split(":")[2])
    await callback.message.answer("Qaysi maydon tahrirlansin?", reply_markup=vacancy_edit_fields_keyboard(vacancy_id))
    await callback.answer()


@router.callback_query(F.data.startswith("vac_edit:"))
async def admin_vacancy_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    _, vacancy_id, field = callback.data.split(":")
    vacancy_id = int(vacancy_id)
    if field == "profession":
        await state.set_state(AdminVacancyEdit.profession)
        await state.update_data(vacancy_id=vacancy_id)
        await callback.message.answer("Yangi kasbni tanlang.", reply_markup=profession_keyboard(db.list_professions(), "vac_edit_prof"))
    elif field == "job_type":
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Offline", callback_data=f"vac_edit_job:{vacancy_id}:Offline"),
                    InlineKeyboardButton(text="Online", callback_data=f"vac_edit_job:{vacancy_id}:Online"),
                    InlineKeyboardButton(text="Gibrid", callback_data=f"vac_edit_job:{vacancy_id}:Gibrid"),
                ]
            ]
        )
        await callback.message.answer("Yangi ish turini tanlang.", reply_markup=markup)
    else:
        await state.set_state(AdminVacancyEdit.value)
        await state.update_data(vacancy_id=vacancy_id, field=field)
        reply_markup = regions_menu() if field == "region" else cancel_menu()
        await callback.message.answer("Yangi qiymatni kiriting.", reply_markup=reply_markup)
    await callback.answer()


@router.callback_query(F.data.startswith("vac_edit_prof:"))
async def admin_vacancy_edit_profession(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    data = await state.get_data()
    vacancy_id = int(data["vacancy_id"])
    profession_id = int(callback.data.split(":")[1])
    profession = db.get_profession(profession_id)
    if not profession:
        await callback.answer("Kasb topilmadi.", show_alert=True)
        return
    db.update_vacancy_field(vacancy_id, "profession_id", profession_id)
    db.update_vacancy_field(vacancy_id, "profession_title", profession["title"])
    db.add_admin_log(callback.from_user.id, "edit_vacancy", "vacancy", vacancy_id, "profession")
    vacancy = db.get_vacancy(vacancy_id)
    if vacancy and clean_text(row_get(vacancy, "moderation_status"), "") == "approved":
        await publish_vacancy(bot, vacancy)
    await state.clear()
    await callback.message.answer("Vakansiya kasbi tahrirlandi.", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("vac_edit_job:"))
async def admin_vacancy_edit_job_type(callback: CallbackQuery, bot: Bot) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat yo'q.", show_alert=True)
        return
    _, vacancy_id, job_type = callback.data.split(":")
    db.update_vacancy_field(int(vacancy_id), "job_type", job_type)
    db.add_admin_log(callback.from_user.id, "edit_vacancy", "vacancy", int(vacancy_id), "job_type")
    vacancy = db.get_vacancy(int(vacancy_id))
    if vacancy and clean_text(row_get(vacancy, "moderation_status"), "") == "approved":
        await publish_vacancy(bot, vacancy)
    await callback.message.answer("Ish turi tahrirlandi.", reply_markup=admin_menu())
    await callback.answer()


@router.message(AdminVacancyEdit.value)
async def admin_vacancy_edit_value(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    field = data["field"]
    value: Any = clean_text(message.text)
    if field == "phone":
        phone = normalize_phone(value)
        if phone is None:
            await message.answer("Telefon raqamni to'g'ri kiriting.\nMisol: <code>+998 90 123 45 67</code>")
            return
        value = phone
    if field == "staff_count":
        parsed = parse_positive_int(value, minimum=1, maximum=10000)
        if parsed is None:
            await message.answer("Xodim sonini raqam bilan kiriting.")
            return
        value = parsed
    if field == "salary":
        db.update_vacancy_field(int(data["vacancy_id"]), "salary_amount", parse_money_amount(value))
    if field == "requirements":
        db.update_vacancy_field(int(data["vacancy_id"]), "min_experience_years", parse_experience_years(value))
    db.update_vacancy_field(int(data["vacancy_id"]), field, value)
    db.add_admin_log(message.from_user.id, "edit_vacancy", "vacancy", int(data["vacancy_id"]), field)
    vacancy = db.get_vacancy(int(data["vacancy_id"]))
    if vacancy and clean_text(row_get(vacancy, "moderation_status"), "") == "approved":
        await publish_vacancy(bot, vacancy)
    await state.clear()
    await message.answer("Vakansiya tahrirlandi.", reply_markup=admin_menu())


@router.message(F.text == "📄 Mening arizam", StateFilter("*"))
async def my_seeker_profile(message: Message, state: FSMContext) -> None:
    await state.clear()
    seeker = db.get_seeker_by_tg(message.from_user.id)
    if not seeker:
        await message.answer(
            "Siz hali ariza topshirmagansiz.\n\nBoshlash uchun <b>👨‍💼 Ishga ariza topshirish</b> tugmasini bosing.",
            reply_markup=menu_for(message.from_user.id),
        )
        return
    try:
        await message.answer_photo(
            photo=row_get(seeker, "photo_id"),
            caption=seeker_card(seeker, hide_phone=False),
            reply_markup=seeker_profile_keyboard(),
        )
    except Exception:
        await message.answer(seeker_card(seeker, hide_phone=False), reply_markup=seeker_profile_keyboard())
    if row_get(seeker, "resume_file_id"):
        await message.answer_document(
            document=row_get(seeker, "resume_file_id"),
            caption=f"📎 Rezyume: {esc(row_get(seeker, 'resume_file_name', 'resume'))}",
        )


@router.callback_query(F.data == "my_seeker:edit")
async def my_seeker_edit_menu(callback: CallbackQuery) -> None:
    seeker = db.get_seeker_by_tg(callback.from_user.id)
    if not seeker:
        await callback.answer("Avval ariza topshiring.", show_alert=True)
        return
    if clean_text(row_get(seeker, "moderation_status"), "") == "pending":
        await callback.answer("Arizangiz hozir admin tekshiruvida.", show_alert=True)
        return
    await callback.message.answer("✏️ Qaysi ma'lumot tahrirlansin?", reply_markup=seeker_edit_fields_keyboard())
    await callback.answer()


@router.callback_query(F.data == "my_seeker:resume")
async def my_seeker_resume(callback: CallbackQuery, state: FSMContext) -> None:
    seeker = db.get_seeker_by_tg(callback.from_user.id)
    if not seeker:
        await callback.answer("Avval ariza topshiring.", show_alert=True)
        return
    await state.set_state(SeekerEditForm.resume)
    await callback.message.answer(
        "📎 Rezyume faylini yuboring.\n\nPDF, DOC yoki DOCX fayl yuborishingiz mumkin.",
        reply_markup=cancel_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "my_seeker:matches")
async def my_seeker_matches(callback: CallbackQuery, bot: Bot) -> None:
    seeker = db.get_seeker_by_tg(callback.from_user.id)
    if not seeker:
        await callback.answer("Avval ariza topshiring.", show_alert=True)
        return
    await send_matched_vacancies_to_seeker(bot, seeker)
    await callback.answer()


@router.callback_query(F.data.startswith("seeker_edit:"))
async def my_seeker_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    seeker = db.get_seeker_by_tg(callback.from_user.id)
    if not seeker:
        await callback.answer("Avval ariza topshiring.", show_alert=True)
        return
    field = callback.data.split(":")[1]
    if field == "profession":
        await state.set_state(SeekerEditForm.profession)
        await callback.message.answer("Yangi kasbni tanlang.", reply_markup=profession_keyboard(db.list_professions(), "seeker_edit_prof"))
    elif field == "job_type":
        await callback.message.answer("Yangi ish turini tanlang.", reply_markup=seeker_edit_job_type_keyboard())
    elif field == "education":
        await callback.message.answer("Yangi ma'lumot darajasini tanlang.", reply_markup=education_keyboard("seeker_edit_education"))
    elif field == "excel_level":
        await callback.message.answer("Yangi Excel darajasini tanlang.", reply_markup=skill_level_keyboard("seeker_edit_excel"))
    elif field == "word_level":
        await callback.message.answer("Yangi Word darajasini tanlang.", reply_markup=skill_level_keyboard("seeker_edit_word"))
    else:
        await state.set_state(SeekerEditForm.value)
        await state.update_data(field=field)
        prompts = {
            "full_name": "Yangi ism familiyangizni kiriting.",
            "birth_date": "Yangi tug'ilgan sanangizni kiriting.\nFormat: <code>kun.oy.yil</code>\nMisol: <code>15.04.2001</code>",
            "gender": "Jinsingizni tanlang.",
            "phone": "Yangi telefon raqamingizni qo'lda kiriting.\nMisol: <code>+998 90 123 45 67</code>",
            "region": "Yangi hududni tanlang.",
            "district": "Yangi tumanni tanlang.",
            "experience": "Yangi tajribangizni kiriting.",
            "education": "Yangi ma'lumot darajangizni kiriting.",
            "previous_job": "Yangi oldingi ish joyingizni kiriting.",
            "previous_salary": "Oldingi ish joyingizdagi oylikni kiriting.",
            "current_salary": "Hozir olayotgan oyligingizni kiriting.",
            "extra": "Qo'shimcha ma'lumotni qisqa yozing: ko'nikmalar, ish vaqti, talablar yoki izohlar.",
        }
        markup = cancel_menu()
        if field == "gender":
            markup = gender_menu()
        elif field == "phone":
            markup = contact_menu()
        elif field == "region":
            markup = regions_menu()
        elif field == "district":
            markup = districts_menu(row_get(seeker, "region"))
        await callback.message.answer(prompts.get(field, "Yangi qiymatni kiriting."), reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("seeker_edit_job_type:"))
async def my_seeker_edit_job_type(callback: CallbackQuery, bot: Bot) -> None:
    seeker = db.get_seeker_by_tg(callback.from_user.id)
    if not seeker:
        await callback.answer("Avval ariza topshiring.", show_alert=True)
        return
    job_type = callback.data.split(":", 1)[1]
    db.update_seeker_field(callback.from_user.id, "job_type", job_type)
    seeker = db.get_seeker_by_tg(callback.from_user.id)
    await callback.message.answer(
        "✅ Ish turi yangilandi.\n\nArizangiz qayta admin tekshiruviga yuborildi.",
        reply_markup=menu_for(callback.from_user.id),
    )
    await send_seeker_moderation_to_admins(bot, seeker)
    await callback.answer()


@router.callback_query(F.data.startswith("seeker_edit_education:"))
async def my_seeker_edit_education(callback: CallbackQuery, bot: Bot) -> None:
    seeker = db.get_seeker_by_tg(callback.from_user.id)
    if not seeker:
        await callback.answer("Avval ariza topshiring.", show_alert=True)
        return
    education = callback.data.split(":", 1)[1]
    db.update_seeker_field(callback.from_user.id, "education", education)
    seeker = db.get_seeker_by_tg(callback.from_user.id)
    await callback.message.answer(
        "✅ Ma'lumot darajasi yangilandi.\n\nArizangiz qayta admin tekshiruviga yuborildi.",
        reply_markup=menu_for(callback.from_user.id),
    )
    await send_seeker_moderation_to_admins(bot, seeker)
    await callback.answer()


@router.callback_query(F.data.startswith("seeker_edit_excel:"))
async def my_seeker_edit_excel(callback: CallbackQuery, bot: Bot) -> None:
    seeker = db.get_seeker_by_tg(callback.from_user.id)
    if not seeker:
        await callback.answer("Avval ariza topshiring.", show_alert=True)
        return
    level = callback.data.split(":", 1)[1]
    db.update_seeker_field(callback.from_user.id, "excel_level", level)
    seeker = db.get_seeker_by_tg(callback.from_user.id)
    await callback.message.answer(
        "✅ Excel darajasi yangilandi.\n\nArizangiz qayta admin tekshiruviga yuborildi.",
        reply_markup=menu_for(callback.from_user.id),
    )
    await send_seeker_moderation_to_admins(bot, seeker)
    await callback.answer()


@router.callback_query(F.data.startswith("seeker_edit_word:"))
async def my_seeker_edit_word(callback: CallbackQuery, bot: Bot) -> None:
    seeker = db.get_seeker_by_tg(callback.from_user.id)
    if not seeker:
        await callback.answer("Avval ariza topshiring.", show_alert=True)
        return
    level = callback.data.split(":", 1)[1]
    db.update_seeker_field(callback.from_user.id, "word_level", level)
    seeker = db.get_seeker_by_tg(callback.from_user.id)
    await callback.message.answer(
        "✅ Word darajasi yangilandi.\n\nArizangiz qayta admin tekshiruviga yuborildi.",
        reply_markup=menu_for(callback.from_user.id),
    )
    await send_seeker_moderation_to_admins(bot, seeker)
    await callback.answer()


@router.callback_query(F.data.startswith("seeker_edit_prof:"))
async def my_seeker_edit_profession(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not db.get_seeker_by_tg(callback.from_user.id):
        await callback.answer("Avval ariza topshiring.", show_alert=True)
        return
    profession_id = int(callback.data.split(":")[1])
    profession = db.get_profession(profession_id)
    if not profession:
        await callback.answer("Kasb topilmadi.", show_alert=True)
        return
    db.update_seeker_profession(callback.from_user.id, profession_id, profession["title"])
    seeker = db.get_seeker_by_tg(callback.from_user.id)
    await state.clear()
    await callback.message.answer(
        "✅ Kasb yangilandi.\n\nArizangiz qayta admin tekshiruviga yuborildi.",
        reply_markup=menu_for(callback.from_user.id),
    )
    await send_seeker_moderation_to_admins(bot, seeker)
    await callback.answer()


@router.message(SeekerEditForm.value)
async def my_seeker_edit_value(message: Message, state: FSMContext, bot: Bot) -> None:
    if not db.get_seeker_by_tg(message.from_user.id):
        await state.clear()
        await message.answer("Avval ariza topshiring.", reply_markup=menu_for(message.from_user.id))
        return
    data = await state.get_data()
    field = data["field"]
    value: Any = clean_text(message.text)
    if field == "phone":
        phone = normalize_phone(value)
        if phone is None:
            await message.answer("Telefon raqamni to'g'ri kiriting.\nMisol: <code>+998 90 123 45 67</code>")
            return
        value = phone
    if field == "birth_date":
        parsed_birth = parse_birth_date(value)
        if parsed_birth is None:
            await message.answer("Sanani to'g'ri kiriting.\nFormat: <code>kun.oy.yil</code>\nMisol: <code>15.04.2001</code>")
            return
        birth_date, age = parsed_birth
        db.update_seeker_field(message.from_user.id, "age", age)
        value = birth_date
    if field == "gender" and value not in {"Erkak", "Ayol"}:
        await message.answer("Jinsni tugmadan tanlang.", reply_markup=gender_menu())
        return
    if field == "previous_salary":
        amount = parse_money_amount(value)
        if amount is None:
            await message.answer("Oylikni raqam bilan kiriting.\nMisol: <code>5 000 000</code>")
            return
        db.update_seeker_field(message.from_user.id, "previous_salary_amount", amount)
    if field == "current_salary":
        amount = parse_money_amount(value)
        if amount is None and value != "0":
            await message.answer("Oylikni raqam bilan kiriting.\nMisol: <code>6 000 000</code> yoki <code>0</code>")
            return
        if value == "0":
            amount = 0
        db.update_seeker_field(message.from_user.id, "current_salary_amount", amount)
        db.update_seeker_field(message.from_user.id, "salary", value)
        db.update_seeker_field(message.from_user.id, "salary_amount", amount)
    if field == "experience":
        db.update_seeker_field(message.from_user.id, "experience_years", parse_experience_years(value))
    db.update_seeker_field(message.from_user.id, field, value)
    seeker = db.get_seeker_by_tg(message.from_user.id)
    await state.clear()
    await message.answer(
        "✅ Ma'lumot yangilandi.\n\nArizangiz qayta admin tekshiruviga yuborildi.",
        reply_markup=menu_for(message.from_user.id),
    )
    await send_seeker_moderation_to_admins(bot, seeker)


@router.message(SeekerEditForm.resume)
async def my_seeker_edit_resume_file(message: Message, state: FSMContext, bot: Bot) -> None:
    if not db.get_seeker_by_tg(message.from_user.id):
        await state.clear()
        await message.answer("Avval ariza topshiring.", reply_markup=menu_for(message.from_user.id))
        return
    if not message.document:
        await message.answer("Iltimos, rezyume faylini document ko'rinishida yuboring.")
        return
    db.update_seeker_field(message.from_user.id, "resume_file_id", message.document.file_id)
    db.update_seeker_field(message.from_user.id, "resume_file_name", message.document.file_name or "resume")
    seeker = db.get_seeker_by_tg(message.from_user.id)
    await state.clear()
    await message.answer(
        "✅ Rezyume yuklandi.\n\nArizangiz qayta admin tekshiruviga yuborildi.",
        reply_markup=menu_for(message.from_user.id),
    )
    await send_seeker_moderation_to_admins(bot, seeker)


@router.message(F.text == "📌 Mening vakansiyalarim", StateFilter("*"))
async def my_vacancies(message: Message, state: FSMContext) -> None:
    await state.clear()
    vacancies = db.list_vacancies_by_employer(message.from_user.id, limit=20)
    if not vacancies:
        await message.answer(
            "Siz hali vakansiya yaratmagansiz.\n\nBoshlash uchun <b>🏢 Ishchi topish</b> tugmasini bosing.",
            reply_markup=menu_for(message.from_user.id),
        )
        return
    await message.answer(f"📌 Sizning vakansiyalaringiz: {len(vacancies)}")
    for vacancy in vacancies:
        await message.answer(
            vacancy_card(vacancy),
            reply_markup=my_vacancy_keyboard(int(row_get(vacancy, "id")), int(row_get(vacancy, "active", 0)) == 1),
        )


@router.callback_query(F.data.startswith("my_vac:toggle:"))
async def my_vacancy_toggle(callback: CallbackQuery) -> None:
    vacancy_id = int(callback.data.split(":")[2])
    vacancy = db.get_vacancy(vacancy_id)
    if not vacancy or int(row_get(vacancy, "employer_tg_id")) != callback.from_user.id:
        await callback.answer("Vakansiya topilmadi.", show_alert=True)
        return
    new_active = 0 if int(row_get(vacancy, "active", 0)) == 1 else 1
    db.update_vacancy_field(vacancy_id, "active", new_active)
    await callback.message.answer("✅ Vakansiya holati yangilandi.")
    await callback.answer()


@router.callback_query(F.data.startswith("my_vac:matches:"))
async def my_vacancy_matches(callback: CallbackQuery, bot: Bot) -> None:
    vacancy_id = int(callback.data.split(":")[2])
    vacancy = db.get_vacancy(vacancy_id)
    if not vacancy or int(row_get(vacancy, "employer_tg_id")) != callback.from_user.id:
        await callback.answer("Vakansiya topilmadi.", show_alert=True)
        return
    await send_matches_to_employer(bot, vacancy)
    await callback.answer()


@router.message(F.text == "👨‍💼 Ishga ariza topshirish", StateFilter("*"))
async def seeker_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    existing = db.get_seeker_by_tg(message.from_user.id)
    if existing and clean_text(row_get(existing, "moderation_status"), "") == "pending":
        await message.answer(
            "⏳ Arizangiz hozir admin tekshiruvida.\n\n"
            "Tekshiruv tugaguncha yangi ariza yuborish shart emas.",
            reply_markup=menu_for(message.from_user.id),
        )
        return
    await state.set_state(SeekerForm.photo)
    await message.answer(
        "👨‍💼 <b>Ishga ariza topshirish</b>\n\n"
        "Avval profilingiz uchun rasm yuboring.\n\n"
        "📸 Rasm talabi:\n"
        "• o'zingizning oxirgi 15 kunda tushgan rasmingiz bo'lsin\n"
        "• yuzingiz aniq ko'rinsin\n"
        "• begona odamlar, reklama yoki xira rasm bo'lmasin",
        reply_markup=cancel_menu(),
    )


@router.message(SeekerForm.photo)
async def seeker_photo(message: Message, state: FSMContext) -> None:
    if not message.photo:
        await message.answer("Iltimos, foto yuboring.")
        return
    await state.update_data(photo_id=message.photo[-1].file_id)
    await state.set_state(SeekerForm.full_name)
    await message.answer("Ism familiyangizni kiriting.\nMisol: Ozodbek Mamatov", reply_markup=cancel_menu())


@router.message(SeekerForm.full_name)
async def seeker_full_name(message: Message, state: FSMContext) -> None:
    await state.update_data(full_name=clean_text(message.text))
    await state.set_state(SeekerForm.birth_date)
    await message.answer("Tug'ilgan sanangizni kiriting.\nFormat: <code>kun.oy.yil</code>\nMisol: <code>15.04.2001</code>")


@router.message(SeekerForm.birth_date)
async def seeker_birth_date(message: Message, state: FSMContext) -> None:
    parsed = parse_birth_date(message.text)
    if parsed is None:
        await message.answer("Sanani to'g'ri kiriting.\nFormat: <code>kun.oy.yil</code>\nMisol: <code>15.04.2001</code>")
        return
    birth_date, age = parsed
    await state.update_data(birth_date=birth_date, age=age)
    await state.set_state(SeekerForm.gender)
    await message.answer("Jinsingizni tanlang.", reply_markup=gender_menu())


@router.message(SeekerForm.gender)
async def seeker_gender(message: Message, state: FSMContext) -> None:
    if message.text not in {"Erkak", "Ayol"}:
        await message.answer("Jinsni tugmadan tanlang.", reply_markup=gender_menu())
        return
    await state.update_data(gender=message.text)
    await state.set_state(SeekerForm.phone)
    await message.answer(
        "Telefon raqamingizni qo'lda kiriting.\nMisol: <code>+998 90 123 45 67</code>",
        reply_markup=contact_menu(),
    )


@router.message(SeekerForm.phone)
async def seeker_phone(message: Message, state: FSMContext) -> None:
    phone = normalize_phone(message.text)
    if phone is None:
        await message.answer("Telefon raqam noto'g'ri. Misol: <code>+998 90 123 45 67</code>")
        return
    await state.update_data(phone=phone)
    await state.set_state(SeekerForm.region)
    await message.answer("Hududingizni tanlang.", reply_markup=regions_menu())


@router.message(SeekerForm.region)
async def seeker_region(message: Message, state: FSMContext) -> None:
    region = clean_text(message.text)
    if not is_valid_region(region):
        await message.answer("Iltimos, viloyatni tugmalardan tanlang.", reply_markup=regions_menu())
        return
    await state.update_data(region=region, district=None)
    await state.set_state(SeekerForm.district)
    await message.answer("Tuman yoki shaharni tanlang.", reply_markup=districts_menu(region))


@router.message(SeekerForm.district)
async def seeker_district(message: Message, state: FSMContext) -> None:
    district = clean_text(message.text)
    data = await state.get_data()
    region = data.get("region")
    if not is_valid_district(region, district):
        await message.answer("Iltimos, tumanni tugmalardan tanlang.", reply_markup=districts_menu(region))
        return
    await state.update_data(district=district)
    await state.set_state(SeekerForm.profession)
    await message.answer("Kasbingizni tanlang.", reply_markup=profession_keyboard(db.list_professions(), "seeker_prof"))


@router.callback_query(SeekerForm.profession, F.data.startswith("seeker_prof:"))
async def seeker_profession(callback: CallbackQuery, state: FSMContext) -> None:
    profession_id = int(callback.data.split(":")[1])
    profession = db.get_profession(profession_id)
    if not profession:
        await callback.answer("Kasb topilmadi.", show_alert=True)
        return
    await state.update_data(profession_id=profession_id, profession_title=profession["title"])
    await state.set_state(SeekerForm.job_type)
    await callback.message.answer("Qaysi ish turi sizga ma'qul?", reply_markup=seeker_job_type_keyboard())
    await callback.answer()


@router.callback_query(SeekerForm.job_type, F.data.startswith("seeker_job_type:"))
async def seeker_job_type(callback: CallbackQuery, state: FSMContext) -> None:
    job_type = callback.data.split(":", 1)[1]
    await state.update_data(job_type=job_type)
    await state.set_state(SeekerForm.experience)
    await callback.message.answer("Tajribangizni kiriting.\nMisol: <code>2 yil</code>", reply_markup=cancel_menu())
    await callback.answer()


@router.message(SeekerForm.experience)
async def seeker_experience(message: Message, state: FSMContext) -> None:
    experience = clean_text(message.text)
    await state.update_data(experience=experience, experience_years=parse_experience_years(experience))
    await state.set_state(SeekerForm.education)
    await message.answer("Ma'lumot darajangizni tanlang.", reply_markup=education_keyboard("seeker_education"))


@router.callback_query(SeekerForm.education, F.data.startswith("seeker_education:"))
async def seeker_education(callback: CallbackQuery, state: FSMContext) -> None:
    education = callback.data.split(":", 1)[1]
    await state.update_data(education=education)
    await state.set_state(SeekerForm.excel_level)
    await callback.message.answer("📊 Excel bilish darajangizni tanlang.", reply_markup=skill_level_keyboard("seeker_excel"))
    await callback.answer()


@router.callback_query(SeekerForm.excel_level, F.data.startswith("seeker_excel:"))
async def seeker_excel_level(callback: CallbackQuery, state: FSMContext) -> None:
    level = callback.data.split(":", 1)[1]
    await state.update_data(excel_level=level)
    await state.set_state(SeekerForm.word_level)
    await callback.message.answer("📝 Word bilish darajangizni tanlang.", reply_markup=skill_level_keyboard("seeker_word"))
    await callback.answer()


@router.callback_query(SeekerForm.word_level, F.data.startswith("seeker_word:"))
async def seeker_word_level(callback: CallbackQuery, state: FSMContext) -> None:
    level = callback.data.split(":", 1)[1]
    await state.update_data(word_level=level)
    await state.set_state(SeekerForm.previous_job)
    await callback.message.answer("Oldingi ish joyingizni kiriting.\nAgar bo'lmasa: Yo'q", reply_markup=cancel_menu())
    await callback.answer()


@router.message(SeekerForm.previous_job)
async def seeker_previous_job(message: Message, state: FSMContext) -> None:
    await state.update_data(previous_job=clean_text(message.text))
    await state.set_state(SeekerForm.previous_salary)
    await message.answer("Oldingi ish joyingizdagi oylikni kiriting.\nMisol: <code>5 000 000</code>")


@router.message(SeekerForm.previous_salary)
async def seeker_previous_salary(message: Message, state: FSMContext) -> None:
    previous_salary = clean_text(message.text)
    amount = parse_money_amount(previous_salary)
    if amount is None:
        await message.answer("Maoshni raqam bilan kiriting.\nMisol: <code>6 000 000</code>")
        return
    await state.update_data(previous_salary=previous_salary, previous_salary_amount=amount)
    await state.set_state(SeekerForm.current_salary)
    await message.answer("Hozir olayotgan oyligingizni kiriting.\nAgar hozir ishlamayotgan bo'lsangiz: <code>0</code>")


@router.message(SeekerForm.current_salary)
async def seeker_current_salary(message: Message, state: FSMContext) -> None:
    current_salary = clean_text(message.text)
    amount = parse_money_amount(current_salary)
    if amount is None and current_salary != "0":
        await message.answer("Oylikni raqam bilan kiriting.\nMisol: <code>6 000 000</code> yoki <code>0</code>")
        return
    if current_salary == "0":
        amount = 0
    await state.update_data(
        current_salary=current_salary,
        current_salary_amount=amount,
        salary=current_salary,
        salary_amount=amount,
    )
    await state.set_state(SeekerForm.extra)
    await message.answer(
        "Qo'shimcha ma'lumot kiriting.\n\n"
        "Qisqa yozing: qaysi ishni xohlaysiz, qaysi ko'nikmalaringiz bor, ish vaqti yoki boshqa muhim talablaringiz.\n"
        "Agar qo'shimcha ma'lumot bo'lmasa: <code>Yo'q</code>"
    )


@router.message(SeekerForm.extra)
async def seeker_extra(message: Message, state: FSMContext) -> None:
    await state.update_data(extra=clean_text(message.text))
    await state.set_state(SeekerForm.resume)
    await message.answer(
        "📎 Rezyume fayl yuboring.\n\nPDF, DOC yoki DOCX yuborishingiz mumkin. Agar rezyume bo'lmasa, <b>⏭ O'tkazib yuborish</b> tugmasini bosing.",
        reply_markup=skip_menu(),
    )


@router.message(SeekerForm.resume)
async def seeker_resume(message: Message, state: FSMContext) -> None:
    if message.text == SKIP:
        await state.update_data(resume_file_id=None, resume_file_name=None)
    elif message.document:
        await state.update_data(
            resume_file_id=message.document.file_id,
            resume_file_name=message.document.file_name or "resume",
        )
    else:
        await message.answer("Rezyumeni document ko'rinishida yuboring yoki <b>⏭ O'tkazib yuborish</b> tugmasini bosing.")
        return
    await state.set_state(SeekerForm.confirm)
    data = await state.get_data()
    await message.answer(seeker_summary(data), reply_markup=seeker_confirm_keyboard())


@router.callback_query(SeekerForm.confirm, F.data == "seeker_confirm")
async def seeker_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    db.upsert_user(callback.from_user.id, callback.from_user.username, callback.from_user.full_name, "seeker")
    seeker_id = db.save_seeker(callback.from_user.id, data)
    seeker = db.get_seeker(seeker_id)
    await send_seeker_moderation_to_admins(bot, seeker)
    await state.clear()
    await callback.message.answer(
        "✅ Arizangiz qabul qilindi.\n\nAriza admin tekshiruviga yuborildi. Tasdiqlangandan keyin kanalga chiqadi va sizga mos vakansiyalar yuboriladi.",
        reply_markup=menu_for(callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(SeekerForm.confirm, F.data == "seeker_cancel")
async def seeker_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("❌ Ariza bekor qilindi.", reply_markup=menu_for(callback.from_user.id))
    await callback.answer()


@router.message(F.text == "🏢 Ishchi topish", StateFilter("*"))
async def vacancy_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    today_vacancies = db.count_vacancies_since(message.from_user.id, day_start_iso())
    if today_vacancies >= 3 and not is_admin(message.from_user.id):
        await message.answer(
            "🛡 Anti-spam cheklovi.\n\nBir kunda ko'pi bilan 3 ta vakansiya yaratish mumkin.",
            reply_markup=menu_for(message.from_user.id),
        )
        return
    await state.set_state(VacancyForm.full_name)
    await message.answer(
        "🏢 <b>Ishchi topish</b>\n\n"
        "Tashkilot ma'lumotlarini bosqichma-bosqich kiriting.\n\n"
        "👤 Ism familiya\n"
        "Misol: <code>Azamat Xudoyberdiyev</code>",
        reply_markup=cancel_menu(),
    )


@router.message(VacancyForm.full_name)
async def vacancy_full_name(message: Message, state: FSMContext) -> None:
    await state.update_data(full_name=clean_text(message.text))
    await state.set_state(VacancyForm.organization)
    await message.answer(
        "Tashkilot nomini kiriting.\nMisol: <code>Techno Market</code>\n\n"
        "Agar tashkilot nomini ko'rsatishni xohlamasangiz, pastdagi tugmani bosing.",
        reply_markup=skip_inline_keyboard("vacancy_org_skip"),
    )


@router.message(VacancyForm.organization)
async def vacancy_organization(message: Message, state: FSMContext) -> None:
    await state.update_data(organization=clean_text(message.text))
    await state.set_state(VacancyForm.phone)
    await message.answer(
        "Telefon raqamni qo'lda kiriting.\nMisol: <code>+998 90 123 45 67</code>",
        reply_markup=contact_menu(),
    )


@router.callback_query(VacancyForm.organization, F.data == "vacancy_org_skip")
async def vacancy_organization_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(organization="Ko'rsatilmagan")
    await state.set_state(VacancyForm.phone)
    await callback.message.answer(
        "Telefon raqamni qo'lda kiriting.\nMisol: <code>+998 90 123 45 67</code>",
        reply_markup=contact_menu(),
    )
    await callback.answer()


@router.message(VacancyForm.phone)
async def vacancy_phone(message: Message, state: FSMContext) -> None:
    phone = normalize_phone(message.text)
    if phone is None:
        await message.answer("Telefon raqam noto'g'ri. Misol: <code>+998 90 123 45 67</code>")
        return
    await state.update_data(phone=phone)
    await state.set_state(VacancyForm.region)
    await message.answer("Viloyatni tanlang.", reply_markup=regions_menu())


@router.message(VacancyForm.region)
async def vacancy_region(message: Message, state: FSMContext) -> None:
    region = clean_text(message.text)
    if not is_valid_region(region):
        await message.answer("Iltimos, viloyatni tugmalardan tanlang.", reply_markup=regions_menu())
        return
    await state.update_data(region=region, district=None)
    await state.set_state(VacancyForm.district)
    await message.answer("Tuman yoki shaharni tanlang.", reply_markup=districts_menu(region))


@router.message(VacancyForm.district)
async def vacancy_district(message: Message, state: FSMContext) -> None:
    district = clean_text(message.text)
    data = await state.get_data()
    region = data.get("region")
    if not is_valid_district(region, district):
        await message.answer("Iltimos, tumanni tugmalardan tanlang.", reply_markup=districts_menu(region))
        return
    await state.update_data(district=district)
    await state.set_state(VacancyForm.profession)
    await message.answer("Kerakli mutaxassislikni tanlang.", reply_markup=profession_keyboard(db.list_professions(), "vac_prof"))


@router.callback_query(VacancyForm.profession, F.data.startswith("vac_prof:"))
async def vacancy_profession(callback: CallbackQuery, state: FSMContext) -> None:
    profession_id = int(callback.data.split(":")[1])
    profession = db.get_profession(profession_id)
    if not profession:
        await callback.answer("Kasb topilmadi.", show_alert=True)
        return
    await state.update_data(profession_id=profession_id, profession_title=profession["title"])
    await state.set_state(VacancyForm.staff_count)
    await callback.message.answer("Nechta xodim kerak?\nMisol: 5", reply_markup=cancel_menu())
    await callback.answer()


@router.message(VacancyForm.staff_count)
async def vacancy_staff_count(message: Message, state: FSMContext) -> None:
    staff_count = parse_positive_int(clean_text(message.text), minimum=1, maximum=10000)
    if staff_count is None:
        await message.answer("Xodim sonini raqam bilan kiriting.")
        return
    await state.update_data(staff_count=staff_count)
    await state.set_state(VacancyForm.job_type)
    await message.answer("Ish turini tanlang.", reply_markup=job_type_keyboard())


@router.callback_query(VacancyForm.job_type, F.data.startswith("job_type:"))
async def vacancy_job_type(callback: CallbackQuery, state: FSMContext) -> None:
    job_type = callback.data.split(":")[1]
    await state.update_data(job_type=job_type)
    await state.set_state(VacancyForm.salary)
    await callback.message.answer("Maoshni kiriting.\nMisol: 6 000 000", reply_markup=cancel_menu())
    await callback.answer()


@router.message(VacancyForm.salary)
async def vacancy_salary(message: Message, state: FSMContext) -> None:
    salary = clean_text(message.text)
    amount = parse_money_amount(salary)
    if amount is None:
        await message.answer("Maoshni raqam bilan kiriting.\nMisol: <code>6 000 000</code>")
        return
    await state.update_data(salary=salary, salary_amount=amount)
    await state.set_state(VacancyForm.requirements)
    await message.answer(
        "Talablarni kiriting.\nMisol:\n2 yil tajriba\nWord, Excel bilishi kerak"
    )


@router.message(VacancyForm.requirements)
async def vacancy_requirements(message: Message, state: FSMContext) -> None:
    requirements = clean_text(message.text)
    await state.update_data(requirements=requirements, min_experience_years=parse_experience_years(requirements))
    await state.set_state(VacancyForm.confirm)
    data = await state.get_data()
    await message.answer(vacancy_summary(data), reply_markup=vacancy_confirm_keyboard())


@router.callback_query(VacancyForm.confirm, F.data == "vacancy_confirm")
async def vacancy_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    db.upsert_user(callback.from_user.id, callback.from_user.username, callback.from_user.full_name, "employer")
    db.save_employer(callback.from_user.id, data)
    vacancy_id = db.save_vacancy(callback.from_user.id, data)
    vacancy = db.get_vacancy(vacancy_id)
    await send_vacancy_moderation_to_admins(bot, vacancy)
    await state.clear()
    await callback.message.answer(
        "✅ Vakansiya yaratildi.\n\nVakansiya admin tekshiruviga yuborildi. Tasdiqlangandan keyin kanalga chiqadi va mos nomzodlar yuboriladi.",
        reply_markup=menu_for(callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(VacancyForm.confirm, F.data == "vacancy_cancel")
async def vacancy_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("❌ Vakansiya bekor qilindi.", reply_markup=menu_for(callback.from_user.id))
    await callback.answer()


@router.callback_query(F.data.startswith("emp_interest:"))
async def employer_interest(callback: CallbackQuery, bot: Bot) -> None:
    _, vacancy_id_raw, seeker_id_raw = callback.data.split(":")
    vacancy_id = int(vacancy_id_raw)
    seeker_id = int(seeker_id_raw)
    vacancy = db.get_vacancy(vacancy_id)
    seeker = db.get_seeker(seeker_id)
    if not vacancy or not seeker:
        await callback.answer("Ma'lumot topilmadi.", show_alert=True)
        return
    if int(row_get(vacancy, "employer_tg_id")) != callback.from_user.id and not is_admin(callback.from_user.id):
        await callback.answer("Bu vakansiya sizga tegishli emas.", show_alert=True)
        return
    interest_id = db.create_interest(
        vacancy_id,
        seeker_id,
        int(row_get(vacancy, "employer_tg_id")),
        int(row_get(seeker, "telegram_id")),
        "pending",
    )
    try:
        await notify_candidate_about_interest(bot, interest_id, vacancy, seeker)
    except Exception as exc:
        logger.warning("Failed to notify candidate: %s", exc)
        await callback.answer("Nomzodga xabar yuborib bo'lmadi.", show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Nomzodga taklif yuborildi.")
    await callback.answer()


@router.callback_query(F.data.startswith("emp_save:"))
async def employer_save_candidate(callback: CallbackQuery) -> None:
    _, vacancy_id_raw, seeker_id_raw = callback.data.split(":")
    vacancy_id = int(vacancy_id_raw)
    seeker_id = int(seeker_id_raw)
    vacancy = db.get_vacancy(vacancy_id)
    if not vacancy:
        await callback.answer("Vakansiya topilmadi.", show_alert=True)
        return
    if int(row_get(vacancy, "employer_tg_id")) != callback.from_user.id and not is_admin(callback.from_user.id):
        await callback.answer("Bu vakansiya sizga tegishli emas.", show_alert=True)
        return
    db.save_candidate_action(int(row_get(vacancy, "employer_tg_id")), vacancy_id, seeker_id, "saved")
    await callback.answer("Nomzod saqlandi.")
    await callback.message.answer("⭐ Nomzod saqlanganlar ro'yxatiga qo'shildi.")


@router.callback_query(F.data.startswith("emp_ignore:"))
async def employer_ignore(callback: CallbackQuery) -> None:
    _, vacancy_id_raw, seeker_id_raw = callback.data.split(":")
    vacancy = db.get_vacancy(int(vacancy_id_raw))
    if not vacancy:
        await callback.answer("Vakansiya topilmadi.", show_alert=True)
        return
    if int(row_get(vacancy, "employer_tg_id")) != callback.from_user.id and not is_admin(callback.from_user.id):
        await callback.answer("Bu vakansiya sizga tegishli emas.", show_alert=True)
        return
    db.save_candidate_action(int(row_get(vacancy, "employer_tg_id")), int(vacancy_id_raw), int(seeker_id_raw), "rejected")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Rad etildi.")


@router.callback_query(F.data.startswith("seeker_vac_interest:"))
async def seeker_vacancy_interest(callback: CallbackQuery, bot: Bot) -> None:
    vacancy_id = int(callback.data.split(":")[1])
    vacancy = db.get_vacancy(vacancy_id)
    seeker = db.get_seeker_by_tg(callback.from_user.id)
    if not vacancy or not seeker:
        await callback.answer("Ma'lumot topilmadi.", show_alert=True)
        return
    if clean_text(row_get(seeker, "moderation_status"), "pending") != "approved":
        await callback.answer("Arizangiz hali admin tasdig'idan o'tmagan.", show_alert=True)
        return
    if clean_text(row_get(vacancy, "moderation_status"), "pending") != "approved" or int(row_get(vacancy, "active", 0)) != 1:
        await callback.answer("Vakansiya hozir aktiv emas.", show_alert=True)
        return
    interest_id = db.create_interest(
        vacancy_id,
        int(row_get(seeker, "id")),
        int(row_get(vacancy, "employer_tg_id")),
        int(row_get(seeker, "telegram_id")),
        "seeker_requested",
    )
    await bot.send_message(
        int(row_get(vacancy, "employer_tg_id")),
        "📩 <b>Nomzod vakansiyangizga qiziqish bildirdi</b>\n\n"
        + f"🎯 Moslik: {match_score(seeker, vacancy)}%\n\n"
        + seeker_match_card(seeker),
        reply_markup=employer_candidate_request_keyboard(interest_id),
    )
    await callback.message.answer("✅ Ish beruvchiga aloqa so'rovi yuborildi.")
    await callback.answer()


@router.callback_query(F.data.startswith("emp_accept_request:"))
async def employer_accept_candidate_request(callback: CallbackQuery, bot: Bot) -> None:
    interest_id = int(callback.data.split(":")[1])
    interest = db.get_interest(interest_id)
    if not interest:
        await callback.answer("So'rov topilmadi.", show_alert=True)
        return
    if int(row_get(interest, "employer_tg_id")) != callback.from_user.id and not is_admin(callback.from_user.id):
        await callback.answer("Bu so'rov sizga tegishli emas.", show_alert=True)
        return
    vacancy = db.get_vacancy(int(row_get(interest, "vacancy_id")))
    seeker = db.get_seeker(int(row_get(interest, "seeker_id")))
    if not vacancy or not seeker:
        await callback.answer("Ma'lumot topilmadi.", show_alert=True)
        return
    db.update_interest_status(interest_id, "accepted")
    await bot.send_message(
        int(row_get(seeker, "telegram_id")),
        "📞 <b>Ish beruvchi:</b>\n"
        f"{esc(row_get(vacancy, 'full_name'))}\n"
        f"{esc(row_get(vacancy, 'phone'))}",
    )
    await bot.send_message(
        int(row_get(vacancy, "employer_tg_id")),
        "📞 <b>Nomzod:</b>\n"
        f"{esc(row_get(seeker, 'full_name'))}\n"
        f"{esc(row_get(seeker, 'phone'))}",
    )
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Kontaktlar yuborildi.")


@router.callback_query(F.data.startswith("emp_reject_request:"))
async def employer_reject_candidate_request(callback: CallbackQuery, bot: Bot) -> None:
    interest_id = int(callback.data.split(":")[1])
    interest = db.get_interest(interest_id)
    if not interest:
        await callback.answer("So'rov topilmadi.", show_alert=True)
        return
    if int(row_get(interest, "employer_tg_id")) != callback.from_user.id and not is_admin(callback.from_user.id):
        await callback.answer("Bu so'rov sizga tegishli emas.", show_alert=True)
        return
    vacancy = db.get_vacancy(int(row_get(interest, "vacancy_id")))
    db.update_interest_status(interest_id, "employer_rejected")
    if vacancy:
        await bot.send_message(
            int(row_get(interest, "seeker_tg_id")),
            f"❌ Ish beruvchi aloqa so'rovini rad etdi.\n\n🏢 {esc(row_get(vacancy, 'organization'))}",
        )
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Rad etildi.")


@router.callback_query(F.data.startswith("cand_accept:"))
async def candidate_accept(callback: CallbackQuery, bot: Bot) -> None:
    interest_id = int(callback.data.split(":")[1])
    interest = db.get_interest(interest_id)
    if not interest:
        await callback.answer("Taklif topilmadi.", show_alert=True)
        return
    if int(row_get(interest, "seeker_tg_id")) != callback.from_user.id:
        await callback.answer("Bu taklif sizga tegishli emas.", show_alert=True)
        return
    vacancy = db.get_vacancy(int(row_get(interest, "vacancy_id")))
    seeker = db.get_seeker(int(row_get(interest, "seeker_id")))
    if not vacancy or not seeker:
        await callback.answer("Ma'lumot topilmadi.", show_alert=True)
        return
    db.update_interest_status(interest_id, "accepted")
    await bot.send_message(
        int(row_get(seeker, "telegram_id")),
        "📞 <b>Ish beruvchi:</b>\n"
        f"{esc(row_get(vacancy, 'full_name'))}\n"
        f"{esc(row_get(vacancy, 'phone'))}",
    )
    await bot.send_message(
        int(row_get(vacancy, "employer_tg_id")),
        "📞 <b>Nomzod:</b>\n"
        f"{esc(row_get(seeker, 'full_name'))}\n"
        f"{esc(row_get(seeker, 'phone'))}",
    )
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Kontaktlar yuborildi.")


@router.callback_query(F.data.startswith("cand_reject:"))
async def candidate_reject(callback: CallbackQuery, bot: Bot) -> None:
    interest_id = int(callback.data.split(":")[1])
    interest = db.get_interest(interest_id)
    if not interest:
        await callback.answer("Taklif topilmadi.", show_alert=True)
        return
    if int(row_get(interest, "seeker_tg_id")) != callback.from_user.id:
        await callback.answer("Bu taklif sizga tegishli emas.", show_alert=True)
        return
    vacancy = db.get_vacancy(int(row_get(interest, "vacancy_id")))
    seeker = db.get_seeker(int(row_get(interest, "seeker_id")))
    db.update_interest_status(interest_id, "rejected")
    if vacancy and seeker:
        await bot.send_message(
            int(row_get(vacancy, "employer_tg_id")),
            f"Nomzod taklifni rad etdi.\n\n👤 {esc(row_get(seeker, 'full_name'))}",
        )
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Rad etildi.")


@router.message()
async def unknown_message(message: Message) -> None:
    await message.answer("Menyudan kerakli bo'limni tanlang.", reply_markup=menu_for(message.from_user.id))


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(".env faylida BOT_TOKEN ko'rsatilmagan.")
    db.init()
    bot = Bot(
        BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    router.message.middleware(SubscriptionMiddleware())
    router.callback_query.middleware(SubscriptionMiddleware())
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
