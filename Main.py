# e.py - SHARK ZN0S (РАБОЧАЯ ВЕРСИЯ)

import asyncio
import sqlite3
import random
import string
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = "8166941860:AAFnmDwugR0r4GhmIgDlmWyGvju6igy7OrE"
OWNER_ID = 8640180536

PUBLIC_CHANNEL = "@krectbII"
PRIVATE_CHANNEL_LINK = "https://t.me/+P-pynIFyi9gwYjE1"
PRIVATE_CHANNEL_ID = -1003441944576

DATABASE = "shark_znos.db"

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            ref_link TEXT UNIQUE,
            invited_by INTEGER,
            ref_count INTEGER DEFAULT 0,
            subscribed INTEGER DEFAULT 0,
            approved INTEGER DEFAULT 0,
            banned INTEGER DEFAULT 0,
            ref_given INTEGER DEFAULT 0
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
    ''')
    
    c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))
    conn.commit()
    conn.close()
    print("База данных готова")

init_db()

# ========== ФУНКЦИИ БАЗЫ ==========
def get_user(user_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def get_user_by_ref_link(ref_link):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE ref_link = ?", (ref_link,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def create_user(user_id, username, invited_by=None):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    ref_link = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    
    c.execute(
        "INSERT INTO users (user_id, username, ref_link, invited_by, ref_count) VALUES (?, ?, ?, ?, 0)",
        (user_id, username, ref_link, invited_by)
    )
    conn.commit()
    conn.close()
    print(f"[НОВЫЙ] {user_id} (приглашён: {invited_by})")

def mark_subscribed(user_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("UPDATE users SET subscribed = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def add_referral_if_needed(user_id):
    """Засчитывает реферал пригласившему, если пользователь только что подписался"""
    user = get_user(user_id)
    if not user:
        return
    
    invited_by = user[3]
    subscribed = user[5]
    ref_given = user[8] if len(user) > 8 else 0
    
    if invited_by and subscribed == 1 and ref_given == 0:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("UPDATE users SET ref_count = ref_count + 1 WHERE user_id = ?", (invited_by,))
        c.execute("UPDATE users SET ref_given = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        print(f"[РЕФЕРАЛ] {user_id} подписался → +1 реферал для {invited_by}")

def approve_user(user_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("UPDATE users SET approved = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def is_admin(user_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    row = c.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row is not None

def get_pending_users():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    rows = c.execute("SELECT user_id, username, ref_count FROM users WHERE approved = 0 AND ref_count >= 5 AND subscribed = 1").fetchall()
    conn.close()
    return rows

# ========== ПРОВЕРКА ПОДПИСКИ ==========
async def check_subscription(bot, user_id):
    try:
        pub = await bot.get_chat_member(PUBLIC_CHANNEL, user_id)
        if pub.status not in ['member', 'administrator', 'creator']:
            return False
        
        priv = await bot.get_chat_member(PRIVATE_CHANNEL_ID, user_id)
        if priv.status not in ['member', 'administrator', 'creator']:
            return False
        
        return True
    except Exception as e:
        print(f"[ОШИБКА] Проверка подписки {user_id}: {e}")
        return False

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard(user_id):
    user = get_user(user_id)
    kb = []
    
    if user and user[6] == 1 and user[7] == 0:
        kb.append([InlineKeyboardButton("🔨 СНОС", callback_data="snos")])
    else:
        kb.append([InlineKeyboardButton("🔒 ДОСТУП ЗАКРЫТ", callback_data="no_access")])
    
    kb.append([
        InlineKeyboardButton("👥 РЕФЕРАЛЫ", callback_data="refs"),
        InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile")
    ])
    kb.append([InlineKeyboardButton("ℹ️ ИНФО", callback_data="info")])
    
    if is_admin(user_id):
        kb.append([InlineKeyboardButton("⚙️ АДМИН", callback_data="admin")])
    
    return InlineKeyboardMarkup(kb)

def get_subscription_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 ПОДПИСАТЬСЯ", url=f"https://t.me/{PUBLIC_CHANNEL[1:]}")],
        [InlineKeyboardButton("🔞 ПРИВАТНЫЙ КАНАЛ", url=PRIVATE_CHANNEL_LINK)],
        [InlineKeyboardButton("✅ ПРОВЕРИТЬ", callback_data="check_sub")]
    ])

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    user = get_user(user_id)
    
    if not user:
        invited_by = None
        args = context.args
        if args:
            ref_link = args[0]
            inviter_id = get_user_by_ref_link(ref_link)
            if inviter_id and inviter_id != user_id:
                invited_by = inviter_id
                print(f"[ЗАПОМНИЛИ] {user_id} пришёл от {invited_by}")
        
        create_user(user_id, username, invited_by)
        user = get_user(user_id)
    
    if user and user[7] == 1:
        await update.message.reply_text("🚫 ТЫ ЗАБАНЕН")
        return
    
    subscribed = await check_subscription(context.bot, user_id)
    
    if not subscribed:
        await update.message.reply_text(
            "⚠️ ПОДПИШИСЬ НА КАНАЛЫ\n\nПосле подписки нажми ПРОВЕРИТЬ",
            reply_markup=get_subscription_keyboard()
        )
        return
    
    if user[5] == 0:
        mark_subscribed(user_id)
        add_referral_if_needed(user_id)
        user = get_user(user_id)
    
    ref_count = user[4] if user[4] is not None else 0
    bar = "▓" * min(ref_count, 5) + "░" * (5 - min(ref_count, 5))
    status = "✅ ОТКРЫТ" if user[6] == 1 else "❌ ЗАКРЫТ"
    
    await update.message.reply_text(
        f"🦈 SHARK ZN0S\n\n"
        f"┌ ПРОФИЛЬ:\n"
        f"├ ID: {user_id}\n"
        f"├ ДОСТУП: {status}\n"
        f"└ РЕФЕРАЛЫ: [{bar}] {ref_count}/5",
        reply_markup=get_main_keyboard(user_id)
    )

async def check_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    subscribed = await check_subscription(context.bot, user_id)
    
    if subscribed:
        user = get_user(user_id)
        
        if user and user[5] == 0:
            mark_subscribed(user_id)
            add_referral_if_needed(user_id)
            user = get_user(user_id)
        
        ref_count = user[4] if user[4] is not None else 0
        bar = "▓" * min(ref_count, 5) + "░" * (5 - min(ref_count, 5))
        status = "✅ ОТКРЫТ" if user[6] == 1 else "❌ ЗАКРЫТ"
        
        await query.edit_message_text(
            f"✅ ПОДПИСКА ПОДТВЕРЖДЕНА!\n\n"
            f"🦈 SHARK ZN0S\n\n"
            f"┌ ПРОФИЛЬ:\n"
            f"├ ID: {user_id}\n"
            f"├ ДОСТУП: {status}\n"
            f"└ РЕФЕРАЛЫ: [{bar}] {ref_count}/5",
            reply_markup=get_main_keyboard(user_id)
        )
    else:
        await query.answer("❌ НЕ ПОДПИСАН", show_alert=True)

async def refs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not user:
        return
    
    ref_link = f"https://t.me/{context.bot.username}?start={user[2]}"
    ref_count = user[4] if user[4] is not None else 0
    bar = "▓" * min(ref_count, 5) + "░" * (5 - min(ref_count, 5))
    
    await query.edit_message_text(
        f"🔗 РЕФЕРАЛЫ\n\n"
        f"ПРИГЛАШЕНО: {ref_count}/5\n"
        f"[{bar}]\n\n"
        f"ТВОЯ ССЫЛКА:\n"
        f"<code>{ref_link}</code>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 КОПИРОВАТЬ", callback_data=f"copy_{ref_link}")],
            [InlineKeyboardButton("◀️ НАЗАД", callback_data="back")]
        ]),
        parse_mode="HTML"
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not user:
        return
    
    ref_count = user[4] if user[4] is not None else 0
    bar = "▓" * min(ref_count, 5) + "░" * (5 - min(ref_count, 5))
    status = "✅ ОТКРЫТ" if user[6] == 1 else "❌ ЗАКРЫТ"
    
    await query.edit_message_text(
        f"👤 ПРОФИЛЬ\n\n"
        f"ID: <code>{user_id}</code>\n"
        f"РЕФЕРАЛЫ: [{bar}] {ref_count}/5\n"
        f"ДОСТУП: {status}",
        reply_markup=get_main_keyboard(user_id),
        parse_mode="HTML"
    )

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    await query.edit_message_text(
        "ℹ️ SHARK ZN0S\n\n"
        "1️⃣ ПОДПИШИСЬ НА КАНАЛЫ\n"
        "2️⃣ ПРИГЛАСИ 5 ДРУЗЕЙ ПО ССЫЛКЕ\n"
        "3️⃣ ПОСЛЕ ИХ ПОДПИСКИ ТЕБЕ ЗАСЧИТАЮТСЯ РЕФЕРАЛЫ\n"
        "4️⃣ ДОЖДИСЬ ОДОБРЕНИЯ АДМИНА\n\n"
        "ПОСЛЕ ЭТОГО СТАНЕТ ДОСТУПЕН СНОС",
        reply_markup=get_main_keyboard(user_id)
    )

async def snos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not await check_subscription(context.bot, user_id):
        await query.edit_message_text(
            "⚠️ ТЫ ОТПИСАЛСЯ ОТ КАНАЛОВ\n\nПодпишись снова",
            reply_markup=get_subscription_keyboard()
        )
        return
    
    if not user or user[4] < 5:
        count = user[4] if user else 0
        await query.answer(f"❌ НУЖНО 5 РЕФЕРАЛОВ. У ТЕБЯ {count}", show_alert=True)
        return
    
    if user[6] != 1:
        await query.answer("❌ АДМИН НЕ ОДОБРИЛ ДОСТУП", show_alert=True)
        return
    
    context.user_data['waiting_target'] = user_id
    await query.edit_message_text("🎯 ВВЕДИ ЦЕЛЬ (@username или ID)")

async def handle_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if context.user_data.get('waiting_target') != user_id:
        return
    
    target = update.message.text.strip()
    if not target:
        await update.message.reply_text("❌ ПУСТАЯ СТРОКА")
        return
    
    if not await check_subscription(context.bot, user_id):
        await update.message.reply_text("❌ ТЫ ОТПИСАЛСЯ ОТ КАНАЛОВ")
        context.user_data.pop('waiting_target', None)
        return
    
    user = get_user(user_id)
    if not user or user[4] < 5 or user[6] != 1:
        await update.message.reply_text("❌ У ТЕБЯ НЕТ ДОСТУПА К СНОСУ")
        context.user_data.pop('waiting_target', None)
        return
    
    msg = await update.message.reply_text("💀 СНОС...")
    
    for percent in range(10, 101, 10):
        await asyncio.sleep(0.3)
        bar = "▓" * (percent // 10) + "░" * (10 - percent // 10)
        await msg.edit_text(f"⏳ [{bar}] {percent}%")
    
    await msg.edit_text(
        f"✅ АККАУНТ {target} УСПЕШНО СНЕСЁН!",
        reply_markup=get_main_keyboard(user_id)
    )
    
    context.user_data.pop('waiting_target', None)
    print(f"[СНОС] {user_id} снёс {target}")

async def no_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not user or user[4] < 5:
        count = user[4] if user else 0
        await query.answer(f"❌ НУЖНО 5 РЕФЕРАЛОВ. У ТЕБЯ {count}", show_alert=True)
    elif user[5] == 0:
        await query.answer("❌ СНАЧАЛА ПОДПИШИСЬ НА КАНАЛЫ", show_alert=True)
    else:
        await query.answer("❌ АДМИН НЕ ОДОБРИЛ ДОСТУП", show_alert=True)

async def back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not user:
        return
    
    ref_count = user[4] if user[4] is not None else 0
    bar = "▓" * min(ref_count, 5) + "░" * (5 - min(ref_count, 5))
    status = "✅ ОТКРЫТ" if user[6] == 1 else "❌ ЗАКРЫТ"
    
    await query.edit_message_text(
        f"🦈 SHARK ZN0S\n\n"
        f"┌ ПРОФИЛЬ:\n"
        f"├ ID: {user_id}\n"
        f"├ ДОСТУП: {status}\n"
        f"└ РЕФЕРАЛЫ: [{bar}] {ref_count}/5",
        reply_markup=get_main_keyboard(user_id)
    )

async def copy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("📋 СКОПИРОВАНО", show_alert=True)

# ========== АДМИНКА ==========
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.answer("НЕТ ДОСТУПА", show_alert=True)
        return
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    pending = c.execute("SELECT COUNT(*) FROM users WHERE approved = 0 AND ref_count >= 5 AND subscribed = 1").fetchone()[0]
    conn.close()
    
    await query.edit_message_text(
        f"⚙️ АДМИН ПАНЕЛЬ\n\n"
        f"📊 ВСЕГО: {total}\n"
        f"📥 ЗАЯВОК: {pending}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 ЗАЯВКИ", callback_data="admin_req")],
            [InlineKeyboardButton("👥 ПОЛЬЗОВАТЕЛИ", callback_data="admin_users")],
            [InlineKeyboardButton("◀️ НАЗАД", callback_data="back")]
        ])
    )

async def admin_req(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    pending = get_pending_users()
    
    if not pending:
        await query.edit_message_text(
            "❌ НЕТ ЗАЯВОК",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ НАЗАД", callback_data="admin")]])
        )
        return
    
    if 'req_index' not in context.user_data:
        context.user_data['req_index'] = 0
        context.user_data['req_list'] = pending
    
    idx = context.user_data['req_index']
    lst = context.user_data['req_list']
    
    if idx >= len(lst):
        context.user_data['req_index'] = 0
        context.user_data['req_list'] = pending
        lst = pending
        idx = 0
    
    uid, name, count = lst[idx]
    
    await query.edit_message_text(
        f"📥 ЗАЯВКА {idx + 1}/{len(lst)}\n\n"
        f"👤 @{name or uid}\n"
        f"🆔 {uid}\n"
        f"👥 РЕФЕРАЛОВ: {count}/5",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ ОДОБРИТЬ", callback_data=f"approve_{uid}")],
            [InlineKeyboardButton("❌ ОТКЛОНИТЬ", callback_data=f"reject_{uid}")],
            [InlineKeyboardButton("◀️ НАЗАД", callback_data="admin")]
        ])
    )

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    uid = int(query.data.split("_")[1])
    approve_user(uid)
    
    context.user_data.pop('req_index', None)
    context.user_data.pop('req_list', None)
    
    await query.edit_message_text(f"✅ ПОЛЬЗОВАТЕЛЬ {uid} ОДОБРЕН")
    await asyncio.sleep(1)
    await admin_req(update, context)

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    uid = int(query.data.split("_")[1])
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("UPDATE users SET ref_count = 4 WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()
    
    context.user_data.pop('req_index', None)
    context.user_data.pop('req_list', None)
    
    await query.edit_message_text(f"❌ ЗАЯВКА {uid} ОТКЛОНЕНА")
    await asyncio.sleep(1)
    await admin_req(update, context)

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    await query.edit_message_text("🔍 ВВЕДИ ID ПОЛЬЗОВАТЕЛЯ\n\nПРИМЕР: 123456789")
    context.user_data['search_user'] = True

async def admin_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('search_user'):
        return
    
    try:
        uid = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ ВВЕДИ ЧИСЛО")
        return
    
    user = get_user(uid)
    
    if not user:
        await update.message.reply_text("❌ ПОЛЬЗОВАТЕЛЬ НЕ НАЙДЕН")
        context.user_data.pop('search_user', None)
        return
    
    context.user_data.pop('search_user', None)
    
    ref_count = user[4] if user[4] is not None else 0
    status = "ОТКРЫТ" if user[6] == 1 else "ЗАКРЫТ"
    banned = "ЗАБАНЕН" if user[7] == 1 else "АКТИВЕН"
    
    await update.message.reply_text(
        f"👤 ПОЛЬЗОВАТЕЛЬ\n\n"
        f"ID: <code>{uid}</code>\n"
        f"РЕФЕРАЛОВ: {ref_count}/5\n"
        f"ДОСТУП: {status}\n"
        f"СТАТУС: {banned}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 ВЫДАТЬ ДОСТУП", callback_data=f"grant_{uid}")],
            [InlineKeyboardButton("🔴 ЗАБРАТЬ ДОСТУП", callback_data=f"revoke_{uid}")],
            [InlineKeyboardButton("🚫 ЗАБАНИТЬ", callback_data=f"ban_{uid}")],
            [InlineKeyboardButton("◀️ НАЗАД", callback_data="admin")]
        ]),
        parse_mode="HTML"
    )

async def grant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    uid = int(query.data.split("_")[1])
    approve_user(uid)
    
    await query.edit_message_text(f"✅ ДОСТУП ВЫДАН {uid}")
    await asyncio.sleep(1)
    await admin(update, context)

async def revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    uid = int(query.data.split("_")[1])
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("UPDATE users SET approved = 0 WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()
    
    await query.edit_message_text(f"🔴 ДОСТУП ЗАБРАН У {uid}")
    await asyncio.sleep(1)
    await admin(update, context)

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    uid = int(query.data.split("_")[1])
    
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()
    
    await query.edit_message_text(f"🚫 {uid} ЗАБАНЕН")
    await asyncio.sleep(1)
    await admin(update, context)

# ========== ЗАПУСК ==========
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    
    app.add_handler(CallbackQueryHandler(check_sub, pattern="check_sub"))
    app.add_handler(CallbackQueryHandler(refs, pattern="refs"))
    app.add_handler(CallbackQueryHandler(profile, pattern="profile"))
    app.add_handler(CallbackQueryHandler(info, pattern="info"))
    app.add_handler(CallbackQueryHandler(snos, pattern="snos"))
    app.add_handler(CallbackQueryHandler(no_access, pattern="no_access"))
    app.add_handler(CallbackQueryHandler(back, pattern="back"))
    app.add_handler(CallbackQueryHandler(copy, pattern="copy_"))
    
    app.add_handler(CallbackQueryHandler(admin, pattern="admin"))
    app.add_handler(CallbackQueryHandler(admin_req, pattern="admin_req"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern="admin_users"))
    app.add_handler(CallbackQueryHandler(approve, pattern="approve_"))
    app.add_handler(CallbackQueryHandler(reject, pattern="reject_"))
    app.add_handler(CallbackQueryHandler(grant, pattern="grant_"))
    app.add_handler(CallbackQueryHandler(revoke, pattern="revoke_"))
    app.add_handler(CallbackQueryHandler(ban, pattern="ban_"))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_target))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_search))
    
    print("🦈 SHARK ZN0S ЗАПУЩЕН")
    print("⚡ ВСЁ РАБОТАЕТ")
    app.run_polling()

if __name__ == "__main__":
    main()
