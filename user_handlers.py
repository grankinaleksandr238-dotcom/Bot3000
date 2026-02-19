# ========== user_handlers.py ==========
import asyncio
import logging
import random
from datetime import datetime, timedelta, date
from typing import Optional

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command, Text
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from core import (
    dp, bot, db_pool,
    get_setting,
    is_banned, is_admin, is_super_admin,
    get_user_balance, update_user_balance,
    get_user_reputation, update_user_reputation,
    get_user_stats, update_user_stats,
    add_exp, get_user_level, get_user_exp,
    get_random_user, find_user_by_input,
    update_user_total_spent,
    is_chat_confirmed,
    notify_chats, safe_send_message,
    create_chat_confirmation_request,
    get_pending_chat_requests, update_chat_request_status,
    add_confirmed_chat, remove_confirmed_chat,
    check_subscription,
    # Клавиатуры
    user_main_keyboard, subscription_inline, back_keyboard,
    theft_choice_keyboard,
    auction_list_keyboard, auction_detail_keyboard,
    # Состояния
    CasinoBet, DiceBet, GuessBet, PromoActivate, TheftTarget,
    FindUser, CreateAuction, AuctionBid,
    # Константы и фразы
    ITEMS_PER_PAGE, BIG_WIN_THRESHOLD, BIG_PURCHASE_THRESHOLD,
    BONUS_PHRASES, PURCHASE_PHRASES,
    THEFT_CHOICE_PHRASES, THEFT_COOLDOWN_PHRASES,
    THEFT_NO_MONEY_PHRASES, THEFT_SUCCESS_PHRASES, THEFT_FAIL_PHRASES,
    THEFT_DEFENSE_PHRASES, THEFT_VICTIM_DEFENSE_PHRASES,
    CHAT_WIN_PHRASES, CHAT_PURCHASE_PHRASES, CHAT_GIVEAWAY_PHRASES,
)
from utils import get_random_phrase, format_time_remaining

# ===== КОМАНДА HELP =====
@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    text = (
        "🤖 <b>Malboro GAME</b> – помощь:\n\n"
        "• 👤 Профиль – баланс, уровень, репутация, статы\n"
        "• 🎁 Бонус – ежедневная награда\n"
        "• 🛒 Магазин подарков – покупка подарков\n"
        "• 🎰 Казино – испытай удачу (/casino)\n"
        "• 🎟 Промокод – активация промокодов\n"
        "• 🏆 Топ игроков – лучшие по балансу, уровню, статам\n"
        "• 💰 Мои покупки – история заказов\n"
        "• 🔫 Ограбить – укради монеты у другого\n"
        "• 🎲 Игры – кости, угадай число, мультиплеер 21\n"
        "• ⭐️ Репутация – твой авторитет\n"
        "• 📋 Задания – выполняй и получай награды\n"
        "• 🔗 Рефералка – приглашай друзей\n"
        "• 📊 Уровень – твой прогресс\n"
        "• 🏷 Аукцион – участвуй в торгах\n\n"
        "Администраторы имеют дополнительные функции."
    )
    await message.answer(text, reply_markup=user_main_keyboard(await is_admin(user_id)))

# ===== СТАРТ =====
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        await message.answer("⛔ Вы заблокированы.")
        return

    args = message.get_args()
    if args and args.startswith('ref'):
        try:
            referrer_id = int(args[3:])
            if referrer_id != user_id and not await is_banned(referrer_id):
                async with db_pool.acquire() as conn:
                    existing = await conn.fetchval("SELECT 1 FROM referrals WHERE referred_id=$1", user_id)
                    if not existing:
                        await conn.execute(
                            "INSERT INTO referrals (referrer_id, referred_id, referred_date, reward_given, clicks) VALUES ($1, $2, $3, $4, 1) ON CONFLICT (referred_id) DO NOTHING",
                            referrer_id, user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), False
                        )
                        # Увеличиваем счётчик кликов у реферера
                        await conn.execute("UPDATE referrals SET clicks = clicks + 1 WHERE referred_id=$1", user_id)
                        await safe_send_message(referrer_id, f"🔗 Новый пользователь {message.from_user.first_name} зарегистрировался по вашей ссылке! Награда будет выдана после того, как он совершит 15 успешных ограблений.")
        except:
            pass

    username = message.from_user.username
    first_name = message.from_user.first_name
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (user_id, username, first_name, joined_date, balance, reputation, total_spent, negative_balance, game_wins, exp, level, strength, agility, defense) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14) ON CONFLICT (user_id) DO NOTHING",
                user_id, username, first_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0, 0, 0, 0, 0, 0, 1, 1, 1, 1
            )
    except Exception as e:
        logging.error(f"DB error in start: {e}")
        await message.answer("❌ Ошибка базы данных. Попробуй позже.")
        return

    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer(
            "❗️ Для доступа к боту нужно подписаться на наши каналы.\nПосле подписки нажми кнопку ниже.",
            reply_markup=subscription_inline(not_subscribed)
        )
        return
    admin_flag = await is_admin(user_id)
    await message.answer(
        f"Привет, {first_name}!\n"
        f"Добро пожаловать в <b>Malboro GAME</b>! 🚬\n"
        f"Тут ты найдёшь: казино, розыгрыши, магазин, аукцион.\n"
        f"А ещё можешь грабить других – случайно или по username!\n"
        f"У тебя 1 уровень. Зарабатывай опыт и повышай уровень!\n\n"
        f"Канал: @lllMALBOROlll (подпишись!)",
        reply_markup=user_main_keyboard(admin_flag)
    )

# ===== ПРОВЕРКА ПОДПИСКИ =====
@dp.callback_query_handler(lambda c: c.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    if callback.message.chat.type != 'private':
        await callback.answer("Эта функция работает только в личке", show_alert=True)
        return
    if await is_banned(callback.from_user.id) and not await is_admin(callback.from_user.id):
        await callback.answer("⛔ Вы заблокированы.", show_alert=True)
        return
    ok, not_subscribed = await check_subscription(callback.from_user.id)
    if ok:
        admin_flag = await is_admin(callback.from_user.id)
        await callback.message.edit_text("✅ Подписка подтверждена! Добро пожаловать.")
        await callback.message.answer("Главное меню:", reply_markup=user_main_keyboard(admin_flag))
    else:
        await callback.answer("❌ Ты ещё не подписался на все каналы!", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=subscription_inline(not_subscribed))

@dp.callback_query_handler(lambda c: c.data == "no_link")
async def no_link(callback: types.CallbackQuery):
    await callback.answer("Ссылка временно недоступна, найди канал вручную", show_alert=True)

# ===== ПРОФИЛЬ =====
@dp.message_handler(lambda message: message.text == "👤 Профиль")
async def profile_handler(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT balance, reputation, total_spent, negative_balance, joined_date, theft_attempts, theft_success, theft_failed, theft_protected, casino_wins, casino_losses, guess_wins, guess_losses, game_wins, exp, level, strength, agility, defense FROM users WHERE user_id=$1",
                user_id
            )
        if row:
            balance, rep, spent, neg, joined, attempts, success, failed, protected, cw, cl, gw, gl, gwins, exp, level, strength, agility, defense = (
                row['balance'], row['reputation'], row['total_spent'], row['negative_balance'], row['joined_date'],
                row['theft_attempts'], row['theft_success'], row['theft_failed'], row['theft_protected'],
                row['casino_wins'], row['casino_losses'], row['guess_wins'], row['guess_losses'],
                row['game_wins'], row['exp'], row['level'], row['strength'], row['agility'], row['defense']
            )
            neg_text = f" (долг: {neg})" if neg > 0 else ""
            level_mult = int(await get_setting("level_multiplier"))
            exp_needed = level * level_mult
            progress = exp / exp_needed if exp_needed > 0 else 0
            bar_length = 10
            filled = int(progress * bar_length)
            bar = "🟩" * filled + "⬜" * (bar_length - filled)
            text = (
                f"👤 <b>Твой профиль</b>\n"
                f"📊 <b>Уровень:</b> {level}\n"
                f"📈 <b>Опыт:</b> {exp}/{exp_needed}\n{bar}\n"
                f"💪 Сила: {strength} | 🏃 Ловкость: {agility} | 🛡 Защита: {defense}\n"
                f"💰 Баланс: {balance} монет{neg_text}\n"
                f"⭐️ Репутация: {rep}\n"
                f"💸 Всего потрачено: {spent} монет\n"
                f"📅 Зарегистрирован: {joined}\n"
                f"🔫 Ограблений: {attempts} (успешно: {success}, провал: {failed})\n"
                f"⚔️ Отбито атак: {protected}\n"
                f"🎰 Казино: побед {cw}, поражений {cl}\n"
                f"🔢 Угадайка: побед {gw}, поражений {gl}\n"
                f"👥 Побед в мультиплеере: {gwins}"
            )
        else:
            text = "Профиль не найден"
    except Exception as e:
        logging.error(f"Profile error: {e}")
        text = "❌ Ошибка загрузки профиля."
    await message.answer(text, reply_markup=user_main_keyboard(await is_admin(user_id)))

# ===== УРОВЕНЬ =====
@dp.message_handler(lambda message: message.text == "📊 Уровень")
async def level_handler(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    level = await get_user_level(user_id)
    exp = await get_user_exp(user_id)
    level_mult = int(await get_setting("level_multiplier"))
    exp_needed = level * level_mult
    progress = exp / exp_needed if exp_needed > 0 else 0
    bar_length = 15
    filled = int(progress * bar_length)
    bar = "🟩" * filled + "⬜" * (bar_length - filled)
    level_names = {
        1: "🔰 Новичок",
        2: "⛏️ Искатель",
        3: "⚔️ Воин",
        4: "🛡️ Защитник",
        5: "🌟 Звезда",
        6: "🔥 Ветеран",
        7: "💫 Мастер",
        8: "👑 Легенда",
        9: "💎 Алмазный",
        10: "👁‍🗨 Патриарх",
    }
    level_name = level_names.get(level, f"Уровень {level}")
    text = (
        f"📊 <b>{level_name}</b>\n\n"
        f"Уровень: {level}\n"
        f"Опыт: {exp} / {exp_needed}\n"
        f"{bar}\n\n"
        f"За повышение уровня ты получаешь монеты, репутацию и очки статов!\n"
        f"Следующая награда: +{await get_level_reward_coins(level+1)} монет, +{await get_level_reward_rep(level+1)} репутации."
    )
    await message.answer(text, reply_markup=user_main_keyboard(await is_admin(user_id)))

async def get_level_reward_coins(level: int) -> int:
    async with db_pool.acquire() as conn:
        val = await conn.fetchval("SELECT coins FROM level_rewards WHERE level=$1", level)
        return val if val else 0

async def get_level_reward_rep(level: int) -> int:
    async with db_pool.acquire() as conn:
        val = await conn.fetchval("SELECT reputation FROM level_rewards WHERE level=$1", level)
        return val if val else 0

# ===== РЕПУТАЦИЯ =====
@dp.message_handler(lambda message: message.text == "⭐️ Репутация")
async def reputation_handler(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    rep = await get_user_reputation(user_id)
    theft_bonus = float(await get_setting("reputation_theft_bonus")) * rep
    defense_bonus = float(await get_setting("reputation_defense_bonus")) * rep
    await message.answer(
        f"⭐️ Твоя репутация: {rep}\n\n"
        f"Репутация увеличивает шансы:\n"
        f"🔫 Бонус к грабежу: +{theft_bonus:.1f}%\n"
        f"🛡 Бонус к защите: +{defense_bonus:.1f}%\n\n"
        f"Зарабатывай репутацию в играх и за выполнение заданий!",
        reply_markup=user_main_keyboard(await is_admin(user_id))
    )

# ===== БОНУС =====
@dp.message_handler(lambda message: message.text == "🎁 Бонус")
async def bonus_handler(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    try:
        async with db_pool.acquire() as conn:
            last_bonus_str = await conn.fetchval("SELECT last_bonus FROM users WHERE user_id=$1", user_id)

        now = datetime.now()
        if last_bonus_str:
            last_bonus = datetime.strptime(last_bonus_str, "%Y-%m-%d %H:%M:%S")
            if now - last_bonus < timedelta(days=1):
                remaining = timedelta(days=1) - (now - last_bonus)
                hours = remaining.seconds // 3600
                minutes = (remaining.seconds // 60) % 60
                await message.answer(f"⏳ Бонус можно будет получить через {hours} ч {minutes} мин")
                return

        bonus = random.randint(5, 15)
        phrase = get_random_phrase(BONUS_PHRASES, bonus=bonus)

        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET balance = balance + $1, last_bonus = $2 WHERE user_id=$3",
                bonus, now.strftime("%Y-%m-%d %H:%M:%S"), user_id
            )
        await message.answer(phrase, reply_markup=user_main_keyboard(await is_admin(user_id)))
    except Exception as e:
        logging.error(f"Bonus error: {e}")
        await message.answer("❌ Ошибка при получении бонуса.")

# ===== ТОП ИГРОКОВ =====
@dp.message_handler(lambda message: message.text == "🏆 Топ игроков")
async def leaderboard_menu(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💰 Самые богатые")],
        [KeyboardButton(text="💸 Транжиры")],
        [KeyboardButton(text="🔫 Крадуны")],
        [KeyboardButton(text="⭐️ По репутации")],
        [KeyboardButton(text="👥 Победы в мультиплеере")],
        [KeyboardButton(text="📈 По уровню")],
        [KeyboardButton(text="💪 По силе")],
        [KeyboardButton(text="🏃 По ловкости")],
        [KeyboardButton(text="🛡 По защите")],
        [KeyboardButton(text="◀️ Назад")]
    ], resize_keyboard=True)
    await message.answer("Выбери категорию топа:", reply_markup=kb)

async def show_top(message: types.Message, order_field: str, title: str):
    page = 1
    try:
        parts = message.text.split()
        if len(parts) > 1:
            page = int(parts[1])
    except:
        pass
    offset = (page - 1) * ITEMS_PER_PAGE
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval(f"SELECT COUNT(*) FROM users")
            rows = await conn.fetch(
                f"SELECT first_name, {order_field} FROM users ORDER BY {order_field} DESC LIMIT $1 OFFSET $2",
                ITEMS_PER_PAGE, offset
            )
        if not rows:
            await message.answer("Нет данных.")
            return
        text = f"{title} (страница {page}):\n\n"
        for idx, row in enumerate(rows, start=offset+1):
            text += f"{idx}. {row['first_name']} – {row[order_field]}\n"
        kb = []
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"top:{order_field}:{page-1}"))
        if offset + ITEMS_PER_PAGE < total:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"top:{order_field}:{page+1}"))
        if nav_buttons:
            kb.append(nav_buttons)
        if kb:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        else:
            await message.answer(text)
    except Exception as e:
        logging.error(f"Top error: {e}")
        await message.answer("❌ Ошибка загрузки топа.")

# Обработчики категорий топа
@dp.message_handler(lambda message: message.text == "💰 Самые богатые")
async def top_rich_handler(message: types.Message):
    await show_top(message, "balance", "💰 Самые богатые")

@dp.message_handler(lambda message: message.text == "💸 Транжиры")
async def top_spenders_handler(message: types.Message):
    await show_top(message, "total_spent", "💸 Транжиры")

@dp.message_handler(lambda message: message.text == "🔫 Крадуны")
async def top_thieves_handler(message: types.Message):
    await show_top(message, "theft_success", "🔫 Крадуны")

@dp.message_handler(lambda message: message.text == "⭐️ По репутации")
async def top_reputation_handler(message: types.Message):
    await show_top(message, "reputation", "⭐️ По репутации")

@dp.message_handler(lambda message: message.text == "👥 Победы в мультиплеере")
async def top_multiplayer_handler(message: types.Message):
    await show_top(message, "game_wins", "👥 Победы в мультиплеере")

@dp.message_handler(lambda message: message.text == "📈 По уровню")
async def top_level_handler(message: types.Message):
    await show_top(message, "level", "📈 По уровню")

@dp.message_handler(lambda message: message.text == "💪 По силе")
async def top_strength_handler(message: types.Message):
    await show_top(message, "strength", "💪 По силе")

@dp.message_handler(lambda message: message.text == "🏃 По ловкости")
async def top_agility_handler(message: types.Message):
    await show_top(message, "agility", "🏃 По ловкости")

@dp.message_handler(lambda message: message.text == "🛡 По защите")
async def top_defense_handler(message: types.Message):
    await show_top(message, "defense", "🛡 По защите")

@dp.callback_query_handler(lambda c: c.data.startswith("top:"))
async def top_page_callback(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    field = parts[1]
    page = int(parts[2])
    titles = {
        "balance": "💰 Самые богатые",
        "total_spent": "💸 Транжиры",
        "theft_success": "🔫 Крадуны",
        "reputation": "⭐️ По репутации",
        "game_wins": "👥 Победы в мультиплеере",
        "level": "📈 По уровню",
        "strength": "💪 По силе",
        "agility": "🏃 По ловкости",
        "defense": "🛡 По защите"
    }
    title = titles.get(field, "Топ")
    await show_top(callback.message, field, title)
    await callback.answer()

# ===== МАГАЗИН ПОДАРКОВ =====
@dp.message_handler(lambda message: message.text == "🛒 Магазин подарков")
async def shop_handler(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    page = 1
    try:
        parts = message.text.split()
        if len(parts) > 1:
            page = int(parts[1])
    except:
        pass
    offset = (page - 1) * ITEMS_PER_PAGE
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM shop_items")
            rows = await conn.fetch(
                "SELECT id, name, description, price, stock FROM shop_items ORDER BY id LIMIT $1 OFFSET $2",
                ITEMS_PER_PAGE, offset
            )
        if not rows:
            await message.answer("🎁 В магазине пока нет подарков.")
            return
        text = f"🎁 Подарки (страница {page}):\n\n"
        kb = []
        for row in rows:
            item_id = row['id']
            name = row['name']
            desc = row['description']
            price = row['price']
            stock = row['stock']
            stock_info = f" (в наличии: {stock})" if stock != -1 else ""
            text += f"🔹 {name}\n{desc}\n💰 {price} монет{stock_info}\n\n"
            kb.append([InlineKeyboardButton(text=f"Купить {name}", callback_data=f"buy_{item_id}")])
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"shop_page_{page-1}"))
        if offset + ITEMS_PER_PAGE < total:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"shop_page_{page+1}"))
        if nav_buttons:
            kb.append(nav_buttons)
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    except Exception as e:
        logging.error(f"Shop error: {e}")
        await message.answer("❌ Ошибка загрузки магазина.")

@dp.callback_query_handler(lambda c: c.data.startswith("shop_page_"))
async def shop_page_callback(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    callback.message.text = f"🛒 Магазин подарков {page}"
    await shop_handler(callback.message)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("buy_"))
async def buy_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        await callback.answer("⛔ Вы заблокированы.", show_alert=True)
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await callback.message.edit_text("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    item_id = int(callback.data.split("_")[1])
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT name, price, stock FROM shop_items WHERE id=$1", item_id)
            if not row:
                await callback.answer("Товар не найден", show_alert=True)
                return
            name, price, stock = row['name'], row['price'], row['stock']
            if stock != -1 and stock <= 0:
                await callback.answer("Товара нет в наличии!", show_alert=True)
                return
            balance = await get_user_balance(user_id)
            if balance < price:
                await callback.answer("Не хватает монет!", show_alert=True)
                return
            async with conn.transaction():
                await update_user_balance(user_id, -price, conn=conn)
                await update_user_total_spent(user_id, price)
                await conn.execute(
                    "INSERT INTO purchases (user_id, item_id, purchase_date) VALUES ($1, $2, $3)",
                    user_id, item_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                if stock != -1:
                    await conn.execute("UPDATE shop_items SET stock = stock - 1 WHERE id=$1", item_id)

        phrase = get_random_phrase(PURCHASE_PHRASES)
        await callback.answer(f"✅ Ты купил {name}! {phrase}", show_alert=True)

        if await get_setting("chat_notify_big_purchase") == "1" and price >= BIG_PURCHASE_THRESHOLD:
            user = callback.from_user
            chat_phrase = get_random_phrase(CHAT_PURCHASE_PHRASES, name=user.first_name, item=name, price=price)
            await notify_chats(chat_phrase, 'purchase')

        asyncio.create_task(notify_admins_about_purchase(callback.from_user, name, price))
        try:
            await callback.message.edit_text(f"✅ Покупка совершена!")
        except:
            pass
        await callback.message.answer("Главное меню:", reply_markup=user_main_keyboard(await is_admin(user_id)))
    except Exception as e:
        logging.error(f"Purchase error: {e}")
        await callback.answer("❌ Ошибка при покупке. Попробуй позже.", show_alert=True)

async def notify_admins_about_purchase(user: types.User, item_name: str, price: int):
    admins = SUPER_ADMINS.copy()
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM admins")
        for row in rows:
            admins.append(row['user_id'])
    for admin_id in admins:
        await safe_send_message(admin_id,
            f"🛒 Покупка: пользователь {user.full_name} (@{user.username})\n"
            f"<a href=\"tg://user?id={user.id}\">Ссылка</a> купил {item_name} за {price} монет."
        )

# ===== МОИ ПОКУПКИ =====
@dp.message_handler(lambda message: message.text == "💰 Мои покупки")
async def my_purchases(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    page = 1
    try:
        parts = message.text.split()
        if len(parts) > 1:
            page = int(parts[1])
    except:
        pass
    offset = (page - 1) * ITEMS_PER_PAGE
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM purchases WHERE user_id=$1", user_id)
            rows = await conn.fetch(
                "SELECT p.id, s.name, p.purchase_date, p.status, p.admin_comment FROM purchases p "
                "JOIN shop_items s ON p.item_id = s.id WHERE p.user_id=$1 ORDER BY p.purchase_date DESC LIMIT $2 OFFSET $3",
                user_id, ITEMS_PER_PAGE, offset
            )
        if not rows:
            await message.answer("У тебя пока нет покупок.", reply_markup=user_main_keyboard(await is_admin(user_id)))
            return
        text = f"📦 Твои покупки (страница {page}):\n"
        for row in rows:
            pid, name, date, status, comment = row['id'], row['name'], row['purchase_date'], row['status'], row['admin_comment']
            status_emoji = "⏳" if status == 'pending' else "✅" if status == 'completed' else "❌"
            text += f"{status_emoji} {name} от {date}\n"
            if comment:
                text += f"   Комментарий: {comment}\n"
        kb = []
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"mypurchases_page_{page-1}"))
        if offset + ITEMS_PER_PAGE < total:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"mypurchases_page_{page+1}"))
        if nav_buttons:
            kb.append(nav_buttons)
        if kb:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        else:
            await message.answer(text, reply_markup=user_main_keyboard(await is_admin(user_id)))
    except Exception as e:
        logging.error(f"My purchases error: {e}")
        await message.answer("❌ Ошибка загрузки покупок.")

@dp.callback_query_handler(lambda c: c.data.startswith("mypurchases_page_"))
async def mypurchases_page_callback(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    callback.message.text = f"💰 Мои покупки {page}"
    await my_purchases(callback.message)
    await callback.answer()

# ===== ПРОМОКОД =====
@dp.message_handler(lambda message: message.text == "🎟 Промокод")
async def promo_handler(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    await message.answer("Введи промокод:", reply_markup=back_keyboard())
    await PromoActivate.code.set()

@dp.message_handler(state=PromoActivate.code)
async def promo_activate(message: types.Message, state: FSMContext):
    if message.chat.type != 'private':
        await state.finish()
        return
    if message.text == "◀️ Назад":
        await state.finish()
        await message.answer("Главное меню:", reply_markup=user_main_keyboard(await is_admin(message.from_user.id)))
        return
    code = message.text.strip().upper()
    user_id = message.from_user.id
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        await state.finish()
        return
    try:
        async with db_pool.acquire() as conn:
            already_used = await conn.fetchval(
                "SELECT 1 FROM promo_activations WHERE user_id=$1 AND promo_code=$2",
                user_id, code
            )
            if already_used:
                await message.answer("❌ Ты уже активировал этот промокод.")
                await state.finish()
                return
            row = await conn.fetchrow("SELECT reward, max_uses, used_count FROM promocodes WHERE code=$1", code)
            if not row:
                await message.answer("❌ Промокод не найден.")
                await state.finish()
                return
            reward, max_uses, used = row['reward'], row['max_uses'], row['used_count']
            if used >= max_uses:
                await message.answer("❌ Промокод уже использован максимальное количество раз.")
                await state.finish()
                return
            async with conn.transaction():
                await update_user_balance(user_id, reward, conn=conn)
                await conn.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code=$1", code)
                await conn.execute(
                    "INSERT INTO promo_activations (user_id, promo_code, activated_at) VALUES ($1, $2, $3)",
                    user_id, code, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
        await message.answer(
            f"✅ Промокод активирован! Ты получил {reward} монет.",
            reply_markup=user_main_keyboard(await is_admin(user_id))
        )
    except Exception as e:
        logging.error(f"Promo error: {e}")
        await message.answer("❌ Ошибка активации промокода.")
    await state.finish()

# ===== ОГРАБЛЕНИЕ =====
async def get_theft_success_chance(attacker_id: int) -> float:
    base = int(await get_setting("theft_success_chance"))
    rep = await get_user_reputation(attacker_id)
    bonus = float(await get_setting("reputation_theft_bonus")) * rep
    return base + bonus

async def get_defense_chance(victim_id: int) -> float:
    base = int(await get_setting("theft_defense_chance"))
    rep = await get_user_reputation(victim_id)
    bonus = float(await get_setting("reputation_defense_bonus")) * rep
    return base + bonus

@dp.message_handler(lambda message: message.text == "🔫 Ограбить")
async def theft_menu(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    phrase = get_random_phrase(THEFT_CHOICE_PHRASES)
    await message.answer(phrase, reply_markup=theft_choice_keyboard())

@dp.message_handler(lambda message: message.text == "🎲 Случайная цель")
async def theft_random(message: types.Message, state: FSMContext):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    cooldown_minutes = int(await get_setting("theft_cooldown_minutes"))
    async with db_pool.acquire() as conn:
        last_time_str = await conn.fetchval("SELECT last_theft_time FROM users WHERE user_id=$1", user_id)
        if last_time_str:
            last_time = datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
            diff = datetime.now() - last_time
            if diff < timedelta(minutes=cooldown_minutes):
                remaining = cooldown_minutes - int(diff.total_seconds() // 60)
                phrase = get_random_phrase(THEFT_COOLDOWN_PHRASES, minutes=remaining)
                await message.answer(phrase, reply_markup=user_main_keyboard(await is_admin(user_id)))
                return
    target_id = await get_random_user(user_id)
    if not target_id:
        await message.answer("😕 В игре пока нет других игроков.", reply_markup=user_main_keyboard(await is_admin(user_id)))
        return
    cost = int(await get_setting("random_attack_cost"))
    if cost > 0:
        balance = await get_user_balance(user_id)
        if balance < cost:
            await message.answer(get_random_phrase(THEFT_NO_MONEY_PHRASES), reply_markup=user_main_keyboard(await is_admin(user_id)))
            return
        await update_user_balance(user_id, -cost)
    await perform_theft(message, user_id, target_id)

@dp.message_handler(lambda message: message.text == "👤 Выбрать пользователя")
async def theft_choose_user(message: types.Message, state: FSMContext):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    cooldown_minutes = int(await get_setting("theft_cooldown_minutes"))
    async with db_pool.acquire() as conn:
        last_time_str = await conn.fetchval("SELECT last_theft_time FROM users WHERE user_id=$1", user_id)
        if last_time_str:
            last_time = datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
            diff = datetime.now() - last_time
            if diff < timedelta(minutes=cooldown_minutes):
                remaining = cooldown_minutes - int(diff.total_seconds() // 60)
                phrase = get_random_phrase(THEFT_COOLDOWN_PHRASES, minutes=remaining)
                await message.answer(phrase, reply_markup=user_main_keyboard(await is_admin(user_id)))
                return
    await message.answer("Введи @username или ID того, кого хочешь ограбить:", reply_markup=back_keyboard())
    await TheftTarget.target.set()

@dp.message_handler(state=TheftTarget.target)
async def theft_target_entered(message: types.Message, state: FSMContext):
    if message.chat.type != 'private':
        await state.finish()
        return
    if message.text == "◀️ Назад":
        await state.finish()
        await message.answer("Главное меню:", reply_markup=user_main_keyboard(await is_admin(message.from_user.id)))
        return
    target_input = message.text.strip()
    robber_id = message.from_user.id

    target_data = await find_user_by_input(target_input)
    if not target_data:
        await message.answer("❌ Пользователь не найден. Проверь username или ID.")
        return
    target_id = target_data['user_id']

    if target_id == robber_id:
        await message.answer("Сам себя не ограбишь, бро! 😆")
        await state.finish()
        return

    if await is_banned(target_id):
        await message.answer("❌ Этот пользователь заблокирован и не может быть целью.")
        await state.finish()
        return

    cost = int(await get_setting("targeted_attack_cost"))
    if cost > 0:
        balance = await get_user_balance(robber_id)
        if balance < cost:
            await message.answer(get_random_phrase(THEFT_NO_MONEY_PHRASES), reply_markup=user_main_keyboard(await is_admin(robber_id)))
            await state.finish()
            return
        await update_user_balance(robber_id, -cost)

    await perform_theft(message, robber_id, target_id)
    await state.finish()

async def perform_theft(message: types.Message, robber_id: int, victim_id: int):
    success_chance = await get_theft_success_chance(robber_id)
    defense_chance = await get_defense_chance(victim_id)
    defense_penalty = int(await get_setting("theft_defense_penalty"))
    min_amount = int(await get_setting("min_theft_amount"))
    max_amount = int(await get_setting("max_theft_amount"))

    try:
        async with db_pool.acquire() as conn:
            victim_balance = await conn.fetchval("SELECT balance FROM users WHERE user_id=$1", victim_id)
            if victim_balance is None:
                await message.answer("❌ Цель не найдена в базе.")
                return

            victim_info = await conn.fetchrow("SELECT username, first_name FROM users WHERE user_id=$1", victim_id)
            victim_name = victim_info['first_name'] if victim_info else str(victim_id)

            defense_triggered = random.randint(1, 100) <= defense_chance
            if defense_triggered:
                penalty = defense_penalty
                robber_balance = await get_user_balance(robber_id)
                if penalty > robber_balance:
                    penalty = robber_balance
                if penalty > 0:
                    await update_user_balance(robber_id, -penalty, conn=conn)
                    await update_user_balance(victim_id, penalty, conn=conn)
                await conn.execute("UPDATE users SET theft_attempts = theft_attempts + 1, theft_failed = theft_failed + 1 WHERE user_id=$1", robber_id)
                await conn.execute("UPDATE users SET theft_protected = theft_protected + 1 WHERE user_id=$1", victim_id)
                await conn.execute("UPDATE users SET last_theft_time = $1 WHERE user_id=$2", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), robber_id)

                exp_defense = int(await get_setting("exp_per_theft_defense"))
                await add_exp(victim_id, exp_defense, conn=conn)
                exp_fail = int(await get_setting("exp_per_theft_fail"))
                await add_exp(robber_id, exp_fail, conn=conn)

                robber_phrase = get_random_phrase(THEFT_DEFENSE_PHRASES, target=victim_name, penalty=penalty)
                victim_phrase = get_random_phrase(THEFT_VICTIM_DEFENSE_PHRASES, attacker=message.from_user.first_name, penalty=penalty)
                await message.answer(robber_phrase, reply_markup=user_main_keyboard(await is_admin(robber_id)))
                await safe_send_message(victim_id, victim_phrase)
                return

            success = random.randint(1, 100) <= success_chance
            if success and victim_balance > 0:
                max_possible = min(max_amount, victim_balance)
                if max_possible < min_amount:
                    steal_amount = victim_balance
                else:
                    steal_amount = random.randint(min_amount, max_possible)

                await update_user_balance(victim_id, -steal_amount, conn=conn)
                await update_user_balance(robber_id, steal_amount, conn=conn)
                await conn.execute("UPDATE users SET theft_attempts = theft_attempts + 1, theft_success = theft_success + 1 WHERE user_id=$1", robber_id)

                exp_success = int(await get_setting("exp_per_theft_success"))
                await add_exp(robber_id, exp_success, conn=conn)

                new_success = await conn.fetchval("SELECT theft_success FROM users WHERE user_id=$1", robber_id)
                if new_success == 15:
                    ref = await conn.fetchrow("SELECT referrer_id FROM referrals WHERE referred_id=$1 AND reward_given=FALSE", robber_id)
                    if ref:
                        referrer_id = ref['referrer_id']
                        bonus_coins = int(await get_setting("referral_bonus"))
                        bonus_rep = int(await get_setting("referral_reputation"))
                        await update_user_balance(referrer_id, bonus_coins, conn=conn)
                        await update_user_reputation(referrer_id, bonus_rep)
                        await conn.execute("UPDATE referrals SET reward_given=TRUE WHERE referred_id=$1", robber_id)
                        await safe_send_message(referrer_id, f"🎉 Ваш реферал совершил 15 успешных ограблений! Вы получили {bonus_coins} монет и {bonus_rep} репутации.")
                        # Отмечаем реферала как активного
                        await conn.execute("UPDATE referrals SET active=TRUE WHERE referred_id=$1", robber_id)

                phrase = get_random_phrase(THEFT_SUCCESS_PHRASES, amount=steal_amount, target=victim_name)
                await message.answer(phrase, reply_markup=user_main_keyboard(await is_admin(robber_id)))
                await safe_send_message(victim_id, f"🔫 Вас ограбили! {message.from_user.first_name} украл {steal_amount} монет.")
            else:
                await conn.execute("UPDATE users SET theft_attempts = theft_attempts + 1, theft_failed = theft_failed + 1 WHERE user_id=$1", robber_id)
                exp_fail = int(await get_setting("exp_per_theft_fail"))
                await add_exp(robber_id, exp_fail, conn=conn)
                phrase = get_random_phrase(THEFT_FAIL_PHRASES, target=victim_name)
                await message.answer(phrase, reply_markup=user_main_keyboard(await is_admin(robber_id)))

            await conn.execute("UPDATE users SET last_theft_time = $1 WHERE user_id=$2", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), robber_id)

    except Exception as e:
        logging.error(f"Theft error: {e}")
        await message.answer("❌ Ошибка при ограблении.")

# ===== РЕФЕРАЛЬНАЯ ССЫЛКА =====
@dp.message_handler(lambda message: message.text == "🔗 Рефералка")
async def referral_link(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    bot_username = (await bot.me).username
    link = f"https://t.me/{bot_username}?start=ref{user_id}"
    bonus_coins = await get_setting("referral_bonus")
    bonus_rep = await get_setting("referral_reputation")

    # Статистика рефералов
    async with db_pool.acquire() as conn:
        clicks = await conn.fetchval("SELECT SUM(clicks) FROM referrals WHERE referrer_id=$1", user_id) or 0
        active = await conn.fetchval("SELECT COUNT(*) FROM referrals WHERE referrer_id=$1 AND active=TRUE", user_id) or 0
        # Заработанные монеты (сумма бонусов за активных рефералов)
        earned = active * int(bonus_coins)

    await message.answer(
        f"🔗 Твоя реферальная ссылка:\n{link}\n\n"
        f"📊 Статистика:\n"
        f"• Переходов: {clicks}\n"
        f"• Активных рефералов: {active}\n"
        f"• Заработано монет: {earned}\n\n"
        f"Бонус: {bonus_coins} монет и {bonus_rep} репутации за каждого активного реферала (15 успешных краж)."
    )

# ===== ЗАДАНИЯ =====
@dp.message_handler(lambda message: message.text == "📋 Задания")
async def tasks_menu(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, description, reward_coins, reward_reputation, max_completions, completed_count FROM tasks WHERE active=TRUE")
    if not rows:
        await message.answer("📋 Пока нет доступных заданий.", reply_markup=user_main_keyboard(await is_admin(user_id)))
        return

    text = "📋 Доступные задания:\n\n"
    kb = []
    for row in rows:
        progress = f" (выполнено {row['completed_count']}/{row['max_completions']})" if row['max_completions'] > 1 else ""
        text += f"🔹 {row['name']}{progress}\n{row['description']}\nНаграда: {row['reward_coins']} монет, {row['reward_reputation']} репутации\n\n"
        kb.append([InlineKeyboardButton(text=f"Выполнить {row['name']}", callback_data=f"task_{row['id']}")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query_handler(lambda c: c.data.startswith("task_"))
async def take_task(callback: types.CallbackQuery):
    task_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    async with db_pool.acquire() as conn:
        existing = await conn.fetchval("SELECT 1 FROM user_tasks WHERE user_id=$1 AND task_id=$2", user_id, task_id)
        if existing:
            await callback.answer("Ты уже выполнял это задание!", show_alert=True)
            return

        task = await conn.fetchrow("SELECT * FROM tasks WHERE id=$1 AND active=TRUE", task_id)
        if not task:
            await callback.answer("Задание не найдено или неактивно.", show_alert=True)
            return

        # Проверка глобального лимита
        if task['max_completions'] > 0 and task['completed_count'] >= task['max_completions']:
            await callback.answer("Это задание больше недоступно (лимит выполнений исчерпан).", show_alert=True)
            return

        if task['task_type'] == 'subscribe':
            channel_id = task['target_id']
            try:
                member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                if member.status in ['left', 'kicked']:
                    await callback.answer("❌ Ты не подписан на этот канал!", show_alert=True)
                    return
            except Exception as e:
                logging.error(f"Task subscribe check error: {e}")
                await callback.answer("❌ Не удалось проверить подписку. Возможно, бот не админ канала.", show_alert=True)
                return

            async with conn.transaction():
                await update_user_balance(user_id, task['reward_coins'], conn=conn)
                await update_user_reputation(user_id, task['reward_reputation'])
                expires_at = (datetime.now() + timedelta(days=task['required_days'])).strftime("%Y-%m-%d %H:%M:%S") if task['required_days'] > 0 else None
                await conn.execute(
                    "INSERT INTO user_tasks (user_id, task_id, completed_at, expires_at, status) VALUES ($1, $2, $3, $4, $5)",
                    user_id, task_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), expires_at, 'completed'
                )
                # Увеличиваем счётчик выполнений задания
                await conn.execute("UPDATE tasks SET completed_count = completed_count + 1 WHERE id=$1", task_id)

            await callback.answer(f"✅ Задание выполнено! +{task['reward_coins']} монет, +{task['reward_reputation']} репутации", show_alert=True)
            await callback.message.delete()
        else:
            await callback.answer("Этот тип заданий пока не поддерживается.", show_alert=True)

# ===== АУКЦИОН =====
@dp.message_handler(lambda message: message.text == "🏷 Аукцион")
async def auction_menu(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    await list_auctions(message)

async def list_auctions(message: types.Message, page: int = 1):
    offset = (page - 1) * ITEMS_PER_PAGE
    async with db_pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM auctions WHERE status='active'")
        rows = await conn.fetch(
            "SELECT id, item_name, current_price, end_time, target_price FROM auctions WHERE status='active' ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            ITEMS_PER_PAGE, offset
        )
    if not rows:
        await message.answer("🏷 На данный момент нет активных аукционов.", reply_markup=user_main_keyboard(await is_admin(message.from_user.id)))
        return
    text = f"🏷 Активные аукционы (страница {page}):\n\n"
    for row in rows:
        text += f"🆔 {row['id']} | {row['item_name']} | Текущая ставка: {row['current_price']}\n"
        if row['end_time']:
            end = datetime.strptime(row['end_time'], "%Y-%m-%d %H:%M:%S")
            remaining = end - datetime.now()
            if remaining.total_seconds() > 0:
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                text += f"⏳ Осталось: {hours}ч {minutes}м\n"
        if row['target_price']:
            text += f"🎯 Целевая цена: {row['target_price']}\n"
        text += "\n"
    total_pages = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    kb = auction_list_keyboard(rows, page, total_pages)
    await message.answer(text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("auction_page_"))
async def auction_page_callback(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    await list_auctions(callback.message, page)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("auction_view_"))
async def auction_view(callback: types.CallbackQuery):
    auction_id = int(callback.data.split("_")[2])
    async with db_pool.acquire() as conn:
        auction = await conn.fetchrow("SELECT * FROM auctions WHERE id=$1 AND status='active'", auction_id)
        if not auction:
            await callback.answer("Аукцион не найден или завершён.", show_alert=True)
            return
        bids = await conn.fetch("SELECT user_id, bid_amount, bid_time FROM auction_bids WHERE auction_id=$1 ORDER BY bid_time DESC LIMIT 5", auction_id)
    text = (
        f"🏷 <b>{auction['item_name']}</b>\n"
        f"📝 {auction['description']}\n\n"
        f"💰 Стартовая цена: {auction['start_price']}\n"
        f"💵 Текущая ставка: {auction['current_price']}\n"
    )
    if auction['end_time']:
        end = datetime.strptime(auction['end_time'], "%Y-%m-%d %H:%M:%S")
        remaining = end - datetime.now()
        if remaining.total_seconds() > 0:
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            text += f"⏳ Окончание через: {hours}ч {minutes}м\n"
    if auction['target_price']:
        text += f"🎯 Целевая цена: {auction['target_price']}\n"
    text += "\n📊 Последние ставки:\n"
    if bids:
        for bid in bids:
            user = await conn.fetchval("SELECT first_name FROM users WHERE user_id=$1", bid['user_id'])
            text += f"• {user or 'Неизвестно'}: {bid['bid_amount']} монет ({bid['bid_time']})\n"
    else:
        text += "Пока нет ставок.\n"
    await callback.message.answer(text, reply_markup=auction_detail_keyboard(auction_id))
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("auction_bid_"))
async def auction_bid_start(callback: types.CallbackQuery, state: FSMContext):
    auction_id = int(callback.data.split("_")[2])
    await state.update_data(auction_id=auction_id)
    await callback.message.answer("Введи сумму ставки (целое число):", reply_markup=back_keyboard())
    await AuctionBid.amount.set()
    await callback.answer()

@dp.message_handler(state=AuctionBid.amount)
async def auction_bid_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await auction_menu(message)
        return
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи положительное целое число.")
        return
    data = await state.get_data()
    auction_id = data['auction_id']
    user_id = message.from_user.id
    async with db_pool.acquire() as conn:
        auction = await conn.fetchrow("SELECT * FROM auctions WHERE id=$1 AND status='active'", auction_id)
        if not auction:
            await message.answer("❌ Аукцион не найден или завершён.")
            await state.finish()
            return
        min_step = int(await get_setting("auction_min_bid_step"))
        min_bid = auction['current_price'] + min_step
        if amount < min_bid:
            await message.answer(f"❌ Ставка должна быть не меньше {min_bid} (текущая цена + минимальный шаг).")
            return
        balance = await get_user_balance(user_id)
        if balance < amount:
            await message.answer("❌ Недостаточно монет.")
            return
        # Списываем ставку сразу (без возврата)
        await update_user_balance(user_id, -amount, conn=conn)
        # Обновляем аукцион
        await conn.execute(
            "UPDATE auctions SET current_price=$1 WHERE id=$2",
            amount, auction_id
        )
        # Записываем ставку
        await conn.execute(
            "INSERT INTO auction_bids (auction_id, user_id, bid_amount, bid_time) VALUES ($1, $2, $3, $4)",
            auction_id, user_id, amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        # Проверяем, не достигнута ли целевая цена
        if auction['target_price'] and amount >= auction['target_price']:
            # Завершаем аукцион
            await conn.execute("UPDATE auctions SET status='ended', winner_id=$1 WHERE id=$2", user_id, auction_id)
            await safe_send_message(user_id, f"🎉 Поздравляем! Ты выиграл аукцион «{auction['item_name']}» с ценой {amount} монет. Админ скоро свяжется для передачи товара.")
            await safe_send_message(auction['created_by'], f"🏁 Аукцион «{auction['item_name']}» завершён по достижению целевой цены. Победитель: {message.from_user.first_name} (ID: {user_id}) с суммой {amount} монет.")
            await message.answer("✅ Аукцион завершён! Ты победитель.")
        else:
            await message.answer(f"✅ Ставка принята! Ты теперь лидер с ценой {amount} монет.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "auction_list")
async def auction_list_back(callback: types.CallbackQuery):
    await list_auctions(callback.message)
    await callback.answer()

# ===== НАЗАД В ГЛАВНОЕ МЕНЮ =====
@dp.message_handler(lambda message: message.text == "◀️ Назад в главное меню")
async def back_to_main_from_admin(message: types.Message):
    if message.chat.type != 'private':
        return
    admin_flag = await is_admin(message.from_user.id)
    await message.answer("Главное меню:", reply_markup=user_main_keyboard(admin_flag))

@dp.message_handler(lambda message: message.text == "◀️ Назад")
async def back_from_submenu(message: types.Message):
    if message.chat.type != 'private':
        return
    admin_flag = await is_admin(message.from_user.id)
    await message.answer("Главное меню:", reply_markup=user_main_keyboard(admin_flag))

# ===== ОБРАБОТКА НЕИЗВЕСТНЫХ СООБЩЕНИЙ =====
@dp.message_handler()
async def unknown_message(message: types.Message):
    if message.chat.type != 'private':
        return
    if await is_banned(message.from_user.id) and not await is_admin(message.from_user.id):
        return
    admin_flag = await is_admin(message.from_user.id)
    await message.answer("Я не понимаю эту команду. Используй кнопки меню.", reply_markup=user_main_keyboard(admin_flag))
