# Ish topish boti

Telegram orqali ish qidiruvchi va ish beruvchilarni bog'laydigan bot. Bot aiogram 3, SQLite va inline/reply tugmalar asosida yozilgan.

## Imkoniyatlar

- `/start` menyu:
  - 👨‍💼 Ishga ariza topshirish
  - 🏢 Ishchi topish
  - 📄 Mening arizam
  - 📌 Mening vakansiyalarim
- Majburiy obuna:
  - admin paneldan yoqish/o'chirish
  - kanal qo'shish/o'chirish
  - obuna bo'lmaguncha bot ishlamaydi
- Ish qidiruvchi anketasi:
  - foto, ism familiya, tug'ilgan sana `kun.oy.yil`, jins, qo'lda telefon, hudud
  - admin qo'shadigan kasb
  - ish turi: Offline, Online, Gibrid, Farqi yo'q
  - tajriba matni va tajriba yili
  - tugma orqali ma'lumot darajasi
  - Excel va Word bilish darajasi
  - oldingi ish joyi
  - oldingi ish joyidagi oylik
  - hozir olayotgan oylik
  - qisqa qo'shimcha ma'lumot
  - ixtiyoriy rezyume fayl
  - tasdiqlash va admin moderatsiyasiga yuborish
- Ish qidiruvchi profili:
  - arizasini ko'rish
  - profil ma'lumotlarini tahrirlash
  - rezyume yuklash/almashtirish
  - mos vakansiyalarni ko'rish
- Ish beruvchi vakansiyasi:
  - mas'ul, tashkilot, qo'lda telefon, viloyat
  - kerakli mutaxassislik, xodim soni, ish turi, maosh, talablar
  - maosh raqami va minimal tajriba avtomatik ajratiladi
  - vakansiya 30 kundan keyin muddati tugagan holatga o'tadi
  - tasdiqlash va admin moderatsiyasiga yuborish
- Mening vakansiyalarim:
  - vakansiyalarni ko'rish
  - aktiv/yopilgan holatga o'tkazish
  - mos nomzodlarni qayta ko'rish
- Avtomatik mos nomzodlar:
  - vakansiya kasbiga mos nomzodlar ish beruvchiga yuboriladi
  - har bir nomzod uchun kuchaytirilgan moslik foizi ko'rsatiladi
  - moslikda kasb, hudud, ish turi, tajriba, maosh, ta'lim va rezyume hisobga olinadi
  - ish beruvchi nomzodni saqlashi, aloqa so'rashi yoki rad etishi mumkin
  - ish beruvchi qiziqish bildirsa, nomzodga taklif boradi
  - nomzod qabul qilsa, ikki tomonga telefon raqamlari yuboriladi
- Nomzodga mos vakansiyalar:
  - ariza tasdiqlangandan keyin mos vakansiyalar nomzodga yuboriladi
  - nomzod vakansiya bo'yicha aloqa so'rashi mumkin
  - ish beruvchi tasdiqlasa, ikki tomonga kontaktlar yuboriladi
- Admin panel:
  - dashboard
  - admin qo'shish/o'chirish
  - ariza va vakansiyalar moderatsiyasi
  - rad etish sababini yozish
  - qidiruv: ID, telefon, ism, tashkilot nomi
  - keng Excel eksport: nomzodlar, vakansiyalar, ish beruvchilar, qiziqishlar, saralashlar, admin log
  - anti-spam cheklovlari
  - admin log: muhim admin amallari saqlanadi
  - SQLite backup olish
  - ommaviy xabarni oldin ko'rish, keyin tasdiqlab yuborish
  - majburiy obuna
  - kasblar qo'shish/tahrirlash/o'chirish
  - ommaviy xabar
  - nomzodlarni filtr va Excel eksport qilish
  - vakansiyalarni ko'rish/o'chirish/tahrirlash

## O'rnatish

1. Kerakli paketlarni o'rnating:

```powershell
python -m pip install -r requirements.txt
```

2. `.env.example` faylidan `.env` yarating va to'ldiring:

```env
BOT_TOKEN=telegram_bot_tokeningiz
ADMIN_IDS=123456789
PUBLIC_CHANNEL_ID=@ish_elonlari
DATABASE_PATH=data/bot.sqlite3
BACKUP_DIR=backups
```

`ADMIN_IDS` uchun o'zingizning Telegram ID raqamingizni yozing. Bir nechta admin bo'lsa vergul bilan ajrating.

`PUBLIC_CHANNEL_ID` nomzodlar va vakansiyalar chiqadigan kanal. Bot shu kanalga admin qilingan bo'lishi kerak.

## Ma'lumotlar O'chib Ketmasligi

Bot barcha foydalanuvchi, ariza, vakansiya va admin ma'lumotlarini SQLite bazada saqlaydi:

```text
data/bot.sqlite3
```

Yangilash paytida `data/` papkasini va `.env` faylini o'chirmang. Kod fayllarini yangilasangiz ham baza shu joyda qolsa, ma'lumotlar saqlanadi.

Bot ishga tushganda avtomatik backup oladi:

```text
backups/
```

Admin panelda `💾 Backup` tugmasi bor. Admin shu tugmani bosib SQLite bazaning nusxasini Telegram orqali fayl sifatida oladi.

GitHubga `.env`, `data/`, `generated/` va `backups/` papkalari chiqmaydi. Bu token, baza va backup fayllarni himoya qiladi.

3. Botni ishga tushiring:

```powershell
python main.py
```

## Admin panel

Admin panelga kirish:

```text
/admin
```

Admin bo'lgan foydalanuvchilarda asosiy menyuda `🛠 Admin panel` tugmasi ham chiqadi. Oddiy foydalanuvchilarga bu tugma ko'rinmaydi.

Admin qo'shish uchun admin paneldan `👑 Adminlar` bo'limiga kiring va foydalanuvchining Telegram ID raqamini yuboring. `.env` ichidagi asosiy adminlarni paneldan o'chirib bo'lmaydi.

Majburiy obuna uchun kanal qo'shganda oddiy kanal username kiritsa bo'ladi:

```text
@kanal_username
```

Yopiq kanal uchun quyidagi formatdan foydalaning:

```text
-1001234567890 | Kanal nomi | https://t.me/+invite_link
```

## Fayllar

- `main.py` - bot handlerlari va biznes logika
- `database.py` - SQLite jadval va so'rovlar
- `keyboards.py` - reply va inline tugmalar
- `config.py` - `.env` konfiguratsiya
- `requirements.txt` - kerakli Python paketlar
- `data/bot.sqlite3` - bot ishga tushganda yaratiladigan SQLite baza
- `generated/nomzodlar.xlsx` - admin Excel eksport fayli
