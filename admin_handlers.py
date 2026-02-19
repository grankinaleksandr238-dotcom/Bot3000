# ========== admin_handlers.py ==========
import asyncio
import logging
import csv
import io
from datetime import datetime, timedelta

from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import BotBlocked, UserDeactivated, ChatNotFound, RetryAfter

from core import (
    dp, bot, db_pool,
    get_setting, set_setting,
    is_banned, is_admin, is_super_admin,
    get_user_balance, update_user_balance,
    get_user_reputation, update_user_reputation,
    get_user_stats, update_user_stats,
    add_exp, get_user_level, get_user_exp,
    find_user_by_input,
    is_chat_confirmed, get_confirmed_chats,
    safe_send_message,
    create_chat_confirmation_request,
    get_pending_chat_requests, update_chat_request_status,
    add_confirmed_chat, remove_confirmed_chat,
    spawn_boss,
    check_subscription,
    # Клавиатуры
    admin_main_keyboard, admin_users_keyboard, admin_shop_keyboard,
    admin_giveaway_keyboard, admin_channel_keyboard, admin_promo_keyboard,
    admin_tasks_keyboard, admin_ban_keyboard, admin_admins_keyboard,
    admin_chats_keyboard, admin_boss_keyboard, admin_helper_keyboard,
    admin_auction_keyboard, admin_ad_keyboard,
    settings_reply_keyboard, back_keyboard,
    purchase_action_keyboard, confirm_chat_inline,
    # Состояния
    AddBalance, RemoveBalance, AddReputation, RemoveReputation,
    AddExp, SetLevel, FindUser, AddJuniorAdmin, RemoveJuniorAdmin,
    CreateGiveaway, CompleteGiveaway,
    AddChannel, RemoveChannel,
    CreatePromocode,
    AddShopItem, RemoveShopItem, EditShopItem,
    CreateTask, DeleteTask,
    BlockUser, UnblockUser,
    ManageChats, BossSpawn,
    CreateAuction, CancelAuction,
    CreateAd, EditSettings,
    Broadcast,
)
from utils import export_users_to_csv, export_table_to_csv, get_random_phrase

# ===== ВХОД В АДМИН-ПАНЕЛЬ =====
@dp.message_handler(lambda message: message.text == "⚙️ Админ панель")
async def admin_panel(message: types.Message):
    if message.chat.type != 'private':
        return
    if not await is_admin(message.from_user.id):
        await message.answer("У тебя нет прав администратора.")
        return
    super_admin = await is_super_admin(message.from_user.id)
    await message.answer("Панель администратора:", reply_markup=admin_main_keyboard(super_admin))

# ===== УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ =====
@dp.message_handler(lambda message: message.text == "👥 Управление пользователями")
async def admin_users_menu(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    await message.answer("Управление пользователями:", reply_markup=admin_users_keyboard())

@dp.message_handler(lambda message: message.text == "💰 Начислить монеты")
async def add_balance_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может начислять монеты.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await AddBalance.user_id.set()

@dp.message_handler(state=AddBalance.user_id)
async def add_balance_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи сумму начисления (целое положительное число):")
    await AddBalance.amount.set()

@dp.message_handler(state=AddBalance.amount)
async def add_balance_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи положительное целое число.")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        await update_user_balance(uid, amount)
        await message.answer(f"✅ Пользователю {uid} начислено {amount} монет.")
        await safe_send_message(uid, f"💰 Вам начислено {amount} монет администратором.")
    except Exception as e:
        logging.error(f"Add balance error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "💸 Списать монеты")
async def remove_balance_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может списывать монеты.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await RemoveBalance.user_id.set()

@dp.message_handler(state=RemoveBalance.user_id)
async def remove_balance_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи сумму списания (целое положительное число):")
    await RemoveBalance.amount.set()

@dp.message_handler(state=RemoveBalance.amount)
async def remove_balance_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи положительное целое число.")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        await update_user_balance(uid, -amount)
        await message.answer(f"✅ У пользователя {uid} списано {amount} монет.")
        await safe_send_message(uid, f"💸 У тебя списано {amount} монет администратором.")
    except Exception as e:
        logging.error(f"Remove balance error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "⭐️ Начислить репутацию")
async def add_reputation_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может начислять репутацию.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await AddReputation.user_id.set()

@dp.message_handler(state=AddReputation.user_id)
async def add_reputation_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи количество репутации для начисления (целое число):")
    await AddReputation.amount.set()

@dp.message_handler(state=AddReputation.amount)
async def add_reputation_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("❌ Введи целое число.")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        await update_user_reputation(uid, amount)
        await message.answer(f"✅ Пользователю {uid} начислено {amount} репутации.")
        await safe_send_message(uid, f"⭐️ Вам начислено {amount} репутации администратором.")
    except Exception as e:
        logging.error(f"Add reputation error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "🔻 Снять репутацию")
async def remove_reputation_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может снимать репутацию.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await RemoveReputation.user_id.set()

@dp.message_handler(state=RemoveReputation.user_id)
async def remove_reputation_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи количество репутации для снятия (целое число):")
    await RemoveReputation.amount.set()

@dp.message_handler(state=RemoveReputation.amount)
async def remove_reputation_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("❌ Введи целое число.")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        await update_user_reputation(uid, -amount)
        await message.answer(f"✅ У пользователя {uid} снято {amount} репутации.")
        await safe_send_message(uid, f"🔻 У вас снято {amount} репутации администратором.")
    except Exception as e:
        logging.error(f"Remove reputation error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📈 Начислить опыт")
async def add_exp_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может начислять опыт.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await AddExp.user_id.set()

@dp.message_handler(state=AddExp.user_id)
async def add_exp_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи количество опыта для начисления (целое число):")
    await AddExp.amount.set()

@dp.message_handler(state=AddExp.amount)
async def add_exp_amount(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("❌ Введи целое число.")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        await add_exp(uid, amount)
        await message.answer(f"✅ Пользователю {uid} начислено {amount} опыта.")
    except Exception as e:
        logging.error(f"Add exp error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "🔝 Установить уровень")
async def set_level_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может устанавливать уровень.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await SetLevel.user_id.set()

@dp.message_handler(state=SetLevel.user_id)
async def set_level_user(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    await state.update_data(user_id=uid)
    await message.answer("Введи новый уровень (целое число ≥ 1):")
    await SetLevel.level.set()

@dp.message_handler(state=SetLevel.level)
async def set_level_value(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_users_menu(message)
        return
    try:
        level = int(message.text)
        if level < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи целое число ≥ 1.")
        return
    data = await state.get_data()
    uid = data['user_id']
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET level=$1 WHERE user_id=$2", level, uid)
        await message.answer(f"✅ Пользователю {uid} установлен уровень {level}.")
        await safe_send_message(uid, f"🔝 Ваш уровень изменён на {level} администратором.")
    except Exception as e:
        logging.error(f"Set level error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "👥 Найти пользователя")
async def find_user_start(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У тебя нет прав администратора.")
        return
    await message.answer("Введи ID или @username пользователя:", reply_markup=back_keyboard())
    await FindUser.query.set()

@dp.message_handler(state=FindUser.query)
async def find_user_result(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        super_admin = await is_super_admin(message.from_user.id)
        await message.answer("Панель администратора:", reply_markup=admin_main_keyboard(super_admin))
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    name = user_data['first_name']
    bal = user_data['balance']
    rep = user_data['reputation']
    spent = user_data['total_spent']
    joined = user_data['joined_date']
    attempts = user_data['theft_attempts']
    success = user_data['theft_success']
    failed = user_data['theft_failed']
    protected = user_data['theft_protected']
    level = user_data['level']
    exp = user_data['exp']
    strength = user_data['strength']
    agility = user_data['agility']
    defense = user_data['defense']
    banned = await is_banned(uid)
    ban_status = "⛔ Заблокирован" if banned else "✅ Активен"
    text = (
        f"👤 Пользователь: {name} (ID: {uid})\n"
        f"📊 Уровень: {level}, опыт: {exp}\n"
        f"💪 Сила: {strength} | 🏃 Ловкость: {agility} | 🛡 Защита: {defense}\n"
        f"💰 Баланс: {bal}\n"
        f"⭐️ Репутация: {rep}\n"
        f"💸 Потрачено: {spent}\n"
        f"📅 Регистрация: {joined}\n"
        f"🔫 Ограблений: {attempts} (успешно: {success}, провал: {failed})\n"
        f"⚔️ Отбито атак: {protected}\n"
        f"Статус: {ban_status}"
    )
    await message.answer(text)
    await state.finish()

@dp.message_handler(lambda message: message.text == "📊 Экспорт пользователей")
async def export_users(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может экспортировать пользователей.")
        return
    try:
        csv_data = await export_users_to_csv()
        if not csv_data:
            await message.answer("Нет пользователей для экспорта.")
            return
        await message.answer_document(
            types.InputFile(io.BytesIO(csv_data), filename="users.csv"),
            caption="📊 Список пользователей"
        )
    except Exception as e:
        logging.error(f"Export error: {e}")
        await message.answer("❌ Ошибка при экспорте.")

# ===== УПРАВЛЕНИЕ МАГАЗИНОМ =====
@dp.message_handler(lambda message: message.text == "🛒 Управление магазином")
async def admin_shop_menu(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может управлять магазином.")
        return
    await message.answer("Управление магазином:", reply_markup=admin_shop_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Добавить товар")
async def add_shop_item_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может добавлять товары.")
        return
    await message.answer("Введи название товара:", reply_markup=back_keyboard())
    await AddShopItem.name.set()

@dp.message_handler(state=AddShopItem.name)
async def add_shop_item_name(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    await state.update_data(name=message.text)
    await message.answer("Введи описание товара:")
    await AddShopItem.next()

@dp.message_handler(state=AddShopItem.description)
async def add_shop_item_description(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    await state.update_data(description=message.text)
    await message.answer("Введи цену (целое число):")
    await AddShopItem.next()

@dp.message_handler(state=AddShopItem.price)
async def add_shop_item_price(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    try:
        price = int(message.text)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Цена должна быть положительным целым числом.")
        return
    await state.update_data(price=price)
    await message.answer("Введи количество товара (целое число, -1 для бесконечного):")
    await AddShopItem.stock.set()

@dp.message_handler(state=AddShopItem.stock)
async def add_shop_item_stock(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    try:
        stock = int(message.text)
    except ValueError:
        await message.answer("❌ Введи целое число.")
        return
    data = await state.get_data()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO shop_items (name, description, price, stock) VALUES ($1, $2, $3, $4)",
                data['name'], data['description'], data['price'], stock
            )
        await message.answer("✅ Товар добавлен!", reply_markup=admin_shop_keyboard())
    except Exception as e:
        logging.error(f"Add shop item error: {e}")
        await message.answer("❌ Ошибка при добавлении товара.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "➖ Удалить товар")
async def remove_shop_item_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может удалять товары.")
        return
    try:
        async with db_pool.acquire() as conn:
            items = await conn.fetch("SELECT id, name FROM shop_items ORDER BY id")
        if not items:
            await message.answer("В магазине нет товаров.")
            return
        text = "Товары:\n" + "\n".join([f"ID {i['id']}: {i['name']}" for i in items])
        await message.answer(text + "\n\nВведи ID товара для удаления:", reply_markup=back_keyboard())
    except Exception as e:
        logging.error(f"List items for remove error: {e}")
        await message.answer("❌ Ошибка.")
        return
    await RemoveShopItem.item_id.set()

@dp.message_handler(state=RemoveShopItem.item_id)
async def remove_shop_item(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    try:
        item_id = int(message.text)
    except ValueError:
        await message.answer("❌ Введи число.")
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM shop_items WHERE id=$1", item_id)
        await message.answer("✅ Товар удалён, если существовал.", reply_markup=admin_shop_keyboard())
    except Exception as e:
        logging.error(f"Remove shop item error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Список товаров")
async def list_shop_items(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может просматривать список товаров.")
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
            items = await conn.fetch(
                "SELECT id, name, description, price, stock FROM shop_items ORDER BY id LIMIT $1 OFFSET $2",
                ITEMS_PER_PAGE, offset
            )
        if not items:
            await message.answer("В магазине нет товаров.")
            return
        text = f"📦 Товары (страница {page}):\n"
        for item in items:
            text += f"\nID {item['id']} | {item['name']}\n{item['description']}\n💰 {item['price']} | наличие: {item['stock'] if item['stock']!=-1 else '∞'}\n"
        kb = []
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"shopitems_page_{page-1}"))
        if offset + ITEMS_PER_PAGE < total:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"shopitems_page_{page+1}"))
        if nav_buttons:
            kb.append(nav_buttons)
        if kb:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        else:
            await message.answer(text, reply_markup=admin_shop_keyboard())
    except Exception as e:
        logging.error(f"List shop items error: {e}")
        await message.answer("❌ Ошибка.")

@dp.callback_query_handler(lambda c: c.data.startswith("shopitems_page_"))
async def shopitems_page_callback(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    callback.message.text = f"📋 Список товаров {page}"
    await list_shop_items(callback.message)
    await callback.answer()

@dp.message_handler(lambda message: message.text == "✏️ Редактировать товар")
async def edit_shop_item_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может редактировать товары.")
        return
    await message.answer("Введи ID товара для редактирования:", reply_markup=back_keyboard())
    await EditShopItem.item_id.set()

@dp.message_handler(state=EditShopItem.item_id)
async def edit_shop_item_field(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    try:
        item_id = int(message.text)
    except ValueError:
        await message.answer("❌ Введи число.")
        return
    await state.update_data(item_id=item_id)
    await message.answer("Что хочешь изменить? (price/stock)", reply_markup=back_keyboard())
    await EditShopItem.field.set()

@dp.message_handler(state=EditShopItem.field)
async def edit_shop_item_value(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    field = message.text.lower()
    if field not in ['price', 'stock']:
        await message.answer("❌ Можно изменить только price или stock.")
        return
    await state.update_data(field=field)
    await message.answer(f"Введи новое значение для {field}:")
    await EditShopItem.value.set()

@dp.message_handler(state=EditShopItem.value)
async def edit_shop_item_final(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_shop_menu(message)
        return
    try:
        value = int(message.text)
    except ValueError:
        await message.answer("❌ Введи целое число.")
        return
    data = await state.get_data()
    item_id = data['item_id']
    field = data['field']
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(f"UPDATE shop_items SET {field}=$1 WHERE id=$2", value, item_id)
        await message.answer("✅ Товар обновлён.", reply_markup=admin_shop_keyboard())
    except Exception as e:
        logging.error(f"Edit shop item error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "🛍️ Список покупок")
async def admin_purchases(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У тебя нет прав администратора.")
        return
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT p.id, u.user_id, u.username, s.name, p.purchase_date, p.status FROM purchases p "
                "JOIN users u ON p.user_id = u.user_id JOIN shop_items s ON p.item_id = s.id "
                "WHERE p.status='pending' ORDER BY p.purchase_date"
            )
        if not rows:
            await message.answer("Нет необработанных покупок.")
            return
        for row in rows:
            pid, uid, username, item_name, date, status = row['id'], row['user_id'], row['username'], row['name'], row['purchase_date'], row['status']
            text = f"🆔 {pid}\nПользователь: {uid} (@{username})\nТовар: {item_name}\nДата: {date}"
            await message.answer(text, reply_markup=purchase_action_keyboard(pid))
    except Exception as e:
        logging.error(f"Admin purchases error: {e}")
        await message.answer("❌ Ошибка загрузки покупок.")

@dp.callback_query_handler(lambda c: c.data.startswith("purchase_done_"))
async def purchase_done(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    purchase_id = int(callback.data.split("_")[2])
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE purchases SET status='completed' WHERE id=$1", purchase_id)
            user_id = await conn.fetchval("SELECT user_id FROM purchases WHERE id=$1", purchase_id)
            if user_id:
                await safe_send_message(user_id, "✅ Твоя покупка обработана! Админ выслал подарок.")
        await callback.answer("Покупка отмечена как выполненная")
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Purchase done error: {e}")
        await callback.answer("Ошибка", show_alert=True)

@dp.callback_query_handler(lambda c: c.data.startswith("purchase_reject_"))
async def purchase_reject(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("Недостаточно прав", show_alert=True)
        return
    purchase_id = int(callback.data.split("_")[2])
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE purchases SET status='rejected' WHERE id=$1", purchase_id)
            user_id = await conn.fetchval("SELECT user_id FROM purchases WHERE id=$1", purchase_id)
            if user_id:
                await safe_send_message(user_id, "❌ К сожалению, твоя покупка не может быть выполнена. Свяжись с админом.")
        await callback.answer("Покупка отклонена")
        await callback.message.delete()
    except Exception as e:
        logging.error(f"Purchase reject error: {e}")
        await callback.answer("Ошибка", show_alert=True)

# ===== УПРАВЛЕНИЕ РОЗЫГРЫШАМИ =====
@dp.message_handler(lambda message: message.text == "🎁 Управление розыгрышами")
async def admin_giveaway_menu(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может управлять розыгрышами.")
        return
    await message.answer("Управление розыгрышами:", reply_markup=admin_giveaway_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Создать розыгрыш")
async def create_giveaway_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может создавать розыгрыши.")
        return
    await message.answer("Введи название приза:", reply_markup=back_keyboard())
    await CreateGiveaway.prize.set()

@dp.message_handler(state=CreateGiveaway.prize)
async def create_giveaway_prize(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_giveaway_menu(message)
        return
    await state.update_data(prize=message.text)
    await message.answer("Введи описание розыгрыша:")
    await CreateGiveaway.description.set()

@dp.message_handler(state=CreateGiveaway.description)
async def create_giveaway_description(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_giveaway_menu(message)
        return
    await state.update_data(description=message.text)
    await message.answer("Введи дату окончания в формате ДД.ММ.ГГГГ ЧЧ:ММ (например, 31.12.2025 23:59):")
    await CreateGiveaway.end_date.set()

@dp.message_handler(state=CreateGiveaway.end_date)
async def create_giveaway_end_date(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_giveaway_menu(message)
        return
    try:
        end_date = datetime.strptime(message.text, "%d.%m.%Y %H:%M")
        if end_date <= datetime.now():
            await message.answer("Дата окончания должна быть в будущем.")
            return
        await state.update_data(end_date=end_date.strftime("%Y-%m-%d %H:%M:%S"))
    except ValueError:
        await message.answer("Неверный формат. Используй ДД.ММ.ГГГГ ЧЧ:ММ")
        return
    await message.answer("Отправь медиа (фото, видео или документ) для розыгрыша или отправь 'пропустить':")
    await CreateGiveaway.media.set()

@dp.message_handler(state=CreateGiveaway.media, content_types=['text', 'photo', 'video', 'document'])
async def create_giveaway_media(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_giveaway_menu(message)
        return
    data = await state.get_data()
    media_file_id = None
    media_type = None
    if message.photo:
        media_file_id = message.photo[-1].file_id
        media_type = 'photo'
    elif message.video:
        media_file_id = message.video.file_id
        media_type = 'video'
    elif message.document:
        media_file_id = message.document.file_id
        media_type = 'document'
    elif message.text and message.text.lower() == 'пропустить':
        pass
    else:
        await message.answer("Пожалуйста, отправь фото, видео, документ или 'пропустить'.")
        return

    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO giveaways (prize, description, end_date, media_file_id, media_type) VALUES ($1, $2, $3, $4, $5)",
                data['prize'], data['description'], data['end_date'], media_file_id, media_type
            )
        await message.answer("✅ Розыгрыш создан!", reply_markup=admin_giveaway_keyboard())
    except Exception as e:
        logging.error(f"Create giveaway error: {e}")
        await message.answer("❌ Ошибка при создании розыгрыша.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Активные розыгрыши")
async def list_active_giveaways(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может просматривать активные розыгрыши.")
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
            total = await conn.fetchval("SELECT COUNT(*) FROM giveaways WHERE status='active'")
            rows = await conn.fetch(
                "SELECT id, prize, end_date, description FROM giveaways WHERE status='active' ORDER BY end_date LIMIT $1 OFFSET $2",
                ITEMS_PER_PAGE, offset
            )
        if not rows:
            await message.answer("Нет активных розыгрышей.")
            return
        text = f"Активные розыгрыши (страница {page}):\n"
        for row in rows:
            gid, prize, end, desc = row['id'], row['prize'], row['end_date'], row['description']
            async with db_pool.acquire() as conn2:
                count = await conn2.fetchval("SELECT COUNT(*) FROM participants WHERE giveaway_id=$1", gid)
            text += f"ID: {gid} | {prize} | до {end} | 👥 {count} участников\n{desc}\n\n"
        kb = []
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"activegiveaways_page_{page-1}"))
        if offset + ITEMS_PER_PAGE < total:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"activegiveaways_page_{page+1}"))
        if nav_buttons:
            kb.append(nav_buttons)
        if kb:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        else:
            await message.answer(text, reply_markup=admin_giveaway_keyboard())
    except Exception as e:
        logging.error(f"List giveaways error: {e}")
        await message.answer("❌ Ошибка.")

@dp.callback_query_handler(lambda c: c.data.startswith("activegiveaways_page_"))
async def activegiveaways_page_callback(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    callback.message.text = f"📋 Активные розыгрыши {page}"
    await list_active_giveaways(callback.message)
    await callback.answer()

@dp.message_handler(lambda message: message.text == "✅ Завершить розыгрыш")
async def finish_giveaway_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может завершать розыгрыши.")
        return
    await message.answer("Введи ID розыгрыша, который нужно завершить:", reply_markup=back_keyboard())
    await CompleteGiveaway.giveaway_id.set()

@dp.message_handler(state=CompleteGiveaway.giveaway_id)
async def finish_giveaway(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_giveaway_menu(message)
        return
    try:
        gid = int(message.text)
    except ValueError:
        await message.answer("❌ Введи число.")
        return
    await state.update_data(giveaway_id=gid)
    await message.answer("Введи количество победителей (целое число):")
    await CompleteGiveaway.winners_count.set()

@dp.message_handler(state=CompleteGiveaway.winners_count)
async def finish_giveaway_winners(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_giveaway_menu(message)
        return
    try:
        winners_count = int(message.text)
        if winners_count < 1:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи положительное целое число.")
        return
    data = await state.get_data()
    gid = data['giveaway_id']
    try:
        async with db_pool.acquire() as conn:
            status = await conn.fetchval("SELECT status FROM giveaways WHERE id=$1", gid)
            if not status or status != 'active':
                await message.answer("Розыгрыш не активен или не существует.")
                await state.finish()
                return
            participants = await conn.fetch("SELECT user_id FROM participants WHERE giveaway_id=$1", gid)
            participants = [r['user_id'] for r in participants]
            if not participants:
                await message.answer("В этом розыгрыше нет участников.")
                await state.finish()
                return
            if winners_count > len(participants):
                winners_count = len(participants)
            winners = random.sample(participants, winners_count)
            await conn.execute("UPDATE giveaways SET status='completed', winner_id=$1 WHERE id=$2", winners[0], gid)
            for wid in winners:
                await safe_send_message(wid, f"🎉 Поздравляем! Ты выиграл в розыгрыше! Свяжись с админом.")
        await message.answer(f"🏆 Победители выбраны! ({len(winners)})", reply_markup=admin_giveaway_keyboard())
    except Exception as e:
        logging.error(f"Finish giveaway error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

# ===== УПРАВЛЕНИЕ КАНАЛАМИ =====
@dp.message_handler(lambda message: message.text == "📢 Управление каналами")
async def admin_channel_menu(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может управлять каналами.")
        return
    await message.answer("Управление каналами:", reply_markup=admin_channel_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Добавить канал")
async def add_channel_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может добавлять каналы.")
        return
    await message.answer("Введи chat_id канала (можно получить у @username_to_id_bot):", reply_markup=back_keyboard())
    await AddChannel.chat_id.set()

@dp.message_handler(state=AddChannel.chat_id)
async def add_channel_chat_id(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_channel_menu(message)
        return
    await state.update_data(chat_id=message.text.strip())
    await message.answer("Введи название канала:")
    await AddChannel.next()

@dp.message_handler(state=AddChannel.title)
async def add_channel_title(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_channel_menu(message)
        return
    await state.update_data(title=message.text)
    await message.answer("Введи invite-ссылку (или отправь 'нет'):")
    await AddChannel.next()

@dp.message_handler(state=AddChannel.invite_link)
async def add_channel_link(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_channel_menu(message)
        return
    link = None if message.text.lower() == 'нет' else message.text.strip()
    data = await state.get_data()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO channels (chat_id, title, invite_link) VALUES ($1, $2, $3)",
                data['chat_id'], data['title'], link
            )
        await message.answer("✅ Канал добавлен!", reply_markup=admin_channel_keyboard())
    except asyncpg.UniqueViolationError:
        await message.answer("❌ Канал с таким chat_id уже существует.")
    except Exception as e:
        logging.error(f"Add channel error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "➖ Удалить канал")
async def remove_channel_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может удалять каналы.")
        return
    await message.answer("Введи chat_id канала для удаления:", reply_markup=back_keyboard())
    await RemoveChannel.chat_id.set()

@dp.message_handler(state=RemoveChannel.chat_id)
async def remove_channel(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_channel_menu(message)
        return
    chat_id = message.text.strip()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM channels WHERE chat_id=$1", chat_id)
        await message.answer("✅ Канал удалён, если существовал.", reply_markup=admin_channel_keyboard())
    except Exception as e:
        logging.error(f"Remove channel error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Список каналов")
async def list_channels(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может просматривать список каналов.")
        return
    channels = await get_channels()
    if not channels:
        await message.answer("Нет добавленных каналов.")
        return
    text = "📺 Каналы для подписки:\n"
    for chat_id, title, link in channels:
        text += f"• {title} (chat_id: {chat_id})\n  Ссылка: {link or 'нет'}\n"
    await message.answer(text, reply_markup=admin_channel_keyboard())

# ===== УПРАВЛЕНИЕ ПРОМОКОДАМИ =====
@dp.message_handler(lambda message: message.text == "🎫 Управление промокодами")
async def admin_promo_menu(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может управлять промокодами.")
        return
    await message.answer("Управление промокодами:", reply_markup=admin_promo_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Создать промокод")
async def create_promo_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может создавать промокоды.")
        return
    await message.answer("Введи код промокода (латиница, цифры):", reply_markup=back_keyboard())
    await CreatePromocode.code.set()

@dp.message_handler(state=CreatePromocode.code)
async def create_promo_code(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_promo_menu(message)
        return
    code = message.text.strip().upper()
    await state.update_data(code=code)
    await message.answer("Введи количество монет, которые даёт промокод:")
    await CreatePromocode.next()

@dp.message_handler(state=CreatePromocode.reward)
async def create_promo_reward(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_promo_menu(message)
        return
    try:
        reward = int(message.text)
        if reward <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи положительное целое число.")
        return
    await state.update_data(reward=reward)
    await message.answer("Введи максимальное количество использований:")
    await CreatePromocode.next()

@dp.message_handler(state=CreatePromocode.max_uses)
async def create_promo_max_uses(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_promo_menu(message)
        return
    try:
        max_uses = int(message.text)
        if max_uses <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введи положительное целое число.")
        return
    data = await state.get_data()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO promocodes (code, reward, max_uses, created_at) VALUES ($1, $2, $3, $4)",
                data['code'], data['reward'], max_uses, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        await message.answer("✅ Промокод создан!", reply_markup=admin_promo_keyboard())
    except asyncpg.UniqueViolationError:
        await message.answer("❌ Промокод с таким кодом уже существует.")
    except Exception as e:
        logging.error(f"Create promo error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Список промокодов")
async def list_promos(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может просматривать список промокодов.")
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
            total = await conn.fetchval("SELECT COUNT(*) FROM promocodes")
            rows = await conn.fetch(
                "SELECT code, reward, max_uses, used_count FROM promocodes LIMIT $1 OFFSET $2",
                ITEMS_PER_PAGE, offset
            )
        if not rows:
            await message.answer("Нет промокодов.")
            return
        text = f"🎫 Промокоды (страница {page}):\n"
        for row in rows:
            text += f"• {row['code']}: {row['reward']} монет, использовано {row['used_count']}/{row['max_uses']}\n"
        kb = []
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"promos_page_{page-1}"))
        if offset + ITEMS_PER_PAGE < total:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"promos_page_{page+1}"))
        if nav_buttons:
            kb.append(nav_buttons)
        if kb:
            await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        else:
            await message.answer(text, reply_markup=admin_promo_keyboard())
    except Exception as e:
        logging.error(f"List promos error: {e}")
        await message.answer("❌ Ошибка.")

@dp.callback_query_handler(lambda c: c.data.startswith("promos_page_"))
async def promos_page_callback(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    callback.message.text = f"📋 Список промокодов {page}"
    await list_promos(callback.message)
    await callback.answer()

# ===== УПРАВЛЕНИЕ ЗАДАНИЯМИ =====
@dp.message_handler(lambda message: message.text == "📋 Управление заданиями")
async def admin_tasks_menu(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может управлять заданиями.")
        return
    await message.answer("Управление заданиями:", reply_markup=admin_tasks_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Создать задание")
async def create_task_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может создавать задания.")
        return
    await message.answer("Введи название задания:", reply_markup=back_keyboard())
    await CreateTask.name.set()

@dp.message_handler(state=CreateTask.name)
async def create_task_name(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    await state.update_data(name=message.text)
    await message.answer("Введи описание задания:")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.description)
async def create_task_description(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    await state.update_data(description=message.text)
    await message.answer("Введи тип задания (subscribe):")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.task_type)
async def create_task_type(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    task_type = message.text.lower()
    if task_type not in ['subscribe']:
        await message.answer("Поддерживается только 'subscribe'")
        return
    await state.update_data(task_type=task_type)
    await message.answer("Введи ID канала (с -100) для подписки:")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.target_id)
async def create_task_target(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    await state.update_data(target_id=message.text.strip())
    await message.answer("Введи награду (монеты):")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.reward_coins)
async def create_task_reward_coins(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    try:
        coins = int(message.text)
    except:
        await message.answer("Введи целое число.")
        return
    await state.update_data(reward_coins=coins)
    await message.answer("Введи награду (репутация):")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.reward_reputation)
async def create_task_reward_rep(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    try:
        rep = int(message.text)
    except:
        await message.answer("Введи целое число.")
        return
    await state.update_data(reward_reputation=rep)
    await message.answer("Сколько дней нужно быть подписанным? (0 - не проверять):")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.required_days)
async def create_task_required_days(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    try:
        days = int(message.text)
        if days < 0:
            raise ValueError
    except:
        await message.answer("Введи неотрицательное целое число.")
        return
    await state.update_data(required_days=days)
    await message.answer("Штрафных дней (если отписался раньше, 0 - нет штрафа):")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.penalty_days)
async def create_task_penalty_days(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    try:
        days = int(message.text)
        if days < 0:
            raise ValueError
    except:
        await message.answer("Введи неотрицательное целое число.")
        return
    await state.update_data(penalty_days=days)
    await message.answer("Максимальное количество выполнений задания (0 - бесконечно):")
    await CreateTask.next()

@dp.message_handler(state=CreateTask.max_completions)
async def create_task_max_completions(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    try:
        max_completions = int(message.text)
        if max_completions < 0:
            raise ValueError
    except:
        await message.answer("Введи неотрицательное целое число.")
        return
    data = await state.get_data()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO tasks (name, description, task_type, target_id, reward_coins, reward_reputation, required_days, penalty_days, max_completions, created_by, created_at, active) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, TRUE)",
                data['name'], data['description'], data['task_type'], data['target_id'], data['reward_coins'], data['reward_reputation'], data['required_days'], data['penalty_days'], max_completions, message.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        await message.answer("✅ Задание создано!", reply_markup=admin_tasks_keyboard())
    except Exception as e:
        logging.error(f"Create task error: {e}")
        await message.answer("❌ Ошибка при создании задания.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Список заданий")
async def list_tasks(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может просматривать список заданий.")
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, active, max_completions, completed_count FROM tasks ORDER BY id")
    if not rows:
        await message.answer("Нет заданий.")
        return
    text = "📋 Задания:\n"
    for row in rows:
        status = "активно" if row['active'] else "неактивно"
        progress = f" (выполнено {row['completed_count']}/{row['max_completions'] if row['max_completions']>0 else '∞'})"
        text += f"ID {row['id']}: {row['name']} - {status}{progress}\n"
    await message.answer(text, reply_markup=admin_tasks_keyboard())

@dp.message_handler(lambda message: message.text == "❌ Удалить задание")
async def delete_task_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может удалять задания.")
        return
    await message.answer("Введи ID задания для удаления (деактивации):", reply_markup=back_keyboard())
    await DeleteTask.task_id.set()

@dp.message_handler(state=DeleteTask.task_id)
async def delete_task_finish(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_tasks_menu(message)
        return
    try:
        task_id = int(message.text)
    except:
        await message.answer("Введи число.")
        return
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE tasks SET active=FALSE WHERE id=$1", task_id)
    await message.answer("✅ Задание деактивировано.", reply_markup=admin_tasks_keyboard())
    await state.finish()

# ===== УПРАВЛЕНИЕ ЧАТАМИ =====
@dp.message_handler(lambda message: message.text == "🤖 Управление чатами")
async def admin_chats_menu(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может управлять чатами.")
        return
    await message.answer("Управление чатами:", reply_markup=admin_chats_keyboard())

@dp.message_handler(lambda message: message.text == "📋 Список запросов на подтверждение")
async def list_pending_requests(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        return
    requests = await get_pending_chat_requests()
    if not requests:
        await message.answer("Нет ожидающих запросов.")
        return
    text = "📋 Ожидающие запросы:\n\n"
    for req in requests:
        text += f"• {req['title']} (ID: {req['chat_id']})\n  Запросил: {req['requested_by']} ({req['request_date']})\n"
    await message.answer(text)

@dp.message_handler(lambda message: message.text == "✅ Подтвердить чат")
async def confirm_chat_manual(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        return
    await message.answer("Введи ID чата, который хочешь подтвердить:", reply_markup=back_keyboard())
    await ManageChats.chat_id.set()
    async with state.proxy() as data:
        data['action'] = "confirm"

@dp.message_handler(lambda message: message.text == "❌ Отклонить запрос")
async def reject_chat_manual(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        return
    await message.answer("Введи ID чата, запрос которого хочешь отклонить:", reply_markup=back_keyboard())
    await ManageChats.chat_id.set()
    async with state.proxy() as data:
        data['action'] = "reject"

@dp.message_handler(lambda message: message.text == "🗑 Удалить чат из подтверждённых")
async def remove_confirmed_chat_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        return
    await message.answer("Введи ID чата, который нужно удалить из подтверждённых:", reply_markup=back_keyboard())
    await ManageChats.chat_id.set()
    async with state.proxy() as data:
        data['action'] = "remove"

@dp.message_handler(lambda message: message.text == "📋 Список подтверждённых чатов")
async def list_confirmed_chats(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        return
    confirmed = await get_confirmed_chats(force_update=True)
    if not confirmed:
        await message.answer("Нет подтверждённых чатов.")
        return
    text = "✅ Подтверждённые чаты:\n\n"
    for chat_id, data in confirmed.items():
        text += f"• {data['title']} (ID: {chat_id})\n  Подтверждён: {data.get('confirmed_date', 'неизвестно')}\n"
    await message.answer(text)

@dp.message_handler(state=ManageChats.chat_id)
async def process_chat_id(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_chats_menu(message)
        return
    try:
        chat_id = int(message.text)
    except:
        await message.answer("❌ Введи число.")
        return
    data = await state.get_data()
    action = data.get('action')
    async with db_pool.acquire() as conn:
        if action == "confirm":
            request = await conn.fetchrow("SELECT * FROM chat_confirmation_requests WHERE chat_id=$1", chat_id)
            if request:
                await add_confirmed_chat(chat_id, request['title'], request['type'], message.from_user.id)
                await update_chat_request_status(chat_id, 'approved')
                await message.answer(f"✅ Чат {request['title']} подтверждён.")
                await safe_send_message(request['requested_by'], f"✅ Ваш чат «{request['title']}» активирован!")
            else:
                # Если запроса нет, но админ хочет подтвердить (чат уже есть)
                try:
                    chat = await bot.get_chat(chat_id)
                    await add_confirmed_chat(chat_id, chat.title, chat.type, message.from_user.id)
                    await message.answer(f"✅ Чат {chat.title} подтверждён.")
                except:
                    await message.answer("❌ Не удалось получить информацию о чате.")
        elif action == "reject":
            request = await conn.fetchrow("SELECT * FROM chat_confirmation_requests WHERE chat_id=$1", chat_id)
            if not request:
                await message.answer("❌ Запрос не найден.")
                await state.finish()
                return
            await update_chat_request_status(chat_id, 'rejected')
            await message.answer(f"❌ Запрос для чата {request['title']} отклонён.")
            await safe_send_message(request['requested_by'], f"❌ Запрос на активацию чата «{request['title']}» отклонён.")
        elif action == "remove":
            await remove_confirmed_chat(chat_id)
            await message.answer(f"✅ Чат {chat_id} удалён из подтверждённых.")
    await state.finish()

# ===== УПРАВЛЕНИЕ БОССАМИ =====
@dp.message_handler(lambda message: message.text == "👾 Управление боссами")
async def admin_boss_menu(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может управлять боссами.")
        return
    await message.answer("Управление боссами:", reply_markup=admin_boss_keyboard())

@dp.message_handler(lambda message: message.text == "📋 Активные боссы")
async def list_active_bosses(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM bosses WHERE status='active' ORDER BY spawned_at")
    if not rows:
        await message.answer("Нет активных боссов.")
        return
    text = "Активные боссы:\n"
    for row in rows:
        text += f"ID {row['id']}: {row['name']} (ур. {row['level']}) в чате {row['chat_id']}, HP {row['hp']}/{row['max_hp']}\n"
    await message.answer(text)

@dp.message_handler(lambda message: message.text == "⚔️ Создать босса вручную")
async def manual_spawn_boss_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        return
    await message.answer("Введи ID чата, где создать босса:", reply_markup=back_keyboard())
    await BossSpawn.chat_id.set()

@dp.message_handler(state=BossSpawn.chat_id)
async def manual_spawn_boss_chat(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_boss_menu(message)
        return
    try:
        chat_id = int(message.text)
    except:
        await message.answer("❌ Введи число.")
        return
    if not await is_chat_confirmed(chat_id):
        await message.answer("❌ Чат не подтверждён. Сначала подтвердите его.")
        await state.finish()
        return
    await state.update_data(chat_id=chat_id)
    await message.answer("Введи уровень босса (1-10):")
    await BossSpawn.level.set()

@dp.message_handler(state=BossSpawn.level)
async def manual_spawn_boss_level(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_boss_menu(message)
        return
    try:
        level = int(message.text)
        if level < 1 or level > 10:
            raise ValueError
    except:
        await message.answer("❌ Введи число от 1 до 10.")
        return
    data = await state.get_data()
    chat_id = data['chat_id']
    await spawn_boss(chat_id, level=level)
    await message.answer(f"✅ Босс {level} уровня создан в чате {chat_id}.")
    await state.finish()

# ===== УПРАВЛЕНИЕ ПОМОЩНИКАМИ (будущая реализация) =====
@dp.message_handler(lambda message: message.text == "⚔️ Управление помощниками")
async def admin_helper_menu(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может управлять помощниками.")
        return
    await message.answer("Управление помощниками:", reply_markup=admin_helper_keyboard())

@dp.message_handler(lambda message: message.text == "📋 Активные помощники")
async def list_active_helpers(message: types.Message):
    # Заглушка, будет реализовано позже
    await message.answer("Функция в разработке.")

@dp.message_handler(lambda message: message.text == "📊 Топы чатов")
async def chat_tops(message: types.Message):
    # Заглушка
    await message.answer("Функция в разработке.")

# ===== УПРАВЛЕНИЕ АУКЦИОНАМИ =====
@dp.message_handler(lambda message: message.text == "🏷 Управление аукционами")
async def admin_auction_menu(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может управлять аукционами.")
        return
    await message.answer("Управление аукционами:", reply_markup=admin_auction_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Создать аукцион")
async def create_auction_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может создавать аукционы.")
        return
    await message.answer("Введи название товара:", reply_markup=back_keyboard())
    await CreateAuction.item_name.set()

@dp.message_handler(state=CreateAuction.item_name)
async def create_auction_name(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_auction_menu(message)
        return
    await state.update_data(item_name=message.text)
    await message.answer("Введи описание товара:")
    await CreateAuction.next()

@dp.message_handler(state=CreateAuction.description)
async def create_auction_description(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_auction_menu(message)
        return
    await state.update_data(description=message.text)
    await message.answer("Введи стартовую цену (целое число):")
    await CreateAuction.next()

@dp.message_handler(state=CreateAuction.start_price)
async def create_auction_start_price(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_auction_menu(message)
        return
    try:
        price = int(message.text)
        if price <= 0:
            raise ValueError
    except:
        await message.answer("❌ Введи положительное целое число.")
        return
    await state.update_data(start_price=price, current_price=price)
    await message.answer("Введи время окончания в часах (целое число) или 'нет', если не нужно:")
    await CreateAuction.next()

@dp.message_handler(state=CreateAuction.end_time)
async def create_auction_end_time(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_auction_menu(message)
        return
    if message.text.lower() == 'нет':
        end_time = None
    else:
        try:
            hours = int(message.text)
            if hours <= 0:
                raise ValueError
            end_time = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        except:
            await message.answer("❌ Введи целое положительное число часов или 'нет'.")
            return
    await state.update_data(end_time=end_time)
    await message.answer("Введи целевую цену (целое число) или 'нет', если не нужна:")
    await CreateAuction.next()

@dp.message_handler(state=CreateAuction.target_price)
async def create_auction_target_price(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_auction_menu(message)
        return
    if message.text.lower() == 'нет':
        target_price = None
    else:
        try:
            target_price = int(message.text)
            if target_price <= 0:
                raise ValueError
        except:
            await message.answer("❌ Введи целое положительное число или 'нет'.")
            return
    data = await state.get_data()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO auctions (item_name, description, start_price, current_price, end_time, target_price, created_by) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                data['item_name'], data['description'], data['start_price'], data['start_price'], data['end_time'], target_price, message.from_user.id
            )
        await message.answer("✅ Аукцион создан!", reply_markup=admin_auction_keyboard())
    except Exception as e:
        logging.error(f"Create auction error: {e}")
        await message.answer("❌ Ошибка при создании аукциона.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Активные аукционы")
async def list_active_auctions(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM auctions WHERE status='active' ORDER BY created_at")
    if not rows:
        await message.answer("Нет активных аукционов.")
        return
    text = "Активные аукционы:\n"
    for row in rows:
        text += f"ID {row['id']}: {row['item_name']} | Текущая цена: {row['current_price']} | Создатель: {row['created_by']}\n"
    await message.answer(text)

@dp.message_handler(lambda message: message.text == "❌ Отменить аукцион")
async def cancel_auction_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        return
    await message.answer("Введи ID аукциона для отмены:", reply_markup=back_keyboard())
    await CancelAuction.auction_id.set()

@dp.message_handler(state=CancelAuction.auction_id)
async def cancel_auction_finish(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_auction_menu(message)
        return
    try:
        auction_id = int(message.text)
    except:
        await message.answer("❌ Введи число.")
        return
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE auctions SET status='cancelled' WHERE id=$1", auction_id)
    await message.answer(f"✅ Аукцион {auction_id} отменён.")
    await state.finish()

# ===== УПРАВЛЕНИЕ РЕКЛАМОЙ =====
@dp.message_handler(lambda message: message.text == "📢 Управление рекламой")
async def admin_ad_menu(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может управлять рекламой.")
        return
    await message.answer("Управление рекламой:", reply_markup=admin_ad_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Создать рекламу")
async def create_ad_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        return
    await message.answer("Введи текст рекламного сообщения:", reply_markup=back_keyboard())
    await CreateAd.text.set()

@dp.message_handler(state=CreateAd.text)
async def create_ad_text(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ad_menu(message)
        return
    await state.update_data(text=message.text)
    await message.answer("Введи интервал отправки в минутах (целое число):")
    await CreateAd.interval.set()

@dp.message_handler(state=CreateAd.interval)
async def create_ad_interval(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ad_menu(message)
        return
    try:
        interval = int(message.text)
        if interval <= 0:
            raise ValueError
    except:
        await message.answer("❌ Введи целое положительное число.")
        return
    await state.update_data(interval=interval)
    await message.answer("Куда отправлять? (chats / private / all):")
    await CreateAd.target.set()

@dp.message_handler(state=CreateAd.target)
async def create_ad_target(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ad_menu(message)
        return
    target = message.text.lower()
    if target not in ['chats', 'private', 'all']:
        await message.answer("❌ Выбери: chats, private или all.")
        return
    data = await state.get_data()
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO ads (text, interval_minutes, target, last_sent, enabled) VALUES ($1, $2, $3, $4, $5)",
                data['text'], data['interval'], target, datetime.now(), True
            )
        await message.answer("✅ Рекламное объявление создано!", reply_markup=admin_ad_keyboard())
    except Exception as e:
        logging.error(f"Create ad error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Список рекламы")
async def list_ads(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, text, interval_minutes, enabled FROM ads ORDER BY id")
    if not rows:
        await message.answer("Нет рекламных объявлений.")
        return
    text = "📢 Рекламные объявления:\n"
    for row in rows:
        status = "✅" if row['enabled'] else "❌"
        text += f"{status} ID {row['id']}: {row['text'][:50]}... (интервал {row['interval_minutes']} мин)\n"
    await message.answer(text)

# ===== НАСТРОЙКИ ИГРЫ =====
@dp.message_handler(lambda message: message.text == "⚙️ Настройки игры")
async def settings_menu(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может изменять настройки игры.")
        return
    await message.answer("Выбери категорию настроек:", reply_markup=settings_reply_keyboard())

# Обработчики категорий настроек будут вызывать соответствующие подменю
# Здесь для краткости приведён только один пример, в реальности нужно реализовать все категории
@dp.message_handler(lambda message: message.text == "⚙️ Кража")
async def settings_theft(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        return
    # Здесь можно показать клавиатуру с параметрами кражи
    await message.answer("Настройки кражи:\n"
                         "• random_attack_cost\n"
                         "• targeted_attack_cost\n"
                         "• theft_cooldown_minutes\n"
                         "• theft_success_chance\n"
                         "• theft_defense_chance\n"
                         "• theft_defense_penalty\n"
                         "• min_theft_amount\n"
                         "• max_theft_amount\n"
                         "Введи название параметра для изменения или /cancel.")
    # Далее можно реализовать редактирование через FSM

# ===== СТАТИСТИКА =====
@dp.message_handler(lambda message: message.text == "📊 Статистика")
async def stats_handler(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У тебя нет прав администратора.")
        return
    try:
        async with db_pool.acquire() as conn:
            users = await conn.fetchval("SELECT COUNT(*) FROM users")
            total_balance = await conn.fetchval("SELECT SUM(balance) FROM users") or 0
            total_reputation = await conn.fetchval("SELECT SUM(reputation) FROM users") or 0
            total_spent = await conn.fetchval("SELECT SUM(total_spent) FROM users") or 0
            active_giveaways = await conn.fetchval("SELECT COUNT(*) FROM giveaways WHERE status='active'") or 0
            shop_items = await conn.fetchval("SELECT COUNT(*) FROM shop_items") or 0
            purchases_pending = await conn.fetchval("SELECT COUNT(*) FROM purchases WHERE status='pending'") or 0
            purchases_completed = await conn.fetchval("SELECT COUNT(*) FROM purchases WHERE status='completed'") or 0
            total_thefts = await conn.fetchval("SELECT SUM(theft_attempts) FROM users") or 0
            total_thefts_success = await conn.fetchval("SELECT SUM(theft_success) FROM users") or 0
            promos = await conn.fetchval("SELECT COUNT(*) FROM promocodes") or 0
            banned = await conn.fetchval("SELECT COUNT(*) FROM banned_users") or 0
            total_bosses = await conn.fetchval("SELECT COUNT(*) FROM bosses") or 0
            active_bosses = await conn.fetchval("SELECT COUNT(*) FROM bosses WHERE status='active'") or 0
            confirmed_chats = await conn.fetchval("SELECT COUNT(*) FROM confirmed_chats") or 0
        text = (
            f"📊 Статистика:\n"
            f"👥 Пользователей: {users}\n"
            f"💰 Всего монет: {total_balance}\n"
            f"⭐️ Всего репутации: {total_reputation}\n"
            f"💸 Всего потрачено: {total_spent}\n"
            f"🎁 Активных розыгрышей: {active_giveaways}\n"
            f"🛒 Товаров в магазине: {shop_items}\n"
            f"🛍️ Ожидающих покупок: {purchases_pending}\n"
            f"✅ Выполненных покупок: {purchases_completed}\n"
            f"🔫 Всего ограблений: {total_thefts} (успешно: {total_thefts_success})\n"
            f"🎫 Промокодов создано: {promos}\n"
            f"⛔ Заблокировано: {banned}\n"
            f"👾 Всего боссов: {total_bosses} (активных: {active_bosses})\n"
            f"✅ Подтверждённых чатов: {confirmed_chats}"
        )
        await message.answer(text, reply_markup=admin_main_keyboard(await is_super_admin(message.from_user.id)))
    except Exception as e:
        logging.error(f"Stats error: {e}")
        await message.answer("❌ Ошибка получения статистики.")

# ===== БЛОКИРОВКИ =====
@dp.message_handler(lambda message: message.text == "🔨 Блокировки")
async def admin_ban_menu(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может управлять блокировками.")
        return
    await message.answer("Управление блокировками:", reply_markup=admin_ban_keyboard())

@dp.message_handler(lambda message: message.text == "🔨 Заблокировать пользователя")
async def block_user_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может блокировать пользователей.")
        return
    await message.answer("Введи ID или @username пользователя для блокировки:", reply_markup=back_keyboard())
    await BlockUser.user_id.set()

@dp.message_handler(state=BlockUser.user_id)
async def block_user_id(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ban_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    if await is_admin(uid):
        await message.answer("❌ Нельзя заблокировать администратора.")
        await state.finish()
        return
    await state.update_data(user_id=uid)
    await message.answer("Введи причину блокировки (можно отправить 'нет'):")
    await BlockUser.reason.set()

@dp.message_handler(state=BlockUser.reason)
async def block_user_reason(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ban_menu(message)
        return
    reason = None if message.text.lower() == 'нет' else message.text
    data = await state.get_data()
    uid = data['user_id']
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO banned_users (user_id, banned_by, banned_date, reason) VALUES ($1, $2, $3, $4) ON CONFLICT (user_id) DO NOTHING",
                uid, message.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), reason
            )
        await message.answer(f"✅ Пользователь {uid} заблокирован.")
        await safe_send_message(uid, f"⛔ Вы заблокированы в боте. Причина: {reason if reason else 'не указана'}")
    except Exception as e:
        logging.error(f"Block user error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "🔓 Разблокировать пользователя")
async def unblock_user_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может разблокировать пользователей.")
        return
    await message.answer("Введи ID или @username пользователя для разблокировки:", reply_markup=back_keyboard())
    await UnblockUser.user_id.set()

@dp.message_handler(state=UnblockUser.user_id)
async def unblock_user_finish(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_ban_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM banned_users WHERE user_id=$1", uid)
        await message.answer(f"✅ Пользователь {uid} разблокирован.")
        await safe_send_message(uid, "🔓 Вы разблокированы в боте.")
    except Exception as e:
        logging.error(f"Unblock user error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Список заблокированных")
async def list_banned(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, banned_date, reason FROM banned_users ORDER BY banned_date DESC")
    if not rows:
        await message.answer("Нет заблокированных пользователей.")
        return
    text = "⛔ Заблокированные пользователи:\n\n"
    for row in rows:
        text += f"ID: {row['user_id']}, Дата: {row['banned_date']}\nПричина: {row['reason'] or 'не указана'}\n\n"
    await message.answer(text)

# ===== УПРАВЛЕНИЕ АДМИНАМИ =====
@dp.message_handler(lambda message: message.text == "➕ Управление админами")
async def admin_admins_menu(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может управлять админами.")
        return
    await message.answer("Управление админами:", reply_markup=admin_admins_keyboard())

@dp.message_handler(lambda message: message.text == "➕ Добавить админа")
async def add_admin_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("Только суперадмин может добавлять админов.")
        return
    await message.answer("Введи ID или @username пользователя, которого хочешь сделать младшим админом:", reply_markup=back_keyboard())
    await AddJuniorAdmin.user_id.set()

@dp.message_handler(state=AddJuniorAdmin.user_id)
async def add_admin_finish(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_admins_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO admins (user_id, added_by, added_date) VALUES ($1, $2, $3)",
                uid, message.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        await message.answer(f"✅ Пользователь {uid} теперь младший админ.")
    except asyncpg.UniqueViolationError:
        await message.answer("❌ Этот пользователь уже админ.")
    except Exception as e:
        logging.error(f"Add admin error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "➖ Удалить админа")
async def remove_admin_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("Только суперадмин может удалять админов.")
        return
    await message.answer("Введи ID или @username пользователя, которого хочешь лишить прав админа:", reply_markup=back_keyboard())
    await RemoveJuniorAdmin.user_id.set()

@dp.message_handler(state=RemoveJuniorAdmin.user_id)
async def remove_admin_finish(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        await admin_admins_menu(message)
        return
    user_data = await find_user_by_input(message.text)
    if not user_data:
        await message.answer("❌ Пользователь не найден.")
        return
    uid = user_data['user_id']
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM admins WHERE user_id=$1", uid)
        await message.answer(f"✅ Пользователь {uid} больше не админ, если был им.")
    except Exception as e:
        logging.error(f"Remove admin error: {e}")
        await message.answer("❌ Ошибка.")
    await state.finish()

@dp.message_handler(lambda message: message.text == "📋 Список админов")
async def list_admins(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, added_date FROM admins ORDER BY added_date")
    if not rows:
        await message.answer("Нет младших админов.")
        return
    text = "👥 Младшие админы:\n"
    for row in rows:
        text += f"• ID: {row['user_id']}, назначен: {row['added_date']}\n"
    await message.answer(text)

# ===== РАССЫЛКА =====
@dp.message_handler(lambda message: message.text == "📢 Рассылка")
async def broadcast_start(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        await message.answer("❌ Только суперадмин может делать рассылку.")
        return
    await message.answer("Отправь сообщение для рассылки (текст, фото, видео или документ).", reply_markup=back_keyboard())
    await Broadcast.media.set()

@dp.message_handler(state=Broadcast.media, content_types=['text', 'photo', 'video', 'document'])
async def broadcast_media(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.finish()
        super_admin = await is_super_admin(message.from_user.id)
        await message.answer("Панель администратора:", reply_markup=admin_main_keyboard(super_admin))
        return

    content = {}
    if message.text:
        content['type'] = 'text'
        content['text'] = message.text
    elif message.photo:
        content['type'] = 'photo'
        content['file_id'] = message.photo[-1].file_id
        content['caption'] = message.caption or ""
    elif message.video:
        content['type'] = 'video'
        content['file_id'] = message.video.file_id
        content['caption'] = message.caption or ""
    elif message.document:
        content['type'] = 'document'
        content['file_id'] = message.document.file_id
        content['caption'] = message.caption or ""
    else:
        await message.answer("Неподдерживаемый тип.")
        return

    await state.finish()

    status_msg = await message.answer("⏳ Рассылка начата... Это может занять некоторое время.")

    async with db_pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users")
        users = [r['user_id'] for r in users]

    sent = 0
    failed = 0
    total = len(users)

    for i, uid in enumerate(users):
        if await is_banned(uid):
            continue
        try:
            if content['type'] == 'text':
                await bot.send_message(uid, content['text'])
            elif content['type'] == 'photo':
                await bot.send_photo(uid, content['file_id'], caption=content['caption'])
            elif content['type'] == 'video':
                await bot.send_video(uid, content['file_id'], caption=content['caption'])
            elif content['type'] == 'document':
                await bot.send_document(uid, content['file_id'], caption=content['caption'])
            sent += 1
        except (BotBlocked, UserDeactivated, ChatNotFound):
            failed += 1
        except RetryAfter as e:
            logging.warning(f"Flood limit, waiting {e.timeout} seconds")
            await asyncio.sleep(e.timeout)
            try:
                if content['type'] == 'text':
                    await bot.send_message(uid, content['text'])
                else:
                    if content['type'] == 'photo':
                        await bot.send_photo(uid, content['file_id'], caption=content['caption'])
                    elif content['type'] == 'video':
                        await bot.send_video(uid, content['file_id'], caption=content['caption'])
                    elif content['type'] == 'document':
                        await bot.send_document(uid, content['file_id'], caption=content['caption'])
                sent += 1
            except:
                failed += 1
        except Exception as e:
            failed += 1
            logging.warning(f"Failed to send to {uid}: {e}")

        if (i + 1) % 10 == 0:
            try:
                await status_msg.edit_text(f"⏳ Прогресс: {i+1}/{total}\n✅ Отправлено: {sent}\n❌ Ошибок: {failed}")
            except:
                pass

        await asyncio.sleep(0.05)

    await status_msg.edit_text(f"✅ Рассылка завершена!\n📊 Отправлено: {sent}\n❌ Ошибок: {failed}\n👥 Всего: {total}")

# ===== ОЧИСТКА СТАРЫХ ЗАПИСЕЙ =====
@dp.message_handler(lambda message: message.text == "🧹 Очистка старых записей")
async def cleanup_old_data(message: types.Message):
    if not await is_super_admin(message.from_user.id):
        return
    # Ручная очистка по настройкам
    days_bosses = int(await get_setting("cleanup_days_bosses"))
    days_auctions = int(await get_setting("cleanup_days_auctions"))
    days_purchases = int(await get_setting("cleanup_days_purchases"))
    days_giveaways = int(await get_setting("cleanup_days_giveaways"))
    days_tasks = int(await get_setting("cleanup_days_user_tasks"))

    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM bosses WHERE status IN ('defeated', 'expired') AND spawned_at < NOW() - INTERVAL '1 day' * $1", days_bosses)
        await conn.execute("DELETE FROM boss_attacks WHERE attack_time < NOW() - INTERVAL '1 day' * $1", days_bosses)
        await conn.execute("DELETE FROM auctions WHERE status='ended' AND end_time < NOW() - INTERVAL '1 day' * $1", days_auctions)
        await conn.execute("DELETE FROM purchases WHERE status IN ('completed','rejected') AND purchase_date < NOW() - INTERVAL '1 day' * $1", days_purchases)
        await conn.execute("DELETE FROM giveaways WHERE status='completed' AND end_date < NOW() - INTERVAL '1 day' * $1", days_giveaways)
        await conn.execute("DELETE FROM user_tasks WHERE expires_at IS NOT NULL AND expires_at < NOW()")
        # Также очищаем старые логи боёв
        days_fight = int(await get_setting("cleanup_days_fight_logs"))
        await conn.execute("DELETE FROM fight_logs WHERE timestamp < NOW() - INTERVAL '1 day' * $1", days_fight)
        await conn.execute("DELETE FROM fight_cooldowns WHERE last_fight < NOW() - INTERVAL '1 day' * $1", days_fight)

    await message.answer("✅ Старые записи очищены согласно настройкам.")

# ===== ОБРАБОТКА НЕИЗВЕСТНЫХ СООБЩЕНИЙ В АДМИНКЕ =====
@dp.message_handler()
async def unknown_admin_message(message: types.Message):
    if message.chat.type != 'private':
        return
    if await is_admin(message.from_user.id):
        # Если админ ввёл что-то не то, предлагаем вернуться в меню
        await message.answer("Неизвестная команда. Используй кнопки меню.", reply_markup=admin_main_keyboard(await is_super_admin(message.from_user.id)))
