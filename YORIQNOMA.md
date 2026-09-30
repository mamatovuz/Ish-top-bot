# 📝 Ish Topish Bot — Test biriktirish yo'riqnomasi (Admin uchun)

Bu qo'llanma **test qanday biriktirilishini** va **nomzod uchun jarayon qanday
kechishini** tushuntiradi. Oddiy, bosqichma-bosqich yozilgan — mijozga ko'rsatish
uchun tayyor.

---

## 1. Qisqacha: bu qanday ishlaydi?

- Testlarning o'zi **DoriKent Test Bot**da tayyorlanadi (savollar, javoblar, o'tish bali).
- Ish Topish Bot esa faqat **qaysi testni** nomzodga berishni belgilaydi.
- Nomzod ish topish botida **ariza yuboradi va kasbini tanlaydi**.
- O'sha kasbga test biriktirilgan bo'lsa — nomzodga **o'sha test** beriladi.
- Kasbga test biriktirilmagan bo'lsa — **yakuniy (umumiy) test** beriladi.
- Test tugagach, natija **kanalga** tushadi va nomzodning arizasida ko'rinadi.

> Qisqasi: **Kasbga test → bo'lmasa → Yakuniy test.**

---

## 2. Tayyorgarlik (bir marta)

1. DoriKent botida (`@Dorikent_imtihonbot`) kamida **bitta faol test** bo'lishi kerak
   (savollari bilan). Faol bo'lmagan yoki savolsiz testlar ro'yxatda chiqmaydi.
2. Ish Topish botida siz **admin** bo'lishingiz kerak (Admin panel ochiladi).

---

## 3. Admin: testni biriktirish

### 3.1. "📝 Testlar" bo'limini ochish
1. Botda **🛠 Admin panel** tugmasini bosing.
2. **📝 Testlar** tugmasini bosing.
3. Ekranda ikki xil sozlama chiqadi:
   - **🌐 Yakuniy (umumiy) test** — hamma kasblar uchun zaxira (fallback) test.
   - **💼 Har bir kasb** (Sotuvchi, Dizayner, Farmatsevt, ...) — alohida test.

### 3.2. Bitta kasbga test biriktirish
1. Kerakli kasb tugmasini bosing (masalan **💼 Sotuvchi: —**).
   > "—" belgisi hali test biriktirilmaganini bildiradi.
2. DoriKent'dagi **faol testlar ro'yxati** chiqadi (masalan: *Мижоз билан ишлаш — 20 savol*).
3. Kerakli testni bosing. Tamom — o'sha kasbga test biriktirildi ✅.
4. Endi shu kasbni tanlagan har bir nomzod aynan shu testdan o'tadi.

### 3.3. Yakuniy (umumiy) testni belgilash
1. **🌐 Yakuniy (umumiy) test** tugmasini bosing.
2. Ro'yxatdan bitta testni tanlang.
3. Endi **kasbiga alohida test biriktirilmagan** har bir nomzod shu umumiy testdan o'tadi.

> **Maslahat:** Avval bitta umumiy (yakuniy) test qo'ying — shunda har qanday nomzod
> hech bo'lmasa bitta testdan o'tadi. Keyin muhim kasblarga alohida test biriktirasiz.

### 3.4. Testni o'zgartirish yoki olib tashlash
- **O'zgartirish:** o'sha kasb (yoki yakuniy test) tugmasini qayta bosib, boshqa testni tanlang.
- **Olib tashlash:** ro'yxatdagi **🗑 Testni olib tashlash** tugmasini bosing.
- **Yangilash:** DoriKent'da yangi test qo'shsangiz, **♻️ Yangilash** tugmasi ro'yxatni yangilaydi.

---

## 4. Nomzod (mijoz) uchun jarayon

1. Nomzod botda **👨‍💼 Ishga ariza topshirish** tugmasini bosadi.
2. Ma'lumotlarini kiritadi va **kasbini tanlaydi** (Sotuvchi, Dizayner, ...).
3. Arizani tasdiqlaydi.
4. Agar shu kasbga (yoki umumiy) test biriktirilgan bo'lsa, nomzodga darhol xabar keladi:
   > 📝 **Arizangizning yakuniy bosqichi — test!**
   > 📚 Test: *...*
   > [📝 Testni boshlash]
5. Nomzod **📝 Testni boshlash** tugmasini bosadi → DoriKent boti ochiladi → testni ishlaydi.
6. Test tugagach natija avtomatik qaytadi.

> Nomzod savollarni faqat DoriKent botida ishlaydi. Ish Topish bot savollarni ko'rsatmaydi.

---

## 5. Natija qayerda ko'rinadi?

Test tugagach natija **3 joyda** paydo bo'ladi:

1. **Nomzodga** shaxsiy xabar keladi (foizi, to'g'ri/noto'g'ri javoblari bilan).
2. **📄 Mening arizam** bo'limida nomzod o'z natijasini ko'radi.
3. **Kanalga** to'liq natija tushadi:
   > 🧪 **Test natijasi**
   > 👤 Nomzod: Ali Valiyev
   > 💼 Kasb: Sotuvchi
   > 📝 Test: Мижоз билан ишлаш
   > ❓ Jami savollar: 20 · ✅ To'g'ri: 17 · ❌ Noto'g'ri: 3 · 🎯 Foiz: 85%
   > 🟢 Testdan o'tdi

Admin nomzodlar ro'yxatida ham (👥 Nomzodlar) va Excel eksportda ham test natijasi ko'rinadi.

---

## 6. Ko'p so'raladigan savollar

**Nomzodga test kelmayapti?**
- O'sha nomzod tanlagan **kasbga** test biriktirilganmi? Yoki **🌐 Yakuniy test** belgilanganmi?
- Ikkalasi ham bo'sh bo'lsa — test tayinlanmaydi. Kamida yakuniy testni qo'ying.

**Testlar ro'yxati bo'sh chiqyapti?**
- DoriKent botida faol va savoli bor test yo'q. Avval o'sha yerda test tayyorlang.

**Testni keyin o'zgartirsam, eski natijalar yo'qoladimi?**
- Yo'q. Eski natijalar saqlanib qoladi. Yangi test faqat yangi arizalarga ta'sir qiladi.

**Bir kasbga nechta test biriktirsa bo'ladi?**
- Bitta. Har bir kasb uchun 1 ta test. O'zgartirsangiz, avvalgisining o'rniga o'tadi.

**Test majburiymi?**
- Ha — test biriktirilgan bo'lsa, u arizaning yakuniy bosqichi hisoblanadi.
- Umuman test qo'ymasangiz, nomzod testsiz ariza beradi (avvalgidek).

---

## 7. Qisqa xotira (admin uchun 3 qadam)

1. **DoriKent botida** test tayyorla (savollari bilan, faol qil).
2. **Ish Topish bot → 🛠 Admin panel → 📝 Testlar** ga kir.
3. Kasbga yoki **🌐 Yakuniy test**ga o'sha testni biriktir. Tamom!
