import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    token: str
    admin_ids: frozenset[int]
    title: str
    database_path: str

    @classmethod
    def from_env(cls):
        load_dotenv()
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise ValueError(".env faylida BOT_TOKEN ni kiriting.")
        try:
            admins = frozenset(int(v.strip()) for v in os.getenv("ADMIN_IDS", "").split(",") if v.strip())
        except ValueError:
            raise ValueError("ADMIN_IDS faqat vergul bilan ajratilgan raqamli IDlardan iborat bo'lsin.") from None
        if not admins or any(v <= 0 for v in admins):
            raise ValueError("ADMIN_IDS ga kamida bitta musbat Telegram foydalanuvchi ID kiriting.")
        return cls(token, admins, os.getenv("BOT_TITLE", "Zamdekan"), os.getenv("DATABASE_PATH", "data/zamdekan.sqlite3"))
