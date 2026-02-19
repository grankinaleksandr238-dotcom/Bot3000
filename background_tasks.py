# ========== background_tasks.py ==========
import asyncio
import logging
import random
from datetime import datetime, timedelta

from core import (
    db_pool, bot,
    get_setting,
    get_confirmed_chats,
    safe_send_chat,
    spawn_boss,
    cleanup_old_logs,  # функция очистки логов боёв (есть в core)
)

# ===== ФОНОВАЯ ЗАДАЧА: СПАВН БОССОВ =====
async def boss_spawn_loop():
    """Проверяет каждый подтверждённый чат и с заданной вероятностью создаёт босса."""
    while True:
        await asyncio.sleep(300)  # каждые 5 минут
        try:
            confirmed = await get_confirmed_chats()
            now = datetime.now()
            for chat_id, data in confirmed.items():
                boss_max_per_day = int(await get_setting("boss_max_per_day"))
                boss_spawn_count = data.get('boss_spawn_count', 0)
                if boss_spawn_count >= boss_max_per_day:
                    continue
                last_spawn_str = data.get('boss_last_spawn')
                if last_spawn_str:
                    last_spawn = datetime.strptime(last_spawn_str, "%Y-%m-%d %H:%M:%S")
                    min_interval = int(await get_setting("boss_min_interval"))
                    if (now - last_spawn).total_seconds() < min_interval * 60:
                        continue
                chance = int(await get_setting("boss_spawn_chance"))
                if random.randint(1, 100) <= chance:
                    await spawn_boss(chat_id)
        except Exception as e:
            logging.error(f"Boss spawn loop error: {e}")

# ===== ФОНОВАЯ ЗАДАЧА: ПРОВЕРКА ПРОСРОЧЕННЫХ БОССОВ =====
async def check_expired_bosses():
    """Помечает боссов, у которых истекло время жизни, как expired."""
    while True:
        await asyncio.sleep(600)  # каждые 10 минут
        try:
            async with db_pool.acquire() as conn:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await conn.execute("UPDATE bosses SET status='expired' WHERE status='active' AND expires_at < $1", now)
                # Удаляем совсем старых боссов (например, через 2 часа после истечения)
                await conn.execute("DELETE FROM bosses WHERE status='expired' AND expires_at < $1", (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"))
        except Exception as e:
            logging.error(f"Check expired bosses error: {e}")

# ===== ФОНОВАЯ ЗАДАЧА: ОЧИСТКА СТАРЫХ ЛОГОВ =====
async def cleanup_loop():
    """Запускает очистку старых записей раз в сутки."""
    while True:
        # Ждём до следующего дня (например, до 00:00)
        now = datetime.now()
        next_reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        sleep_seconds = (next_reset - now).total_seconds()
        await asyncio.sleep(sleep_seconds)

        try:
            # Очистка логов боёв
            await cleanup_old_logs()

            # Очистка боссов и атак (по настройкам)
            days_bosses = int(await get_setting("cleanup_days_bosses"))
            async with db_pool.acquire() as conn:
                await conn.execute("DELETE FROM bosses WHERE status IN ('defeated','expired') AND spawned_at < NOW() - INTERVAL '1 day' * $1", days_bosses)
                await conn.execute("DELETE FROM boss_attacks WHERE attack_time < NOW() - INTERVAL '1 day' * $1", days_bosses)

            # Очистка аукционов
            days_auctions = int(await get_setting("cleanup_days_auctions"))
            async with db_pool.acquire() as conn:
                await conn.execute("DELETE FROM auctions WHERE status='ended' AND end_time < NOW() - INTERVAL '1 day' * $1", days_auctions)
                # Ставки удаляются каскадно

            # Очистка покупок
            days_purchases = int(await get_setting("cleanup_days_purchases"))
            async with db_pool.acquire() as conn:
                await conn.execute("DELETE FROM purchases WHERE status IN ('completed','rejected') AND purchase_date < NOW() - INTERVAL '1 day' * $1", days_purchases)

            # Очистка розыгрышей
            days_giveaways = int(await get_setting("cleanup_days_giveaways"))
            async with db_pool.acquire() as conn:
                await conn.execute("DELETE FROM giveaways WHERE status='completed' AND end_date < NOW() - INTERVAL '1 day' * $1", days_giveaways)

            # Очистка заданий пользователей
            days_tasks = int(await get_setting("cleanup_days_user_tasks"))
            async with db_pool.acquire() as conn:
                await conn.execute("DELETE FROM user_tasks WHERE expires_at IS NOT NULL AND expires_at < NOW() - INTERVAL '1 day' * $1", days_tasks)

            logging.info("Ежедневная очистка старых записей выполнена.")
        except Exception as e:
            logging.error(f"Cleanup loop error: {e}")

# ===== ФОНОВАЯ ЗАДАЧА: РАССЫЛКА РЕКЛАМЫ =====
async def ad_sender_loop():
    """Отправляет рекламные сообщения в соответствии с настройками."""
    while True:
        await asyncio.sleep(60)  # проверяем каждую минуту
        try:
            async with db_pool.acquire() as conn:
                ads = await conn.fetch("SELECT * FROM ads WHERE enabled=TRUE")
                for ad in ads:
                    last_sent = ad['last_sent']
                    interval = ad['interval_minutes']
                    if last_sent:
                        last = last_sent.replace(tzinfo=None) if last_sent.tzinfo else last_sent
                        if datetime.now() - last < timedelta(minutes=interval):
                            continue
                    # Выбираем цель
                    target = ad['target']
                    if target == 'chats' or target == 'all':
                        confirmed = await get_confirmed_chats()
                        for chat_id in confirmed.keys():
                            await safe_send_chat(chat_id, ad['text'])
                    if target == 'private' or target == 'all':
                        # Рассылка в личку всем пользователям (кроме забаненных) – может быть долго
                        # Для простоты можно отправлять не всем сразу, а с паузами
                        # Здесь реализуем упрощённо: отправляем только в чаты.
                        pass
                    # Обновляем время последней отправки
                    await conn.execute("UPDATE ads SET last_sent=$1 WHERE id=$2", datetime.now(), ad['id'])
        except Exception as e:
            logging.error(f"Ad sender loop error: {e}")

# ===== ФОНОВАЯ ЗАДАЧА: СБРОС ЕЖЕДНЕВНЫХ ЛИМИТОВ (ПОДГОНЫ) =====
async def reset_daily_limits():
    """Каждый день в 00:00 обнуляет счётчики подгонов в чатах и у пользователей."""
    while True:
        now = datetime.now()
        next_reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        sleep_seconds = (next_reset - now).total_seconds()
        await asyncio.sleep(sleep_seconds)
        try:
            async with db_pool.acquire() as conn:
                await conn.execute("UPDATE users SET gift_count_today = 0")
                await conn.execute("UPDATE confirmed_chats SET gift_count_today = 0, boss_spawn_count = 0")
            logging.info("Daily limits reset.")
        except Exception as e:
            logging.error(f"Reset daily limits error: {e}")
