# ========== games_handlers.py ==========
import asyncio
import random
import logging
from datetime import datetime, timedelta

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from core import (
    dp, bot, db_pool,
    get_setting,
    is_banned, is_admin,
    get_user_balance, update_user_balance,
    get_user_reputation, update_user_reputation,
    add_exp,
    check_subscription,
    generate_game_id, calculate_hand_value, create_deck,
    safe_send_message,
    notify_chats,
    # Клавиатуры
    user_main_keyboard, back_keyboard, subscription_inline,
    room_control_keyboard, room_action_keyboard, leave_room_keyboard,
    # Состояния
    CasinoBet, DiceBet, GuessBet,
    MultiplayerGame, RoomChat,
    # Константы
    ITEMS_PER_PAGE, BIG_WIN_THRESHOLD,
    MIN_PLAYERS, MAX_PLAYERS, MIN_BET,
    # Фразы
    CASINO_WIN_PHRASES, CASINO_LOSE_PHRASES,
    DICE_WIN_PHRASES, DICE_LOSE_PHRASES,
    GUESS_WIN_PHRASES, GUESS_LOSE_PHRASES,
    CHAT_WIN_PHRASES,
)
from utils import get_random_phrase

# ===== КОСТИ =====
@dp.message_handler(Command("dice"))
async def cmd_dice(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    await message.answer("🎲 Введи сумму ставки (целое число):", reply_markup=back_keyboard())
    await DiceBet.amount.set()

@dp.message_handler(state=DiceBet.amount)
async def dice_bet_amount(message: types.Message, state: FSMContext):
    if message.chat.type != 'private':
        await state.finish()
        return
    if message.text == "◀️ Назад":
        await state.finish()
        await message.answer("Главное меню:", reply_markup=user_main_keyboard(await is_admin(message.from_user.id)))
        return
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return
    if amount <= 0:
        await message.answer("❌ Ставка должна быть положительной.")
        return
    user_id = message.from_user.id
    balance = await get_user_balance(user_id)
    if amount > balance:
        await message.answer("❌ Недостаточно монет.")
        await state.finish()
        return

    dice1 = random.randint(1, 6)
    dice2 = random.randint(1, 6)
    total = dice1 + dice2
    multiplier = int(await get_setting("dice_multiplier"))

    if total > 7:
        profit = amount * multiplier
        await update_user_balance(user_id, profit)
        phrase = get_random_phrase(DICE_WIN_PHRASES, dice1=dice1, dice2=dice2, total=total, profit=profit)
        exp = int(await get_setting("exp_per_dice_win"))
        await add_exp(user_id, exp)
        exp_text = f" +{exp} опыта"
    else:
        await update_user_balance(user_id, -amount)
        phrase = get_random_phrase(DICE_LOSE_PHRASES, dice1=dice1, dice2=dice2, total=total, loss=amount)
        exp = int(await get_setting("exp_per_dice_lose"))
        await add_exp(user_id, exp)
        exp_text = f" +{exp} опыта"

    new_balance = await get_user_balance(user_id)
    await message.answer(f"{phrase}\n💰 Баланс: {new_balance}{exp_text}")
    await state.finish()

# ===== УГАДАЙ ЧИСЛО =====
@dp.message_handler(Command("guess"))
async def cmd_guess(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    await message.answer("🔢 Введи сумму ставки (целое число):", reply_markup=back_keyboard())
    await GuessBet.amount.set()

@dp.message_handler(state=GuessBet.amount)
async def guess_bet_amount(message: types.Message, state: FSMContext):
    if message.chat.type != 'private':
        await state.finish()
        return
    if message.text == "◀️ Назад":
        await state.finish()
        await message.answer("Главное меню:", reply_markup=user_main_keyboard(await is_admin(message.from_user.id)))
        return
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("❌ Введите целое число.")
        return
    if amount <= 0:
        await message.answer("❌ Ставка должна быть положительной.")
        return
    user_id = message.from_user.id
    balance = await get_user_balance(user_id)
    if amount > balance:
        await message.answer("❌ Недостаточно монет.")
        await state.finish()
        return
    await state.update_data(amount=amount)
    await message.answer("🔢 Загадай число от 1 до 5:", reply_markup=back_keyboard())
    await GuessBet.number.set()

@dp.message_handler(state=GuessBet.number)
async def guess_bet_number(message: types.Message, state: FSMContext):
    if message.chat.type != 'private':
        await state.finish()
        return
    if message.text == "◀️ Назад":
        await state.finish()
        await message.answer("Главное меню:", reply_markup=user_main_keyboard(await is_admin(message.from_user.id)))
        return
    try:
        guess = int(message.text)
        if guess < 1 or guess > 5:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите число от 1 до 5.")
        return
    data = await state.get_data()
    amount = data['amount']
    user_id = message.from_user.id

    secret = random.randint(1, 5)
    multiplier = int(await get_setting("guess_multiplier"))
    rep_reward = int(await get_setting("guess_reputation"))

    if guess == secret:
        profit = amount * multiplier
        await update_user_balance(user_id, profit)
        await update_user_reputation(user_id, rep_reward)
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET guess_wins = guess_wins + 1 WHERE user_id=$1", user_id)
        phrase = get_random_phrase(GUESS_WIN_PHRASES, secret=secret, profit=profit, rep=rep_reward)
        exp = int(await get_setting("exp_per_guess_win"))
        await add_exp(user_id, exp)
        exp_text = f" +{exp} опыта"
    else:
        await update_user_balance(user_id, -amount)
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET guess_losses = guess_losses + 1 WHERE user_id=$1", user_id)
        phrase = get_random_phrase(GUESS_LOSE_PHRASES, secret=secret, loss=amount)
        exp = int(await get_setting("exp_per_guess_lose"))
        await add_exp(user_id, exp)
        exp_text = f" +{exp} опыта"

    new_balance = await get_user_balance(user_id)
    new_rep = await get_user_reputation(user_id)
    await message.answer(f"{phrase}\n💰 Баланс: {new_balance}\n⭐️ Репутация: {new_rep}{exp_text}")
    await state.finish()

# ===== МУЛЬТИПЛЕЕР 21 =====
# (весь код из предыдущих версий, адаптированный под новые core и utils)

@dp.message_handler(Command("21"))
async def multiplayer_main(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    await message.answer("🎮 Мультиплеер 21 – выбери действие:", reply_markup=room_menu_keyboard())

@dp.message_handler(Command("21_rules"))
async def game_rules(message: types.Message):
    rules = """
🎯 **Правила игры "21" (мультиплеер):**
• Каждый игрок делает ставку (от 3 монет).
• Цель – набрать сумму очков как можно ближе к 21, но не больше.
• Карты: 2–10 по номиналу, J/Q/K – 10 очков, Туз – 11 или 1.
• Игроки ходят по очереди: можно взять ещё карту ("Ещё") или остановиться ("Хватит").
• Доступна опция **"Удвоить"** – увеличить ставку вдвое и взять ровно одну карту (доступно только на первом ходу).
• Дилер добирает до 17 очков.
• Победитель забирает банк за вычетом комиссии (1 монета с игрока).
• В случае ничьей ставка возвращается.
• Создатель комнаты может начать игру при наличии от 2 до 5 игроков.
• До начала игры можно выйти без потери монет.
• Во время игры выход или сдача приводят к проигрышу ставки.
    """
    await message.answer(rules)

@dp.message_handler(Command("21_top"))
async def game_top(message: types.Message):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT first_name, game_wins FROM users WHERE game_wins > 0 ORDER BY game_wins DESC LIMIT 10")
    if not rows:
        await message.answer("🏆 Топ пока пуст.")
        return
    text = "🏆 **Лучшие игроки в 21:**\n\n"
    for i, row in enumerate(rows, 1):
        text += f"{i}. {row['first_name']} – {row['game_wins']} побед\n"
    await message.answer(text)

@dp.message_handler(Command("rooms"))
async def list_rooms(message: types.Message):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT game_id, host_id, max_players, bet_amount,
                   (SELECT COUNT(*) FROM game_players WHERE game_id = g.game_id) as player_count
            FROM multiplayer_games g
            WHERE status = 'waiting'
            ORDER BY created_at
        """)
    if not rows:
        await message.answer("📭 Нет открытых комнат. Создай свою!")
        return
    text = "📋 **Открытые комнаты:**\n\n"
    kb = []
    for row in rows:
        game_id = row['game_id']
        max_pl = row['max_players']
        cur_pl = row['player_count']
        bet = row['bet_amount']
        text += f"🆔 `{game_id}` | {cur_pl}/{max_pl} игр. | 💰 {bet} монет\n"
        kb.append([InlineKeyboardButton(text=f"Присоединиться к {game_id}", callback_data=f"join_room_{game_id}")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query_handler(lambda c: c.data.startswith("join_room_"))
async def join_room_callback(callback: types.CallbackQuery):
    game_id = callback.data.replace("join_room_", "")
    user_id = callback.from_user.id
    username = callback.from_user.username or "NoName"
    async with db_pool.acquire() as conn:
        game = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1 AND status='waiting'", game_id)
        if not game:
            await callback.answer("❌ Комната не найдена или игра уже началась.", show_alert=True)
            return
        players = await conn.fetch("SELECT user_id FROM game_players WHERE game_id=$1", game_id)
        if len(players) >= game['max_players']:
            await callback.answer("❌ Комната уже заполнена.", show_alert=True)
            return
        existing = await conn.fetchval("SELECT 1 FROM game_players WHERE game_id=$1 AND user_id=$2", game_id, user_id)
        if existing:
            await callback.answer("❌ Ты уже в этой комнате.", show_alert=True)
            return
        balance = await get_user_balance(user_id)
        bet = game['bet_amount']
        if balance < bet:
            await callback.answer(f"❌ Недостаточно монет. Нужно {bet}", show_alert=True)
            return
        await conn.execute(
            "INSERT INTO game_players (game_id, user_id, username, cards, value, stopped, joined_at, doubled, surrendered) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
            game_id, user_id, username, '', 0, False, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), False, False
        )
        host_id = game['host_id']
        if host_id != user_id:
            await safe_send_message(host_id, f"✅ @{username} присоединился к твоей комнате `{game_id}`.")
    await callback.message.edit_text(f"✅ Ты присоединился к комнате `{game_id}`. Ожидаем остальных...")
    await callback.message.answer("Ты в комнате. Можешь выйти в любой момент до начала игры.", reply_markup=leave_room_keyboard(game_id))
    await callback.answer()

@dp.message_handler(Command("create_room"))
async def create_room_start(message: types.Message):
    async with db_pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM multiplayer_games WHERE status='waiting'")
    if count >= MAX_ROOMS:
        await message.answer(f"❌ Достигнут лимит активных комнат ({MAX_ROOMS}). Попробуй позже.")
        return
    await message.answer("Введи количество игроков (2–5):", reply_markup=back_keyboard())
    await MultiplayerGame.create_max_players.set()

@dp.message_handler(state=MultiplayerGame.create_max_players)
async def create_room_max_players(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await multiplayer_main(message)
        return
    try:
        max_players = int(message.text)
        if max_players < MIN_PLAYERS or max_players > MAX_PLAYERS:
            raise ValueError
    except:
        await message.answer(f"❌ Введи число от {MIN_PLAYERS} до {MAX_PLAYERS}.")
        return
    await state.update_data(max_players=max_players)
    await message.answer(f"Введи ставку (целое число, не меньше {MIN_BET}):")
    await MultiplayerGame.create_bet.set()

@dp.message_handler(state=MultiplayerGame.create_bet)
async def create_room_bet(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await multiplayer_main(message)
        return
    try:
        bet = int(message.text)
        if bet < MIN_BET:
            raise ValueError
    except:
        await message.answer(f"❌ Введи целое число не меньше {MIN_BET}.")
        return
    data = await state.get_data()
    max_players = data['max_players']
    user_id = message.from_user.id
    balance = await get_user_balance(user_id)
    if balance < bet:
        await message.answer(f"❌ У тебя недостаточно монет. Нужно {bet}")
        await state.finish()
        return
    game_id = generate_game_id()
    async with db_pool.acquire() as conn:
        existing = await conn.fetchval("SELECT game_id FROM multiplayer_games WHERE game_id=$1", game_id)
        while existing:
            game_id = generate_game_id()
            existing = await conn.fetchval("SELECT game_id FROM multiplayer_games WHERE game_id=$1", game_id)
        await conn.execute(
            "INSERT INTO multiplayer_games (game_id, host_id, max_players, bet_amount, status, created_at, current_player_index) VALUES ($1, $2, $3, $4, $5, $6, $7)",
            game_id, user_id, max_players, bet, 'waiting', datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0
        )
        await conn.execute(
            "INSERT INTO game_players (game_id, user_id, username, cards, value, stopped, joined_at, doubled, surrendered) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
            game_id, user_id, message.from_user.username or "NoName", '', 0, False, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), False, False
        )
    await state.finish()
    await message.answer(
        f"✅ Комната `{game_id}` создана!\n"
        f"👥 Игроков: 1/{max_players}\n"
        f"💰 Ставка: {bet} монет\n\n"
        f"Ты можешь запустить игру, когда наберётся не менее {MIN_PLAYERS} игроков.",
        reply_markup=room_control_keyboard(game_id)
    )

@dp.callback_query_handler(lambda c: c.data.startswith("close_room_"))
async def close_room_callback(callback: types.CallbackQuery):
    game_id = callback.data.replace("close_room_", "")
    user_id = callback.from_user.id
    async with db_pool.acquire() as conn:
        game = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1 AND status='waiting'", game_id)
        if not game:
            await callback.answer("❌ Комната не найдена или игра уже началась.", show_alert=True)
            return
        if game['host_id'] != user_id:
            await callback.answer("❌ Только создатель может закрыть комнату.", show_alert=True)
            return
        await conn.execute("DELETE FROM game_players WHERE game_id=$1", game_id)
        await conn.execute("DELETE FROM multiplayer_games WHERE game_id=$1", game_id)
    await callback.message.edit_text("🏁 Комната закрыта.")
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("leave_room_"))
async def leave_room_callback(callback: types.CallbackQuery):
    game_id = callback.data.replace("leave_room_", "")
    user_id = callback.from_user.id
    async with db_pool.acquire() as conn:
        game = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1", game_id)
        if not game:
            await callback.answer("❌ Комната не найдена.", show_alert=True)
            return
        if game['status'] == 'waiting':
            await conn.execute("DELETE FROM game_players WHERE game_id=$1 AND user_id=$2", game_id, user_id)
            if game['host_id'] == user_id:
                next_host = await conn.fetchval("SELECT user_id FROM game_players WHERE game_id=$1 ORDER BY joined_at LIMIT 1", game_id)
                if next_host:
                    await conn.execute("UPDATE multiplayer_games SET host_id=$1 WHERE game_id=$2", next_host, game_id)
                    await safe_send_message(next_host, f"🎮 Ты стал создателем комнаты `{game_id}`.")
                else:
                    await conn.execute("DELETE FROM multiplayer_games WHERE game_id=$1", game_id)
            await callback.message.edit_text("❌ Ты покинул комнату.")
        else:
            bet = game['bet_amount']
            player = await conn.fetchrow("SELECT doubled, surrendered FROM game_players WHERE game_id=$1 AND user_id=$2", game_id, user_id)
            if player and player['doubled']:
                bet *= 2
            if player and not player['surrendered']:
                await update_user_balance(user_id, -bet, conn=conn)
            await conn.execute("UPDATE game_players SET stopped=TRUE WHERE game_id=$1 AND user_id=$2", game_id, user_id)
            await callback.message.edit_text(f"❌ Ты покинул игру и потерял {bet} монет.")
            active = await conn.fetchval("SELECT COUNT(*) FROM game_players WHERE game_id=$1 AND user_id != 0 AND stopped = FALSE", game_id)
            if active == 0:
                await dealer_turn(game_id)
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("start_game_"))
async def start_game_callback(callback: types.CallbackQuery):
    game_id = callback.data.replace("start_game_", "")
    user_id = callback.from_user.id
    async with db_pool.acquire() as conn:
        game = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1 AND status='waiting'", game_id)
        if not game:
            await callback.answer("❌ Комната не найдена или игра уже началась.", show_alert=True)
            return
        if game['host_id'] != user_id:
            await callback.answer("❌ Только создатель комнаты может начать игру.", show_alert=True)
            return
        players = await conn.fetch("SELECT user_id FROM game_players WHERE game_id=$1", game_id)
        if len(players) < MIN_PLAYERS:
            await callback.answer(f"❌ Недостаточно игроков. Нужно минимум {MIN_PLAYERS}.", show_alert=True)
            return
        await conn.execute("UPDATE multiplayer_games SET status='playing' WHERE game_id=$1", game_id)
        deck = create_deck()
        # Списать ставки у всех игроков
        bet = game['bet_amount']
        for player in players:
            await update_user_balance(player['user_id'], -bet, conn=conn)
        for player in players:
            cards = [deck.pop(), deck.pop()]
            cards_str = ','.join(cards)
            value = calculate_hand_value(cards)
            await conn.execute(
                "UPDATE game_players SET cards=$1, value=$2 WHERE game_id=$3 AND user_id=$4",
                cards_str, value, game_id, player['user_id']
            )
        # Добавляем дилера
        await conn.execute(
            "INSERT INTO game_players (game_id, user_id, username, cards, value, stopped, joined_at, doubled, surrendered) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
            game_id, 0, 'Дилер', '', 0, False, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), False, False
        )
        await conn.execute("UPDATE multiplayer_games SET deck=$1 WHERE game_id=$2", ','.join(deck), game_id)
        # Устанавливаем текущего игрока
        await conn.execute("UPDATE multiplayer_games SET current_player_index=0 WHERE game_id=$1", game_id)
    for player in players:
        await safe_send_message(player['user_id'], f"🎮 Игра в комнате `{game_id}` началась! Твой ход.")
    await process_next_turn(game_id)

async def process_next_turn(game_id: str):
    async with db_pool.acquire() as conn:
        game = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1", game_id)
        if not game or game['status'] != 'playing':
            return
        players = await conn.fetch("SELECT * FROM game_players WHERE game_id=$1 AND user_id != 0 AND stopped = FALSE ORDER BY joined_at", game_id)
        current_index = game['current_player_index']
        if current_index >= len(players):
            await dealer_turn(game_id)
            return
        current_player = players[current_index]
        cards = current_player['cards'].split(',') if current_player['cards'] else []
        value = calculate_hand_value(cards)
        can_double = len(cards) == 2 and not current_player['doubled']
        kb = room_action_keyboard(game_id, can_double)
        await safe_send_message(
            current_player['user_id'],
            f"🎮 Твой ход!\nТвои карты: {', '.join(cards)} (очков: {value})\n\nВыбери действие:",
            reply_markup=kb
        )

@dp.callback_query_handler(lambda c: c.data in ["room_hit", "room_stand", "room_double", "room_surrender", "room_chat"])
async def room_action_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    async with db_pool.acquire() as conn:
        # Найдём игру, в которой сейчас ход этого игрока
        game = await conn.fetchrow("""
            SELECT g.* FROM multiplayer_games g
            JOIN game_players p ON g.game_id = p.game_id
            WHERE p.user_id=$1 AND g.status='playing' AND p.stopped=FALSE
        """, user_id)
        if not game:
            await callback.answer("❌ Сейчас не твой ход или игра не активна.", show_alert=True)
            return
        game_id = game['game_id']
        # Проверим, что это действительно текущий игрок
        players = await conn.fetch("SELECT * FROM game_players WHERE game_id=$1 AND user_id != 0 AND stopped = FALSE ORDER BY joined_at", game_id)
        current_index = game['current_player_index']
        if current_index >= len(players) or players[current_index]['user_id'] != user_id:
            await callback.answer("❌ Сейчас не твой ход.", show_alert=True)
            return
        current_player = players[current_index]
        deck = game['deck'].split(',') if game['deck'] else []
        cards = current_player['cards'].split(',') if current_player['cards'] else []
        value = calculate_hand_value(cards)

        if callback.data == "room_hit":
            if not deck:
                await callback.answer("Колода кончилась, передаём ход...", show_alert=True)
                await conn.execute("UPDATE game_players SET stopped=TRUE WHERE game_id=$1 AND user_id=$2", game_id, user_id)
                await callback.answer()
                active = await conn.fetchval("SELECT COUNT(*) FROM game_players WHERE game_id=$1 AND user_id != 0 AND stopped = FALSE", game_id)
                if active == 0:
                    await dealer_turn(game_id)
                else:
                    await conn.execute("UPDATE multiplayer_games SET current_player_index = current_player_index + 1 WHERE game_id=$1", game_id)
                    await process_next_turn(game_id)
                return
            new_card = deck.pop()
            cards.append(new_card)
            value = calculate_hand_value(cards)
            await conn.execute(
                "UPDATE game_players SET cards=$1, value=$2 WHERE game_id=$3 AND user_id=$4",
                ','.join(cards), value, game_id, user_id
            )
            await conn.execute("UPDATE multiplayer_games SET deck=$1 WHERE game_id=$2", ','.join(deck), game_id)
            if value > 21:
                await conn.execute("UPDATE game_players SET stopped=TRUE WHERE game_id=$1 AND user_id=$2", game_id, user_id)
                await callback.message.edit_text(f"💥 Перебор! Твои карты: {', '.join(cards)} (очков: {value})\nТы проиграл свою ставку.")
                await callback.answer()
                active = await conn.fetchval("SELECT COUNT(*) FROM game_players WHERE game_id=$1 AND user_id != 0 AND stopped = FALSE", game_id)
                if active == 0:
                    await dealer_turn(game_id)
                else:
                    await conn.execute("UPDATE multiplayer_games SET current_player_index = current_player_index + 1 WHERE game_id=$1", game_id)
                    await process_next_turn(game_id)
                return
            else:
                can_double = len(cards) == 2 and not current_player['doubled']
                kb = room_action_keyboard(game_id, can_double)
                await callback.message.edit_text(
                    f"Твои карты: {', '.join(cards)} (очков: {value})\nВыбери действие:",
                    reply_markup=kb
                )
                await callback.answer()
            return

        elif callback.data == "room_stand":
            await conn.execute("UPDATE game_players SET stopped=TRUE WHERE game_id=$1 AND user_id=$2", game_id, user_id)
            await callback.message.edit_text(f"✅ Ты остановился на {value} очках.")
            await callback.answer()
            active = await conn.fetchval("SELECT COUNT(*) FROM game_players WHERE game_id=$1 AND user_id != 0 AND stopped = FALSE", game_id)
            if active == 0:
                await dealer_turn(game_id)
            else:
                await conn.execute("UPDATE multiplayer_games SET current_player_index = current_player_index + 1 WHERE game_id=$1", game_id)
                await process_next_turn(game_id)
            return

        elif callback.data == "room_double":
            if len(cards) != 2 or current_player['doubled']:
                await callback.answer("❌ Удвоение сейчас недоступно.", show_alert=True)
                return
            bet = game['bet_amount']
            balance = await get_user_balance(user_id)
            if balance < bet:
                await callback.answer("❌ Недостаточно монет для удвоения.", show_alert=True)
                return
            # Удваиваем ставку (списываем ещё одну ставку)
            await update_user_balance(user_id, -bet, conn=conn)
            await conn.execute("UPDATE game_players SET doubled=TRUE WHERE game_id=$1 AND user_id=$2", game_id, user_id)
            if not deck:
                await callback.answer("Колода кончилась, удвоение невозможно.", show_alert=True)
                return
            new_card = deck.pop()
            cards.append(new_card)
            value = calculate_hand_value(cards)
            await conn.execute(
                "UPDATE game_players SET cards=$1, value=$2, stopped=TRUE WHERE game_id=$3 AND user_id=$4",
                ','.join(cards), value, game_id, user_id
            )
            await conn.execute("UPDATE multiplayer_games SET deck=$1 WHERE game_id=$2", ','.join(deck), game_id)
            if value > 21:
                await callback.message.edit_text(f"💥 Перебор! Твои карты: {', '.join(cards)} (очков: {value})\nТы проиграл удвоенную ставку.")
            else:
                await callback.message.edit_text(f"💰 Ты удвоил ставку и взял карту {new_card}. Остановился на {value} очках.")
            await callback.answer()
            active = await conn.fetchval("SELECT COUNT(*) FROM game_players WHERE game_id=$1 AND user_id != 0 AND stopped = FALSE", game_id)
            if active == 0:
                await dealer_turn(game_id)
            else:
                await conn.execute("UPDATE multiplayer_games SET current_player_index = current_player_index + 1 WHERE game_id=$1", game_id)
                await process_next_turn(game_id)
            return

        elif callback.data == "room_surrender":
            bet = game['bet_amount']
            effective_bet = bet * 2 if current_player['doubled'] else bet
            loss = effective_bet // 2
            # Сдавшийся теряет половину ставки
            await update_user_balance(user_id, -loss, conn=conn)
            await conn.execute("UPDATE game_players SET stopped=TRUE, surrendered=TRUE WHERE game_id=$1 AND user_id=$2", game_id, user_id)
            await callback.message.edit_text(f"🏳️ Ты сдался и потерял {loss} монет.")
            await callback.answer()
            active = await conn.fetchval("SELECT COUNT(*) FROM game_players WHERE game_id=$1 AND user_id != 0 AND stopped = FALSE", game_id)
            if active == 0:
                await dealer_turn(game_id)
            else:
                await conn.execute("UPDATE multiplayer_games SET current_player_index = current_player_index + 1 WHERE game_id=$1", game_id)
                await process_next_turn(game_id)
            return

        elif callback.data == "room_chat":
            await callback.message.answer("Введи сообщение для всех в комнате (или /cancel для отмены):")
            await RoomChat.message.set()
            await callback.answer()

@dp.message_handler(state=RoomChat.message)
async def room_chat_message(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.finish()
        await message.answer("Отправка отменена.")
        return
    user_id = message.from_user.id
    async with db_pool.acquire() as conn:
        # Найдём активную игру, где участвует пользователь
        game = await conn.fetchrow("""
            SELECT g.game_id FROM multiplayer_games g
            JOIN game_players p ON g.game_id = p.game_id
            WHERE p.user_id=$1 AND g.status='playing'
        """, user_id)
        if not game:
            await state.finish()
            await message.answer("❌ Ты не участвуешь в активной игре.")
            return
        game_id = game['game_id']
        players = await conn.fetch("SELECT user_id FROM game_players WHERE game_id=$1 AND user_id != 0 AND user_id != $2", game_id, user_id)
        for player in players:
            await safe_send_message(player['user_id'], f"💬 {message.from_user.first_name}: {message.text}")
    await state.finish()
    await message.answer("✅ Сообщение отправлено всем игрокам в комнате.")

async def dealer_turn(game_id: str):
    async with db_pool.acquire() as conn:
        game = await conn.fetchrow("SELECT * FROM multiplayer_games WHERE game_id=$1", game_id)
        if not game or game['status'] != 'playing':
            return
        deck = game['deck'].split(',') if game['deck'] else []
        dealer = await conn.fetchrow("SELECT * FROM game_players WHERE game_id=$1 AND user_id=0", game_id)
        if dealer:
            dealer_cards = dealer['cards'].split(',') if dealer['cards'] else []
            dealer_value = dealer['value']
        else:
            dealer_cards = []
            dealer_value = 0
        while dealer_value < 17 and deck:
            new_card = deck.pop()
            dealer_cards.append(new_card)
            dealer_value = calculate_hand_value(dealer_cards)
            await conn.execute(
                "UPDATE game_players SET cards=$1, value=$2 WHERE game_id=$3 AND user_id=0",
                ','.join(dealer_cards), dealer_value, game_id
            )
            await conn.execute("UPDATE multiplayer_games SET deck=$1 WHERE game_id=$2", ','.join(deck), game_id)
        # Учитываем всех игроков, кроме дилера (включая сдавшихся)
        players = await conn.fetch("SELECT * FROM game_players WHERE game_id=$1 AND user_id != 0", game_id)
        bet = game['bet_amount']
        results = []
        for player in players:
            user_id = player['user_id']
            player_value = player['value']
            doubled = player['doubled']
            effective_bet = bet * 2 if doubled else bet
            if player['surrendered']:
                # Сдавшиеся уже получили результат (потеряли половину)
                results.append((user_id, f"🏳️ Сдался, потеряно {effective_bet//2}", 0))
                continue
            if player_value > 21:
                # Уже проиграл (ставка списана при переборе)
                results.append((user_id, f"❌ Проигрыш (перебор) -{effective_bet}", 0))
            elif dealer_value > 21:
                win = effective_bet - 1
                await update_user_balance(user_id, win, conn=conn)
                await conn.execute("UPDATE users SET game_wins = game_wins + 1 WHERE user_id=$1", user_id)
                exp = int(await get_setting("exp_per_game_win"))
                await add_exp(user_id, exp, conn=conn)
                results.append((user_id, f"✅ Выигрыш +{win}", win))
            elif player_value > dealer_value:
                win = effective_bet - 1
                await update_user_balance(user_id, win, conn=conn)
                await conn.execute("UPDATE users SET game_wins = game_wins + 1 WHERE user_id=$1", user_id)
                exp = int(await get_setting("exp_per_game_win"))
                await add_exp(user_id, exp, conn=conn)
                results.append((user_id, f"✅ Выигрыш +{win}", win))
            elif player_value < dealer_value:
                results.append((user_id, f"❌ Проигрыш -{effective_bet}", 0))
            else:
                # Ничья – возврат ставки
                await update_user_balance(user_id, effective_bet, conn=conn)
                results.append((user_id, f"🤝 Ничья (возврат ставки)", effective_bet))
        dealer_cards_str = ', '.join(dealer_cards) if dealer_cards else 'нет карт'
        for user_id, res, _ in results:
            await safe_send_message(user_id,
                f"🎮 Итоги игры в комнате `{game_id}`:\n"
                f"Карты дилера: {dealer_cards_str} (очков: {dealer_value})\n"
                f"Результат: {res}"
            )
        await conn.execute("DELETE FROM game_players WHERE game_id=$1", game_id)
        await conn.execute("DELETE FROM multiplayer_games WHERE game_id=$1", game_id)

# ===== КАЗИНО (НОВОЕ) =====
class CasinoGame(StatesGroup):
    choice = State()
    amount = State()
    number = State()  # для рулетки

@dp.message_handler(Command("casino"))
async def cmd_casino(message: types.Message):
    if message.chat.type != 'private':
        return
    user_id = message.from_user.id
    if await is_banned(user_id) and not await is_admin(user_id):
        return
    ok, not_subscribed = await check_subscription(user_id)
    if not ok:
        await message.answer("❗️ Сначала подпишись на каналы.", reply_markup=subscription_inline(not_subscribed))
        return
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎰 Классика", callback_data="casino_classic"),
        InlineKeyboardButton("🎲 Рулетка", callback_data="casino_roulette"),
        InlineKeyboardButton("🍒 Слоты", callback_data="casino_slots"),
        InlineKeyboardButton("❌ Отмена", callback_data="casino_cancel")
    )
    await message.answer("Выбери режим казино:", reply_markup=kb)
    await CasinoGame.choice.set()

@dp.callback_query_handler(state=CasinoGame.choice)
async def casino_choice(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "casino_cancel":
        await state.finish()
        await callback.message.delete()
        await callback.answer()
        return
    await state.update_data(mode=callback.data.split("_")[1])
    await callback.message.edit_text("Введи сумму ставки (целое число):")
    await CasinoGame.amount.set()
    await callback.answer()

@dp.message_handler(state=CasinoGame.amount)
async def casino_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи положительное целое число.")
        return
    data = await state.get_data()
    mode = data['mode']
    user_id = message.from_user.id
    balance = await get_user_balance(user_id)
    if amount > balance:
        await message.answer("❌ Недостаточно монет.")
        await state.finish()
        return
    await state.update_data(amount=amount)
    if mode == "roulette":
        await message.answer("Введи число от 1 до 36 (или 0 для зеро):")
        await CasinoGame.number.set()
    else:
        await process_casino(message, state, mode, amount, user_id)

@dp.message_handler(state=CasinoGame.number)
async def casino_number(message: types.Message, state: FSMContext):
    try:
        number = int(message.text)
        if number < 0 or number > 36:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи число от 0 до 36.")
        return
    data = await state.get_data()
    amount = data['amount']
    user_id = message.from_user.id
    await process_casino(message, state, "roulette", amount, user_id, number)

async def process_casino(message: types.Message, state: FSMContext, mode: str, amount: int, user_id: int, number: int = None):
    win_chance_base = int(await get_setting("casino_win_chance"))  # в процентах
    if mode == "classic":
        win = random.randint(1, 100) <= win_chance_base
        if win:
            profit = amount
            win_amount = amount * 2
        else:
            profit = -amount
            win_amount = amount
    elif mode == "roulette":
        # Рулетка: угадать число – множитель 36, шанс 1/37
        secret = random.randint(0, 36)
        if secret == number:
            profit = amount * 36
            win = True
        else:
            profit = -amount
            win = False
    else:  # slots
        # Слоты: три барабана, выигрыш при совпадении
        reel1 = random.choice(["🍒", "🍋", "🍊", "7️⃣", "💎"])
        reel2 = random.choice(["🍒", "🍋", "🍊", "7️⃣", "💎"])
        reel3 = random.choice(["🍒", "🍋", "🍊", "7️⃣", "💎"])
        if reel1 == reel2 == reel3:
            if reel1 == "7️⃣":
                profit = amount * 10
            elif reel1 == "💎":
                profit = amount * 5
            else:
                profit = amount * 3
            win = True
        else:
            profit = -amount
            win = False
        await message.answer(f"🎰 | {reel1} | {reel2} | {reel3} |")

    if win:
        await update_user_balance(user_id, profit)
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET casino_wins = casino_wins + 1 WHERE user_id=$1", user_id)
        exp = int(await get_setting("exp_per_casino_win"))
        await add_exp(user_id, exp)
        if mode == "classic":
            phrase = get_random_phrase(CASINO_WIN_PHRASES, win=amount*2, profit=profit)
        else:
            phrase = f"🎉 Ты выиграл {profit} монет!"
        # Уведомление в чаты, если большой выигрыш
        if profit >= BIG_WIN_THRESHOLD and await get_setting("chat_notify_big_win") == "1":
            user = message.from_user
            chat_phrase = get_random_phrase(CHAT_WIN_PHRASES, name=user.first_name, amount=profit)
            await notify_chats(chat_phrase)
    else:
        await update_user_balance(user_id, -amount)
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET casino_losses = casino_losses + 1 WHERE user_id=$1", user_id)
        exp = int(await get_setting("exp_per_casino_lose"))
        await add_exp(user_id, exp)
        if mode == "classic":
            phrase = get_random_phrase(CASINO_LOSE_PHRASES, loss=amount)
        else:
            phrase = f"😢 Ты проиграл {amount} монет."

    new_balance = await get_user_balance(user_id)
    await message.answer(f"{phrase}\n💰 Баланс: {new_balance}")
    await state.finish()
