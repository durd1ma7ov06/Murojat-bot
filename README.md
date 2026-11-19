# Zamdekan Telegram boti

Talabalar murojaatini qabul qilish va zamdekan javoblarini yuborish uchun o'zbekcha bot.

## Imkoniyatlar

- Profil: ism, familiya va guruh; ma'lumotlarni yangilash.
- Murojaat mavzusini tanlash, matn kiritish va yuborishdan oldin tasdiqlash.
- Anonim rejim: botning admin ekranida ism va guruh yashiriladi. Bazada akkaunt bilan bog'lanish saqlanadi, to'liq anonimlik ta'minlanmaydi.
- Talaba o'z murojaatlari, holati va zamdekan javoblarini ko'radi.
- Admin: ochiq murojaatlar ro'yxati, statistika, javob berish va holat o'zgartirish.
- SQLite bazasi: profil, murojaat va javoblar qayta ishga tushganda saqlanadi.
- Bot faqat shaxsiy chatda ishlaydi. Ism va guruhni talaba o'zi kiritadi; universitet tizimi bilan tekshirish ulanmagan.

## Ishga tushirish (Windows, Python 3.10+)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

`.env` ichida:

1. `BOT_TOKEN`: Telegramdagi @BotFather orqali `/newbot` bilan yaratilgan bot tokeni. Tokenni ochiq joyga yubormang.
2. `ADMIN_IDS`: adminlarning raqamli Telegram IDlari, vergul bilan ajratiladi. Bu telefon raqami yoki @username emas.
3. `BOT_TITLE`: universitet/fakultet yoki bot nomi.
4. `DATABASE_PATH`: SQLite fayl manzili.

```powershell
.\.venv\Scripts\python.exe -m zamdekan
```

Admin botni ochib `/start` yuborishi kerak; shundan so'ng yangi murojaatlar haqida xabar oladi. `/id` o'z Telegram ID raqamingizni ko'rsatadi. `/cancel` joriy amalni bekor qiladi.

Token va kamida bitta admin ID berilmaguncha bot tushunarli xato bilan to'xtaydi. Bir token uchun botning faqat bitta nusxasini ishga tushiring. Kompyuter o'chsa bot ishlamaydi; doimiy ishlashi uchun serverda ishga tushirish kerak.

## Tekshiruv

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Testlar Telegramga ulanmasdan talaba oqimi, ruxsatlar, takroriy tasdiqlash, javoblar, profil o'zgarishi, sahifalash va qayta ishga tushishni tekshiradi. Token kiritilgach, haqiqiy talaba va admin akkauntlaridan murojaat yuborish, javob berish va holat almashtirishni sinang.

## Saqlash va cheklovlar

Murojaatlar matn ko'rinishida, 10–3000 belgi; javoblar 1–3000 belgi. Foto/hujjat yuborish va HEMIS integratsiyasi hozircha qo'shilmagan. Tugallanmagan forma xotirada turadi va bot qayta ishga tushsa qaytadan to'ldiriladi; tasdiqlangan murojaatlar bazada qoladi.

Telegram xabarini yetkazish imkoni bo'lmasa, javob bazada saqlanadi va talaba uni “Murojaatlarim” bo'limidan o'qiydi. Admin xabarnomasi yetkazilmasa, admin panelidagi ro'yxatdan murojaatni topish mumkin. Xabarnomalarni avtomatik qayta yuborish navbati yo'q.

Botni to'xtatib, `data/` papkasini nusxalash orqali zaxiralang. `.env` va bazani ommaga bermang. Murojaatlardagi shaxsiy ma'lumotlarni faqat mas'ullar ko'rishi kerak.

Aiogram ishlatilishi [rasmiy hujjatlar](https://docs.aiogram.dev/en/latest/) asosida tuzilgan.
