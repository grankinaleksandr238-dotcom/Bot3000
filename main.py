# ========== main.py ==========
import asyncio
import logging
import time
import os

from aiogram.utils import executor
from aiogram.utils.exceptions import TerminatedByOtherGetUpdates

from core import (
    dp, db_pool,
    before_start,
    create_db_pool, init_db,
    start_web_server,  # если нужен веб-сервер для health checks
)
from utils import *
from games_handlers import *
from user_handlers import *
from admin_handlers import *
from background_tasks import (
    boss_spawn_loop,
    check_expired_bosses,
    cleanup_loop,
    ad_sender_loop,
    reset_daily_limits,
)

# ===== ЗАПУСК =====
async def on_startup(dp):
    await before_start()
    await create_db_pool()
    await init_db()
    # Запускаем фоновые задачи
    asyncio.create_task(boss_spawn_loop())
    asyncio.create_task(check_expired_bosses())
    asyncio.create_task(cleanup_loop())
    asyncio.create_task(ad_sender_loop())
    asyncio.create_task(reset_daily_limits())
    # Запускаем веб-сервер (для Railway)
    asyncio.create_task(start_web_server())
    logging.info("🤖 Бот запущен и готов к работе!")
    logging.info(f"👑 Суперадмины: {SUPER_ADMINS}")
    logging.info(f"🗄 База данных: PostgreSQL")

async def on_shutdown(dp):
    await db_pool.close()
    await dp.storage.close()
    await dp.bot.close()
    logging.info("Бот остановлен")

if __name__ == "__main__":
    while True:
        try:
            executor.start_polling(dp, skip_updates=True, on_startup=on_startup, on_shutdown=on_shutdown)
        except TerminatedByOtherGetUpdates:
            logging.error("Конфликт с другим экземпляром. Жду 5 сек...")
            time.sleep(5)
            continue
        except Exception as e:
            logging.error(f"Критическая ошибка: {e}")
            time.sleep(5)
            continue
