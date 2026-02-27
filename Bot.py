import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler

# استبدل هذه القيم
BOT_TOKEN = "7087088730:AAGuiJOguuFn4_F1xXZpAsskrhlaeTmIFWs"
OWNER_CHAT_ID = 7828957324  # ضع معرف المالك هنا

# حلة المحادثة (للتأد من أننا في خطوة طلب الرقم)
ASK_PHONE = 1

# إعداد تسجيل الأخطاء
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context):
    """بداية المحادثة: نرسل رسالة ترحيب ونطلب رقم الهاتف."""
    # زر مشاركة رقم الهاتف
    contact_keyboard = KeyboardButton(text="📱 مشاركة رقم الهاتف", request_contact=True)
    reply_markup = ReplyKeyboardMarkup([[contact_keyboard]], resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "مرحباً! للتحقق من أنك مستخدم حقيقي، يرجى مشاركة رقم هاتفك عبر الزر أدناه.",
        reply_markup=reply_markup
    )
    return ASK_PHONE

async def handle_contact(update: Update, context):
    """استقبال رقم الهاتف وإرساله للمالك."""
    contact = update.message.contact
    user = update.effective_user

    if contact:
        phone = contact.phone_number
        user_info = f"مستخدم: {user.first_name} {user.last_name or ''} (@{user.username or 'لا يوجد'})"
        # إرسال الرقم إلى المالك
        await context.bot.send_message(
            chat_id=OWNER_CHAT_ID,
            text=f"📞 رقم هاتف جديد:\n{user_info}\nرقم الهاتف: {phone}"
        )
        # إشعار المستخدم بأنه تم التحقق
        await update.message.reply_text("شكراً! تم التحقق من رقمك وإرساله إلى المالك.")
    else:
        await update.message.reply_text("حدث خطأ، يرجى المحاولة مرة أخرى.")

    # إنهاء المحادثة
    return ConversationHandler.END

async def cancel(update: Update, context):
    """إلغاء العملية."""
    await update.message.reply_text("تم الإلغاء.")
    return ConversationHandler.END

def main():
    # إنشاء التطبيق
    app = Application.builder().token(BOT_TOKEN).build()

    # إدارة المحادثة
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_PHONE: [MessageHandler(filters.CONTACT, handle_contact)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler)

    # بدء البوت
    print("البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()
