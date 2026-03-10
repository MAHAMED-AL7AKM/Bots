import os
import json
import base64
import asyncio
from typing import Dict, Optional, Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2

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

# ==================== الإعدادات ====================
# ملف تخزين الجلسات المشفر
SESSIONS_FILE = "sessions.dat"

# مفتاح التشفير (يُفضل أخذه من متغير بيئة)
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    # إذا لم يكن موجوداً، ننشئ مفتاحاً جديداً ونتنبيه المستخدم بحفظه
    key = Fernet.generate_key()
    print("=" * 60)
    print("لم يتم العثور على ENCRYPTION_KEY في متغيرات البيئة.")
    print("تم إنشاء مفتاح تشفير جديد. يجب حفظه لاستخدامه في المرات القادمة:")
    print(key.decode())
    print("=" * 60)
    ENCRYPTION_KEY = key.decode()
else:
    # التأكد من أن المفتاح بالطول الصحيح
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
        # تحويل المفاتيح إلى int (json يخزنها كنصوص)
        return {int(k): v for k, v in sessions.items()}
    except Exception as e:
        print(f"خطأ في تحميل الجلسات: {e}")
        return {}

def save_sessions(sessions: Dict[int, Dict[str, Any]]) -> None:
    """حفظ الجلسات في الملف المشفر."""
    try:
        # تحويل المفاتيح إلى نصوص json
        data = {str(k): v for k, v in sessions.items()}
        json_data = json.dumps(data, ensure_ascii=False).encode()
        encrypted_data = cipher.encrypt(json_data)
        with open(SESSIONS_FILE, "wb") as f:
            f.write(encrypted_data)
    except Exception as e:
        print(f"خطأ في حفظ الجلسات: {e}")

# تخزين الجلسات في الذاكرة مع التزامن مع الملف
user_sessions = load_sessions()

# ==================== حالات المحادثة ====================
(
    MAIN_MENU,
    CHANNEL_SECTION,
    LIST_CHANNELS,
    LIST_GROUPS,
    AWAITING_API_ID,
    AWAITING_API_HASH,
    AWAITING_PHONE,
    AWAITING_CODE,
    AWAITING_PASSWORD,
) = range(9)

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

# ==================== لوحات المفاتيح ====================
def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🚪 إدارة المغادرة (القنوات والجروبات)", callback_data="channel_section")],
        [InlineKeyboardButton("ℹ️ معلومات الحساب", callback_data="account_info")],
        [InlineKeyboardButton("🔐 تسجيل الخروج", callback_data="logout")],
    ]
    return InlineKeyboardMarkup(keyboard)

def channel_section_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📢 مغادرة كل القنوات", callback_data="leave_all_channels")],
        [InlineKeyboardButton("👥 مغادرة كل الجروبات", callback_data="leave_all_groups")],
        [InlineKeyboardButton("📋 عرض القنوات لمغادرة محددة", callback_data="list_channels")],
        [InlineKeyboardButton("🗂 عرض الجروبات لمغادرة محددة", callback_data="list_groups")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")],
    ]
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
        }
        save_sessions(user_sessions)  # حفظ مشفر

        login_data.pop(user_id, None)
        await client.disconnect()

        await update.message.reply_text(
            f"✅ تم تسجيل الدخول بنجاح!\nمرحباً {me.first_name}.\nيمكنك الآن استخدام القائمة.",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU
    except Exception as e:
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

    elif query.data == "account_info":
        user_data = get_user_session_data(user_id)
        if not user_data:
            await query.edit_message_text("لم يتم العثور على جلسة. أرسل /start مرة أخرى.")
            return ConversationHandler.END

        info = f"📌 الاسم: {user_data.get('first_name', 'غير معروف')}\n"
        info += f"👤 اليوزرنيم: @{user_data['username']}" if user_data.get('username') else ""
        info += f"\n📱 الرقم: {user_data.get('phone', 'غير معروف')}"
        await query.edit_message_text(info, reply_markup=main_menu_keyboard())
        return MAIN_MENU

    elif query.data == "logout":
        user_sessions.pop(user_id, None)
        save_sessions(user_sessions)
        await query.edit_message_text("تم تسجيل الخروج. أرسل /start للدخول مجدداً.")
        return ConversationHandler.END

    return MAIN_MENU

# ==================== قسم إدارة المغادرة ====================
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
                    except RPCError as e:
                        print(f"خطأ في مغادرة {dialog.chat.title}: {e}")
            await query.edit_message_text(
                f"✅ تمت مغادرة {left_count} قناة.", reply_markup=channel_section_keyboard()
            )
        except Exception as e:
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
                    except RPCError as e:
                        print(f"خطأ في مغادرة {dialog.chat.title}: {e}")
            await query.edit_message_text(
                f"✅ تمت مغادرة {left_count} جروب.", reply_markup=channel_section_keyboard()
            )
        except Exception as e:
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
            await show_channels_page(update, context)
        except Exception as e:
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
            await show_groups_page(update, context)
        except Exception as e:
            await query.edit_message_text(f"حدث خطأ: {e}", reply_markup=channel_section_keyboard())
        finally:
            await client.disconnect()
        return LIST_GROUPS

    elif query.data == "back_to_main":
        await query.edit_message_text("القائمة الرئيسية:", reply_markup=main_menu_keyboard())
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

# ==================== معالج التنقل والمغادرة المحددة ====================
async def list_navigation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_data = get_user_session_data(user_id)
    if not user_data:
        await query.edit_message_text("الجلسة غير موجودة. أرسل /start.")
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
        chat_id = int(data.split(":")[1])
        session_str = user_data["session"]
        api_id = user_data["api_id"]
        api_hash = user_data["api_hash"]
        client = await create_pyrogram_client(api_id, api_hash, session_str)
        try:
            await client.connect()
            await client.leave_chat(chat_id)
            # إزالة الدردشة من القائمة
            for lst_name in ["channels_list", "groups_list"]:
                lst = context.user_data.get(lst_name, [])
                context.user_data[lst_name] = [item for item in lst if item[0] != chat_id]
            await query.edit_message_text("✅ تمت المغادرة بنجاح.")
        except RPCError as e:
            await query.edit_message_text(f"❌ فشلت المغادرة: {e}")
        finally:
            await client.disconnect()

        if "channels_list" in context.user_data:
            await show_channels_page(update, context)
            return LIST_CHANNELS
        elif "groups_list" in context.user_data:
            await show_groups_page(update, context)
            return LIST_GROUPS
        else:
            await query.edit_message_text("العودة للقسم", reply_markup=channel_section_keyboard())
            return CHANNEL_SECTION

    if data == "back_to_channel_section":
        await query.edit_message_text("اختر العملية:", reply_markup=channel_section_keyboard())
        return CHANNEL_SECTION

    return CHANNEL_SECTION

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
            MAIN_MENU: [CallbackQueryHandler(main_menu_handler, pattern="^(channel_section|account_info|logout)$")],
            CHANNEL_SECTION: [CallbackQueryHandler(channel_section_handler)],
            LIST_CHANNELS: [CallbackQueryHandler(list_navigation_handler)],
            LIST_GROUPS: [CallbackQueryHandler(list_navigation_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == "__main__":
    main()
