# ========== background_tasks.py ==========
import asyncio
import logging
import random
from datetime import datetime, timedelta

from core import (
    db_pool,
    get_setting,
    get_confirmed_chats,
    spawn_boss,
    safe_send_chat, safe_send_message,
)

# ===== СПАВН БОССОВ =====
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

# ===== АВТОМАТИЧЕСКАЯ ОЧИСТКА ЛОГОВ =====
async def cleanup_loop():
    """Раз в сутки удаляет старые записи согласно настройкам."""
    while True:
        await asyncio.sleep(86400)  # 24 часа
        try:
            days_bosses = int(await get_setting("cleanup_days_bosses"))
            days_auctions = int(await get_setting("cleanup_days_auctions"))
            days_purchases = int(await get_setting("cleanup_days_purchases"))
            days_giveaways = int(await get_setting("cleanup_days_giveaways"))
            days_tasks = int(await get_setting("cleanup_days_user_tasks"))
            days_fight = int(await get_setting("cleanup_days_fight_logs"))

            async with db_pool.acquire() as conn:
                # Боссы и атаки
                await conn.execute("DELETE FROM bosses WHERE status IN ('defeated', 'expired') AND spawned_at < NOW() - INTERVAL '1 day' * $1", days_bosses)
                await conn.execute("DELETE FROM boss_attacks WHERE attack_time < NOW() - INTERVAL '1 day' * $1", days_bosses)
                # Аукционы и ставки
                await conn.execute("DELETE FROM auctions WHERE status='ended' AND end_time < NOW() - INTERVAL '1 day' * $1", days_auctions)
                # Покупки
                await conn.execute("DELETE FROM purchases WHERE status IN ('completed','rejected') AND purchase_date < NOW() - INTERVAL '1 day' * $1", days_purchases)
                # Розыгрыши
                await conn.execute("DELETE FROM giveaways WHERE status='completed' AND end_date < NOW() - INTERVAL '1 day' * $1", days_giveaways)
                # Просроченные задания
                await conn.execute("DELETE FROM user_tasks WHERE expires_at IS NOT NULL AND expires_at < NOW()")
                # Логи боёв
                await conn.execute("DELETE FROM fight_logs WHERE timestamp < NOW() - INTERVAL '1 day' * $1", days_fight)
                # Устаревшие кулдауны (больше 2x от кулдауна)
                cooldown = int(await get_setting("fight_cooldown_minutes"))
                await conn.execute("DELETE FROM fight_cooldowns WHERE last_fight < NOW() - INTERVAL '1 minute' * $1", cooldown * 2)

            logging.info("Автоматическая очистка логов выполнена.")
        except Exception as e:
            logging.error(f"Cleanup loop error: {e}")

# ===== РАССЫЛКА РЕКЛАМЫ =====
async def ad_sender_loop():
    """Периодически отправляет рекламные сообщения в чаты или личку."""
    while True:
        await asyncio.sleep(60)  # проверка каждую минуту
        try:
            async with db_pool.acquire() as conn:
                ads = await conn.fetch("SELECT * FROM ads WHERE enabled=TRUE")
                now = datetime.now()
                for ad in ads:
                    last_sent = ad['last_sent']
                    if last_sent and (now - last_sent).total_seconds() < ad['interval_minutes'] * 60:
                        continue
                    # Определяем получателей
                    if ad['target'] in ('chats', 'all'):
                        chats = await get_confirmed_chats()
                        chat_ids = list(chats.keys())
                        if chat_ids:
                            chat_id = random.choice(chat_ids)
                            await safe_send_chat(chat_id, ad['text'])
                    if ad['target'] in ('private', 'all'):
                        # Отправляем случайному пользователю (не админу)
                        async with db_pool.acquire() as conn2:
                            users = await conn2.fetch("SELECT user_id FROM users WHERE user_id NOT IN (SELECT user_id FROM admins) ORDER BY RANDOM() LIMIT 1")
                            if users:
                                await safe_send_message(users[0]['user_id'], ad['text'])
                    # Обновляем last_sent
                    await conn.execute("UPDATE ads SET last_sent=$1 WHERE id=$2", now, ad['id'])
        except Exception as e:
            logging.error(f"Ad sender loop error: {e}")
