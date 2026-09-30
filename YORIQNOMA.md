# 📝 Ish Topish Bot — Test biriktirish yo'riqnomasi (Admin uchun)

Bu qo'llanma **test qanday biriktirilishini** va **nomzod uchun jarayon qanday
kechishini** tushuntiradi. Oddiy, bosqichma-bosqich yozilgan — mijozga ko'rsatish
uchun tayyor.

---

## 1. Qisqacha: bu qanday ishlaydi?

- Testlarning o'zi **DoriKent Test Bot**da tayyorlanadi (savollar, javoblar, o'tish bali).
- Ish Topish Bot esa faqat **qaysi testni** nomzodga berishni belgilaydi.
- Test **kasbga** biriktiriladi (har kasbga 1 ta), yoki bitta **yakuniy (umumiy) test** bo'ladi.

**Jarayon tartibi (muhim):**
1. Nomzod **ma'lumotlarini kiritadi** va **kasbini tanlaydi**.
2. Darhol **testni topshiradi** (bu — arizaning yakuniy bosqichi).
3. Test tugagach **natija** hisoblanadi va nomzodga ko'rsatiladi.
4. Ariza **natijasi bilan birga ADMINGA** yuboriladi.
5. Admin **tasdiqlasa** → nomzod va uning **test natijasi kanalga** joylanadi.

> Qisqasi: **Ma'lumot → Test → Natija → Admin tasdig'i → Kanal.**
> Test biriktirish qoidasi: **Kasbga test → bo'lmasa → Yakuniy test.**

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
2. Ma'lumotlarini kiritadi va **kasbini tanlaydi** (Sotuvchi, Dizayner, ...) va tasdiqlaydi.
3. Agar shu kasbga (yoki umumiy) test biriktirilgan bo'lsa, darhol xabar keladi:
   > ✅ Ma'lumotlaringiz qabul qilindi.
   > 📝 **Yakuniy bosqich — test.** Test yakunlangach arizangiz admin tekshiruviga yuboriladi.
   > [📝 Testni boshlash]
4. Nomzod **📝 Testni boshlash** tugmasini bosadi → DoriKent boti ochiladi → testni ishlaydi.
5. Test tugagach **natijasini darhol ko'radi** (foizi, to'g'ri/noto'g'ri).
6. Shundan **keyin** arizasi natija bilan birga **adminga** yuboriladi.

> ⚠️ Muhim: test topshirilmaguncha ariza adminga **bormaydi**. Test — majburiy yakuniy bosqich.
> Nomzod savollarni faqat DoriKent botida ishlaydi; Ish Topish bot savollarni ko'rsatmaydi.

---

## 5. Admin va natija

1. Test tugagach ariza **admin**ga keladi — nomzod ma'lumoti **+ test natijasi** bilan.
2. Admin **✅ Tasdiqlash** yoki **❌ Rad etish** qiladi.
3. **Tasdiqlagach:**
   - Nomzod maxfiy kanalga chiqadi va unga mos vakansiyalar yuboriladi.
   - **Test natijasi kanalga** to'liq joylanadi:
     > 🧪 **Test natijasi**
     > 👤 Nomzod: Ali Valiyev · 💼 Kasb: Sotuvchi · 📝 Test: Мижоз билан ишлаш
     > ❓ Jami: 20 · ✅ To'g'ri: 17 · ❌ Noto'g'ri: 3 · 🎯 Foiz: 85% · 🟢 O'tdi
4. Nomzod o'z natijasini **📄 Mening arizam** bo'limida ham ko'radi.

> Rad etilsa — kanalga hech narsa joylanmaydi. Natija faqat **admin tasdig'idan keyin** chiqadi.
> Admin **👥 Nomzodlar** ro'yxatida va **Excel eksport**da ham test natijasi ko'rinadi.

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
