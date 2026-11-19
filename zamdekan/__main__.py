import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup

from .config import Config
from .database import CATEGORIES, STATUSES, Database


class Form(StatesGroup):
    name = State()
    group = State()
    category = State()
    body = State()
    confirm = State()
    reply = State()


def buttons(rows):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
        for row in rows
    ])


def menu(is_admin=False):
    rows = [["📝 Murojaat yuborish"], ["📂 Murojaatlarim", "👤 Profil"], ["ℹ️ Yordam"]]
    if is_admin:
        rows.append(["🛠 Admin panel"])
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t) for t in row] for row in rows], resize_keyboard=True)


def render_ticket(t):
    author = "Talaba: Anonim\n" if t['anonymous'] else f"Talaba: {t['full_name']}\nGuruh: {t['group_name']}\n"
    return (f"Murojaat #{t['id']}\n{author}"
            f"Mavzu: {t['category']}\nHolat: {STATUSES[t['status']]}\n"
            f"Sana (UTC): {t['created_at']}\n\n{t['body']}")


def make_router(config: Config, db: Database):
    router = Router()
    router.message.filter(F.chat.type == ChatType.PRIVATE)
    router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)

    def admin(user_id):
        return user_id in config.admin_ids

    async def notify(bot, chat_id, text, reply_markup=None):
        try:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
            return True
        except TelegramAPIError as exc:
            # Log only the exception type: URLs and message bodies may contain secrets.
            logging.warning("Notification failed (%s)", type(exc).__name__)
            return False

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext):
        await state.clear()
        await message.answer(f"{config.title}\n\nTalaba murojaatini zamdekanga yuborish va javob olish uchun bot.\n"
                             "Ism va guruh talabaning o'zi tomonidan kiritiladi.\nBoshlash uchun menyudan tanlang.", reply_markup=menu(admin(message.from_user.id)))

    @router.message(Command("cancel"))
    async def cancel(message: Message, state: FSMContext):
        await state.clear()
        await message.answer("Amal bekor qilindi.", reply_markup=menu(admin(message.from_user.id)))

    @router.message(Command("id"))
    async def identity(message: Message):
        await message.answer(f"Sizning Telegram ID: {message.from_user.id}")

    @router.message(Command("help"))
    @router.message(F.text == "ℹ️ Yordam")
    async def help_message(message: Message, state: FSMContext):
        await state.clear()
        await message.answer("📝 Murojaat yuborish — ism, guruh, mavzu va murojaat matnini kiriting.\n"
                             "📂 Murojaatlarim — holat va zamdekan javoblarini ko'ring.\n"
                             "👤 Profil — ism va guruhni yangilang.\n"
                             "/cancel — joriy amalni bekor qilish.\n/id — Telegram ID.\n\n"
                             "Murojaat va profil ma'lumotlaringiz bot bazasida saqlanadi va adminlarga ko'rinadi. "
                             "Parol yoki bank karta ma'lumotlarini yubormang.", reply_markup=menu(admin(message.from_user.id)))

    async def registration(message, state, next_action):
        await state.clear()
        await state.update_data(next_action=next_action)
        await state.set_state(Form.name)
        await message.answer("Ism va familiyangizni kiriting (3–100 belgi).\nBekor qilish: /cancel")

    async def ask_category(message, state):
        await state.update_data(anonymous=False)
        await state.set_state(Form.category)
        await message.answer("Murojaat mavzusini tanlang. Ism va guruh zamdekanga ko'rinadi.\n"
                             "Ismni yashirish uchun avval “Anonim yuborish”ni bosing.", reply_markup=buttons(
            [[(category, f"cat:{i}")] for i, category in enumerate(CATEGORIES)] + [[('Anonim yuborish', 'anonymous')]]))

    @router.callback_query(Form.category, F.data == 'anonymous')
    async def anonymous_mode(callback: CallbackQuery, state: FSMContext):
        await state.update_data(anonymous=True)
        await callback.answer("Anonim rejim yoqildi")
        await callback.message.answer("Bot zamdekanga ism va guruhni ko'rsatmaydi. "
                                      "Texnik bazada akkaunt bilan bog'lanish saqlanadi; bu to'liq anonimlik emas. "
                                      "Murojaat matnida shaxsingizni oshkor qiladigan ma'lumot yozmang.\n"
                                      "Endi yuqoridan mavzuni tanlang.")

    @router.message(F.text == "👤 Profil")
    async def profile(message: Message, state: FSMContext):
        await state.clear()
        student = await db.student(message.from_user.id)
        if not student:
            return await registration(message, state, "profile")
        await message.answer(f"Ism: {student['full_name']}\nGuruh: {student['group_name']}",
                             reply_markup=buttons([[('Profilni yangilash', 'profile:edit')]]))

    @router.callback_query(F.data == "profile:edit")
    async def edit_profile(callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        await registration(callback.message, state, "profile")

    @router.message(F.text == "📝 Murojaat yuborish")
    async def new_ticket(message: Message, state: FSMContext):
        await state.clear()
        if not await db.student(message.from_user.id):
            return await registration(message, state, "ticket")
        await ask_category(message, state)

    @router.message(F.text == "📂 Murojaatlarim")
    async def my_tickets(message: Message, state: FSMContext):
        await state.clear()
        await show_list(message, message.from_user.id, False, 0)

    @router.message(Command("admin"))
    @router.message(F.text == "🛠 Admin panel")
    async def admin_panel(message: Message, state: FSMContext):
        if not admin(message.from_user.id):
            return await message.answer("Bu bo'lim faqat adminlar uchun.")
        await state.clear()
        stats = {row['status']: row['total'] for row in await db.stats()}
        await message.answer("Admin panel\n\n" + "\n".join(f"{label}: {stats.get(key, 0)}" for key, label in STATUSES.items()),
                             reply_markup=buttons([[('Ochiq murojaatlar', 'list:a:0')]]))

    @router.message(Form.name)
    async def name(message: Message, state: FSMContext):
        value = (message.text or "").strip()
        if not 3 <= len(value) <= 100 or value.startswith('/'):
            return await message.answer("Ism-familiya 3–100 belgili matn bo'lsin.")
        await state.update_data(full_name=value)
        await state.set_state(Form.group)
        await message.answer("Guruhingizni kiriting. Masalan: 21-IT (2–50 belgi).")

    @router.message(Form.group)
    async def group(message: Message, state: FSMContext):
        value = (message.text or "").strip()
        if not 2 <= len(value) <= 50 or value.startswith('/'):
            return await message.answer("Guruh nomi 2–50 belgili matn bo'lsin.")
        data = await state.get_data()
        await db.save_student(message.from_user.id, data['full_name'], value)
        await state.clear()
        await message.answer("Profil saqlandi.")
        if data.get('next_action') == 'ticket':
            await ask_category(message, state)

    @router.callback_query(Form.category, F.data.startswith("cat:"))
    async def category(callback: CallbackQuery, state: FSMContext):
        index = callback.data.split(':')[-1]
        if not index.isdigit() or not 0 <= int(index) < len(CATEGORIES):
            return await callback.answer("Noto'g'ri mavzu.")
        await state.update_data(category=CATEGORIES[int(index)])
        await state.set_state(Form.body)
        await callback.answer()
        await callback.message.answer("Murojaatingizni bitta matnli xabarda yozing (10–3000 belgi).\nBekor qilish: /cancel")

    @router.message(Form.body)
    async def body(message: Message, state: FSMContext):
        value = (message.text or "").strip()
        if not 10 <= len(value) <= 3000 or value.startswith('/'):
            return await message.answer("Murojaatni 10–3000 belgili matn sifatida yuboring.")
        await state.update_data(body=value)
        await state.set_state(Form.confirm)
        data = await state.get_data()
        mode = "Anonim" if data.get('anonymous') else "Ism bilan"
        await message.answer(f"Mavzu: {data['category']}\nYuborish: {mode}\n\n{value}\n\nZamdekanga yuborilsinmi?",
                             reply_markup=buttons([[('✅ Yuborish', 'submit'), ('Bekor qilish', 'discard')]]))

    @router.callback_query(F.data == 'discard')
    async def discard(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await callback.answer("Bekor qilindi")
        await callback.message.edit_reply_markup(reply_markup=None)

    @router.callback_query(Form.confirm, F.data == 'submit')
    async def submit(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        ticket_id = await db.create_ticket(callback.from_user.id, data['category'], data['body'], data.get('anonymous', False))
        await state.clear()
        await callback.answer("Saqlandi")
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"Murojaat #{ticket_id} qabul qilindi. Holat va javobni “📂 Murojaatlarim” bo'limida ko'rasiz.")
        ticket = await db.ticket(ticket_id)
        for admin_id in config.admin_ids:
            await notify(callback.bot, admin_id, render_ticket(ticket), buttons([[('Murojaatni ochish', f'ticket:{ticket_id}')]]))

    async def show_list(message, user_id, for_admin, offset):
        rows = await db.tickets(None if for_admin else user_id, offset)
        markup = [[(f"#{t['id']} · {STATUSES[t['status']]} · {t['category']}", f"ticket:{t['id']}")] for t in rows[:5]]
        mode = 'a' if for_admin else 's'
        nav = []
        if offset:
            nav.append(('⬅️ Oldingi', f'list:{mode}:{max(0, offset - 5)}'))
        if len(rows) > 5:
            nav.append(('Keyingi ➡️', f'list:{mode}:{offset + 5}'))
        if nav:
            markup.append(nav)
        await message.answer("Ochiq murojaatlar:" if for_admin and rows else "Murojaatlar:" if rows else "Hozircha murojaat yo'q.",
                             reply_markup=buttons(markup) if markup else None)

    @router.callback_query(F.data.startswith('list:'))
    async def ticket_list(callback: CallbackQuery):
        parts = callback.data.split(':')
        if len(parts) != 3 or parts[1] not in ('a', 's') or not parts[2].isdigit():
            return await callback.answer("Noto'g'ri so'rov.")
        for_admin = parts[1] == 'a'
        if for_admin and not admin(callback.from_user.id):
            return await callback.answer("Ruxsat yo'q.", show_alert=True)
        await callback.answer()
        await show_list(callback.message, callback.from_user.id, for_admin, int(parts[2]))

    @router.callback_query(F.data.startswith('ticket:'))
    async def ticket_detail(callback: CallbackQuery):
        value = callback.data.split(':')[-1]
        if not value.isdigit():
            return await callback.answer("Noto'g'ri raqam.")
        is_admin = admin(callback.from_user.id)
        ticket = await db.ticket(int(value), None if is_admin else callback.from_user.id)
        if not ticket:
            return await callback.answer("Murojaat topilmadi.", show_alert=True)
        await callback.answer()
        markup = None
        if is_admin:
            markup = buttons([[('✍️ Javob berish', f'reply:{value}')],
                              [(label, f'status:{value}:{key}') for key, label in STATUSES.items() if key != ticket['status']]])
        await callback.message.answer(render_ticket(ticket), reply_markup=markup)
        for reply in await db.replies(ticket['id']):
            await callback.message.answer(f"Zamdekan javobi · {reply['created_at']} UTC\n\n{reply['body']}")

    @router.callback_query(F.data.startswith('status:'))
    async def change_status(callback: CallbackQuery):
        if not admin(callback.from_user.id):
            return await callback.answer("Ruxsat yo'q.", show_alert=True)
        parts = callback.data.split(':')
        if len(parts) != 3 or not parts[1].isdigit() or parts[2] not in STATUSES:
            return await callback.answer("Noto'g'ri so'rov.")
        ticket = await db.ticket(int(parts[1]))
        if not ticket:
            return await callback.answer("Murojaat topilmadi.")
        if ticket['status'] == parts[2]:
            return await callback.answer("Holat allaqachon o'zgartirilgan.")
        await db.set_status(ticket['id'], parts[2])
        await callback.answer("Holat yangilandi")
        await callback.message.answer(f"#{ticket['id']}: {STATUSES[parts[2]]}")
        await notify(callback.bot, ticket['user_id'], f"Murojaat #{ticket['id']} holati: {STATUSES[parts[2]]}")

    @router.callback_query(F.data.startswith('reply:'))
    async def begin_reply(callback: CallbackQuery, state: FSMContext):
        if not admin(callback.from_user.id):
            return await callback.answer("Ruxsat yo'q.", show_alert=True)
        value = callback.data.split(':')[-1]
        if not value.isdigit() or not await db.ticket(int(value)):
            return await callback.answer("Murojaat topilmadi.")
        await state.clear()
        await state.update_data(ticket_id=int(value))
        await state.set_state(Form.reply)
        await callback.answer()
        await callback.message.answer(f"#{value} uchun javob yozing (1–3000 belgi).\nBekor qilish: /cancel")

    @router.message(Form.reply)
    async def save_reply(message: Message, state: FSMContext):
        if not admin(message.from_user.id):
            await state.clear()
            return await message.answer("Ruxsat yo'q.")
        value = (message.text or '').strip()
        if not 1 <= len(value) <= 3000 or value.startswith('/'):
            return await message.answer("Javob 1–3000 belgili matn bo'lsin.")
        data = await state.get_data()
        ticket = await db.ticket(data['ticket_id'])
        await db.add_reply(ticket['id'], message.from_user.id, value)
        await state.clear()
        delivered = await notify(message.bot, ticket['user_id'], f"Murojaat #{ticket['id']} uchun zamdekan javobi:\n\n{value}")
        await message.answer("Javob saqlandi va talabaga yuborildi." if delivered else
                             "Javob saqlandi. Telegram xabari yetkazilmadi; talaba uni “Murojaatlarim” bo'limida ko'radi.")

    @router.message()
    async def fallback(message: Message, state: FSMContext):
        current = await state.get_state()
        await message.answer("Yuqoridagi tugmadan tanlang yoki /cancel yuboring." if current else
                             "Menyudan kerakli bo'limni tanlang. /help — yordam.", reply_markup=menu(admin(message.from_user.id)))

    @router.callback_query()
    async def stale_button(callback: CallbackQuery):
        await callback.answer("Bu tugma eskirgan. Menyudan qayta boshlang.", show_alert=True)

    return router


async def main():
    config = Config.from_env()
    db = Database(config.database_path)
    await db.open()
    try:
        async with Bot(config.token) as bot:
            await bot.set_my_commands([
                BotCommand(command='start', description='Bosh menyu'),
                BotCommand(command='help', description='Yordam'),
                BotCommand(command='cancel', description='Amalni bekor qilish'),
                BotCommand(command='id', description='Telegram ID'),
            ])
            dispatcher = Dispatcher()
            dispatcher.include_router(make_router(config, db))
            await dispatcher.start_polling(bot, handle_as_tasks=False)
    finally:
        await db.close()


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    try:
        asyncio.run(main())
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
