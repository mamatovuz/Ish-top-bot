from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder


REGIONS = [
    "Toshkent",
    "Toshkent viloyati",
    "Andijon",
    "Farg'ona",
    "Namangan",
    "Samarqand",
    "Buxoro",
    "Navoiy",
    "Qashqadaryo",
    "Surxondaryo",
    "Jizzax",
    "Sirdaryo",
    "Xorazm",
    "Qoraqalpog'iston",
]

CANCEL = "❌ Bekor qilish"
SKIP = "⏭ O'tkazib yuborish"


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="👨‍💼 Ishga ariza topshirish")],
        [KeyboardButton(text="🏢 Ishchi topish")],
        [KeyboardButton(text="📄 Mening arizam"), KeyboardButton(text="📌 Mening vakansiyalarim")],
    ]
    if is_admin:
        keyboard.append([KeyboardButton(text="🛠 Admin panel")])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
    )


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=CANCEL)]],
        resize_keyboard=True,
    )


def skip_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=SKIP)],
            [KeyboardButton(text=CANCEL)],
        ],
        resize_keyboard=True,
    )


def gender_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Erkak"), KeyboardButton(text="Ayol")],
            [KeyboardButton(text=CANCEL)],
        ],
        resize_keyboard=True,
    )


def contact_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=CANCEL)]],
        resize_keyboard=True,
    )


def regions_menu() -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=region)] for region in REGIONS]
    rows.append([KeyboardButton(text=CANCEL)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Dashboard"), KeyboardButton(text="🔐 Majburiy obuna")],
            [KeyboardButton(text="🛂 Moderatsiya"), KeyboardButton(text="👑 Adminlar")],
            [KeyboardButton(text="🧰 Kasblar"), KeyboardButton(text="📣 Ommaviy xabar")],
            [KeyboardButton(text="👥 Nomzodlar"), KeyboardButton(text="🏢 Vakansiyalar")],
            [KeyboardButton(text="🔎 Qidiruv"), KeyboardButton(text="📤 Excel eksport")],
            [KeyboardButton(text="💾 Backup"), KeyboardButton(text="🧾 Admin log")],
            [KeyboardButton(text="🏠 Asosiy menyu")],
        ],
        resize_keyboard=True,
    )


def subscription_keyboard(channels) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for channel in channels:
        url = channel["invite_link"]
        chat_id = str(channel["chat_id"])
        if not url and chat_id.startswith("@"):
            url = f"https://t.me/{chat_id.lstrip('@')}"
        if url:
            builder.button(text=channel["title"], url=url)
    builder.button(text="✅ Tekshirish", callback_data="check_sub")
    builder.adjust(1)
    return builder.as_markup()


def profession_keyboard(professions, prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for profession in professions:
        builder.button(text=profession["title"], callback_data=f"{prefix}:{profession['id']}")
    builder.adjust(2)
    return builder.as_markup()


def seeker_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="seeker_confirm"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="seeker_cancel"),
            ]
        ]
    )


def vacancy_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="vacancy_confirm"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="vacancy_cancel"),
            ]
        ]
    )


def skip_inline_keyboard(callback_data: str = "skip") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⏭ Bo'sh qoldirish", callback_data=callback_data)]]
    )


def job_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Offline", callback_data="job_type:Offline"),
                InlineKeyboardButton(text="Online", callback_data="job_type:Online"),
                InlineKeyboardButton(text="Gibrid", callback_data="job_type:Gibrid"),
            ]
        ]
    )


def seeker_job_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Offline", callback_data="seeker_job_type:Offline"),
                InlineKeyboardButton(text="Online", callback_data="seeker_job_type:Online"),
            ],
            [
                InlineKeyboardButton(text="Gibrid", callback_data="seeker_job_type:Gibrid"),
                InlineKeyboardButton(text="Farqi yo'q", callback_data="seeker_job_type:Farqi yo'q"),
            ],
        ]
    )


def seeker_edit_job_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Offline", callback_data="seeker_edit_job_type:Offline"),
                InlineKeyboardButton(text="Online", callback_data="seeker_edit_job_type:Online"),
            ],
            [
                InlineKeyboardButton(text="Gibrid", callback_data="seeker_edit_job_type:Gibrid"),
                InlineKeyboardButton(text="Farqi yo'q", callback_data="seeker_edit_job_type:Farqi yo'q"),
            ],
        ]
    )


def education_keyboard(prefix: str = "education") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="O'rta", callback_data=f"{prefix}:O'rta"),
                InlineKeyboardButton(text="O'rta maxsus", callback_data=f"{prefix}:O'rta maxsus"),
            ],
            [
                InlineKeyboardButton(text="Bakalavr", callback_data=f"{prefix}:Bakalavr"),
                InlineKeyboardButton(text="Magistr", callback_data=f"{prefix}:Magistr"),
            ],
            [InlineKeyboardButton(text="Farqi yo'q", callback_data=f"{prefix}:Farqi yo'q")],
        ]
    )


def skill_level_keyboard(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❌ Bilmayman", callback_data=f"{prefix}:Bilmayman"),
                InlineKeyboardButton(text="🟡 O'rtacha", callback_data=f"{prefix}:O'rtacha"),
            ],
            [InlineKeyboardButton(text="🟢 Yaxshi", callback_data=f"{prefix}:Yaxshi")],
        ]
    )


def employer_candidate_keyboard(vacancy_id: int, seeker_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Saqlash",
                    callback_data=f"emp_save:{vacancy_id}:{seeker_id}",
                ),
                InlineKeyboardButton(
                    text="📞 Aloqa so'rash",
                    callback_data=f"emp_interest:{vacancy_id}:{seeker_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Rad etish",
                    callback_data=f"emp_ignore:{vacancy_id}:{seeker_id}",
                )
            ],
        ]
    )


def candidate_offer_keyboard(interest_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Aloqaga chiqish", callback_data=f"cand_accept:{interest_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"cand_reject:{interest_id}"),
            ]
        ]
    )


def employer_candidate_request_keyboard(interest_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Aloqaga chiqish", callback_data=f"emp_accept_request:{interest_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"emp_reject_request:{interest_id}"),
            ]
        ]
    )


def matched_vacancy_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📞 Aloqa so'rash", callback_data=f"seeker_vac_interest:{vacancy_id}")]
        ]
    )


def seeker_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Tahrirlash", callback_data="my_seeker:edit"),
                InlineKeyboardButton(text="📎 Rezyume yuklash", callback_data="my_seeker:resume"),
            ],
            [InlineKeyboardButton(text="💼 Mos vakansiyalar", callback_data="my_seeker:matches")],
        ]
    )


def seeker_edit_fields_keyboard() -> InlineKeyboardMarkup:
    fields = [
        ("👤 Ism", "full_name"),
        ("🎂 Tug'ilgan sana", "birth_date"),
        ("🚻 Jins", "gender"),
        ("📞 Telefon", "phone"),
        ("📍 Hudud", "region"),
        ("💼 Kasb", "profession"),
        ("🧭 Ish turi", "job_type"),
        ("📈 Tajriba", "experience"),
        ("🎓 Ma'lumot", "education"),
        ("📊 Excel", "excel_level"),
        ("📝 Word", "word_level"),
        ("🏢 Oldingi ish", "previous_job"),
        ("💸 Oldingi oylik", "previous_salary"),
        ("💰 Hozirgi oylik", "current_salary"),
        ("ℹ️ Qo'shimcha", "extra"),
    ]
    builder = InlineKeyboardBuilder()
    for title, field in fields:
        builder.button(text=title, callback_data=f"seeker_edit:{field}")
    builder.adjust(2)
    return builder.as_markup()


def my_vacancy_keyboard(vacancy_id: int, active: bool) -> InlineKeyboardMarkup:
    status_text = "🔴 Yopish" if active else "🟢 Faollashtirish"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=status_text, callback_data=f"my_vac:toggle:{vacancy_id}"),
                InlineKeyboardButton(text="🔎 Mos nomzodlar", callback_data=f"my_vac:matches:{vacancy_id}"),
            ]
        ]
    )


def admin_moderation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👨‍💼 Arizalar", callback_data="moderation:seekers"),
                InlineKeyboardButton(text="🏢 Vakansiyalar", callback_data="moderation:vacancies"),
            ]
        ]
    )


def seeker_moderation_keyboard(seeker_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"mod_seeker:approve:{seeker_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"mod_seeker:reject:{seeker_id}"),
            ]
        ]
    )


def vacancy_moderation_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"mod_vacancy:approve:{vacancy_id}"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data=f"mod_vacancy:reject:{vacancy_id}"),
            ]
        ]
    )


def admin_subscription_keyboard(enabled: bool, channels) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if enabled:
        builder.button(text="🔴 O'chirish", callback_data="admin_sub:disable")
    else:
        builder.button(text="🟢 Yoqish", callback_data="admin_sub:enable")
    builder.button(text="➕ Kanal qo'shish", callback_data="admin_channel:add")
    for channel in channels:
        builder.button(text=f"🗑 {channel['title']}", callback_data=f"admin_channel:delete:{channel['id']}")
    builder.adjust(1)
    return builder.as_markup()


def admin_professions_keyboard(professions) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Kasb qo'shish", callback_data="admin_prof:add")
    for profession in professions:
        builder.button(text=f"✏️ {profession['title']}", callback_data=f"admin_prof:edit:{profession['id']}")
        builder.button(text="🗑", callback_data=f"admin_prof:delete:{profession['id']}")
    builder.adjust(1, 2)
    return builder.as_markup()


def admin_users_keyboard(admins) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Admin qo'shish", callback_data="admin_user:add")
    for admin in admins:
        builder.button(text=f"🗑 {admin['tg_id']}", callback_data=f"admin_user:delete:{admin['tg_id']}")
    builder.adjust(1)
    return builder.as_markup()


def broadcast_target_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Barcha foydalanuvchilarga", callback_data="broadcast:all")],
            [InlineKeyboardButton(text="🏢 Faqat ish beruvchilarga", callback_data="broadcast:employers")],
            [InlineKeyboardButton(text="👨‍💼 Faqat ish qidiruvchilarga", callback_data="broadcast:seekers")],
        ]
    )


def broadcast_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="broadcast_confirm:yes"),
                InlineKeyboardButton(text="❌ Rad etish", callback_data="broadcast_confirm:no"),
            ]
        ]
    )


def candidate_filter_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚻 Jins", callback_data="filter:gender"),
                InlineKeyboardButton(text="🎂 Yosh", callback_data="filter:age"),
            ],
            [
                InlineKeyboardButton(text="📍 Hudud", callback_data="filter:region"),
                InlineKeyboardButton(text="💼 Kasb", callback_data="filter:profession"),
            ],
            [InlineKeyboardButton(text="📈 Tajriba", callback_data="filter:experience")],
            [
                InlineKeyboardButton(text="🧭 Ish turi", callback_data="filter:job_type"),
                InlineKeyboardButton(text="💰 Maosh", callback_data="filter:salary"),
            ],
            [
                InlineKeyboardButton(text="👁 Ko'rish", callback_data="filter:show"),
                InlineKeyboardButton(text="📤 Excel eksport", callback_data="filter:excel"),
            ],
            [InlineKeyboardButton(text="♻️ Tozalash", callback_data="filter:clear")],
        ]
    )


def vacancy_admin_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"vac_admin:edit:{vacancy_id}"),
                InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"vac_admin:delete:{vacancy_id}"),
            ]
        ]
    )


def vacancy_edit_fields_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:
    fields = [
        ("Tashkilot", "organization"),
        ("Telefon", "phone"),
        ("Viloyat", "region"),
        ("Kasb", "profession"),
        ("Xodim soni", "staff_count"),
        ("Ish turi", "job_type"),
        ("Maosh", "salary"),
        ("Talablar", "requirements"),
    ]
    builder = InlineKeyboardBuilder()
    for title, field in fields:
        builder.button(text=title, callback_data=f"vac_edit:{vacancy_id}:{field}")
    builder.adjust(2)
    return builder.as_markup()


def admin_export_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👨‍💼 Nomzodlar", callback_data="export:seekers"),
                InlineKeyboardButton(text="🏢 Vakansiyalar", callback_data="export:vacancies"),
            ],
            [
                InlineKeyboardButton(text="👔 Ish beruvchilar", callback_data="export:employers"),
                InlineKeyboardButton(text="❤️ Qiziqishlar", callback_data="export:interests"),
            ],
            [
                InlineKeyboardButton(text="⭐ Saralashlar", callback_data="export:candidate_actions"),
                InlineKeyboardButton(text="🧾 Admin log", callback_data="export:admin_logs"),
            ],
        ]
    )
