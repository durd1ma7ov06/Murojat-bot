from pathlib import Path

import aiosqlite


STATUSES = {"new": "Yangi", "review": "Ko'rib chiqilmoqda", "closed": "Yakunlangan"}
CATEGORIES = ("O'qish va darslar", "Davomat", "Stipendiya", "Yotoqxona", "Boshqa masala")


class Database:
    def __init__(self, path: str):
        self.path = path
        self.connection = None

    async def open(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = await aiosqlite.connect(self.path)
        self.connection.row_factory = aiosqlite.Row
        await self.connection.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS students (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                group_name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES students(user_id),
                full_name TEXT NOT NULL,
                group_name TEXT NOT NULL,
                category TEXT NOT NULL,
                body TEXT NOT NULL,
                anonymous INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new', 'review', 'closed')),
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M', 'now'))
            );
            CREATE INDEX IF NOT EXISTS tickets_owner ON tickets(user_id, id);
            CREATE INDEX IF NOT EXISTS tickets_status ON tickets(status, id);
            CREATE TABLE IF NOT EXISTS replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL REFERENCES tickets(id),
                admin_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M', 'now'))
            );
        """)
        await self.connection.commit()

    async def close(self):
        if self.connection:
            await self.connection.close()

    async def one(self, sql, params=()):
        async with self.connection.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def many(self, sql, params=()):
        async with self.connection.execute(sql, params) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def student(self, user_id):
        return await self.one("SELECT * FROM students WHERE user_id=?", (user_id,))

    async def save_student(self, user_id, full_name, group_name):
        await self.connection.execute(
            "INSERT INTO students VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET full_name=excluded.full_name, group_name=excluded.group_name",
            (user_id, full_name, group_name),
        )
        await self.connection.commit()

    async def create_ticket(self, user_id, category, body, anonymous=False):
        if category not in CATEGORIES or not 10 <= len(body) <= 3000:
            raise ValueError("Murojaat turi yoki matni noto'g'ri.")
        student = await self.student(user_id)
        if not student:
            raise ValueError("Avval ro'yxatdan o'ting.")
        async with self.connection.execute(
            "INSERT INTO tickets (user_id, full_name, group_name, category, body, anonymous) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, student["full_name"], student["group_name"], category, body, int(anonymous)),
        ) as cursor:
            ticket_id = cursor.lastrowid
        await self.connection.commit()
        return ticket_id

    async def ticket(self, ticket_id, owner_id=None):
        if owner_id is not None:
            return await self.one("SELECT * FROM tickets WHERE id=? AND user_id=?", (ticket_id, owner_id))
        return await self.one("SELECT * FROM tickets WHERE id=?", (ticket_id,))

    async def tickets(self, owner_id=None, offset=0):
        if owner_id is not None:
            return await self.many("SELECT * FROM tickets WHERE user_id=? ORDER BY id DESC LIMIT 6 OFFSET ?", (owner_id, offset))
        return await self.many("SELECT * FROM tickets WHERE status!='closed' ORDER BY id LIMIT 6 OFFSET ?", (offset,))

    async def set_status(self, ticket_id, status):
        if status not in STATUSES:
            raise ValueError("Noto'g'ri holat.")
        await self.connection.execute("UPDATE tickets SET status=? WHERE id=?", (status, ticket_id))
        await self.connection.commit()

    async def add_reply(self, ticket_id, admin_id, body):
        if not 1 <= len(body) <= 3000:
            raise ValueError("Javob 1–3000 belgi bo'lsin.")
        await self.connection.execute("INSERT INTO replies (ticket_id, admin_id, body) VALUES (?, ?, ?)", (ticket_id, admin_id, body))
        await self.connection.commit()

    async def replies(self, ticket_id):
        return await self.many("SELECT * FROM replies WHERE ticket_id=? ORDER BY id", (ticket_id,))

    async def stats(self):
        return await self.many("SELECT status, COUNT(*) AS total FROM tickets GROUP BY status")
