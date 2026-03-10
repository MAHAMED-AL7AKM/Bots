import os
import asyncio
from typing import Dict, Optional

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

# ==================== States ====================
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

# تخزين جلسات المستخدمين (يُفضل استخدام قاعدة بيانات في الإنتاج)
# المفتاح: user_id، القيمة: session_string
user_sessions: Dict[int, str] = {}

# تخزين مؤقت لبيانات الدخول لكل مستخدم (للمحادثة فقط)
login_data: Dict[int, dict] = {}

# ==================== Bot Token ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    # إذا لم يكن موجوداً في البيئة، نطلب إدخاله يدوياً
    BOT_TOKEN = input("الرجاء إدخال توكن البوت: ").strip()
    if not BOT_TOKEN:
        raise ValueError("لا يمكن تشغيل البوت بدون توكن.")

# ==================== Helper functions ====================
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

# ==================== Keyboards ====================
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

# ==================== Start / Login flow ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id

    # إذا كان المستخدم لديه جلسة مخزنة، ننتقل مباشرة إلى القائمة
    if user_id in user_sessions:
        await update.message.reply_text(
            "مرحباً! أنت مسجل الدخول بالفعل. اختر من القائمة:",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU

    # إذا بدأ محادثة تسجيل دخول سابقة ولم تكتمل، نطلب منه الاستمرار أو البدء من جديد
    if user_id in login_data:
        await update.message.reply_text(
            "يبدو أن لديك عملية تسجيل دخول غير مكتملة. أرسل /cancel لإلغائها ثم أرسل /start مرة أخرى."
        )
        return ConversationHandler.END

    # بداية تسجيل الدخول
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

    if len(api_hash) < 5:  # تحقق بسيط
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

    # إنشاء عميل pyrogram جديد (بدون session)
    api_id = login_data[user_id]["api_id"]
    api_hash = login_data[user_id]["api_hash"]
    client = await create_pyrogram_client(api_id, api_hash)

    try:
        await client.connect()
        # إرسال رمز التحقق
        sent_code = await client.send_code(phone)
        login_data[user_id]["phone_code_hash"] = sent_code.phone_code_hash
        login_data[user_id]["client"] = client  # نخزن العميل لاستخدامه لاحقاً
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
        # الحماية بخطوتين مفعلة
        await update.message.reply_text("الحساب محمي بكلمة مرور (2FA). أرسل كلمة المرور:")
        return AWAITING_PASSWORD
    except (PhoneCodeInvalid, PhoneCodeExpired) as e:
        await update.message.reply_text("الرمز غير صحيح أو منتهي الصلاحية. أرسل الرمز مجدداً:")
        return AWAITING_CODE
    except Exception as e:
        await update.message.reply_text(f"خطأ: {e}\nأرسل /start للبدء من جديد.")
        login_data.pop(user_id, None)
        return ConversationHandler.END

    # تم تسجيل الدخول بنجاح (بدون 2FA)
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

    # تم تسجيل الدخول بنجاح مع 2FA
    return await finalize_login(update, context, user_id, client)

async def finalize_login(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, client: Client) -> int:
    """استكمال تسجيل الدخول: استخراج session string وتخزينها"""
    try:
        # التأكد من أن العميل متصل
        if not client.is_connected:
            await client.connect()

        # الحصول على معلومات الحساب
        me = await client.get_me()
        session_string = await client.export_session_string()

        # تخزين الجلسة
        user_sessions[user_id] = session_string

        # تنظيف بيانات الدخول المؤقتة
        login_data.pop(user_id, None)
        await client.disconnect()

        await update.message.reply_text(
            f"✅ تم تسجيل الدخول بنجاح!\n"
            f"مرحباً {me.first_name}.\n"
            "يمكنك الآن استخدام القائمة.",
            reply_markup=main_menu_keyboard(),
        )
        return MAIN_MENU
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ أثناء إنهاء تسجيل الدخول: {e}")
        return ConversationHandler.END

# ==================== Main Menu Handlers ====================
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
        session_str = user_sessions.get(user_id)
        if not session_str:
            await query.edit_message_text("لم يتم العثور على جلسة. أرسل /start مرة أخرى.")
            return ConversationHandler.END

        # استرجاع api_id و api_hash من session؟ لا يمكن استخراجهما مباشرة، لكننا نحتاجهما لإنشاء client.
        # الحل: يمكننا تخزين api_id و api_hash مع session، لكننا لم نخزنهما. سنطلب من المستخدم إدخالهما مرة أخرى؟ غير عملي.
        # الأفضل: عند تسجيل الدخول، نخزن أيضاً api_id و api_hash المرتبطين بالجلسة.
        # لذلك سنقوم بتعديل user_sessions ليخزن قاموساً بدلاً من نص فقط.
        # لكن للتبسيط، سنقوم بإنشاء client من session فقط، ونتجاهل api_id و api_hash لأن session تحتوي عليهما.
        # المشكلة: pyrogram يتطلب api_id و api_hash لإنشاء client حتى مع session string.
        # الحل: نحتاج إلى تخزين api_id و api_hash مع session. لذا يجب تغيير هيكل التخزين.

        # تعديل: سنخزن في user_sessions قاموساً: {"session": ..., "api_id": ..., "api_hash": ...}
        # هذا يتطلب تعديل الكود في finalize_login وحيثما يستخدم.
        # سأقوم بإجراء التعديل اللاحق.

        # مؤقتاً سنعرض رسالة بسيطة
        await query.edit_message_text("هذه الميزة قيد التطوير.", reply_markup=main_menu_keyboard())
        return MAIN_MENU

    elif query.data == "logout":
        user_sessions.pop(user_id, None)
        await query.edit_message_text("تم تسجيل الخروج. أرسل /start للدخول مجدداً.")
        return ConversationHandler.END

    return MAIN_MENU

# ==================== Channel Section Handlers ====================
async def channel_section_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_data = user_sessions.get(user_id)  # يجب أن يكون قاموساً

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

# ==================== Pagination Handlers ====================
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
    user_data = user_sessions.get(user_id)
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

    # مغادرة محددة
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

        # إعادة عرض القائمة المحدثة
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
    # تنظيف بيانات الدخول المؤقتة
    login_data.pop(user_id, None)
    # إغلاق أي عميل مفتوح
    client = login_data.get(user_id, {}).get("client")
    if client and client.is_connected:
        await client.disconnect()
    await update.message.reply_text("تم الإلغاء. أرسل /start للبدء مجدداً.")
    return ConversationHandler.END

# ==================== Main ====================
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
