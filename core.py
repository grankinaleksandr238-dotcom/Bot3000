# ========== core.py ==========
import asyncio
import logging
import random
import os
import time
import string
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
import asyncpg

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import (
    BotBlocked, UserDeactivated, ChatNotFound, RetryAfter,
    TelegramAPIError, MessageNotModified, MessageToEditNotFound
)
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.dispatcher.handler import CancelHandler

# ===== НАСТРОЙКИ =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в переменных окружения")

SUPER_ADMINS_STR = os.getenv("SUPER_ADMINS", "")
SUPER_ADMINS = [int(x.strip()) for x in SUPER_ADMINS_STR.split(",") if x.strip()]

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не задан. Создай PostgreSQL базу в Railway.")

# Значения по умолчанию для настроек
DEFAULT_SETTINGS = {
    "random_attack_cost": "0",
    "targeted_attack_cost": "50",
    "theft_cooldown_minutes": "30",
    "theft_success_chance": "40",
    "theft_defense_chance": "20",
    "theft_defense_penalty": "10",
    "casino_win_chance": "30",
    "min_theft_amount": "5",
    "max_theft_amount": "15",
    "dice_multiplier": "2",
    "guess_multiplier": "5",
    "guess_reputation": "1",
    "chat_notify_big_win": "1",
    "chat_notify_big_purchase": "1",
    "chat_notify_giveaway": "1",
    "gift_amount": "30",
    "gift_limit_per_day": "3",
    "referral_bonus": "50",
    "referral_reputation": "2",
    # Настройки опыта и уровней
    "exp_per_casino_win": "5",
    "exp_per_casino_lose": "1",
    "exp_per_dice_win": "3",
    "exp_per_dice_lose": "1",
    "exp_per_guess_win": "4",
    "exp_per_guess_lose": "1",
    "exp_per_theft_success": "10",
    "exp_per_theft_fail": "2",
    "exp_per_theft_defense": "5",
    "exp_per_game_win": "15",
    "exp_per_game_lose": "3",
    "level_multiplier": "100",
    "level_reward_coins": "30",          # уменьшено с 50
    "level_reward_reputation": "3",       # уменьшено с 5
    "level_reward_coins_increment": "5",  # уменьшено с 10
    "level_reward_reputation_increment": "1",
    "reputation_theft_bonus": "0.5",
    "reputation_defense_bonus": "0.5",
    # Настройки боссов
    "boss_spawn_chance": "20",
    "boss_min_interval": "360",
    "boss_max_per_day": "2",
    "boss_hp_multiplier": "100",
    "boss_attack_cooldown": "3",
    "boss_base_damage": "10",
    "boss_reward_coins": "500",
    "boss_reward_coins_variance": "200",
    # Настройки подгона
    "gift_global_limit_per_user": "4",
    "gift_cooldown": "60",
    # Настройки статов
    "stat_strength_per_level": "1",
    "stat_agility_per_level": "1",
    "stat_defense_per_level": "1",
    # Настройки аукциона
    "auction_min_bid_step": "10",
    "auction_commission": "0",
    "auction_notify_chats": "1",
    # НОВЫЕ НАСТРОЙКИ ДЛЯ БОЯ В ЧАТАХ
    "fight_cooldown_minutes": "30",
    "fight_base_damage": "5",
    "fight_damage_variance": "3",
    "fight_authority_min": "1",
    "fight_authority_max": "3",
    "gym_strength_cost": "10",
    "gym_agility_cost": "10",
    "gym_defense_cost": "10",
    # Очистка логов
    "cleanup_days_fight_logs": "7",
    "cleanup_days_bosses": "7",
    "cleanup_days_auctions": "30",
    "cleanup_days_purchases": "30",
    "cleanup_days_giveaways": "30",
    "cleanup_days_user_tasks": "30",
}

# Константы
ITEMS_PER_PAGE = 10
BIG_WIN_THRESHOLD = 100
BIG_PURCHASE_THRESHOLD = 100
MAX_ROOMS = 20
MIN_PLAYERS = 2
MAX_PLAYERS = 5
MIN_BET = 3
DEALER_WIN_RATE = 3

# ===== ИНИЦИАЛИЗАЦИЯ =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)

db_pool = None
settings_cache = {}
last_settings_update = 0
channels_cache = []
last_channels_update = 0
confirmed_chats_cache = {}
last_confirmed_chats_update = 0

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ===== МИДЛВАРЬ ДЛЯ ЗАЩИТЫ ОТ ФЛУДА =====
class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit=1.0):
        self.rate_limit = rate_limit
        self.user_last_time = defaultdict(float)
        super().__init__()

    async def on_process_message(self, message: types.Message, data: dict):
        if message.chat.type != 'private' or await is_admin(message.from_user.id):
            return
        user_id = message.from_user.id
        now = time.time()
        if now - self.user_last_time[user_id] < self.rate_limit:
            await message.reply("⏳ Слишком много запросов. Подожди секунду.")
            raise CancelHandler()
        self.user_last_time[user_id] = now

# ===== БЕЗОПАСНАЯ ОТПРАВКА СООБЩЕНИЙ =====
async def safe_send_message(user_id: int, text: str, **kwargs):
    try:
        await bot.send_message(user_id, text, **kwargs)
    except BotBlocked:
        logging.warning(f"Bot blocked by user {user_id}")
    except UserDeactivated:
        logging.warning(f"User {user_id} deactivated")
    except ChatNotFound:
        logging.warning(f"Chat {user_id} not found")
    except RetryAfter as e:
        logging.warning(f"Flood limit exceeded. Retry after {e.timeout} seconds")
        await asyncio.sleep(e.timeout)
        try:
            await bot.send_message(user_id, text, **kwargs)
        except Exception as ex:
            logging.warning(f"Still failed after retry: {ex}")
    except TelegramAPIError as e:
        logging.warning(f"Telegram API error for user {user_id}: {e}")
    except Exception as e:
        logging.warning(f"Failed to send message to {user_id}: {e}")

def safe_send_message_task(user_id: int, text: str, **kwargs):
    asyncio.create_task(safe_send_message(user_id, text, **kwargs))

async def safe_send_chat(chat_id: int, text: str, **kwargs):
    try:
        await bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        logging.error(f"Failed to send to chat {chat_id}: {e}")

# ===== ПОДКЛЮЧЕНИЕ К POSTGRESQL =====
async def create_db_pool():
    global db_pool
    db_pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=5,
        max_size=20,
        command_timeout=60,
        max_queries=50000,
        max_inactive_connection_lifetime=300
    )
    logging.info("Подключение к PostgreSQL установлено")

async def init_db():
    async with db_pool.acquire() as conn:
        # Таблица users
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_date TEXT,
                balance INTEGER DEFAULT 0,
                reputation INTEGER DEFAULT 0,
                total_spent INTEGER DEFAULT 0,
                negative_balance INTEGER DEFAULT 0,
                last_bonus TEXT,
                last_theft_time TEXT,
                theft_attempts INTEGER DEFAULT 0,
                theft_success INTEGER DEFAULT 0,
                theft_failed INTEGER DEFAULT 0,
                theft_protected INTEGER DEFAULT 0,
                casino_wins INTEGER DEFAULT 0,
                casino_losses INTEGER DEFAULT 0,
                guess_wins INTEGER DEFAULT 0,
                guess_losses INTEGER DEFAULT 0,
                game_wins INTEGER DEFAULT 0
            )
        ''')
        # Добавляем новые поля
        await conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS exp INTEGER DEFAULT 0')
        await conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS level INTEGER DEFAULT 1')
        await conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS strength INTEGER DEFAULT 1')
        await conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS agility INTEGER DEFAULT 1')
        await conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS defense INTEGER DEFAULT 1')
        await conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS last_gift_time TEXT')
        await conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS gift_count_today INTEGER DEFAULT 0')

        # Таблица подтверждённых чатов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS confirmed_chats (
                chat_id BIGINT PRIMARY KEY,
                title TEXT,
                type TEXT,
                joined_date TEXT,
                confirmed_by BIGINT,
                confirmed_date TEXT,
                notify_enabled BOOLEAN DEFAULT TRUE,
                last_gift_date DATE,
                gift_count_today INTEGER DEFAULT 0,
                boss_last_spawn TEXT,
                boss_spawn_count INTEGER DEFAULT 0
            )
        ''')

        # Таблица запросов на подтверждение чатов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS chat_confirmation_requests (
                chat_id BIGINT PRIMARY KEY,
                title TEXT,
                type TEXT,
                requested_by BIGINT,
                request_date TEXT,
                status TEXT DEFAULT 'pending'
            )
        ''')

        # Таблица боссов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bosses (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                name TEXT,
                level INTEGER,
                hp INTEGER,
                max_hp INTEGER,
                spawned_at TEXT,
                expires_at TEXT,
                reward_coins INTEGER,
                participants BIGINT[] DEFAULT '{}',
                status TEXT DEFAULT 'active'
            )
        ''')

        # Таблица атак на босса
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS boss_attacks (
                boss_id INTEGER,
                user_id BIGINT,
                damage INTEGER,
                attack_time TEXT,
                PRIMARY KEY (boss_id, user_id)
            )
        ''')

        # Таблица каналов для подписки
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id SERIAL PRIMARY KEY,
                chat_id TEXT UNIQUE,
                title TEXT,
                invite_link TEXT
            )
        ''')
        # Таблица рефералов (добавляем поля clicks и active)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                referrer_id BIGINT,
                referred_id BIGINT UNIQUE,
                referred_date TEXT,
                reward_given BOOLEAN DEFAULT FALSE,
                clicks INTEGER DEFAULT 0,
                active BOOLEAN DEFAULT FALSE
            )
        ''')
        # Таблица товаров магазина
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS shop_items (
                id SERIAL PRIMARY KEY,
                name TEXT,
                description TEXT,
                price INTEGER,
                stock INTEGER DEFAULT -1
            )
        ''')
        # Таблица покупок
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                item_id INTEGER,
                purchase_date TEXT,
                status TEXT DEFAULT 'pending',
                admin_comment TEXT
            )
        ''')
        # Таблица промокодов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                reward INTEGER,
                max_uses INTEGER,
                used_count INTEGER DEFAULT 0,
                created_at TEXT
            )
        ''')
        # Таблица активаций промокодов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS promo_activations (
                user_id BIGINT,
                promo_code TEXT,
                activated_at TEXT,
                PRIMARY KEY (user_id, promo_code)
            )
        ''')
        # Таблица розыгрышей
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS giveaways (
                id SERIAL PRIMARY KEY,
                prize TEXT,
                description TEXT,
                end_date TEXT,
                media_file_id TEXT,
                media_type TEXT,
                status TEXT DEFAULT 'active',
                winner_id BIGINT,
                winners_count INTEGER DEFAULT 1,
                notified BOOLEAN DEFAULT FALSE
            )
        ''')
        # Таблица участников розыгрышей
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS participants (
                user_id BIGINT,
                giveaway_id INTEGER,
                PRIMARY KEY (user_id, giveaway_id)
            )
        ''')
        # Таблица младших админов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id BIGINT PRIMARY KEY,
                added_by BIGINT,
                added_date TEXT
            )
        ''')
        # Таблица забаненных
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id BIGINT PRIMARY KEY,
                banned_by BIGINT,
                banned_date TEXT,
                reason TEXT
            )
        ''')
        # Таблица настроек
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        # Таблица заданий (добавляем поля max_completions, completed_count)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                name TEXT,
                description TEXT,
                task_type TEXT,
                target_id TEXT,
                reward_coins INTEGER DEFAULT 0,
                reward_reputation INTEGER DEFAULT 0,
                required_days INTEGER DEFAULT 0,
                penalty_days INTEGER DEFAULT 0,
                created_by BIGINT,
                created_at TEXT,
                active BOOLEAN DEFAULT TRUE,
                max_completions INTEGER DEFAULT 1,
                completed_count INTEGER DEFAULT 0
            )
        ''')
        # Таблица выполненных заданий
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_tasks (
                user_id BIGINT,
                task_id INTEGER,
                completed_at TEXT,
                expires_at TEXT,
                status TEXT DEFAULT 'completed',
                PRIMARY KEY (user_id, task_id)
            )
        ''')
        # Таблица мультиплеерных игр
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS multiplayer_games (
                game_id TEXT PRIMARY KEY,
                host_id BIGINT,
                max_players INTEGER,
                bet_amount INTEGER,
                status TEXT DEFAULT 'waiting',
                deck TEXT,
                created_at TEXT,
                current_player_index INTEGER DEFAULT 0
            )
        ''')
        # Таблица игроков в мультиплеере
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS game_players (
                game_id TEXT,
                user_id BIGINT,
                username TEXT,
                cards TEXT,
                value INTEGER DEFAULT 0,
                stopped BOOLEAN DEFAULT FALSE,
                joined_at TEXT,
                doubled BOOLEAN DEFAULT FALSE,
                surrendered BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (game_id, user_id)
            )
        ''')
        # Таблица наград за уровень
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS level_rewards (
                level INTEGER PRIMARY KEY,
                coins INTEGER,
                reputation INTEGER
            )
        ''')

        # Таблицы аукционов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS auctions (
                id SERIAL PRIMARY KEY,
                item_name TEXT NOT NULL,
                description TEXT,
                start_price INTEGER NOT NULL,
                current_price INTEGER NOT NULL,
                start_time TIMESTAMP NOT NULL DEFAULT NOW(),
                end_time TIMESTAMP,
                target_price INTEGER,
                status TEXT DEFAULT 'active',
                winner_id BIGINT,
                created_by BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS auction_bids (
                id SERIAL PRIMARY KEY,
                auction_id INTEGER REFERENCES auctions(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                bid_amount INTEGER NOT NULL,
                bid_time TIMESTAMP DEFAULT NOW()
            )
        ''')

        # НОВЫЕ ТАБЛИЦЫ ДЛЯ БОЯ В ЧАТАХ
        # Таблица для авторитета в чатах
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS chat_authority (
                chat_id BIGINT,
                user_id BIGINT,
                authority INTEGER DEFAULT 0,
                total_damage INTEGER DEFAULT 0,
                fights INTEGER DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            )
        ''')

        # Таблица кулдаунов для команды /fight
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS fight_cooldowns (
                chat_id BIGINT,
                user_id BIGINT,
                last_fight TIMESTAMP,
                PRIMARY KEY (chat_id, user_id)
            )
        ''')

        # Таблица логов боёв
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS fight_logs (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                user_id BIGINT,
                timestamp TIMESTAMP DEFAULT NOW(),
                damage INTEGER,
                authority_gained INTEGER,
                outcome TEXT
            )
        ''')

        # Таблица рекламных объявлений
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS ads (
                id SERIAL PRIMARY KEY,
                text TEXT NOT NULL,
                interval_minutes INTEGER DEFAULT 60,
                last_sent TIMESTAMP,
                enabled BOOLEAN DEFAULT TRUE,
                target TEXT DEFAULT 'chats'
            )
        ''')

        # Индексы
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance DESC)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_reputation ON users(reputation DESC)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_total_spent ON users(total_spent DESC)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_purchases_user_id ON purchases(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_purchases_status ON purchases(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_giveaways_status ON giveaways(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_promo_activations_user ON promo_activations(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_user_tasks_expires ON user_tasks(expires_at)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_active ON tasks(active)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_multiplayer_games_status ON multiplayer_games(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_level ON users(level)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_exp ON users(exp)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bosses_chat_status ON bosses(chat_id, status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_boss_attacks_boss ON boss_attacks(boss_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_confirmed_chats_chat ON confirmed_chats(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_requests_status ON chat_confirmation_requests(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_auctions_status ON auctions(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_auctions_end_time ON auctions(end_time)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_auction_bids_auction ON auction_bids(auction_id)")
        # Индексы для новых таблиц
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_authority_chat ON chat_authority(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fight_cooldowns_chat ON fight_cooldowns(chat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fight_logs_timestamp ON fight_logs(timestamp)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_ads_enabled ON ads(enabled)")

    # Заполняем настройки
    await init_settings()
    # Заполняем level_rewards (с обновлёнными значениями)
    async with db_pool.acquire() as conn:
        for lvl in range(1, 101):
            exists = await conn.fetchval("SELECT level FROM level_rewards WHERE level=$1", lvl)
            if not exists:
                coins = int(DEFAULT_SETTINGS["level_reward_coins"]) + (lvl-1) * int(DEFAULT_SETTINGS["level_reward_coins_increment"])
                rep = int(DEFAULT_SETTINGS["level_reward_reputation"]) + (lvl-1) * int(DEFAULT_SETTINGS["level_reward_reputation_increment"])
                await conn.execute(
                    "INSERT INTO level_rewards (level, coins, reputation) VALUES ($1, $2, $3)",
                    lvl, coins, rep
                )
    logging.info("Таблицы в PostgreSQL проверены/обновлены")

async def init_settings():
    async with db_pool.acquire() as conn:
        for key, value in DEFAULT_SETTINGS.items():
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING",
                key, value
            )

async def get_setting(key: str) -> str:
    global settings_cache, last_settings_update
    now = time.time()
    if now - last_settings_update > 60 or not settings_cache:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT key, value FROM settings")
            settings_cache = {row['key']: row['value'] for row in rows}
        last_settings_update = now
    return settings_cache.get(key, DEFAULT_SETTINGS[key])

async def set_setting(key: str, value: str):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE settings SET value=$1 WHERE key=$2", value, key)
    settings_cache[key] = value

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
async def is_super_admin(user_id: int) -> bool:
    return user_id in SUPER_ADMINS

async def is_junior_admin(user_id: int) -> bool:
    async with db_pool.acquire() as conn:
        row = await conn.fetchval("SELECT user_id FROM admins WHERE user_id=$1", user_id)
    return row is not None

async def is_admin(user_id: int) -> bool:
    return await is_super_admin(user_id) or await is_junior_admin(user_id)

async def is_banned(user_id: int) -> bool:
    async with db_pool.acquire() as conn:
        row = await conn.fetchval("SELECT user_id FROM banned_users WHERE user_id=$1", user_id)
    return row is not None

async def get_channels():
    global channels_cache, last_channels_update
    now = time.time()
    if now - last_channels_update > 300 or not channels_cache:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT chat_id, title, invite_link FROM channels")
            channels_cache = [(r['chat_id'], r['title'], r['invite_link']) for r in rows]
        last_channels_update = now
    return channels_cache

async def get_confirmed_chats(force_update=False) -> Dict[int, dict]:
    global confirmed_chats_cache, last_confirmed_chats_update
    now = time.time()
    if force_update or now - last_confirmed_chats_update > 300 or not confirmed_chats_cache:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM confirmed_chats")
            confirmed_chats_cache = {row['chat_id']: dict(row) for row in rows}
        last_confirmed_chats_update = now
    return confirmed_chats_cache

async def is_chat_confirmed(chat_id: int) -> bool:
    confirmed = await get_confirmed_chats()
    return chat_id in confirmed

async def add_confirmed_chat(chat_id: int, title: str, chat_type: str, confirmed_by: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO confirmed_chats (chat_id, title, type, joined_date, confirmed_by, confirmed_date) VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (chat_id) DO UPDATE SET confirmed_by=$5, confirmed_date=$6",
            chat_id, title, chat_type, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), confirmed_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    await get_confirmed_chats(force_update=True)

async def remove_confirmed_chat(chat_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM confirmed_chats WHERE chat_id=$1", chat_id)
    await get_confirmed_chats(force_update=True)

async def create_chat_confirmation_request(chat_id: int, title: str, chat_type: str, requested_by: int):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO chat_confirmation_requests (chat_id, title, type, requested_by, request_date, status) VALUES ($1, $2, $3, $4, $5, $6) ON CONFLICT (chat_id) DO UPDATE SET status='pending', requested_by=$4, request_date=$5",
            chat_id, title, chat_type, requested_by, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'pending'
        )

async def get_pending_chat_requests() -> List[dict]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM chat_confirmation_requests WHERE status='pending' ORDER BY request_date")
        return [dict(r) for r in rows]

async def update_chat_request_status(chat_id: int, status: str):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE chat_confirmation_requests SET status=$1 WHERE chat_id=$2", status, chat_id)

# Работа с пользователями
async def get_user_balance(user_id: int) -> int:
    async with db_pool.acquire() as conn:
        balance = await conn.fetchval("SELECT balance FROM users WHERE user_id=$1", user_id)
        return balance if balance is not None else 0

async def update_user_balance(user_id: int, delta: int, conn=None):
    async def _update(conn):
        row = await conn.fetchrow("SELECT balance, negative_balance FROM users WHERE user_id=$1", user_id)
        if not row:
            await conn.execute(
                "INSERT INTO users (user_id, balance, negative_balance) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                user_id, 0, 0
            )
            row = {'balance': 0, 'negative_balance': 0}
        balance, negative = row['balance'], row['negative_balance']
        new_balance = balance + delta
        if new_balance < 0:
            negative += abs(new_balance)
            new_balance = 0
        await conn.execute(
            "UPDATE users SET balance=$1, negative_balance=$2 WHERE user_id=$3",
            new_balance, negative, user_id
        )
    if conn:
        await _update(conn)
    else:
        async with db_pool.acquire() as new_conn:
            await _update(new_conn)

async def get_user_reputation(user_id: int) -> int:
    async with db_pool.acquire() as conn:
        rep = await conn.fetchval("SELECT reputation FROM users WHERE user_id=$1", user_id)
        return rep if rep is not None else 0

async def update_user_reputation(user_id: int, delta: int):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET reputation = reputation + $1 WHERE user_id=$2", delta, user_id)

async def get_user_stats(user_id: int) -> dict:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT level, strength, agility, defense FROM users WHERE user_id=$1", user_id)
        if row:
            return dict(row)
        return {'level': 1, 'strength': 1, 'agility': 1, 'defense': 1}

async def update_user_stats(user_id: int, strength_delta=0, agility_delta=0, defense_delta=0):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET strength = strength + $1, agility = agility + $2, defense = defense + $3 WHERE user_id=$4",
            strength_delta, agility_delta, defense_delta, user_id
        )

async def add_exp(user_id: int, exp: int, conn=None):
    async def _add(conn):
        user = await conn.fetchrow("SELECT exp, level FROM users WHERE user_id=$1", user_id)
        if not user:
            return
        new_exp = user['exp'] + exp
        level = user['level']
        level_mult = int(await get_setting("level_multiplier"))
        levels_gained = 0
        while new_exp >= level * level_mult:
            new_exp -= level * level_mult
            level += 1
            levels_gained += 1
        await conn.execute(
            "UPDATE users SET exp=$1, level=$2 WHERE user_id=$3",
            new_exp, level, user_id
        )
        if levels_gained > 0:
            str_inc = int(await get_setting("stat_strength_per_level")) * levels_gained
            agi_inc = int(await get_setting("stat_agility_per_level")) * levels_gained
            def_inc = int(await get_setting("stat_defense_per_level")) * levels_gained
            await update_user_stats(user_id, str_inc, agi_inc, def_inc)
            for lvl in range(level - levels_gained + 1, level + 1):
                await reward_level_up(user_id, lvl, conn)
    if conn:
        await _add(conn)
    else:
        async with db_pool.acquire() as conn2:
            await _add(conn2)

async def reward_level_up(user_id: int, new_level: int, conn=None):
    async def _reward(conn):
        reward = await conn.fetchrow(
            "SELECT coins, reputation FROM level_rewards WHERE level=$1",
            new_level
        )
        if reward:
            await update_user_balance(user_id, reward['coins'], conn=conn)
            await update_user_reputation(user_id, reward['reputation'])
            await safe_send_message(
                user_id,
                f"🎉 Поздравляем! Ты достиг {new_level} уровня!\n"
                f"Награда: +{reward['coins']} монет, +{reward['reputation']} репутации!\n"
                f"Твои статы увеличены: сила +{int(await get_setting('stat_strength_per_level'))}, ловкость +{int(await get_setting('stat_agility_per_level'))}, защита +{int(await get_setting('stat_defense_per_level'))}."
            )
    if conn:
        await _reward(conn)
    else:
        async with db_pool.acquire() as conn2:
            await _reward(conn2)

async def get_user_level(user_id: int) -> int:
    async with db_pool.acquire() as conn:
        level = await conn.fetchval("SELECT level FROM users WHERE user_id=$1", user_id)
        return level if level is not None else 1

async def get_user_exp(user_id: int) -> int:
    async with db_pool.acquire() as conn:
        exp = await conn.fetchval("SELECT exp FROM users WHERE user_id=$1", user_id)
        return exp if exp is not None else 0

async def update_user_total_spent(user_id: int, amount: int):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET total_spent = total_spent + $1 WHERE user_id=$2", amount, user_id)

async def get_random_user(exclude_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT user_id FROM users 
            WHERE user_id != $1 AND user_id NOT IN (SELECT user_id FROM banned_users)
            ORDER BY RANDOM() LIMIT 1
        """, exclude_id)
        return row['user_id'] if row else None

async def find_user_by_input(input_str: str) -> Optional[Dict]:
    input_str = input_str.strip()
    try:
        uid = int(input_str)
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", uid)
            return dict(row) if row else None
    except ValueError:
        username = input_str.lower()
        if username.startswith('@'):
            username = username[1:]
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE LOWER(username)=$1", username)
            return dict(row) if row else None

async def notify_chats(message_text: str, importance: str = 'info'):
    confirmed = await get_confirmed_chats()
    for chat_id, data in confirmed.items():
        if not data.get('notify_enabled', True):
            continue
        await safe_send_chat(chat_id, message_text)

# Функции для мультиплеера
def generate_game_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def calculate_hand_value(cards):
    value = 0
    aces = 0
    for card in cards:
        rank = card[:-1]
        if rank in ['J', 'Q', 'K']:
            value += 10
        elif rank == 'A':
            aces += 1
            value += 11
        else:
            value += int(rank)
    while value > 21 and aces:
        value -= 10
        aces -= 1
    return value

def create_deck():
    suits = ['♠', '♥', '♦', '♣']
    ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    deck = [f"{rank}{suit}" for suit in suits for rank in ranks]
    random.shuffle(deck)
    return deck

# ===== НОВЫЕ ФУНКЦИИ ДЛЯ АВТОРИТЕТА =====
async def get_chat_authority(chat_id: int, user_id: int) -> int:
    async with db_pool.acquire() as conn:
        val = await conn.fetchval("SELECT authority FROM chat_authority WHERE chat_id=$1 AND user_id=$2", chat_id, user_id)
        return val if val is not None else 0

async def add_chat_authority(chat_id: int, user_id: int, amount: int, damage: int = 0):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO chat_authority (chat_id, user_id, authority, total_damage, fights)
            VALUES ($1, $2, $3, $4, 1)
            ON CONFLICT (chat_id, user_id) DO UPDATE
            SET authority = chat_authority.authority + $3,
                total_damage = chat_authority.total_damage + $4,
                fights = chat_authority.fights + 1
        ''', chat_id, user_id, amount, damage)

async def spend_chat_authority(chat_id: int, user_id: int, amount: int) -> bool:
    current = await get_chat_authority(chat_id, user_id)
    if current < amount:
        return False
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE chat_authority SET authority = authority - $1 WHERE chat_id=$2 AND user_id=$3", amount, chat_id, user_id)
    return True

async def log_fight(chat_id: int, user_id: int, damage: int, authority: int, outcome: str):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO fight_logs (chat_id, user_id, timestamp, damage, authority_gained, outcome) VALUES ($1, $2, $3, $4, $5, $6)",
            chat_id, user_id, datetime.now(), damage, authority, outcome
        )

async def cleanup_old_logs():
    days = int(await get_setting("cleanup_days_fight_logs"))
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM fight_logs WHERE timestamp < NOW() - INTERVAL '1 day' * $1", days)
        # Также очищаем старые кулдауны, если прошло больше, чем кулдаун*2
        cooldown = int(await get_setting("fight_cooldown_minutes"))
        await conn.execute("DELETE FROM fight_cooldowns WHERE last_fight < NOW() - INTERVAL '1 minute' * $1", cooldown * 2)

async def can_fight(chat_id: int, user_id: int) -> Tuple[bool, int]:
    """Возвращает (можно ли атаковать, сколько минут осталось)"""
    cooldown = int(await get_setting("fight_cooldown_minutes"))
    async with db_pool.acquire() as conn:
        last = await conn.fetchval("SELECT last_fight FROM fight_cooldowns WHERE chat_id=$1 AND user_id=$2", chat_id, user_id)
        if last:
            diff = datetime.now() - last
            remaining = cooldown * 60 - diff.total_seconds()
            if remaining > 0:
                return False, int(remaining // 60) + 1
        return True, 0

async def set_fight_cooldown(chat_id: int, user_id: int):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO fight_cooldowns (chat_id, user_id, last_fight)
            VALUES ($1, $2, $3)
            ON CONFLICT (chat_id, user_id) DO UPDATE SET last_fight = $3
        ''', chat_id, user_id, datetime.now())

# ===== СОСТОЯНИЯ FSM =====
class CreateGiveaway(StatesGroup):
    prize = State()
    description = State()
    end_date = State()
    media = State()

class AddChannel(StatesGroup):
    chat_id = State()
    title = State()
    invite_link = State()

class RemoveChannel(StatesGroup):
    chat_id = State()

class AddShopItem(StatesGroup):
    name = State()
    description = State()
    price = State()
    stock = State()

class RemoveShopItem(StatesGroup):
    item_id = State()

class EditShopItem(StatesGroup):
    item_id = State()
    field = State()
    value = State()

class CreatePromocode(StatesGroup):
    code = State()
    reward = State()
    max_uses = State()

class Broadcast(StatesGroup):
    media = State()

class AddBalance(StatesGroup):
    user_id = State()
    amount = State()

class RemoveBalance(StatesGroup):
    user_id = State()
    amount = State()

class AddReputation(StatesGroup):
    user_id = State()
    amount = State()

class RemoveReputation(StatesGroup):
    user_id = State()
    amount = State()

class AddExp(StatesGroup):
    user_id = State()
    amount = State()

class SetLevel(StatesGroup):
    user_id = State()
    level = State()

class CasinoBet(StatesGroup):
    amount = State()

class DiceBet(StatesGroup):
    amount = State()

class GuessBet(StatesGroup):
    amount = State()
    number = State()

class PromoActivate(StatesGroup):
    code = State()

class TheftTarget(StatesGroup):
    target = State()

class FindUser(StatesGroup):
    query = State()

class AddJuniorAdmin(StatesGroup):
    user_id = State()

class RemoveJuniorAdmin(StatesGroup):
    user_id = State()

class CompleteGiveaway(StatesGroup):
    giveaway_id = State()
    winners_count = State()

class BlockUser(StatesGroup):
    user_id = State()
    reason = State()

class UnblockUser(StatesGroup):
    user_id = State()

class EditSettings(StatesGroup):
    key = State()
    value = State()

class CreateTask(StatesGroup):
    name = State()
    description = State()
    task_type = State()
    target_id = State()
    reward_coins = State()
    reward_reputation = State()
    required_days = State()
    penalty_days = State()
    max_completions = State()

class DeleteTask(StatesGroup):
    task_id = State()

class MultiplayerGame(StatesGroup):
    create_max_players = State()
    create_bet = State()
    join_code = State()

class RoomChat(StatesGroup):
    message = State()

class ManageChats(StatesGroup):
    action = State()
    chat_id = State()

class BossSpawn(StatesGroup):
    chat_id = State()
    level = State()

class CreateAuction(StatesGroup):
    item_name = State()
    description = State()
    start_price = State()
    end_time = State()
    target_price = State()

class AuctionBid(StatesGroup):
    auction_id = State()
    amount = State()

class CancelAuction(StatesGroup):
    auction_id = State()

class CreateAd(StatesGroup):
    text = State()
    interval = State()
    target = State()

class FightCooldown(StatesGroup):
    pass

class GymUpgrade(StatesGroup):
    stat = State()
    chat_id = State()

# ===== КЛАВИАТУРЫ =====
def subscription_inline(not_subscribed):
    kb = []
    for title, link in not_subscribed:
        if link:
            kb.append([InlineKeyboardButton(text=f"📢 {title}", url=link)])
        else:
            kb.append([InlineKeyboardButton(text=f"📢 {title}", callback_data="no_link")])
    kb.append([InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")])
    return InlineKeyboardMarkup(row_width=1, inline_keyboard=kb)

def user_main_keyboard(is_admin_user=False):
    buttons = [
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🎁 Бонус")],
        [KeyboardButton(text="🛒 Магазин подарков"), KeyboardButton(text="🎰 Казино")],
        [KeyboardButton(text="🎟 Промокод"), KeyboardButton(text="🏆 Топ игроков")],
        [KeyboardButton(text="💰 Мои покупки"), KeyboardButton(text="🔫 Ограбить")],
        [KeyboardButton(text="🎲 Игры"), KeyboardButton(text="⭐️ Репутация")],
        [KeyboardButton(text="📋 Задания"), KeyboardButton(text="🔗 Рефералка")],
        [KeyboardButton(text="🎲 Розыгрыши"), KeyboardButton(text="📊 Уровень")],
        [KeyboardButton(text="🏷 Аукцион")],
    ]
    if is_admin_user:
        buttons.append([KeyboardButton(text="⚙️ Админ панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def theft_choice_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎲 Случайная цель")],
        [KeyboardButton(text="👤 Выбрать пользователя")],
        [KeyboardButton(text="◀️ Назад")]
    ], resize_keyboard=True)

def games_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎲 Кости"), KeyboardButton(text="🔢 Угадай число")],
        [KeyboardButton(text="👥 Комнатная игра 21")],
        [KeyboardButton(text="◀️ Назад")]
    ], resize_keyboard=True)

def room_menu_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📋 Список комнат")],
        [KeyboardButton(text="🎮 Создать комнату")],
        [KeyboardButton(text="ℹ️ Правила игры")],
        [KeyboardButton(text="🏆 Топ игроков")],
        [KeyboardButton(text="◀️ Назад в игры")]
    ], resize_keyboard=True)

def room_control_keyboard(game_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать игру", callback_data=f"start_game_{game_id}")],
        [InlineKeyboardButton(text="❌ Закрыть комнату", callback_data=f"close_room_{game_id}")]
    ])

def room_action_keyboard(game_id, can_double=True):
    kb_buttons = []
    row1 = [
        InlineKeyboardButton(text="🎯 Ещё", callback_data="room_hit"),
        InlineKeyboardButton(text="🛑 Хватит", callback_data="room_stand")
    ]
    kb_buttons.append(row1)
    row2 = []
    if can_double:
        row2.append(InlineKeyboardButton(text="💰 Удвоить", callback_data="room_double"))
    row2.append(InlineKeyboardButton(text="🏳️ Сдаться", callback_data="room_surrender"))
    kb_buttons.append(row2)
    kb_buttons.append([InlineKeyboardButton(text="💬 Написать в чат", callback_data="room_chat")])
    return InlineKeyboardMarkup(inline_keyboard=kb_buttons)

def leave_room_keyboard(game_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚪 Выйти из комнаты", callback_data=f"leave_room_{game_id}")]
    ])

# ===== АДМИН-КЛАВИАТУРЫ =====
def admin_main_keyboard(is_super):
    buttons = [
        [KeyboardButton(text="👥 Управление пользователями")],
        [KeyboardButton(text="🛒 Управление магазином")],
        [KeyboardButton(text="🎁 Управление розыгрышами")],
        [KeyboardButton(text="📢 Управление каналами")],
        [KeyboardButton(text="🎫 Управление промокодами")],
        [KeyboardButton(text="📋 Управление заданиями")],
        [KeyboardButton(text="🤖 Управление чатами")],
        [KeyboardButton(text="👾 Управление боссами")],
        [KeyboardButton(text="🏷 Управление аукционами")],
        [KeyboardButton(text="⚔️ Управление помощниками")],
        [KeyboardButton(text="📢 Управление рекламой")],
        [KeyboardButton(text="⚙️ Настройки игры")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🔨 Блокировки")],
        [KeyboardButton(text="📢 Рассылка")],
        [KeyboardButton(text="🧹 Очистка старых записей")],
    ]
    if is_super:
        buttons.append([KeyboardButton(text="➕ Управление админами")])
    buttons.append([KeyboardButton(text="◀️ Назад в главное меню")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def admin_users_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💰 Начислить монеты"), KeyboardButton(text="💸 Списать монеты")],
        [KeyboardButton(text="⭐️ Начислить репутацию"), KeyboardButton(text="🔻 Снять репутацию")],
        [KeyboardButton(text="📈 Начислить опыт"), KeyboardButton(text="🔝 Установить уровень")],
        [KeyboardButton(text="👥 Найти пользователя")],
        [KeyboardButton(text="📊 Экспорт пользователей")],
        [KeyboardButton(text="◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_shop_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Добавить товар")],
        [KeyboardButton(text="➖ Удалить товар")],
        [KeyboardButton(text="✏️ Редактировать товар")],
        [KeyboardButton(text="📋 Список товаров")],
        [KeyboardButton(text="🛍️ Список покупок")],
        [KeyboardButton(text="◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_giveaway_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Создать розыгрыш")],
        [KeyboardButton(text="📋 Активные розыгрыши")],
        [KeyboardButton(text="✅ Завершить розыгрыш")],
        [KeyboardButton(text="◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_channel_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Добавить канал")],
        [KeyboardButton(text="➖ Удалить канал")],
        [KeyboardButton(text="📋 Список каналов")],
        [KeyboardButton(text="◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_promo_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Создать промокод")],
        [KeyboardButton(text="📋 Список промокодов")],
        [KeyboardButton(text="◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_tasks_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Создать задание")],
        [KeyboardButton(text="📋 Список заданий")],
        [KeyboardButton(text="❌ Удалить задание")],
        [KeyboardButton(text="◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_ban_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔨 Заблокировать пользователя")],
        [KeyboardButton(text="🔓 Разблокировать пользователя")],
        [KeyboardButton(text="📋 Список заблокированных")],
        [KeyboardButton(text="◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_admins_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Добавить админа")],
        [KeyboardButton(text="➖ Удалить админа")],
        [KeyboardButton(text="📋 Список админов")],
        [KeyboardButton(text="◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_chats_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📋 Список запросов на подтверждение")],
        [KeyboardButton(text="✅ Подтвердить чат")],
        [KeyboardButton(text="❌ Отклонить запрос")],
        [KeyboardButton(text="📋 Список подтверждённых чатов")],
        [KeyboardButton(text="🗑 Удалить чат из подтверждённых")],
        [KeyboardButton(text="◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_boss_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📋 Активные боссы")],
        [KeyboardButton(text="⚔️ Создать босса вручную")],
        [KeyboardButton(text="◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_helper_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📋 Активные помощники")],
        [KeyboardButton(text="📊 Топы чатов")],
        [KeyboardButton(text="◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_auction_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Создать аукцион")],
        [KeyboardButton(text="📋 Активные аукционы")],
        [KeyboardButton(text="❌ Отменить аукцион")],
        [KeyboardButton(text="◀️ Назад в админку")]
    ], resize_keyboard=True)

def admin_ad_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="➕ Создать рекламу")],
        [KeyboardButton(text="📋 Список рекламы")],
        [KeyboardButton(text="✏️ Редактировать рекламу")],
        [KeyboardButton(text="❌ Удалить рекламу")],
        [KeyboardButton(text="◀️ Назад в админку")]
    ], resize_keyboard=True)

def settings_reply_keyboard():
    buttons = [
        [KeyboardButton(text="⚙️ Кража")],
        [KeyboardButton(text="⚙️ Казино и игры")],
        [KeyboardButton(text="⚙️ Опыт и уровни")],
        [KeyboardButton(text="⚙️ Боссы")],
        [KeyboardButton(text="⚙️ Помощники")],
        [KeyboardButton(text="⚙️ Аукцион")],
        [KeyboardButton(text="⚙️ Подгон")],
        [KeyboardButton(text="⚙️ Рефералы")],
        [KeyboardButton(text="⚙️ Очистка логов")],
        [KeyboardButton(text="◀️ Назад в админку")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def back_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="◀️ Назад")]], resize_keyboard=True)

def purchase_action_keyboard(purchase_id):
    return InlineKeyboardMarkup(row_width=2, inline_keyboard=[
        [InlineKeyboardButton(text="✅ Выполнено", callback_data=f"purchase_done_{purchase_id}"),
         InlineKeyboardButton(text="❌ Отказ", callback_data=f"purchase_reject_{purchase_id}")]
    ])

def confirm_chat_inline(chat_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_chat_{chat_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_chat_{chat_id}")]
    ])

def boss_attack_keyboard():
    # Убираем инлайн-кнопку, заменяем на команду
    return None

# ===== ТЕКСТОВЫЕ ФРАЗЫ =====
BONUS_PHRASES = [
    "🎉 Красава, лови +{bonus} монет!",
    "💰 Зашкварно богатенький стал! +{bonus}",
    "🌟 Хайпанули? +{bonus} монет в карман!",
    "🍀 Удача крашеная, держи +{bonus}",
    "🎁 Ты в тренде, +{bonus} монет!"
]

CASINO_WIN_PHRASES = [
    "🎰 Краш! Ты выиграл {win} монет (чистыми {profit})!",
    "🍒 Хайповая комбинация! +{profit} монет!",
    "💫 Фортуна крашеная, твой выигрыш: {win} монет!",
    "🎲 Изи-катка, {profit} монет твои!",
    "✨ Ты красавчик, обыграл казино! +{profit} монет!"
]

CASINO_LOSE_PHRASES = [
    "😢 Обидно, потерял {loss} монет.",
    "💔 Зашкварно, минус {loss}.",
    "📉 Не фортануло, -{loss} монет.",
    "🍂 В следующий раз краш будет твоим, а пока -{loss}.",
    "⚡️ Лузернулся на {loss} монет."
]

PURCHASE_PHRASES = [
    "✅ Купил! Админ скоро в личку прилетит.",
    "🛒 Товар твой! Жди админа, бро.",
    "🎁 Крутая покупка! Админ уже в курсе.",
    "💎 Ты краш! Админ свяжется."
]

THEFT_CHOICE_PHRASES = [
    "🔫 Выбери, как хочешь напасть:",
    "💢 Кого будем грабить?",
    "😈 Куда направим бандитские лапы?"
]

THEFT_COOLDOWN_PHRASES = [
    "⏳ Ты ещё не остыл после прошлого налёта. Подожди {minutes} мин.",
    "🕐 Полегче, ковбой! Отдохни {minutes} минут.",
    "😴 Грабить так часто – плохая примета. Возвращайся через {minutes} мин."
]

THEFT_NO_MONEY_PHRASES = [
    "😕 У тебя нет монет даже на подготовку к краже!",
    "💸 Сначала заработай, потом грабить будешь.",
    "💰 Пустой карман – не до криминала."
]

THEFT_SUCCESS_PHRASES = [
    "🔫 Красава! Ты украл {amount} монет у {target}!",
    "💰 Хайпанул, {amount} монет у {target} теперь твои!",
    "🦹‍♂️ Удачная кража! +{amount} от {target}",
    "😈 Ты краш, {target} даже не понял! +{amount}"
]

THEFT_FAIL_PHRASES = [
    "😢 Облом, тебя спалили! Ничего не украл.",
    "🚨 Треск, {target} оказался слишком бдительным!",
    "👮‍♂️ Пришлось сваливать, 0 монет.",
    "💔 Не фортануло, {target} слишком крутой."
]

THEFT_DEFENSE_PHRASES = [
    "🛡️ {target} отразил атаку! Ты потерял {penalty} монет.",
    "💥 Бабах! {target} выставил защиту, и ты лишился {penalty} монет.",
    "😱 Засада! Ты напоролся на защиту и потерял {penalty} монет."
]

THEFT_VICTIM_DEFENSE_PHRASES = [
    "🛡️ Твоя защита сработала! {attacker} ничего не украл и потерял {penalty} монет.",
    "💪 Ты краш! Отбил атаку {attacker} и получил {penalty} монет.",
    "😎 Ха! {attacker} думал поживиться, а сам потерял {penalty} монет."
]

DICE_WIN_PHRASES = [
    "🎲 {dice1} + {dice2} = {total} — Победа! +{profit} монет!",
    "🎲 Круто! {dice1}+{dice2}={total}, ты выиграл {profit}!",
    "🎲 Хайп! {total} очков, твой выигрыш: {profit}!"
]

DICE_LOSE_PHRASES = [
    "🎲 {dice1} + {dice2} = {total} — Проигрыш. -{loss} монет.",
    "🎲 Эх, {total} очков, не повезло. -{loss}.",
    "🎲 В этот раз не зашло, -{loss} монет."
]

GUESS_WIN_PHRASES = [
    "🔢 Ты угадал! Было {secret}. Выигрыш: +{profit} монет и +{rep} репутации!",
    "🔢 Красава! Число {secret}, твой выигрыш {profit} монет!",
    "🔢 Хайпанул! +{profit} монет, репутация +{rep}!"
]

GUESS_LOSE_PHRASES = [
    "🔢 Не угадал. Было {secret}. -{loss} монет.",
    "🔢 Увы, загадано {secret}. Теряешь {loss} монет.",
    "🔢 Не фортануло, правильный ответ {secret}. -{loss}."
]

CHAT_WIN_PHRASES = [
    "🔥 {name} только что выиграл {amount} монет в казино!",
    "💰 Удача на стороне {name}: +{amount} монет!",
    "🎰 {name} сорвал куш — {amount} монет!"
]

CHAT_PURCHASE_PHRASES = [
    "🛒 {name} купил {item} за {price} монет!",
    "🎁 {name} приобрёл {item}! Админ уже в пути.",
    "💎 {name} потратил {price} монет на {item}!"
]

CHAT_GIVEAWAY_PHRASES = [
    "🎁 Не пропусти розыгрыш! Осталось {time}",
    "⏰ Напоминание: розыгрыш {prize} заканчивается через {time}",
    "🔥 Участвуй в розыгрыше {prize}! Осталось {time}"
]

BOSS_SPAWN_PHRASES = [
    "⚠️ ВНИМАНИЕ! В чате появился {name} (Уровень {level})! Здоровье: {hp}",
    "👾 Босс {name} пришёл навестить нас! Уровень {level}, HP: {hp}",
    "🔥 Легендарный {name} пробудился! Уровень {level}, здоровье: {hp}",
]

BOSS_HIT_PHRASES = [
    "💥 Ты нанёс {damage} урона!",
    "⚡️ Удар! -{damage} HP",
    "🔥 Критическое попадание! {damage} урона",
]

BOSS_MISS_PHRASES = [
    "💨 Промах! Босс уклонился",
    "😵 Твоя атака не достигла цели",
    "🛡 Босс отразил удар",
]

BOSS_DEATH_PHRASES = [
    "🏆 Босс {name} повержен! Все участники получают награду!",
    "🎉 Победа! {name} пал! Награда разделена между участниками",
    "💀 Босс уничтожен! Спасибо за участие!",
]

BOSS_STATUS_PHRASES = [
    "👾 {name} | Уровень {level} | HP: {current_hp}/{max_hp}",
]

# НОВЫЕ ФРАЗЫ ДЛЯ БОЯ
FIGHT_HIT_PHRASES = [
    "💥 Ты нанёс {damage} урона банде! Заработал {authority} авторитета.",
    "⚡️ Твой удар пришёлся точно в цель! +{damage} урона, +{authority} авторитета.",
    "🔥 Критический удар! Ты нанёс {damage} урона и получил {authority} авторитета.",
    "🤜 Хрясь! Банда получила {damage} урона. Твой авторитет +{authority}.",
    "👊 Смачный удар! {damage} урона, {authority} авторитета.",
]

FIGHT_CRIT_PHRASES = [
    "💢 СОКРУШИТЕЛЬНЫЙ УДАР! Ты нанёс {damage} урона (крит!) и заработал {authority} авторитета.",
    "🌟 Ты в ярости! Критический урон {damage}, авторитет +{authority}.",
    "⚡️ МОЛНИЕНОСНЫЙ ВЫПАД! {damage} урона, +{authority} авторитета.",
]

FIGHT_MISS_PHRASES = [
    "💨 Ты промахнулся! Банда смеётся над тобой. Авторитет не получен.",
    "😵 Твоя атака не достигла цели. Банда даже не заметила.",
    "🍃 Вжух! Мимо. Попробуй ещё через полчаса.",
]

FIGHT_COUNTER_PHRASES = [
    "😵 Банда контратаковала! Ты потерял {damage} монет и не получил авторитет.",
    "💥 Ответный удар! Ты потерял {damage} монет.",
    "👊 Тебя самого ударили! Минус {damage} монет.",
]

# ===== ФУНКЦИЯ ПРОВЕРКИ ПОДПИСКИ =====
async def check_subscription(user_id: int):
    channels = await get_channels()
    if not channels:
        return True, []
    not_subscribed = []
    for chat_id, title, link in channels:
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_subscribed.append((title, link))
        except Exception:
            not_subscribed.append((title, link))
    return len(not_subscribed) == 0, not_subscribed

# ===== ФУНКЦИЯ ДЛЯ ЗАПУСКА ПЕРЕД СТАРТОМ =====
async def before_start():
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Webhook удалён, пропущены старые обновления")
