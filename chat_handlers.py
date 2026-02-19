# ========== chat_handlers.py ==========
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from core import (
    dp, bot, db_pool,
    get_setting,
    is_chat_confirmed,
    get_user_stats, update_user_stats,
    get_chat_authority, add_chat_authority, spend_chat_authority,
    log_fight, can_fight, set_fight_cooldown,
    safe_send_chat, update_user_balance,
    FIGHT_HIT_PHRASES, FIGHT_CRIT_PHRASES, FIGHT_MISS_PHRASES, FIGHT_COUNTER_PHRASES,
)
from utils import (
    calculate_fight_damage, calculate_fight_authority,
    is_critical, is_counter, format_time_remaining, get_random_phrase
)

# ===== ПРОВЕРКА ЧАТА =====
async def check_chat(message: types.Message) -> bool:
    """Проверяет, активирован ли чат, и отвечает ошибкой, если нет."""
    if message.chat.type == 'private':
        await message.reply("❌ Эта команда работает только в группах.")
        return False
    if not await is_chat_confirmed(message.chat.id):
        await message.reply("❌ Этот чат не активирован. Обратитесь к администратору.")
        return False
    return True

# ===== КОМАНДА /FIGHT =====
@dp.message_handler(Command("fight"))
async def cmd_fight(message: types.Message):
    if not await check_chat(message):
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.first_name

    # Проверка кулдауна
    ok, remaining = await can_fight(chat_id, user_id)
    if not ok:
        await message.reply(
            f"⏳ Ты слишком часто машешь кулаками! Подожди ещё {format_time_remaining(remaining * 60)}.",
            reply=False
        )
        return

    # Получаем статы игрока
    stats = await get_user_stats(user_id)
    strength = stats['strength']
    agility = stats['agility']
    defense = stats['defense']

    # Расчёт урона и авторитета
    damage = await calculate_fight_damage(strength)
    authority = await calculate_fight_authority()

    outcome = "hit"
    counter_damage = 0

    # Проверка на критический удар
    if is_critical(strength, agility):
        damage = int(damage * 1.5)
        authority = int(authority * 1.5)
        phrase_list = FIGHT_CRIT_PHRASES
        outcome = "crit"
    else:
        phrase_list = FIGHT_HIT_PHRASES

    # Проверка на контратаку (цель может ответить)
    if is_counter(defense):
        counter_damage = random.randint(1, 5)
        await update_user_balance(user_id, -counter_damage)
        outcome = "counter"
        phrase_list = FIGHT_COUNTER_PHRASES

    # Сохраняем результаты
    await add_chat_authority(chat_id, user_id, authority, damage)
    await set_fight_cooldown(chat_id, user_id)
    await log_fight(chat_id, user_id, damage, authority, outcome)

    # Выбираем фразу
    if outcome == "counter":
        phrase = get_random_phrase(phrase_list, damage=counter_damage)
    else:
        phrase = get_random_phrase(phrase_list, damage=damage, authority=authority)

    # Отправляем результат в чат
    await message.reply(
        f"{username}, {phrase}\n"
        f"Твой авторитет в этом чате: {await get_chat_authority(chat_id, user_id)}"
    )

    # Если была контратака, добавляем сообщение о потерянных монетах
    if outcome == "counter":
        await message.reply(f"💸 Ты потерял {counter_damage} монет.")

# ===== КОМАНДА /GYM =====
@dp.message_handler(Command("gym"))
async def cmd_gym(message: types.Message):
    if not await check_chat(message):
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    authority = await get_chat_authority(chat_id, user_id)

    # Получаем стоимость улучшений из настроек
    strength_cost = int(await get_setting("gym_strength_cost"))
    agility_cost = int(await get_setting("gym_agility_cost"))
    defense_cost = int(await get_setting("gym_defense_cost"))

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(f"💪 Сила ({strength_cost} авт.)", callback_data="gym_strength"),
        InlineKeyboardButton(f"🏃 Ловкость ({agility_cost} авт.)", callback_data="gym_agility"),
        InlineKeyboardButton(f"🛡 Защита ({defense_cost} авт.)", callback_data="gym_defense"),
        InlineKeyboardButton("❌ Отмена", callback_data="gym_cancel")
    )

    await message.reply(
        f"🏋️ Качалка! У тебя {authority} авторитета.\n"
        f"Что хочешь улучшить?",
        reply_markup=kb
    )

@dp.callback_query_handler(lambda c: c.data.startswith("gym_"))
async def gym_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    if not await is_chat_confirmed(chat_id):
        await callback.answer("Чат не активирован.", show_alert=True)
        return

    action = callback.data.split("_")[1]

    if action == "cancel":
        await callback.message.delete()
        await callback.answer()
        return

    # Определяем стоимость и характеристику
    if action == "strength":
        cost = int(await get_setting("gym_strength_cost"))
        stat = "strength"
    elif action == "agility":
        cost = int(await get_setting("gym_agility_cost"))
        stat = "agility"
    elif action == "defense":
        cost = int(await get_setting("gym_defense_cost"))
        stat = "defense"
    else:
        await callback.answer("Неизвестная опция")
        return

    # Проверяем, хватает ли авторитета
    authority = await get_chat_authority(chat_id, user_id)
    if authority < cost:
        await callback.answer(f"❌ Не хватает авторитета. Нужно {cost}, у тебя {authority}.", show_alert=True)
        return

    # Списываем авторитет и увеличиваем стат
    if await spend_chat_authority(chat_id, user_id, cost):
        if stat == "strength":
            await update_user_stats(user_id, strength_delta=1)
        elif stat == "agility":
            await update_user_stats(user_id, agility_delta=1)
        elif stat == "defense":
            await update_user_stats(user_id, defense_delta=1)

        await callback.answer(f"✅ Ты улучшил {stat}!", show_alert=True)
        await callback.message.edit_text(
            f"✅ Ты улучшил {stat}!\n"
            f"Осталось авторитета: {await get_chat_authority(chat_id, user_id)}"
        )
    else:
        await callback.answer("❌ Ошибка при списании авторитета.", show_alert=True)

# ===== КОМАНДА /STATUS =====
@dp.message_handler(Command("status"))
async def cmd_status(message: types.Message):
    if not await check_chat(message):
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    stats = await get_user_stats(user_id)
    authority = await get_chat_authority(chat_id, user_id)

    # Получаем количество боёв из таблицы chat_authority
    async with db_pool.acquire() as conn:
        fights = await conn.fetchval("SELECT fights FROM chat_authority WHERE chat_id=$1 AND user_id=$2", chat_id, user_id) or 0

    text = (
        f"📊 Твой статус в этом чате:\n"
        f"Авторитет: {authority}\n"
        f"💪 Сила: {stats['strength']}\n"
        f"🏃 Ловкость: {stats['agility']}\n"
        f"🛡 Защита: {stats['defense']}\n"
        f"⚔️ Всего боёв: {fights}"
    )
    await message.reply(text)

# ===== КОМАНДА /TOP =====
@dp.message_handler(Command("top"))
async def cmd_top(message: types.Message):
    if not await check_chat(message):
        return

    chat_id = message.chat.id
    args = message.get_args().split()
    page = 1
    order = "authority"  # по умолчанию
    if args:
        if args[0].isdigit():
            page = int(args[0])
        elif args[0] in ["authority", "damage", "fights"]:
            order = args[0]
            if len(args) > 1 and args[1].isdigit():
                page = int(args[1])

    await show_top(chat_id, message, page, order)

async def show_top(chat_id: int, message: types.Message, page: int = 1, order: str = "authority"):
    offset = (page - 1) * 10
    async with db_pool.acquire() as conn:
        if order == "authority":
            rows = await conn.fetch(
                "SELECT user_id, authority, total_damage, fights FROM chat_authority WHERE chat_id=$1 ORDER BY authority DESC LIMIT 10 OFFSET $2",
                chat_id, offset
            )
        elif order == "damage":
            rows = await conn.fetch(
                "SELECT user_id, authority, total_damage, fights FROM chat_authority WHERE chat_id=$1 ORDER BY total_damage DESC LIMIT 10 OFFSET $2",
                chat_id, offset
            )
        else:  # fights
            rows = await conn.fetch(
                "SELECT user_id, authority, total_damage, fights FROM chat_authority WHERE chat_id=$1 ORDER BY fights DESC LIMIT 10 OFFSET $2",
                chat_id, offset
            )
        total = await conn.fetchval("SELECT COUNT(*) FROM chat_authority WHERE chat_id=$1", chat_id)

    if not rows:
        await message.reply("🏆 В этом чате пока нет участников.")
        return

    text = f"🏆 Топ чата (по {order}):\n"
    for i, row in enumerate(rows, start=offset+1):
        try:
            user = await bot.get_chat_member(chat_id, row['user_id'])
            name = user.user.first_name if user else f"ID {row['user_id']}"
        except:
            name = f"ID {row['user_id']}"
        text += f"{i}. {name} – Авторитет: {row['authority']}, Урон: {row['total_damage']}, Боёв: {row['fights']}\n"

    # Кнопки пагинации и выбора категории
    kb = InlineKeyboardMarkup(row_width=3)
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"top_{order}_{page-1}"))
    nav.append(InlineKeyboardButton(f"{page}", callback_data="noop"))
    if offset + 10 < total:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"top_{order}_{page+1}"))
    kb.row(*nav)

    kb.row(
        InlineKeyboardButton("📊 По авторитету", callback_data=f"top_authority_1"),
        InlineKeyboardButton("💥 По урону", callback_data=f"top_damage_1"),
        InlineKeyboardButton("⚔️ По боям", callback_data=f"top_fights_1")
    )

    await message.reply(text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("top_"))
async def top_callback(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 3:
        await callback.answer()
        return
    order = parts[1]
    page = int(parts[2])
    chat_id = callback.message.chat.id
    await show_top(chat_id, callback.message, page, order)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "noop")
async def noop(callback: types.CallbackQuery):
    await callback.answer()

# ===== КОМАНДА /HELP =====
@dp.message_handler(Command("help"))
async def cmd_help_chat(message: types.Message):
    if not await check_chat(message):
        return
    text = (
        "📚 Доступные команды в этом чате:\n"
        "/fight – атаковать банду (раз в 30 мин)\n"
        "/gym – улучшить характеристики за авторитет\n"
        "/status – твой статус\n"
        "/top – топ чата\n"
        "/help – это сообщение"
    )
    await message.reply(text)

# ===== ОБРАБОТКА НЕИЗВЕСТНЫХ КОМАНД =====
@dp.message_handler(lambda message: message.text and message.text.startswith('/'))
async def unknown_command(message: types.Message):
    if message.chat.type == 'private':
        return
    if not await is_chat_confirmed(message.chat.id):
        return
    await message.reply("❌ Неизвестная команда. Введи /help для списка доступных.")
