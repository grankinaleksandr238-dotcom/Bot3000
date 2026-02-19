# ========== utils.py ==========
import csv
import io
import random
from datetime import datetime, timedelta
from typing import List, Optional

# Импортируем только необходимое из core
from core import db_pool, get_setting

# ===== ЭКСПОРТ ДАННЫХ =====
async def export_users_to_csv() -> bytes:
    """
    Генерирует CSV-файл со всеми пользователями.
    Возвращает содержимое файла в байтах для отправки.
    """
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM users ORDER BY user_id")
    if not rows:
        return b""

    output = io.StringIO()
    writer = csv.writer(output)
    # Заголовки
    writer.writerow(dict(rows[0]).keys())
    for row in rows:
        writer.writerow(dict(row).values())
    return output.getvalue().encode('utf-8')

async def export_table_to_csv(table: str) -> Optional[bytes]:
    """
    Экспортирует произвольную таблицу в CSV.
    Внимание: таблица должна существовать и быть доступной.
    """
    async with db_pool.acquire() as conn:
        # Проверка существования таблицы (защита от SQL-инъекций через параметр)
        # В реальном проекте лучше использовать белый список таблиц
        try:
            rows = await conn.fetch(f"SELECT * FROM {table} ORDER BY id")
        except Exception:
            return None
        if not rows:
            return None
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(dict(rows[0]).keys())
        for row in rows:
            writer.writerow(dict(row).values())
        return output.getvalue().encode('utf-8')

# ===== ФОРМАТИРОВАНИЕ ВРЕМЕНИ =====
def format_time_remaining(seconds: int) -> str:
    """Форматирует секунды в строку вида 'Xч Yм' или 'Yм' или 'меньше минуты'."""
    if seconds < 60:
        return "меньше минуты"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} мин"
    hours = minutes // 60
    minutes %= 60
    if minutes == 0:
        return f"{hours} ч"
    return f"{hours} ч {minutes} мин"

# ===== РАБОТА СО СЛУЧАЙНЫМИ ФРАЗАМИ =====
def get_random_phrase(phrase_list: List[str], **kwargs) -> str:
    """Выбирает случайную фразу из списка и подставляет аргументы."""
    phrase = random.choice(phrase_list)
    return phrase.format(**kwargs)

# ===== РАСЧЁТ УРОНА В БОЮ =====
async def calculate_fight_damage(strength: int) -> int:
    """
    Рассчитывает урон на основе силы и настроек.
    Возвращает целое число урона.
    """
    base = int(await get_setting("fight_base_damage"))
    variance = int(await get_setting("fight_damage_variance"))
    damage = base + strength // 2 + random.randint(-variance, variance)
    return max(1, damage)

# ===== РАСЧЁТ АВТОРИТЕТА ЗА БОЙ =====
async def calculate_fight_authority() -> int:
    """Возвращает случайное количество авторитета за удар."""
    min_auth = int(await get_setting("fight_authority_min"))
    max_auth = int(await get_setting("fight_authority_max"))
    return random.randint(min_auth, max_auth)

# ===== ОПРЕДЕЛЕНИЕ, ЯВЛЯЕТСЯ ЛИ УДАР КРИТИЧЕСКИМ =====
def is_critical(strength: int, agility: int) -> bool:
    """Вероятность критического удара зависит от ловкости."""
    chance = 5 + agility * 2
    if chance > 50:
        chance = 50
    return random.randint(1, 100) <= chance

# ===== ОПРЕДЕЛЕНИЕ, КОНТРАТАКУЕТ ЛИ ЦЕЛЬ =====
def is_counter(defense: int) -> bool:
    """Вероятность контратаки зависит от защиты."""
    chance = 5 + defense * 1
    if chance > 40:
        chance = 40
    return random.randint(1, 100) <= chance
