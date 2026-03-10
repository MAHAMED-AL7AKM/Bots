#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
بوت تليجرام متكامل: إدارة المغادرة + النشر التلقائي
نسخة محسنة بمظهر جذاب وأزرار واضحة
"""

import os
import json
import asyncio
import logging
from typing import Dict, Optional, Any, List

from cryptography.fernet import Fernet

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.errors import (
    RPCError,
    SessionPasswordNeeded,
    PhoneNumberInvalid,
    PhoneCodeInvalid,
    PhoneCodeExpired,
)

# ==================== إعداد التسجيل ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== الإعدادات العامة ====================
SESSIONS_FILE = "sessions.dat"
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")

# إنشاء مفتاح تشفير إذا لم يكن موجوداً
if not ENCRYPTION_KEY:
    key = Fernet.generate_key()
    print("=" * 60)
    print("لم يتم العثور على ENCRYPTION_KEY في متغيرات البيئة.")
    print("تم إنشاء مفتاح تشفير جديد. يجب حفظه لاستخدامه في المرات القادمة:")
    print(key.decode())
    print("=" * 60)
    ENCRYPTION_KEY = key.decode()

try:
    cipher = Fernet(ENCRYPTION_KEY.encode())
except Exception:
    raise ValueError("ENCRYPTION_KEY غير صالح. يجب أن يكون 32 بايت بصيغة base64.")

# ==================== إدارة التخزين المشفر ====================
def load_sessions() -> Dict[int, Dict[str, Any]]:
    if not os.path.exists(SESSIONS_FILE):
        return {}
    try:
        with open(SESSIONS_FILE, "rb") as f:
            encrypted_data = f.read()
        decrypted_data = cipher.decrypt(encrypted_data)
        sessions = json.loads(decrypted_data)
        return {int(k): v for k, v in sessions.items()}
    except Exception as e:
        logger.error(f"خطأ في تحميل الجلسات: {e}")
        return {}

def save_sessions(sessions: Dict[int, Dict[str, Any]]) -> None:
    try:
        data = {str(k): v for k, v in sessions.items()}
        json_data = json.dumps(data, ensure_ascii=False, indent=2).encode()
        encrypted_data = cipher.encrypt(json_data)
        with open(SESSIONS_FILE, "wb") as f:
            f.write(encrypted_data)
    except Exception as e:
        logger.error(f"خطأ في حفظ الجلسات: {e}")

# تحميل الجلسات
user_sessions = load_sessions()

# مهام النشر التلقائي
auto_post_tasks: Dict[int, asyncio.Task] = {}

# ==================== حالات المحادثة ====================
(
    MAIN_MENU,
    CHANNEL_SECTION,
    LIST_CHANNELS,
    LIST_GROUPS,
    AUTO_POST_MENU,
    AUTO_POST_SET_GROUPS,
    AUTO_POST_SET_MESSAGE,
    AUTO_POST_SET_INTERVAL,
    AWAITING_API_ID,
    AWAITING_API_HASH,
    AWAITING_PHONE,
    AWAITING_CODE,
    AWAITING_PASSWORD,
) = range(13)

login_data: Dict[int, dict] = {}

# ==================== توكن البوت ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    BOT_TOKEN = input("الرجاء إدخال توكن البوت: ").strip()
    if not BOT_TOKEN:
        raise ValueError("لا يمكن تشغيل البوت بدون توكن.")

# ==================== دوال مساعدة ====================
def get_user_session_data(user_id: int) -> Optional[Dict]:
    data = user_sessions.get(user_id)
    if isinstance(data, dict) and "session" in data and "api_id" in data and "api_hash" in data:
        return data
    return None

async def create_pyrogram_client(
    api_id: int, api_hash: str, session_string: Optional[str] = None
) -> Client:
    if session_string:
        return Client(":memory:", session_string=session_string, api_id=api_id, api_hash=api_hash)
    else:
        return Client(":memory:", api_id=api_id, api_hash=api_hash)

async def remove_chat_from_list(context, chat_id: int):
    for lst_name in ["channels_list", "groups_list", "auto_groups_list"]:
        lst = context.user_data.get(lst_name, [])
        context.user_data[lst_name] = [item for item in lst if item[0] != chat_id]

# ==================== دوال النشر التلقائي ====================
async def auto_post_worker(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"بدء النشر التلقائي للمستخدم {user_id}")
    failure_count: Dict[int, int] = {}

    while True:
        user_data = get_user_session_data(user_id)
        if not user_data:
            logger.warning(f"المستخدم {user_id} ليس لديه جلسة، إيقاف النشر")
            break

        auto_settings = user_data.get("auto_post")
        if not auto_settings or not auto_settings.get("enabled"):
            logger.info(f"النشر التلقائي للمستخدم {user_id} معطل")
            break

        groups = auto_settings.get("groups", [])
        message = auto_settings.get("message")
        interval = auto_settings.get("interval", 60)

        if not groups or not message:
            logger.warning(f"إعدادات غير مكتملة للمستخدم {user_id}")
            break

        api_id = user_data["api_id"]
        api_hash = user_data["api_hash"]
        session_str = user_data["session"]

        client = await create_pyrogram_client(api_id, api_hash, session_str)
        groups_to_remove: List[int] = []

        try:
            await client.connect()
            logger.info(f"تم الاتصال، جاري الإرسال إلى {len(groups)} مجموعة")

            for chat_id in groups:
                try:
                    await client.send_message(chat_id, message)
                    logger.info(f"تم إرسال رسالة إلى {chat_id}")
                    failure_count.pop(chat_id, None)
                except RPCError as e:
                    logger.error(f"فشل إرسال الرسالة إلى {chat_id}: {e}")
                    err_str = str(e)
                    if any(x in err_str for x in ["USER_NOT_PARTICIPANT", "PEER_ID_INVALID", "CHAT_ID_INVALID"]):
                        failure_count[chat_id] = failure_count.get(chat_id, 0) + 1
                        if failure_count[chat_id] >= 3:
                            groups_to_remove.append(chat_id)
                            logger.info(f"تمت إضافة المجموعة {chat_id} للحذف بعد 3 محاولات فاشلة")
                except Exception as e:
                    logger.error(f"خطأ غير متوقع مع {chat_id}: {e}")

                await asyncio.sleep(2)  # مهلة بين الرسائل

        except Exception as e:
            logger.error(f"خطأ في اتصال العميل: {e}")
        finally:
            await client.disconnect()

        if groups_to_remove:
            user_data = get_user_session_data(user_id)
            if user_data and "auto_post" in user_data:
                current_groups = user_data["auto_post"].get("groups", [])
                updated_groups = [g for g in current_groups if g not in groups_to_remove]
                user_data["auto_post"]["groups"] = updated_groups
                save_sessions(user_sessions)
                logger.info(f"تمت إزالة {len(groups_to_remove)} مجموعة غير صالحة للمستخدم {user_id}")

        logger.info(f"انتهت دورة النشر، انتظار {interval} ثانية")
        await asyncio.sleep(interval)

def stop_auto_post(user_id: int):
    task = auto_post_tasks.pop(user_id, None)
    if task:
        task.cancel()
        logger.info(f"تم إلغاء مهمة النشر للمستخدم {user_id}")

def start_auto_post(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    stop_auto_post(user_id)
    task = asyncio.create_task(auto_post_worker(user_id, context))
    auto_post_tasks[user_id] = task
    logger.info(f"تم بدء مهمة النشر للمستخدم {user_id}")

# ==================== دوال النصوص المنسقة ====================
def get_auto_menu_text(user_data: dict) -> str:
    auto = user_data.get("auto_post", {})
    enabled = auto.get("enabled", False)
    groups_count = len(auto.get("groups", []))
    msg_preview = (auto.get("message", "")[:30] + "…") if auto.get("message") else "غير محددة"
    interval = auto.get("interval", 60)

    status_emoji = "🟢" if enabled else "🔴"
    status_text = "مفعل" if enabled else "متوقف"

    return (
        f"✦ **إعدادات النشر التلقائي** ✦\n\n"
        f"{status_emoji} **الحالة:** {status_text}\n"
        f"👥 **المجموعات:** {groups_count}\n"
        f"📝 **الرسالة:** `{msg_preview}`\n"
        f"⏱ **الفاصل:** {interval} ثانية"
    )

# ==================== لوحات المفاتيح ====================
def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🚪 إدارة المغادرة", callback_data="channel_section")],
        [InlineKeyboardButton("📢 النشر التلقائي", callback_data="auto_post_menu")],
        [InlineKeyboardButton("ℹ️ معلومات الحساب", callback_data="account_info")],
        [InlineKeyboardButton("🔐 تسجيل الخروج", callback_data="logout")],
    ]
    return InlineKeyboardMarkup(keyboard)

def channel_section_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📢 مغادرة كل القنوات", callback_data="leave_all_channels")],
        [InlineKeyboardButton("👥 مغادرة كل الجروبات", callback_data="leave_all_groups")],
        [InlineKeyboardButton("📋 عرض القنوات", callback_data="list_channels")],
        [InlineKeyboardButton("🗂 عرض الجروبات", callback_data="list_groups")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(keyboard)

def auto_post_menu_keyboard(user_data) -> InlineKeyboardMarkup:
    auto = user_data.get("auto_post", {})
    enabled = auto.get("enabled", False)
    groups_count = len(auto.get("groups", []))
    has_message = bool(auto.get("message"))

    keyboard = [
        [InlineKeyboardButton("📋 اختيار المجموعات", callback_data="auto_set_groups")],
        [InlineKeyboardButton("✏️ كتابة الرسالة", callback_data="auto_set_message")],
        [InlineKeyboardButton("⏱ ضبط الفاصل الزمني", callback_data="auto_set_interval")],
    ]

    if enabled:
        keyboard.append([InlineKeyboardButton("⏸️ إيقاف النشر", callback_data="auto_stop")])
    else:
        if groups_count > 0 and has_message:
            keyboard.append([InlineKeyboardButton("▶️ بدء النشر", callback_data="auto_start")])

    keyboard.append([InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

# ==================== بداية المحادثة / تسجيل الدخول ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id

    if get_user_session_data(user_id):
        await update.message.reply_text(
            "✦ **مرحباً بعودتك!** ✦\n\nاختر من القائمة أدناه:",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown"
        )
        return MAIN_MENU

    if user_id in login_data:
        await update.message.reply_text(
            "⚠️ لديك عملية تسجيل دخول غير مكتملة. أرسل /cancel لإلغائها ثم أرسل /start مرة أخرى."
        )
        return ConversationHandler.END

    login_data[user_id] = {}
    await update.message.reply_text(
        "✦ **تسجيل الدخول إلى حساب التليجرام** ✦\n\n"
        "الرجاء إدخال **API ID** الخاص بك (من my.telegram.org).\n"
        "إذا لم يكن لديك، احصل عليه من: https://my.telegram.org/apps"
    )
    return AWAITING_API_ID

# ... باقي دوال تسجيل الدخول (receive_api_id, receive_api_hash, ...) كما هي دون تغيير ...

# ==================== معالجات القوائم الرئيسية ====================
async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if query.data == "channel_section":
        await query.edit_message_text(
            "✦ **إدارة المغادرة** ✦\n\nاختر العملية التي تريدها:",
            reply_markup=channel_section_keyboard(),
            parse_mode="Markdown"
        )
        return CHANNEL_SECTION

    elif query.data == "auto_post_menu":
        user_data = get_user_session_data(user_id)
        if not user_data:
            await query.edit_message_text("❌ الجلسة غير موجودة. أرسل /start مرة أخرى.")
            return ConversationHandler.END

        text = get_auto_menu_text(user_data)
        await query.edit_message_text(
            text,
            reply_markup=auto_post_menu_keyboard(user_data),
            parse_mode="Markdown"
        )
        return AUTO_POST_MENU

    elif query.data == "account_info":
        user_data = get_user_session_data(user_id)
        if not user_data:
            await query.edit_message_text("❌ الجلسة غير موجودة. أرسل /start مرة أخرى.")
            return ConversationHandler.END

        info = (
            f"✦ **معلومات الحساب** ✦\n\n"
            f"📌 **الاسم:** {user_data.get('first_name', 'غير معروف')}\n"
        )
        if user_data.get('username'):
            info += f"👤 **اليوزرنيم:** @{user_data['username']}\n"
        info += f"📱 **الرقم:** {user_data.get('phone', 'غير معروف')}"
        await query.edit_message_text(info, reply_markup=main_menu_keyboard(), parse_mode="Markdown")
        return MAIN_MENU

    elif query.data == "logout":
        stop_auto_post(user_id)
        user_sessions.pop(user_id, None)
        save_sessions(user_sessions)
        await query.edit_message_text("🔐 تم تسجيل الخروج. أرسل /start للدخول مجدداً.")
        return ConversationHandler.END

    return MAIN_MENU

# ==================== قسم إدارة المغادرة ====================
# (كما هو دون تغيير كبير، مع إضافة تنسيق النصوص)
async def channel_section_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_data = get_user_session_data(user_id)

    if not user_data:
        await query.edit_message_text("❌ الجلسة غير موجودة. أرسل /start.")
        return ConversationHandler.END

    session_str = user_data["session"]
    api_id = user_data["api_id"]
    api_hash = user_data["api_hash"]

    client = await create_pyrogram_client(api_id, api_hash, session_str)

    if query.data == "leave_all_channels":
        await query.edit_message_text("⏳ جاري مغادرة كل القنوات...")
        try:
            await client.connect()
            left_count = 0
            async for dialog in client.get_dialogs():
                if dialog.chat.type == ChatType.CHANNEL:
                    try:
                        await client.leave_chat(dialog.chat.id)
                        left_count += 1
                    except RPCError as e:
                        logger.error(f"خطأ في مغادرة {dialog.chat.title}: {e}")
            await query.edit_message_text(
                f"✅ تمت مغادرة {left_count} قناة بنجاح.",
                reply_markup=channel_section_keyboard(),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"خطأ: {e}")
            await query.edit_message_text(f"❌ حدث خطأ: {e}", reply_markup=channel_section_keyboard())
        finally:
            await client.disconnect()
        return CHANNEL_SECTION

    elif query.data == "leave_all_groups":
        await query.edit_message_text("⏳ جاري مغادرة كل الجروبات...")
        try:
            await client.connect()
            left_count = 0
            async for dialog in client.get_dialogs():
                if dialog.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                    try:
                        await client.leave_chat(dialog.chat.id)
                        left_count += 1
                    except RPCError as e:
                        logger.error(f"خطأ في مغادرة {dialog.chat.title}: {e}")
            await query.edit_message_text(
                f"✅ تمت مغادرة {left_count} جروب بنجاح.",
                reply_markup=channel_section_keyboard(),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"خطأ: {e}")
            await query.edit_message_text(f"❌ حدث خطأ: {e}", reply_markup=channel_section_keyboard())
        finally:
            await client.disconnect()
        return CHANNEL_SECTION

    elif query.data == "list_channels":
        await query.edit_message_text("⏳ جاري تحميل القنوات...")
        try:
            await client.connect()
            channels = []
            async for dialog in client.get_dialogs():
                if dialog.chat.type == ChatType.CHANNEL:
                    channels.append((dialog.chat.id, dialog.chat.title or "بدون عنوان"))
            context.user_data["channels_list"] = channels
            context.user_data["channels_page"] = 0
            context.user_data["current_list_state"] = LIST_CHANNELS
            await show_channels_page(update, context)
        except Exception as e:
            logger.error(f"خطأ: {e}")
            await query.edit_message_text(f"❌ حدث خطأ: {e}", reply_markup=channel_section_keyboard())
        finally:
            await client.disconnect()
        return LIST_CHANNELS

    elif query.data == "list_groups":
        await query.edit_message_text("⏳ جاري تحميل الجروبات...")
        try:
            await client.connect()
            groups = []
            async for dialog in client.get_dialogs():
                if dialog.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                    groups.append((dialog.chat.id, dialog.chat.title or "بدون عنوان"))
            context.user_data["groups_list"] = groups
            context.user_data["groups_page"] = 0
            context.user_data["current_list_state"] = LIST_GROUPS
            await show_groups_page(update, context)
        except Exception as e:
            logger.error(f"خطأ: {e}")
            await query.edit_message_text(f"❌ حدث خطأ: {e}", reply_markup=channel_section_keyboard())
        finally:
            await client.disconnect()
        return LIST_GROUPS

    elif query.data == "back_to_main":
        await query.edit_message_text(
            "✦ **القائمة الرئيسية** ✦\n\nاختر أحد الأقسام:",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown"
        )
        return MAIN_MENU

    return CHANNEL_SECTION

# ==================== عرض القوائم مع الترقيم ====================
async def show_channels_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    channels = context.user_data.get("channels_list", [])
    page = context.user_data.get("channels_page", 0)
    items_per_page = 10
    total_pages = (len(channels) + items_per_page - 1) // items_per_page

    start = page * items_per_page
    end = start + items_per_page
    page_channels = channels[start:end]

    keyboard = []
    for chat_id, title in page_channels:
        btn_text = title[:30] + "…" if len(title) > 30 else title
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"leave_chat:{chat_id}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data="channels_page_prev"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data="channels_page_next"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("🔙 رجوع لقسم المغادرة", callback_data="back_to_channel_section")])

    await query.edit_message_text(
        f"✦ **قائمة القنوات** ✦\n(صفحة {page+1}/{total_pages})",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def show_groups_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    groups = context.user_data.get("groups_list", [])
    page = context.user_data.get("groups_page", 0)
    items_per_page = 10
    total_pages = (len(groups) + items_per_page - 1) // items_per_page

    start = page * items_per_page
    end = start + items_per_page
    page_groups = groups[start:end]

    keyboard = []
    for chat_id, title in page_groups:
        btn_text = title[:30] + "…" if len(title) > 30 else title
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"leave_chat:{chat_id}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data="groups_page_prev"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data="groups_page_next"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("🔙 رجوع لقسم المغادرة", callback_data="back_to_channel_section")])

    await query.edit_message_text(
        f"✦ **قائمة الجروبات** ✦\n(صفحة {page+1}/{total_pages})",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def list_navigation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_data = get_user_session_data(user_id)
    if not user_data:
        await query.edit_message_text("❌ الجلسة غير موجودة. أرسل /start.")
        return ConversationHandler.END

    data = query.data

    if data.startswith("channels_page_"):
        if data == "channels_page_next":
            context.user_data["channels_page"] = context.user_data.get("channels_page", 0) + 1
        elif data == "channels_page_prev":
            context.user_data["channels_page"] = context.user_data.get("channels_page", 0) - 1
        await show_channels_page(update, context)
        return LIST_CHANNELS

    if data.startswith("groups_page_"):
        if data == "groups_page_next":
            context.user_data["groups_page"] = context.user_data.get("groups_page", 0) + 1
        elif data == "groups_page_prev":
            context.user_data["groups_page"] = context.user_data.get("groups_page", 0) - 1
        await show_groups_page(update, context)
        return LIST_GROUPS

    if data.startswith("leave_chat:"):
        chat_id_str = data.split(":")[1]
        try:
            chat_id = int(chat_id_str)
        except ValueError:
            await query.edit_message_text("❌ معرف الدردشة غير صالح.")
            return context.user_data.get("current_list_state", CHANNEL_SECTION)

        session_str = user_data["session"]
        api_id = user_data["api_id"]
        api_hash = user_data["api_hash"]
        client = await create_pyrogram_client(api_id, api_hash, session_str)

        try:
            await client.connect()
            await client.leave_chat(chat_id)
            await remove_chat_from_list(context, chat_id)
            await query.edit_message_text("✅ تمت المغادرة بنجاح.")
        except RPCError as e:
            err_str = str(e)
            if "USER_NOT_PARTICIPANT" in err_str:
                await remove_chat_from_list(context, chat_id)
                await query.edit_message_text("⚠️ أنت لست عضوًا في هذه الدردشة. تمت إزالتها من القائمة.")
            elif "CHAT_ID_INVALID" in err_str:
                await remove_chat_from_list(context, chat_id)
                await query.edit_message_text("⚠️ معرف الدردشة غير صالح. تمت إزالتها من القائمة.")
            else:
                await query.edit_message_text(f"❌ فشلت المغادرة: {e}")
        except Exception as e:
            await query.edit_message_text(f"❌ حدث خطأ غير متوقع: {e}")
        finally:
            await client.disconnect()

        if "channels_list" in context.user_data:
            await show_channels_page(update, context)
            return LIST_CHANNELS
        elif "groups_list" in context.user_data:
            await show_groups_page(update, context)
            return LIST_GROUPS
        else:
            await query.edit_message_text(
                "✦ **إدارة المغادرة** ✦",
                reply_markup=channel_section_keyboard(),
                parse_mode="Markdown"
            )
            return CHANNEL_SECTION

    if data == "back_to_channel_section":
        await query.edit_message_text(
            "✦ **إدارة المغادرة** ✦\n\nاختر العملية التي تريدها:",
            reply_markup=channel_section_keyboard(),
            parse_mode="Markdown"
        )
        return CHANNEL_SECTION

    return CHANNEL_SECTION

# ==================== قسم النشر التلقائي ====================
async def auto_post_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_data = get_user_session_data(user_id)
    if not user_data:
        await query.edit_message_text("❌ الجلسة غير موجودة. أرسل /start.")
        return ConversationHandler.END

    data = query.data

    if data == "auto_set_groups":
        session_str = user_data["session"]
        api_id = user_data["api_id"]
        api_hash = user_data["api_hash"]
        client = await create_pyrogram_client(api_id, api_hash, session_str)

        await query.edit_message_text("⏳ جاري تحميل الجروبات...")
        try:
            await client.connect()
            groups = []
            async for dialog in client.get_dialogs():
                if dialog.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                    groups.append((dialog.chat.id, dialog.chat.title or "بدون عنوان"))
            context.user_data["auto_groups_list"] = groups
            context.user_data["auto_groups_page"] = 0
            selected = set(user_data.get("auto_post", {}).get("groups", []))
            context.user_data["auto_selected_groups"] = selected
            await show_auto_groups_page(update, context)
        except Exception as e:
            logger.error(f"خطأ في تحميل الجروبات: {e}")
            await query.edit_message_text(f"❌ حدث خطأ: {e}", reply_markup=auto_post_menu_keyboard(user_data))
        finally:
            await client.disconnect()
        return AUTO_POST_SET_GROUPS

    elif data == "auto_set_message":
        await query.edit_message_text(
            "✏️ **أرسل الرسالة التي تريد نشرها** (يمكنك استخدام Markdown):\n"
            "لإلغاء الأمر أرسل /cancel",
            parse_mode="Markdown"
        )
        return AUTO_POST_SET_MESSAGE

    elif data == "auto_set_interval":
        await query.edit_message_text(
            "⏱ **أرسل الفاصل الزمني بين كل دورة نشر** (بالثواني، رقم فقط):\n"
            "لإلغاء الأمر أرسل /cancel",
            parse_mode="Markdown"
        )
        return AUTO_POST_SET_INTERVAL

    elif data == "auto_start":
        auto = user_data.get("auto_post", {})
        if auto.get("enabled"):
            await query.edit_message_text("⚠️ النشر مفعل بالفعل.")
        else:
            if not auto.get("groups") or not auto.get("message"):
                await query.edit_message_text("⚠️ يجب تحديد المجموعات والرسالة أولاً.")
            else:
                user_data["auto_post"]["enabled"] = True
                save_sessions(user_sessions)
                start_auto_post(user_id, context)
                text = get_auto_menu_text(user_data)
                await query.edit_message_text(
                    text,
                    reply_markup=auto_post_menu_keyboard(user_data),
                    parse_mode="Markdown"
                )
        return AUTO_POST_MENU

    elif data == "auto_stop":
        user_data["auto_post"]["enabled"] = False
        save_sessions(user_sessions)
        stop_auto_post(user_id)
        text = get_auto_menu_text(user_data)
        await query.edit_message_text(
            text,
            reply_markup=auto_post_menu_keyboard(user_data),
            parse_mode="Markdown"
        )
        return AUTO_POST_MENU

    elif data == "back_to_main":
        await query.edit_message_text(
            "✦ **القائمة الرئيسية** ✦\n\nاختر أحد الأقسام:",
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown"
        )
        return MAIN_MENU

    return AUTO_POST_MENU

async def show_auto_groups_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    groups = context.user_data.get("auto_groups_list", [])
    page = context.user_data.get("auto_groups_page", 0)
    selected = context.user_data.get("auto_selected_groups", set())
    items_per_page = 8
    total_pages = (len(groups) + items_per_page - 1) // items_per_page

    start = page * items_per_page
    end = start + items_per_page
    page_groups = groups[start:end]

    keyboard = []
    for chat_id, title in page_groups:
        mark = "✅ " if chat_id in selected else ""
        btn_text = f"{mark}{title[:25]}…" if len(title) > 25 else f"{mark}{title}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"auto_toggle_group:{chat_id}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data="auto_groups_page_prev"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data="auto_groups_page_next"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("✅ حفظ التحديد", callback_data="auto_save_groups")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="auto_back_to_menu")])

    await query.edit_message_text(
        f"✦ **اختر المجموعات** ✦\n(صفحة {page+1}/{total_pages})",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def auto_groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "auto_groups_page_next":
        context.user_data["auto_groups_page"] = context.user_data.get("auto_groups_page", 0) + 1
        await show_auto_groups_page(update, context)
        return AUTO_POST_SET_GROUPS

    elif data == "auto_groups_page_prev":
        context.user_data["auto_groups_page"] = context.user_data.get("auto_groups_page", 0) - 1
        await show_auto_groups_page(update, context)
        return AUTO_POST_SET_GROUPS

    elif data.startswith("auto_toggle_group:"):
        chat_id = int(data.split(":")[1])
        selected = context.user_data.get("auto_selected_groups", set())
        if chat_id in selected:
            selected.remove(chat_id)
        else:
            selected.add(chat_id)
        context.user_data["auto_selected_groups"] = selected
        await show_auto_groups_page(update, context)
        return AUTO_POST_SET_GROUPS

    elif data == "auto_save_groups":
        user_id = update.effective_user.id
        selected = context.user_data.get("auto_selected_groups", set())

        user_data = get_user_session_data(user_id)
        if not user_data:
            await query.edit_message_text("❌ حدث خطأ في استرجاع بيانات المستخدم.")
            return AUTO_POST_MENU

        api_id = user_data["api_id"]
        api_hash = user_data["api_hash"]
        session_str = user_data["session"]
        client = await create_pyrogram_client(api_id, api_hash, session_str)
        valid_groups = []
        try:
            await client.connect()
            for chat_id in selected:
                try:
                    chat = await client.get_chat(chat_id)
                    if chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                        valid_groups.append(chat_id)
                    else:
                        logger.warning(f"المجموعة {chat_id} ليست من النوع المتوقع")
                except Exception as e:
                    logger.warning(f"المجموعة {chat_id} غير صالحة: {e}")
        except Exception as e:
            logger.error(f"خطأ في الاتصال أثناء التحقق: {e}")
        finally:
            await client.disconnect()

        if "auto_post" not in user_data:
            user_data["auto_post"] = {}
        user_data["auto_post"]["groups"] = valid_groups
        user_data["auto_post"]["enabled"] = False
        save_sessions(user_sessions)
        stop_auto_post(user_id)

        invalid_count = len(selected) - len(valid_groups)
        msg = f"✅ تم حفظ {len(valid_groups)} مجموعة صالحة."
        if invalid_count > 0:
            msg += f"\n⚠️ تم تجاهل {invalid_count} مجموعة غير صالحة."

        text = get_auto_menu_text(user_data)
        await query.edit_message_text(
            f"{msg}\n\n{text}",
            reply_markup=auto_post_menu_keyboard(user_data),
            parse_mode="Markdown"
        )
        return AUTO_POST_MENU

    elif data == "auto_back_to_menu":
        user_id = update.effective_user.id
        user_data = get_user_session_data(user_id)
        text = get_auto_menu_text(user_data)
        await query.edit_message_text(
            text,
            reply_markup=auto_post_menu_keyboard(user_data),
            parse_mode="Markdown"
        )
        return AUTO_POST_MENU

    return AUTO_POST_SET_GROUPS

async def auto_set_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message.text

    user_data = get_user_session_data(user_id)
    if user_data:
        if "auto_post" not in user_data:
            user_data["auto_post"] = {}
        user_data["auto_post"]["message"] = message
        user_data["auto_post"]["enabled"] = False
        save_sessions(user_sessions)
        stop_auto_post(user_id)

    text = get_auto_menu_text(user_data)
    await update.message.reply_text(
        text,
        reply_markup=auto_post_menu_keyboard(user_data),
        parse_mode="Markdown"
    )
    return AUTO_POST_MENU

async def auto_set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text("❌ الرجاء إدخال رقم صحيح (بالثواني):")
        return AUTO_POST_SET_INTERVAL

    interval = int(text)
    if interval < 5:
        await update.message.reply_text("⚠️ يجب أن يكون الفاصل 5 ثوانٍ على الأقل.")
        return AUTO_POST_SET_INTERVAL

    user_data = get_user_session_data(user_id)
    if user_data:
        if "auto_post" not in user_data:
            user_data["auto_post"] = {}
        user_data["auto_post"]["interval"] = interval
        user_data["auto_post"]["enabled"] = False
        save_sessions(user_sessions)
        stop_auto_post(user_id)

    text = get_auto_menu_text(user_data)
    await update.message.reply_text(
        text,
        reply_markup=auto_post_menu_keyboard(user_data),
        parse_mode="Markdown"
    )
    return AUTO_POST_MENU

# ==================== معالج الإلغاء ====================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    login_data.pop(user_id, None)
    client = login_data.get(user_id, {}).get("client")
    if client and client.is_connected:
        await client.disconnect()
    await update.message.reply_text("❌ تم الإلغاء. أرسل /start للبدء مجدداً.")
    return ConversationHandler.END

# ==================== التشغيل الرئيسي ====================
def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            AWAITING_API_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_api_id)],
            AWAITING_API_HASH: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_api_hash)],
            AWAITING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
            AWAITING_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_code)],
            AWAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_password)],
            MAIN_MENU: [CallbackQueryHandler(main_menu_handler, pattern="^(channel_section|auto_post_menu|account_info|logout)$")],
            CHANNEL_SECTION: [CallbackQueryHandler(channel_section_handler)],
            LIST_CHANNELS: [CallbackQueryHandler(list_navigation_handler)],
            LIST_GROUPS: [CallbackQueryHandler(list_navigation_handler)],
            AUTO_POST_MENU: [CallbackQueryHandler(auto_post_menu_handler, pattern="^(auto_set_groups|auto_set_message|auto_set_interval|auto_start|auto_stop|back_to_main)$")],
            AUTO_POST_SET_GROUPS: [CallbackQueryHandler(auto_groups_handler)],
            AUTO_POST_SET_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, auto_set_message)],
            AUTO_POST_SET_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, auto_set_interval)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":
    main()
