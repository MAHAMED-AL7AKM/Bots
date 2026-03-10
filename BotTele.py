import os
import json
import asyncio
import logging
from typing import Dict, Optional, Any, List
from datetime import datetime

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

# إعداد التسجيل
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== الإعدادات ====================
SESSIONS_FILE = "sessions.dat"

# مفتاح التشفير (يُفضل أخذه من متغير بيئة)
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    key = Fernet.generate_key()
    print("=" * 60)
    print("لم يتم العثور على ENCRYPTION_KEY في متغيرات البيئة.")
    print("تم إنشاء مفتاح تشفير جديد. يجب حفظه لاستخدامه في المرات القادمة:")
    print(key.decode())
    print("=" * 60)
    ENCRYPTION_KEY = key.decode()
else:
    try:
        Fernet(ENCRYPTION_KEY.encode())
    except Exception:
        raise ValueError("ENCRYPTION_KEY غير صالح. يجب أن يكون 32 بايت مشفرة base64.")

cipher = Fernet(ENCRYPTION_KEY.encode())

# ==================== إدارة التخزين المشفر ====================
def load_sessions() -> Dict[int, Dict[str, Any]]:
    """تحميل الجلسات من الملف المشفر وإرجاع قاموس."""
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
    """حفظ الجلسات في الملف المشفر."""
    try:
        data = {str(k): v for k, v in sessions.items()}
        json_data = json.dumps(data, ensure_ascii=False).encode()
        encrypted_data = cipher.encrypt(json_data)
        with open(SESSIONS_FILE, "wb") as f:
            f.write(encrypted_data)
    except Exception as e:
        logger.error(f"خطأ في حفظ الجلسات: {e}")

# تحميل الجلسات عند بدء التشغيل
user_sessions = load_sessions()

# قاموس لتخزين مهام النشر التلقائي لكل مستخدم
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
    AUTO_POST_CONFIRM,
    AWAITING_API_ID,
    AWAITING_API_HASH,
    AWAITING_PHONE,
    AWAITING_CODE,
    AWAITING_PASSWORD,
) = range(14)

# تخزين مؤقت لبيانات الدخول
login_data: Dict[int, dict] = {}

# ==================== توكن البوت ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    BOT_TOKEN = input("الرجاء إدخال توكن البوت: ").strip()
    if not BOT_TOKEN:
        raise ValueError("لا يمكن تشغيل البوت بدون توكن.")

# ==================== دوال مساعدة ====================
def get_user_session_data(user_id: int) -> Optional[Dict]:
    """إرجاع بيانات جلسة المستخدم إذا كانت موجودة وصالحة"""
    data = user_sessions.get(user_id)
    if isinstance(data, dict) and "session" in data and "api_id" in data and "api_hash" in data:
        return data
    return None

async def create_pyrogram_client(
    api_id: int, api_hash: str, session_string: Optional[str] = None
) -> Client:
    """إنشاء عميل pyrogram (بدون اتصال)"""
    if session_string:
        return Client(":memory:", session_string=session_string, api_id=api_id, api_hash=api_hash)
    else:
        return Client(":memory:", api_id=api_id, api_hash=api_hash)

async def validate_session(session_string: str, api_id: int, api_hash: str) -> bool:
    """التحقق من صحة session string"""
    client = await create_pyrogram_client(api_id, api_hash, session_string)
    try:
        await client.connect()
        me = await client.get_me()
        return me is not None
    except Exception:
        return False
    finally:
        await client.disconnect()

# دوال مساعدة للقوائم
async def remove_chat_from_list(context, chat_id: int):
    """إزالة دردشة من القوائم المخزنة في context"""
    for lst_name in ["channels_list", "groups_list", "auto_groups_list"]:
        lst = context.user_data.get(lst_name, [])
        context.user_data[lst_name] = [item for item in lst if item[0] != chat_id]

async def refresh_current_list(update: Update, context):
    """إعادة عرض القائمة الحالية بعد التعديل"""
    query = update.callback_query
    if "channels_list" in context.user_data:
        await show_channels_page(update, context)
        return LIST_CHANNELS
    elif "groups_list" in context.user_data:
        await show_groups_page(update, context)
        return LIST_GROUPS
    elif "auto_groups_list" in context.user_data:
        await show_auto_groups_page(update, context)
        return AUTO_POST_SET_GROUPS
    else:
        await query.edit_message_text(
            "العودة للقسم", reply_markup=main_menu_keyboard()
        )
        return MAIN_MENU

# دوال النشر التلقائي
async def auto_post_worker(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """مهمة خلفية لإرسال الرسائل بشكل دوري"""
    logger.info(f"بدء النشر التلقائي للمستخدم {user_id}")
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
        try:
            await client.connect()
            for chat_id in groups:
                try:
                    await client.send_message(chat_id, message)
                    logger.info(f"تم إرسال رسالة إلى {chat_id}")
                except RPCError as e:
                    logger.error(f"فشل إرسال الرسالة إلى {chat_id}: {e}")
                # انتظار بين الرسائل داخل نفس الدورة (إذا أردت)
                await asyncio.sleep(2)  # مهلة قصيرة بين الرسائل
        except Exception as e:
            logger.error(f"خطأ في عميل pyrogram: {e}")
        finally:
            await client.disconnect()

        # انتظار الفاصل الزمني المحدد قبل الدورة التالية
        await asyncio.sleep(interval)

def stop_auto_post(user_id: int):
    """إيقاف مهمة النشر التلقائي لمستخدم"""
    task = auto_post_tasks.pop(user_id, None)
    if task:
        task.cancel()
        logger.info(f"تم إلغاء مهمة النشر للمستخدم {user_id}")

def start_auto_post(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """بدء مهمة النشر التلقائي لمستخدم (إذا كانت مفعلة)"""
    stop_auto_post(user_id)  # إلغاء أي مهمة سابقة
    task = asyncio.create_task(auto_post_worker(user_id, context))
    auto_post_tasks[user_id] = task
    logger.info(f"تم بدء مهمة النشر للمستخدم {user_id}")

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
    """لوحة مفاتيح قسم النشر التلقائي حسب حالة الإعدادات"""
    auto = user_data.get("auto_post", {})
    enabled = auto.get("enabled", False)
    groups_count = len(auto.get("groups", []))
    msg_preview = auto.get("message", "غير محددة")[:20] + "..." if auto.get("message") else "غير محددة"
    interval = auto.get("interval", 60)

    status = "🟢 مفعل" if enabled else "🔴 متوقف"
    text = f"الحالة: {status}\nالمجموعات: {groups_count}\nالرسالة: {msg_preview}\nالفاصل: {interval} ثانية"

    keyboard = [
        [InlineKeyboardButton("📋 اختيار المجموعات", callback_data="auto_set_groups")],
        [InlineKeyboardButton("✏️ كتابة الرسالة", callback_data="auto_set_message")],
        [InlineKeyboardButton("⏱ ضبط الفاصل الزمني", callback_data="auto_set_interval")],
    ]
    if enabled:
        keyboard.append([InlineKeyboardButton("⏸ إيقاف النشر", callback_data="auto_stop")])
    else:
        if groups_count > 0 and auto.get("message"):
            keyboard.append([InlineKeyboardButton("▶️ بدء النشر", callback_data="auto_start")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

# ==================== بداية المحادثة / تسجيل الدخول ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id

    if get_user_session_data(user_id):
        await update.message.reply_text(
            "مرحباً! أنت مسجل الدخول بالفعل. اختر من القائمة:",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU

    if user_id in login_data:
        await update.message.reply_text(
            "يبدو أن لديك عملية تسجيل دخول غير مكتملة. أرسل /cancel لإلغائها ثم أرسل /start مرة أخرى."
        )
        return ConversationHandler.END

    login_data[user_id] = {}
    await update.message.reply_text(
        "لبدء استخدام البوت، يرجى إدخال **API ID** الخاص بك (من my.telegram.org).\n"
        "إذا لم يكن لديك، احصل عليه من: https://my.telegram.org/apps"
    )
    return AWAITING_API_ID

async def receive_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text("API ID يجب أن يكون رقماً. حاول مرة أخرى:")
        return AWAITING_API_ID

    login_data[user_id]["api_id"] = int(text)
    await update.message.reply_text("تم استلام API ID. الآن أرسل **API Hash** الخاص بك:")
    return AWAITING_API_HASH

async def receive_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    api_hash = update.message.text.strip()

    if len(api_hash) < 5:
        await update.message.reply_text("API Hash غير صالح. حاول مرة أخرى:")
        return AWAITING_API_HASH

    login_data[user_id]["api_hash"] = api_hash
    await update.message.reply_text(
        "تم استلام API Hash.\n"
        "الآن أرسل رقم هاتفك بالصيغة الدولية (مثال: +9627xxxxxxxx):"
    )
    return AWAITING_PHONE

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    phone = update.message.text.strip()

    login_data[user_id]["phone"] = phone

    api_id = login_data[user_id]["api_id"]
    api_hash = login_data[user_id]["api_hash"]
    client = await create_pyrogram_client(api_id, api_hash)

    try:
        await client.connect()
        sent_code = await client.send_code(phone)
        login_data[user_id]["phone_code_hash"] = sent_code.phone_code_hash
        login_data[user_id]["client"] = client
        await update.message.reply_text("تم إرسال رمز التحقق إلى هاتفك. أرسل الرمز هنا (مثال: 12345):")
        return AWAITING_CODE
    except PhoneNumberInvalid:
        await client.disconnect()
        await update.message.reply_text("رقم الهاتف غير صالح. حاول مرة أخرى:")
        return AWAITING_PHONE
    except Exception as e:
        await client.disconnect()
        await update.message.reply_text(f"حدث خطأ: {e}\nالرجاء إرسال /start للبدء من جديد.")
        login_data.pop(user_id, None)
        return ConversationHandler.END

async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    code = update.message.text.strip()

    data = login_data.get(user_id)
    if not data:
        await update.message.reply_text("حدث خطأ. أرسل /start مرة أخرى.")
        return ConversationHandler.END

    client = data.get("client")
    phone = data["phone"]
    phone_code_hash = data["phone_code_hash"]

    try:
        await client.sign_in(phone, phone_code_hash, code)
    except SessionPasswordNeeded:
        await update.message.reply_text("الحساب محمي بكلمة مرور (2FA). أرسل كلمة المرور:")
        return AWAITING_PASSWORD
    except (PhoneCodeInvalid, PhoneCodeExpired) as e:
        await update.message.reply_text("الرمز غير صحيح أو منتهي الصلاحية. أرسل الرمز مجدداً:")
        return AWAITING_CODE
    except Exception as e:
        await update.message.reply_text(f"خطأ: {e}\nأرسل /start للبدء من جديد.")
        login_data.pop(user_id, None)
        return ConversationHandler.END

    return await finalize_login(update, context, user_id, client)

async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    password = update.message.text.strip()

    data = login_data.get(user_id)
    if not data:
        await update.message.reply_text("حدث خطأ. أرسل /start مرة أخرى.")
        return ConversationHandler.END

    client = data.get("client")
    try:
        await client.check_password(password)
    except Exception as e:
        await update.message.reply_text(f"كلمة المرور غير صحيحة. حاول مرة أخرى:")
        return AWAITING_PASSWORD

    return await finalize_login(update, context, user_id, client)

async def finalize_login(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, client: Client) -> int:
    """استكمال تسجيل الدخول: تخزين البيانات المشفرة"""
    try:
        if not client.is_connected:
            await client.connect()

        me = await client.get_me()
        session_string = await client.export_session_string()

        api_id = login_data[user_id]["api_id"]
        api_hash = login_data[user_id]["api_hash"]

        # تخزين في الذاكرة وفي الملف
        user_sessions[user_id] = {
            "session": session_string,
            "api_id": api_id,
            "api_hash": api_hash,
            "first_name": me.first_name,
            "username": me.username,
            "phone": me.phone_number,
            "auto_post": {
                "enabled": False,
                "groups": [],
                "message": None,
                "interval": 60
            }
        }
        save_sessions(user_sessions)

        login_data.pop(user_id, None)
        await client.disconnect()

        await update.message.reply_text(
            f"✅ تم تسجيل الدخول بنجاح!\nمرحباً {me.first_name}.\nيمكنك الآن استخدام القائمة.",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU
    except Exception as e:
        logger.error(f"خطأ في finalize_login: {e}")
        await update.message.reply_text(f"حدث خطأ أثناء إنهاء تسجيل الدخول: {e}")
        return ConversationHandler.END

# ==================== معالجات القوائم الرئيسية ====================
async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if query.data == "channel_section":
        await query.edit_message_text(
            "اختر العملية التي تريدها:", reply_markup=channel_section_keyboard()
        )
        return CHANNEL_SECTION

    elif query.data == "auto_post_menu":
        user_data = get_user_session_data(user_id)
        if not user_data:
            await query.edit_message_text("لم يتم العثور على جلسة. أرسل /start مرة أخرى.")
            return ConversationHandler.END

        await query.edit_message_text(
            "إعدادات النشر التلقائي:",
            reply_markup=auto_post_menu_keyboard(user_data)
        )
        return AUTO_POST_MENU

    elif query.data == "account_info":
        user_data = get_user_session_data(user_id)
        if not user_data:
            await query.edit_message_text("لم يتم العثور على جلسة. أرسل /start مرة أخرى.")
            return ConversationHandler.END

        info = f"📌 الاسم: {user_data.get('first_name', 'غير معروف')}\n"
        if user_data.get('username'):
            info += f"👤 اليوزرنيم: @{user_data['username']}\n"
        info += f"📱 الرقم: {user_data.get('phone', 'غير معروف')}"
        await query.edit_message_text(info, reply_markup=main_menu_keyboard())
        return MAIN_MENU

    elif query.data == "logout":
        # إيقاف النشر التلقائي إن كان مفعلًا
        stop_auto_post(user_id)
        user_sessions.pop(user_id, None)
        save_sessions(user_sessions)
        await query.edit_message_text("تم تسجيل الخروج. أرسل /start للدخول مجدداً.")
        return ConversationHandler.END

    return MAIN_MENU

# ==================== قسم إدارة المغادرة (مثل السابق) ====================
# (نفس الكود السابق، مختصر هنا للاختصار، لكنه موجود في الكود الكامل)
async def channel_section_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_data = get_user_session_data(user_id)

    if not user_data:
        await query.edit_message_text("الجلسة غير موجودة. أرسل /start.")
        return ConversationHandler.END

    session_str = user_data["session"]
    api_id = user_data["api_id"]
    api_hash = user_data["api_hash"]

    client = await create_pyrogram_client(api_id, api_hash, session_str)

    if query.data == "leave_all_channels":
        await query.edit_message_text("جاري مغادرة كل القنوات...")
        try:
            await client.connect()
            left_count = 0
            async for dialog in client.get_dialogs():
                if dialog.chat.type == ChatType.CHANNEL:
                    try:
                        await client.leave_chat(dialog.chat.id)
                        left_count += 1
                        logger.info(f"مغادرة قناة: {dialog.chat.title}")
                    except RPCError as e:
                        logger.error(f"خطأ في مغادرة {dialog.chat.title}: {e}")
            await query.edit_message_text(
                f"✅ تمت مغادرة {left_count} قناة.", reply_markup=channel_section_keyboard()
            )
        except Exception as e:
            logger.error(f"خطأ عام في leave_all_channels: {e}")
            await query.edit_message_text(f"حدث خطأ: {e}", reply_markup=channel_section_keyboard())
        finally:
            await client.disconnect()
        return CHANNEL_SECTION

    elif query.data == "leave_all_groups":
        await query.edit_message_text("جاري مغادرة كل الجروبات...")
        try:
            await client.connect()
            left_count = 0
            async for dialog in client.get_dialogs():
                if dialog.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                    try:
                        await client.leave_chat(dialog.chat.id)
                        left_count += 1
                        logger.info(f"مغادرة جروب: {dialog.chat.title}")
                    except RPCError as e:
                        logger.error(f"خطأ في مغادرة {dialog.chat.title}: {e}")
            await query.edit_message_text(
                f"✅ تمت مغادرة {left_count} جروب.", reply_markup=channel_section_keyboard()
            )
        except Exception as e:
            logger.error(f"خطأ عام في leave_all_groups: {e}")
            await query.edit_message_text(f"حدث خطأ: {e}", reply_markup=channel_section_keyboard())
        finally:
            await client.disconnect()
        return CHANNEL_SECTION

    elif query.data == "list_channels":
        await query.edit_message_text("جاري تحميل القنوات...")
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
            logger.error(f"خطأ في تحميل القنوات: {e}")
            await query.edit_message_text(f"حدث خطأ: {e}", reply_markup=channel_section_keyboard())
        finally:
            await client.disconnect()
        return LIST_CHANNELS

    elif query.data == "list_groups":
        await query.edit_message_text("جاري تحميل الجروبات...")
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
            logger.error(f"خطأ في تحميل الجروبات: {e}")
            await query.edit_message_text(f"حدث خطأ: {e}", reply_markup=channel_section_keyboard())
        finally:
            await client.disconnect()
        return LIST_GROUPS

    elif query.data == "back_to_main":
        await query.edit_message_text("القائمة الرئيسية:", reply_markup=main_menu_keyboard())
        return MAIN_MENU

    return CHANNEL_SECTION

# دوال عرض القنوات والجروبات (نفس السابق)
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
        btn_text = title[:30] + "..." if len(title) > 30 else title
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
        f"قائمة القنوات (صفحة {page+1}/{total_pages}):",
        reply_markup=InlineKeyboardMarkup(keyboard),
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
        btn_text = title[:30] + "..." if len(title) > 30 else title
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
        f"قائمة الجروبات (صفحة {page+1}/{total_pages}):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def list_navigation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_data = get_user_session_data(user_id)
    if not user_data:
        await query.edit_message_text("الجلسة غير موجودة. أرسل /start.")
        return ConversationHandler.END

    data = query.data

    # التنقل في القنوات
    if data.startswith("channels_page_"):
        if data == "channels_page_next":
            context.user_data["channels_page"] = context.user_data.get("channels_page", 0) + 1
        elif data == "channels_page_prev":
            context.user_data["channels_page"] = context.user_data.get("channels_page", 0) - 1
        await show_channels_page(update, context)
        return LIST_CHANNELS

    # التنقل في الجروبات
    if data.startswith("groups_page_"):
        if data == "groups_page_next":
            context.user_data["groups_page"] = context.user_data.get("groups_page", 0) + 1
        elif data == "groups_page_prev":
            context.user_data["groups_page"] = context.user_data.get("groups_page", 0) - 1
        await show_groups_page(update, context)
        return LIST_GROUPS

    # معالجة طلب المغادرة
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
            logger.info(f"محاولة مغادرة الدردشة: {chat_id}")

            try:
                chat = await client.get_chat(chat_id)
                if not chat:
                    raise Exception("الدردشة غير موجودة")
            except Exception as e:
                logger.warning(f"لا يمكن جلب معلومات الدردشة {chat_id}: {e}")
                await remove_chat_from_list(context, chat_id)
                await query.edit_message_text("⚠️ أنت لست عضوًا في هذه الدردشة (أو تم حذفها). تمت إزالتها من القائمة.")
                return await refresh_current_list(update, context)

            await client.leave_chat(chat_id)
            logger.info(f"تمت المغادرة بنجاح من {chat_id}")

            await remove_chat_from_list(context, chat_id)
            await query.edit_message_text("✅ تمت المغادرة بنجاح.")

        except RPCError as e:
            logger.error(f"خطأ RPC أثناء مغادرة {chat_id}: {e}")
            error_msg = str(e)
            if "USER_NOT_PARTICIPANT" in error_msg:
                await remove_chat_from_list(context, chat_id)
                await query.edit_message_text("⚠️ أنت لست عضوًا في هذه الدردشة. تمت إزالتها من القائمة.")
            elif "CHAT_ID_INVALID" in error_msg:
                await remove_chat_from_list(context, chat_id)
                await query.edit_message_text("⚠️ معرف الدردشة غير صالح (ربما تم حذفها). تمت إزالتها من القائمة.")
            else:
                await query.edit_message_text(f"❌ فشلت المغادرة: {e}")

        except Exception as e:
            logger.error(f"خطأ غير متوقع: {e}")
            await query.edit_message_text(f"❌ حدث خطأ غير متوقع: {e}")

        finally:
            await client.disconnect()

        return await refresh_current_list(update, context)

    if data == "back_to_channel_section":
        await query.edit_message_text("اختر العملية:", reply_markup=channel_section_keyboard())
        return CHANNEL_SECTION

    return CHANNEL_SECTION

# ==================== قسم النشر التلقائي ====================
async def auto_post_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_data = get_user_session_data(user_id)
    if not user_data:
        await query.edit_message_text("الجلسة غير موجودة. أرسل /start.")
        return ConversationHandler.END

    data = query.data

    if data == "auto_set_groups":
        # تحميل قائمة الجروبات من الحساب
        session_str = user_data["session"]
        api_id = user_data["api_id"]
        api_hash = user_data["api_hash"]
        client = await create_pyrogram_client(api_id, api_hash, session_str)

        await query.edit_message_text("جاري تحميل الجروبات...")
        try:
            await client.connect()
            groups = []
            async for dialog in client.get_dialogs():
                if dialog.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                    groups.append((dialog.chat.id, dialog.chat.title or "بدون عنوان"))
            context.user_data["auto_groups_list"] = groups
            context.user_data["auto_groups_page"] = 0
            # تحديد أي منها محدد مسبقاً (إن وجد)
            selected = set(user_data.get("auto_post", {}).get("groups", []))
            context.user_data["auto_selected_groups"] = selected
            await show_auto_groups_page(update, context)
        except Exception as e:
            logger.error(f"خطأ في تحميل الجروبات: {e}")
            await query.edit_message_text(f"حدث خطأ: {e}", reply_markup=auto_post_menu_keyboard(user_data))
        finally:
            await client.disconnect()
        return AUTO_POST_SET_GROUPS

    elif data == "auto_set_message":
        await query.edit_message_text(
            "أرسل الرسالة التي تريد نشرها (يمكنك استخدام Markdown):\n"
            "لإلغاء الأمر أرسل /cancel"
        )
        return AUTO_POST_SET_MESSAGE

    elif data == "auto_set_interval":
        await query.edit_message_text(
            "أرسل الفاصل الزمني بين كل رسالة (بالثواني، رقم فقط):\n"
            "لإلغاء الأمر أرسل /cancel"
        )
        return AUTO_POST_SET_INTERVAL

    elif data == "auto_start":
        auto = user_data.get("auto_post", {})
        if auto.get("enabled"):
            await query.edit_message_text("النشر مفعل بالفعل.")
        else:
            if not auto.get("groups") or not auto.get("message"):
                await query.edit_message_text("⚠️ يجب تحديد المجموعات والرسالة أولاً.")
            else:
                user_data["auto_post"]["enabled"] = True
                save_sessions(user_sessions)
                start_auto_post(user_id, context)
                await query.edit_message_text("✅ تم بدء النشر التلقائي.", reply_markup=auto_post_menu_keyboard(user_data))
        return AUTO_POST_MENU

    elif data == "auto_stop":
        user_data["auto_post"]["enabled"] = False
        save_sessions(user_sessions)
        stop_auto_post(user_id)
        await query.edit_message_text("⏸ تم إيقاف النشر التلقائي.", reply_markup=auto_post_menu_keyboard(user_data))
        return AUTO_POST_MENU

    elif data == "back_to_main":
        await query.edit_message_text("القائمة الرئيسية:", reply_markup=main_menu_keyboard())
        return MAIN_MENU

    return AUTO_POST_MENU

async def show_auto_groups_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض قائمة الجروبات مع إمكانية اختيار متعدد"""
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
        # علامة ✓ إذا كانت محددة
        mark = "✅ " if chat_id in selected else ""
        btn_text = f"{mark}{title[:25]}..." if len(title) > 25 else f"{mark}{title}"
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
        f"اختر المجموعات (صفحة {page+1}/{total_pages}):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def auto_groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالج اختيار المجموعات للنشر التلقائي"""
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
        # تحديث بيانات المستخدم
        user_data = get_user_session_data(user_id)
        if user_data:
            if "auto_post" not in user_data:
                user_data["auto_post"] = {}
            user_data["auto_post"]["groups"] = list(selected)
            user_data["auto_post"]["enabled"] = False  # نوقف النشر عند تغيير المجموعات
            save_sessions(user_sessions)
            stop_auto_post(user_id)
        await query.edit_message_text("✅ تم حفظ المجموعات.", reply_markup=auto_post_menu_keyboard(user_data))
        return AUTO_POST_MENU

    elif data == "auto_back_to_menu":
        user_id = update.effective_user.id
        user_data = get_user_session_data(user_id)
        await query.edit_message_text("إعدادات النشر التلقائي:", reply_markup=auto_post_menu_keyboard(user_data))
        return AUTO_POST_MENU

    return AUTO_POST_SET_GROUPS

async def auto_set_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال رسالة النشر"""
    user_id = update.effective_user.id
    message = update.message.text

    user_data = get_user_session_data(user_id)
    if user_data:
        if "auto_post" not in user_data:
            user_data["auto_post"] = {}
        user_data["auto_post"]["message"] = message
        user_data["auto_post"]["enabled"] = False  # نوقف النشر عند تغيير الرسالة
        save_sessions(user_sessions)
        stop_auto_post(user_id)

    await update.message.reply_text("✅ تم حفظ الرسالة.", reply_markup=auto_post_menu_keyboard(user_data))
    return AUTO_POST_MENU

async def auto_set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال الفاصل الزمني"""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text("الرجاء إدخال رقم صحيح (بالثواني):")
        return AUTO_POST_SET_INTERVAL

    interval = int(text)
    if interval < 5:
        await update.message.reply_text("يجب أن يكون الفاصل 5 ثوانٍ على الأقل.")
        return AUTO_POST_SET_INTERVAL

    user_data = get_user_session_data(user_id)
    if user_data:
        if "auto_post" not in user_data:
            user_data["auto_post"] = {}
        user_data["auto_post"]["interval"] = interval
        user_data["auto_post"]["enabled"] = False
        save_sessions(user_sessions)
        stop_auto_post(user_id)

    await update.message.reply_text("✅ تم حفظ الفاصل الزمني.", reply_markup=auto_post_menu_keyboard(user_data))
    return AUTO_POST_MENU

# ==================== معالج الإلغاء ====================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    login_data.pop(user_id, None)
    client = login_data.get(user_id, {}).get("client")
    if client and client.is_connected:
        await client.disconnect()
    await update.message.reply_text("تم الإلغاء. أرسل /start للبدء مجدداً.")
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
