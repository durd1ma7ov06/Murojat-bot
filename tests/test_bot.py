import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from aiogram.types import Message, Update

from zamdekan.__main__ import make_router
from zamdekan.config import Config
from zamdekan.database import CATEGORIES, Database


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.blocked = set()

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):
        yield b''

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, SendMessage):
            if method.chat_id in self.blocked:
                raise TelegramForbiddenError(method=method, message='Blocked')
            return Message(message_id=1, date=datetime.now(timezone.utc),
                           chat={'id': method.chat_id, 'type': 'private'}, text=method.text)
        return True


class BotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.temp.name) / 'bot.sqlite3'))
        await self.db.open()
        self.session = FakeSession()
        self.bot = Bot('123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijk', session=self.session)
        self.dp = Dispatcher()
        self.dp.include_router(make_router(Config(self.bot.token, frozenset({99}), 'Test', self.db.path), self.db))
        self.counter = 0

    async def asyncTearDown(self):
        await self.dp.storage.close()
        await self.bot.session.close()
        await self.db.close()
        self.temp.cleanup()

    async def send(self, user, text=None, callback=None):
        self.counter += 1
        sender = {'id': user, 'is_bot': False, 'first_name': 'Test'}
        message = {'message_id': self.counter, 'date': int(datetime.now(timezone.utc).timestamp()),
                   'chat': {'id': user, 'type': 'private'}, 'from': sender, 'text': text or 'Buttons'}
        payload = {'update_id': self.counter}
        if callback:
            payload['callback_query'] = {'id': str(self.counter), 'from': sender,
                                         'chat_instance': '1', 'message': message, 'data': callback}
        else:
            payload['message'] = message
        await self.dp.feed_update(self.bot, Update.model_validate(payload))

    async def create(self):
        await self.db.save_student(1, 'Ali Valiyev', '21-IT')
        return await self.db.create_ticket(1, CATEGORIES[0], 'Dars jadvali haqida savolim bor.')

    async def test_full_student_flow_and_duplicate_submit(self):
        await self.send(1, '📝 Murojaat yuborish')
        await self.send(1, 'Ali Valiyev')
        await self.send(1, '21-IT')
        await self.send(1, callback='cat:0')
        await self.send(1, 'Dars jadvali haqida savolim bor.')
        await self.send(1, callback='submit')
        await self.send(1, callback='submit')
        self.assertEqual(len(await self.db.tickets(1)), 1)
        self.assertTrue(any(isinstance(m, SendMessage) and m.chat_id == 99 for m in self.session.calls))

    async def test_other_student_cannot_read_ticket(self):
        ticket = await self.create()
        self.assertIsNone(await self.db.ticket(ticket, 2))
        await self.send(2, callback=f'ticket:{ticket}')
        self.assertFalse(any(isinstance(m, SendMessage) for m in self.session.calls))

    async def test_anonymous_identity_hidden_from_admin(self):
        await self.send(1, '📝 Murojaat yuborish')
        await self.send(1, 'Ali Valiyev')
        await self.send(1, '21-IT')
        await self.send(1, callback='anonymous')
        await self.send(1, callback='cat:0')
        await self.send(1, 'Dars jadvali haqida savolim bor.')
        await self.send(1, callback='submit')
        ticket = (await self.db.tickets(1))[0]
        self.assertEqual(ticket['anonymous'], 1)
        await self.send(99, callback=f"ticket:{ticket['id']}")
        admin_messages = [m.text for m in self.session.calls if isinstance(m, SendMessage) and m.chat_id == 99]
        self.assertTrue(admin_messages)
        self.assertTrue(all('Ali Valiyev' not in text and '21-IT' not in text for text in admin_messages))

    async def test_nonadmin_cannot_change_status_or_reply(self):
        ticket = await self.create()
        await self.send(1, callback=f'status:{ticket}:closed')
        await self.send(1, callback=f'reply:{ticket}')
        await self.send(1, callback='list:a:0')
        self.assertEqual((await self.db.ticket(ticket))['status'], 'new')
        self.assertEqual(await self.db.replies(ticket), [])
        self.assertFalse(any(isinstance(m, SendMessage) for m in self.session.calls))

    async def test_admin_status_and_reply(self):
        ticket = await self.create()
        await self.send(99, callback=f'status:{ticket}:review')
        await self.send(99, callback=f'reply:{ticket}')
        await self.send(99, 'Jadval ertaga beriladi.')
        self.assertEqual((await self.db.ticket(ticket))['status'], 'review')
        self.assertEqual((await self.db.replies(ticket))[0]['body'], 'Jadval ertaga beriladi.')

    async def test_blocked_student_reply_persisted(self):
        ticket = await self.create()
        self.session.blocked.add(1)
        await self.send(99, callback=f'reply:{ticket}')
        await self.send(99, 'Javob bazada saqlanadi.')
        self.assertEqual(len(await self.db.replies(ticket)), 1)

    async def test_profile_update_keeps_ticket_snapshot(self):
        ticket = await self.create()
        await self.db.save_student(1, 'Boshqa Ism', '22-IT')
        self.assertEqual((await self.db.ticket(ticket))['full_name'], 'Ali Valiyev')

    async def test_restart_keeps_data(self):
        ticket = await self.create()
        await self.db.close()
        await self.db.open()
        self.assertIsNotNone(await self.db.ticket(ticket, 1))

    async def test_pagination(self):
        for _ in range(7):
            await self.create()
        first = await self.db.tickets(1)
        second = await self.db.tickets(1, offset=5)
        self.assertEqual(len(first), 6)
        self.assertEqual(len(second), 2)
        self.assertFalse({r['id'] for r in first[:5]} & {r['id'] for r in second})

    async def test_cancel_abandons_draft(self):
        await self.send(1, '📝 Murojaat yuborish')
        await self.send(1, '/cancel')
        await self.send(1, callback='cat:0')
        self.assertEqual(await self.db.tickets(1), [])

    async def test_invalid_body_rejected(self):
        await self.db.save_student(1, 'Ali Valiyev', '21-IT')
        with self.assertRaises(ValueError):
            await self.db.create_ticket(1, CATEGORIES[0], 'short')


if __name__ == '__main__':
    unittest.main()
