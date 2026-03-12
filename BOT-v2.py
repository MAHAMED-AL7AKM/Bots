#!/usr/bin/env python3
import json
import asyncio
import logging
import sys
import subprocess
import random
import datetime
from typing import Dict, List, Set, Optional, Tuple
from pathlib import Path

# ==================== تثبيت المكتبات التلقائي ====================
def install_requirements():
    """تثبيت المكتبات المطلوبة تلقائياً"""
    try:
        import telegram
        print(f"✅ python-telegram-bot {telegram.__version__} مثبت بالفعل")
        
        # التحقق من الإصدار
        version_parts = telegram.__version__.split('.')
        if int(version_parts[0]) < 20:
            print("⚠️  تحذير: إصدار قديم. جاري الترقية...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "python-telegram-bot==20.7", "--quiet"])
            print("✅ تم ترقية المكتبة إلى الإصدار 20.7")
    except ImportError:
        print("📦 جاري تثبيت python-telegram-bot 20.7...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "python-telegram-bot==20.7", "--quiet"])
            print("✅ تم تثبيت المكتبات بنجاح")
        except Exception as e:
            print(f"❌ فشل تثبيت المكتبات: {e}")
            sys.exit(1)
    except Exception as e:
        print(f"⚠️  تحذير: {e}")
        pass

# تشغيل التثبيت
install_requirements()

# ==================== استيراد المكتبات بعد التثبيت ====================
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# ==================== CONFIGURATION ====================
TOKEN = "8562163728:AAHkFc9WcRCyoxtAQ0sodVpvb8p1AanXD40"  # توكنك الجديد
OWNER_ID = 7828957324
OWNER_USERNAME = "@DAD_MOHAMED"
OWNER_TELEGRAM = "@DAD_MOHAMED"
OWNER_TIKTOK = "@mohamed_el7akm"

# ==================== ملفات حفظ البيانات ====================
POINTS_FILE = "data/points.json"
CHANNELS_FILE = "data/channels.json"
SETTINGS_FILE = "data/settings.json"
USERS_FILE = "data/users.json"
GAME_FILE = "data/game_state.json"

# إنشاء مجلد data إذا لم يكن موجوداً
Path("data").mkdir(exist_ok=True)

# ==================== LOGGING ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# ==================== GAME DATA ====================
# قوائم العناصر لكل موضوع (تم نقل جميع مواضيع الميكب والعناية إلى أشياء عشوائية)
TOPICS_DATA = {
    "🍔 أكلات": [
        "كشري", "فول", "طعمية", "شاورما", "برجر", "بيتزا", "كباب", "كفتة",
        "ملوخية", "محشي", "فتة", "سمك مشوي", "جمبري", "سجق", "مكرونة بشاميل",
        "مكرونة سباجيتي", "لازانيا", "رز بسمتي", "كبسة", "مندي", "برياني",
        "سوشي", "نودلز", "رامن", "تاكو", "بوريتو", "كريب", "وافل", "بان كيك",
        "دونات", "تشيز كيك", "آيس كريم", "كنافة", "بسبوسة", "قطايف", "أم علي", "رز بلبن"
    ],
    "👤 شخصيات": [
        "محمد صلاح", "ميسي", "رونالدو", "نيمار", "زيدان", "عادل إمام",
        "أحمد حلمي", "محمد هنيدي", "كريم عبد العزيز", "محمد رمضان",
        "السيسي", "محمد بن سلمان", "أردوغان", "ترامب", "بوتين",
        "سبايدر مان", "باتمان", "سوبر مان", "الجوكر", "هاري بوتر",
        "فولدمورت", "جاندالف", "دارث فيدر", "ناروتو", "لوفي", "جوكو"
    ],
    "🌍 بلاد": [
        "مصر", "السعودية", "الإمارات", "قطر", "الكويت", "البحرين",
        "عمان", "المغرب", "الجزائر", "تونس", "ليبيا", "السودان",
        "الأردن", "فلسطين", "سوريا", "لبنان", "العراق", "تركيا",
        "إيران", "فرنسا", "إيطاليا", "إسبانيا", "ألمانيا", "بريطانيا",
        "أمريكا", "كندا", "البرازيل", "الأرجنتين", "المكسيك", "اليابان"
    ],
    "🏛️ أماكن": [
        "المتحف", "السينما", "المسرح", "الجامعة", "المدرسة", "المستشفى",
        "المطار", "محطة القطار", "المول", "السوق", "الجيم", "الكافيه",
        "المطعم", "الحديقة", "الشاطئ", "الملاهي", "المكتبة", "المسجد",
        "الكنيسة", "الأهرامات", "برج إيفل", "تمثال الحرية", "سور الصين العظيم"
    ],
    "🎮 أشياء عشوائية": [
        "موبايل", "كمبيوتر", "لابتوب", "تابلت", "سماعة", "هيدفون",
        "ساعة", "كتاب", "قلم", "كراسة", "شنطة", "مفتاح", "باب",
        "شباك", "كرسي", "ترابيزة", "لمبة", "مروحة", "تكييف",
        "تلفزيون", "ريموت", "كاميرا", "مايك", "لايت", "كرة",
        "دراجة", "سيارة", "طائرة", "سفينة", "مصعد",
        # منتجات الميكب والعناية
        "فاونديشن", "كونسيلر", "بودرة", "بلاشر", "هايلايتر",
        "برونزر", "ماسكارا", "آيلاينر", "كحل", "آيشادو",
        "برايمر", "روج", "جلوس", "ليب لاينر", "تينت", "سبراي تثبيت",
        # عناية بالأظافر
        "طلاء أظافر", "جيل بوليش", "أكريليك", "فرنش نيل",
        "مانيكير", "باديكير", "مبرد أظافر",
        # عناية بالبشرة
        "غسول وجه", "تونر", "مرطب", "سيروم", "واقي شمس",
        "مقشر", "ماسك", "كريم ليلي", "كريم نهاري",
        # عناية بالشعر
        "شامبو", "بلسم", "حمام كريم", "زيت شعر", "ماسك شعر",
        "سيرم شعر", "كريم تصفيف", "جل", "سبراي",
        # ملابس بنات
        "فستان", "عباية", "جيبة", "بلوزة", "توب", "بنطلون",
        "جينز", "ليجن", "بيجامة", "لانجيري",
        # إكسسوارات
        "شنطة", "محفظة", "حزام", "نظارة شمس", "سلسلة",
        "خاتم", "حلق", "إسورة", "ساعة",
        # أحذية
        "كعب", "سنيكرز", "بوت", "صندل", "شبشب", "باليرينا",
        # عطور
        "برفان", "بودي سبلاش", "مِسك", "عنبر", "فانيليا", "عود"
    ],
    "🏠 أماكن يومية": [
        "المطبخ", "الصالة", "غرفة النوم", "الحمام", "البلكونة",
        "الجراج", "السطح", "المكتب", "المخزن", "المصعد", "الشارع"
    ]
}

# وصف مختصر للمواضيع
TOPICS_DESCRIPTION = {
    "🍔 أكلات": "أطعمة ومأكولات من كل العالم",
    "👤 شخصيات": "مشاهير وشخصيات معروفة",
    "🌍 بلاد": "دول وعواصم ومدن",
    "🏛️ أماكن": "أماكن سياحية ومرافق عامة",
    "🎮 أشياء عشوائية": "أشياء نستخدمها يومياً ",
    "🏠 أماكن يومية": "أماكن في المنزل والحياة اليومية"
}

# أوقات الجولة المحددة مسبقاً (بالدقائق)
PREDEFINED_TIMES = [1, 2, 3, 5, 7, 10]

class DataManager:
    """مدير حفظ واسترجاع البيانات"""
    
    @staticmethod
    def load_json(file_path, default=None):
        if default is None:
            default = {}
        try:
            if Path(file_path).exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"خطأ في تحميل {file_path}: {e}")
        return default
    
    @staticmethod
    def save_json(file_path, data):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"خطأ في حفظ {file_path}: {e}")
            return False
    
    @staticmethod
    def load_all():
        return {
            'points': DataManager.load_json(POINTS_FILE, {}),
            'channels': DataManager.load_json(CHANNELS_FILE, {
                'enabled': False,
                'channels': [],
                'last_update': None
            }),
            'settings': DataManager.load_json(SETTINGS_FILE, {
                'notifications': True,
                'welcome_message': True,
                'auto_restart': True,
                'round_time': 5  # وقت الجولة الافتراضي 5 دقائق
            }),
            'users': DataManager.load_json(USERS_FILE, {}),
            'game_state': DataManager.load_json(GAME_FILE, {
                'players': {},
                'player_names': {},
                'imposters': [],
                'topic': '',
                'secret_item': '',
                'started': False,
                'current_pair': [],
                'question_asked': False,
                'asked_players': [],
                'answered_players': [],
                'question_start_time': None,
                'round_time': 5  # وقت الجولة الافتراضي
            })
        }
    
    @staticmethod
    def save_all(data):
        results = []
        results.append(DataManager.save_json(POINTS_FILE, data.get('points', {})))
        results.append(DataManager.save_json(CHANNELS_FILE, data.get('channels', {})))
        results.append(DataManager.save_json(SETTINGS_FILE, data.get('settings', {})))
        results.append(DataManager.save_json(USERS_FILE, data.get('users', {})))
        results.append(DataManager.save_json(GAME_FILE, data.get('game_state', {})))
        return all(results)

class GameState:
    def __init__(self):
        data = DataManager.load_all()
        
        self.players: Dict[int, str] = data['game_state'].get('players', {})
        self.player_names: Dict[int, str] = data['game_state'].get('player_names', {})
        self.imposters: Set[int] = set(data['game_state'].get('imposters', []))
        self.votes: Dict[int, int] = {}
        self.topic: str = data['game_state'].get('topic', '')
        self.secret_item: str = data['game_state'].get('secret_item', '')
        self.started: bool = data['game_state'].get('started', False)
        self.voting: bool = False
        self.current_pair: List[int] = data['game_state'].get('current_pair', [])
        self.question_asked: bool = data['game_state'].get('question_asked', False)
        self.asked_players: List[int] = data['game_state'].get('asked_players', [])
        self.answered_players: List[int] = data['game_state'].get('answered_players', [])
        self.question_start_time: Optional[datetime.datetime] = None
        if data['game_state'].get('question_start_time'):
            try:
                self.question_start_time = datetime.datetime.fromisoformat(data['game_state']['question_start_time'])
            except:
                self.question_start_time = None
        
        self.scores: Dict[int, int] = data['points']
        
        channels_data = data['channels']
        self.channels_enabled: bool = channels_data.get('enabled', False)
        self.channels: List[dict] = channels_data.get('channels', [])
        
        settings_data = data['settings']
        self.notifications_enabled: bool = settings_data.get('notifications', True)
        self.welcome_message_enabled: bool = settings_data.get('welcome_message', True)
        self.round_time: int = settings_data.get('round_time', 5)  # وقت الجولة بالدقائق
        
        self.users: Dict[int, dict] = data['users']
        
        self.game_chat_id: Optional[int] = None
        self.num_imposters: int = 1
        self.imposters_selected: bool = False
        self.question_task: Optional[asyncio.Task] = None
        self.voting_task: Optional[asyncio.Task] = None
        self.discovery_task: Optional[asyncio.Task] = None
        
        self.bot_start_time = datetime.datetime.now()
        self.total_games = 0
        self.total_players = len(self.scores)
    
    def save_state(self):
        data = {
            'points': self.scores,
            'channels': {
                'enabled': self.channels_enabled,
                'channels': self.channels,
                'last_update': datetime.datetime.now().isoformat()
            },
            'settings': {
                'notifications': self.notifications_enabled,
                'welcome_message': self.welcome_message_enabled,
                'auto_restart': True,
                'round_time': self.round_time
            },
            'users': self.users,
            'game_state': {
                'players': self.players,
                'player_names': self.player_names,
                'imposters': list(self.imposters),
                'topic': self.topic,
                'secret_item': self.secret_item,
                'started': self.started,
                'current_pair': self.current_pair,
                'question_asked': self.question_asked,
                'asked_players': self.asked_players,
                'answered_players': self.answered_players,
                'question_start_time': self.question_start_time.isoformat() if self.question_start_time else None,
                'round_time': self.round_time,
                'saved_at': datetime.datetime.now().isoformat()
            }
        }
        return DataManager.save_all(data)
    
    def add_user(self, user_id: int, username: str, first_name: str = ""):
        if user_id not in self.users:
            self.users[user_id] = {
                'username': username,
                'first_name': first_name,
                'joined_at': datetime.datetime.now().isoformat(),
                'games_played': 0,
                'last_seen': datetime.datetime.now().isoformat()
            }
        else:
            self.users[user_id]['username'] = username
            self.users[user_id]['first_name'] = first_name
            self.users[user_id]['last_seen'] = datetime.datetime.now().isoformat()
        self.save_state()
    
    def add_score(self, user_id: int, points: int):
        if user_id not in self.scores:
            self.scores[user_id] = 0
        self.scores[user_id] += points
        
        if user_id in self.users:
            if 'games_played' not in self.users[user_id]:
                self.users[user_id]['games_played'] = 0
            self.users[user_id]['games_played'] += 1
        
        self.save_state()
    
    def reset_game(self):
        if self.question_task and not self.question_task.done():
            self.question_task.cancel()
        if self.voting_task and not self.voting_task.done():
            self.voting_task.cancel()
        if self.discovery_task and not self.discovery_task.done():
            self.discovery_task.cancel()
        
        self.players.clear()
        self.player_names.clear()
        self.imposters.clear()
        self.votes.clear()
        self.topic = ""
        self.secret_item = ""
        self.started = False
        self.voting = False
        self.current_pair.clear()
        self.question_asked = False
        self.asked_players.clear()
        self.answered_players.clear()
        self.question_start_time = None
        self.imposters_selected = False
        self.num_imposters = 1
        
        self.save_state()

game_state = GameState()

# ==================== KEYBOARD BUILDERS ====================
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("👤 تسجيل باسمي", callback_data="register_name")],
        [InlineKeyboardButton("➕ تسجيل بلاعبين", callback_data="register")],
        [InlineKeyboardButton("👥 اختيار عدد الإمبوستر", callback_data="select_imposters")],
        [InlineKeyboardButton("🎯 اختيار الموضوع", callback_data="choose_topic")],
        [InlineKeyboardButton("⏰ تحديد وقت الجولة", callback_data="set_round_time")],
        [InlineKeyboardButton("🚀 بدء اللعبة", callback_data="start_game")],
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="stats")],
        [InlineKeyboardButton("ℹ️ معلومات المطور", callback_data="dev_info")]
    ]
    
    if game_state.channels_enabled and game_state.channels:
        keyboard.insert(0, [InlineKeyboardButton("📢 قنوات الإشتراك", callback_data="check_subscription")])
    
    if game_state.players:
        keyboard.append([InlineKeyboardButton("🔄 جولة جديدة", callback_data="new_round")])
    
    return InlineKeyboardMarkup(keyboard)

def subscription_keyboard():
    keyboard = []
    for channel in game_state.channels:
        if channel.get('username'):
            keyboard.append([
                InlineKeyboardButton(
                    f"📢 {channel.get('name', 'قناة')}",
                    url=f"https://t.me/{channel['username'].replace('@', '')}"
                )
            ])
    keyboard.append([
        InlineKeyboardButton("✅ تحقق من الإشتراك", callback_data="verify_subscription"),
        InlineKeyboardButton("🔙 رجوع", callback_data="back_to_menu")
    ])
    return InlineKeyboardMarkup(keyboard)

def imposters_count_keyboard():
    keyboard = []
    max_imposters = min(3, len(game_state.players) - 2)
    for i in range(1, max_imposters + 1):
        keyboard.append([InlineKeyboardButton(f"{i} إمبوستر", callback_data=f"imposters_{i}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(keyboard)

def topics_keyboard():
    keyboard = []
    for topic in TOPICS_DATA.keys():
        description = TOPICS_DESCRIPTION.get(topic, '')
        keyboard.append([
            InlineKeyboardButton(f"{topic} ({description})", callback_data=f"topic_{topic}")
        ])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(keyboard)

def round_time_keyboard():
    """لوحة اختيار وقت الجولة"""
    keyboard = []
    
    # الأوقات المحددة مسبقاً
    for time_min in PREDEFINED_TIMES:
        keyboard.append([
            InlineKeyboardButton(f"⏰ {time_min} دقيقة", callback_data=f"round_time_{time_min}")
        ])
    
    # زر الوقت المخصص
    keyboard.append([
        InlineKeyboardButton("🕒 وقت مخصص (أدخل عدد الدقائق)", callback_data="custom_time")
    ])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_menu")])
    
    return InlineKeyboardMarkup(keyboard)

def voting_keyboard():
    keyboard = []
    for user_id, username in game_state.player_names.items():
        keyboard.append([
            InlineKeyboardButton(f"👤 {username}", callback_data=f"vote_{user_id}")
        ])
    keyboard.append([InlineKeyboardButton("✅ إنهاء التصويت", callback_data="end_vote")])
    return InlineKeyboardMarkup(keyboard)

def end_question_keyboard(player_id):
    """زر إنهاء السؤال (يعمل فقط للاعب المحدد)"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ إنهاء إجابتي", callback_data=f"end_question_{player_id}")]
    ])

def discovery_keyboard():
    """زر اكتشاف الإمبوستر بعد انتهاء الوقت"""
    keyboard = []
    for user_id, name in game_state.player_names.items():
        keyboard.append([
            InlineKeyboardButton(f"🚨 أشك بأن {name} هو الإمبوستر", callback_data=f"discover_{user_id}")
        ])
    return InlineKeyboardMarkup(keyboard)

def admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔄 إعادة ضبط كاملة", callback_data="admin_reset")],
        [InlineKeyboardButton("📊 إحصائيات البوت", callback_data="bot_stats")],
        [InlineKeyboardButton("📢 إدارة القنوات", callback_data="manage_channels")],
        [InlineKeyboardButton("🔔 إدارة الإشعارات", callback_data="manage_notifications")],
        [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data="manage_users")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def channels_management_keyboard():
    status = "✅ مفعل" if game_state.channels_enabled else "❌ معطل"
    keyboard = [
        [InlineKeyboardButton(f"🔄 حالة الإشتراك: {status}", callback_data="toggle_subscription")],
        [InlineKeyboardButton("➕ إضافة قناة", callback_data="add_channel")],
        [InlineKeyboardButton("🗑 حذف قناة", callback_data="remove_channel")],
        [InlineKeyboardButton("📋 قائمة القنوات", callback_data="list_channels")],
        [InlineKeyboardButton("🔙 رجوع للإدارة", callback_data="admin_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def notifications_management_keyboard():
    welcome_status = "✅ مفعل" if game_state.welcome_message_enabled else "❌ معطل"
    notif_status = "✅ مفعل" if game_state.notifications_enabled else "❌ معطل"
    keyboard = [
        [InlineKeyboardButton(f"🔔 رسالة الترحيب: {welcome_status}", callback_data="toggle_welcome")],
        [InlineKeyboardButton(f"📢 إشعارات البدء: {notif_status}", callback_data="toggle_notifications")],
        [InlineKeyboardButton("🔙 رجوع للإدارة", callback_data="admin_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==================== SUBSCRIPTION SYSTEM ====================
async def check_user_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """التحقق من اشتراك المستخدم في القنوات المطلوبة"""
    if not game_state.channels_enabled or not game_state.channels:
        return True
    
    for channel in game_state.channels:
        channel_id = channel.get('id')
        if channel_id:
            try:
                member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                if member.status in ['left', 'kicked']:
                    return False
            except Exception as e:
                logger.error(f"خطأ في التحقق من الإشتراك: {e}")
                return False
    return True

async def require_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """طلب الإشتراك إذا كان مطلوباً"""
    if not game_state.channels_enabled or not game_state.channels:
        return True
    
    user_id = update.effective_user.id
    is_subscribed = await check_user_subscription(user_id, context)
    
    if not is_subscribed:
        await update.message.reply_text(
            "📢 **يجب الإشتراك في القنوات التالية لاستخدام البوت:**\n\n"
            "يرجى الإشتراك ثم الضغط على تحقق من الإشتراك",
            reply_markup=subscription_keyboard()
        )
        return False
    return True

# ==================== GAME LOGIC ====================
def select_imposters():
    """اختيار الإمبوستر عشوائياً"""
    player_ids = list(game_state.players.keys())
    if len(player_ids) >= game_state.num_imposters:
        game_state.imposters = set(random.sample(player_ids, game_state.num_imposters))
    else:
        game_state.imposters = set()

def select_secret_item():
    """اختيار عنصر سري للموضوع المحدد"""
    if game_state.topic in TOPICS_DATA:
        items = TOPICS_DATA[game_state.topic]
        game_state.secret_item = random.choice(items)

def select_random_pair():
    """اختيار زوجين من اللاعبين لم يسألوا بعد"""
    available_players = [
        player_id for player_id in game_state.players.keys()
        if player_id not in game_state.asked_players
    ]
    
    if len(available_players) < 2:
        # إعادة تعيين إذا تم سؤال الجميع تقريباً
        game_state.asked_players.clear()
        available_players = list(game_state.players.keys())
    
    if len(available_players) >= 2:
        # اختيار لاعبين عشوائيين
        selected = random.sample(available_players, 2)
        return selected
    return []

def format_pair_question_message(player1_name: str, player2_name: str, secret_item: str, topic: str) -> str:
    """تنسيق رسالة السؤال للزوجين"""
    return (
        f"🎯 **دور الزوجين للإجابة**\n\n"
        f"👥 **اللاعبان:** {player1_name} و {player2_name}\n\n"
        f"📝 **السؤال:**\n"
        f"العنصر السري هو شيء من فئة: **{topic}**\n\n"
        f"💭 **مهمتكم:**\n"
        f"• حاولوا وصف العنصر دون ذكر اسمه مباشرة\n"
        f"• استخدموا التلميحات والإشارات\n"
        f"• الإمبوستر يحاول اكتشاف العنصر من وصفكم\n\n"
        f"⏰ **الوقت:** لديكم 30 ثانية للإجابة"
    )

# ==================== HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /start"""
    user = update.effective_user
    chat = update.effective_chat
    
    # حفظ بيانات المستخدم
    game_state.add_user(user.id, user.username or "", user.first_name)
    
    # التحقق من الإشتراك الإجباري
    if game_state.channels_enabled and game_state.channels:
        if not await require_subscription(update, context):
            return
    
    # إرسال إشعار البدء إذا كان مفعلاً
    if game_state.notifications_enabled and game_state.welcome_message_enabled:
        try:
            await context.bot.send_message(
                chat_id=OWNER_ID,
                text=f"🔔 **مستخدم جديد!**\n\n"
                     f"👤 الاسم: {user.first_name}\n"
                     f"🆔 ID: {user.id}\n"
                     f"📅 الوقت: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except:
            pass
    
    if chat.type == "private":
        await update.message.reply_text(
            f"🎮 **مرحباً {user.first_name} في لعبة الإمبوستر!**\n\n"
            f"👑 **المطور:** {OWNER_TELEGRAM}\n"
            f"📱 **تيك توك:** {OWNER_TIKTOK}\n\n"
            "**قواعد اللعبة الجديدة:**\n"
            "1️⃣ سجل نفسك في اللعبة (3 لاعبين كحد أدنى)\n"
            "2️⃣ اختر عدد الإمبوستر (1-3)\n"
            "3️⃣ اختر موضوعاً للأسئلة\n"
            "4️⃣ حدد وقت الجولة (افتراضي 5 دقائق)\n"
            "5️⃣ ابدأ اللعبة ليتم تعيين الأدوار\n"
            "6️⃣ البوت يختار عنصراً سرياً عشوائياً\n"
            "7️⃣ اللاعبون العاديون يعرفون العنصر السري\n"
            "8️⃣ الإمبوستر لا يعرف العنصر ويحاول اكتشافه\n"
            "9️⃣ البوت يسأل زوجين من اللاعبين في كل مرة\n"
            "🔟 كل لاعب يجيب باستخدام زر إنهاء الإجابة\n"
            "⏰ بعد انتهاء الوقت المحدد، يمكن للجميع التصويت على الإمبوستر\n\n"
            "🏆 الفائزون يحصلون على نقاط تراكمية",
            reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            "🎮 **لعبة الإمبوستر في المجموعة**\n\n"
            "استخدم /play لبدء اللعبة في المجموعة\n"
            "أو تحدث مع البوت في الخاص للتحكم الكامل"
        )

async def play_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /play في المجموعات"""
    if update.effective_chat.type in ["group", "supergroup"]:
        game_state.game_chat_id = update.effective_chat.id
        await update.message.reply_text(
            "🎮 **لعبة الإمبوستر النصية**\n\n"
            "• الحد الأدنى: 3 لاعبين\n"
            "• سيتم إرسال الأدوار والأسئلة في الخاص\n"
            "• التصويت يكون في المجموعة\n"
            "• البوت يسأل زوجين من اللاعبين في كل مرة\n"
            "• استخدم الأزرار أدناه للتحكم:",
            reply_markup=main_menu_keyboard()
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أزرار الإنلاين"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    # التحقق من الإشتراك أولاً
    if game_state.channels_enabled and game_state.channels:
        if data not in ["check_subscription", "verify_subscription", "back_to_menu"]:
            if not await check_user_subscription(query.from_user.id, context):
                await query.edit_message_text(
                    "📢 **يجب الإشتراك في القنوات أولاً!**\n\n"
                    "يرجى الإشتراك ثم الضغط على تحقق من الإشتراك",
                    reply_markup=subscription_keyboard()
                )
                return
    
    # معالجة الأزرار
    handlers = {
        "register_name": register_with_name,
        "register": register_player,
        "select_imposters": select_imposters_menu,
        "choose_topic": choose_topic_menu,
        "set_round_time": set_round_time_menu,
        "start_game": start_game,
        "stats": show_stats,
        "dev_info": show_dev_info,
        "new_round": new_round,
        "check_subscription": check_subscription,
        "verify_subscription": verify_subscription,
        "end_vote": end_voting,
        "back_to_menu": back_to_menu,
        "admin_panel": admin_panel,
        "admin_reset": admin_reset,
        "bot_stats": bot_stats,
        "manage_channels": manage_channels,
        "manage_notifications": manage_notifications,
        "manage_users": manage_users,
        "toggle_subscription": toggle_subscription,
        "add_channel": add_channel_menu,
        "remove_channel": remove_channel_menu,
        "list_channels": list_channels,
        "toggle_welcome": toggle_welcome,
        "toggle_notifications": toggle_notifications,
        "custom_time": custom_time_input
    }
    
    # معالجة اختيار عدد الإمبوستر
    if data.startswith("imposters_"):
        await set_imposters_count(query, context)
    # معالجة اختيار الموضوع
    elif data.startswith("topic_"):
        await choose_topic(query, context)
    # معالجة اختيار وقت الجولة
    elif data.startswith("round_time_"):
        await set_round_time(query, context)
    # معالجة التصويت
    elif data.startswith("vote_"):
        await cast_vote(query, context)
    # معالجة إنهاء السؤال
    elif data.startswith("end_question_"):
        await end_player_question(query, context)
    # معالجة اكتشاف الإمبوستر
    elif data.startswith("discover_"):
        await discover_imposter(query, context)
    # حذف قناة معينة
    elif data.startswith("remove_channel_"):
        await remove_channel(query, context)
    # استدعاء الدالة المناسبة
    elif data in handlers:
        await handlers[data](query, context)

async def check_subscription(query, context):
    """عرض قنوات الإشتراك"""
    if not game_state.channels_enabled or not game_state.channels:
        await query.edit_message_text(
            "📢 **نظام الإشتراك الإجباري معطل حالياً**",
            reply_markup=main_menu_keyboard()
        )
        return
    
    await query.edit_message_text(
        "📢 **قنوات الإشتراك الإجباري:**\n\n"
        "يرجى الإشتراك في القنوات التالية:\n"
        "ثم اضغط على 'تحقق من الإشتراك'",
        reply_markup=subscription_keyboard()
    )

async def verify_subscription(query, context):
    """التحقق من الإشتراك"""
    user_id = query.from_user.id
    is_subscribed = await check_user_subscription(user_id, context)
    
    if is_subscribed:
        await query.edit_message_text(
            "✅ **تم التحقق من إشتراكك!**\n\n"
            "يمكنك الآن استخدام البوت بشكل كامل",
            reply_markup=main_menu_keyboard()
        )
    else:
        await query.answer("❌ لم يتم الإشتراك في جميع القنوات!", show_alert=True)

async def back_to_menu(query, context):
    """العودة للقائمة الرئيسية"""
    await query.edit_message_text(
        "🎮 **القائمة الرئيسية**",
        reply_markup=main_menu_keyboard()
    )

async def admin_panel(query, context):
    """لوحة تحكم المطور"""
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ ليس لديك صلاحية!", show_alert=True)
        return
    
    await query.edit_message_text(
        "👑 **لوحة تحكم المطور**\n\n"
        f"🆔 ID المطور: {OWNER_ID}\n"
        f"📱 تيك توك: {OWNER_TIKTOK}\n"
        f"✉️ تليجرام: {OWNER_TELEGRAM}",
        reply_markup=admin_keyboard()
    )

async def register_with_name(query, context):
    """التسجيل بإدخال اسم"""
    if game_state.started:
        await query.edit_message_text(
            "❌ اللعبة قد بدأت بالفعل!\nلا يمكن تسجيل لاعبين جدد",
            reply_markup=main_menu_keyboard()
        )
        return
    
    await query.edit_message_text(
        "👤 **التسجيل باسمك:**\n\n"
        "أرسل اسمك الذي تريد التسجيل به:\n"
        "(مثال: محمد، أحمد، سارة)\n\n"
        "أو /cancel للإلغاء"
    )
    
    context.user_data['awaiting_name'] = True
    context.user_data['user_id'] = query.from_user.id

async def register_player(query, context):
    """التسجيل باليوزر الافتراضي"""
    if game_state.started:
        await query.edit_message_text(
            "❌ اللعبة قد بدأت بالفعل!\nلا يمكن تسجيل لاعبين جدد",
            reply_markup=main_menu_keyboard()
        )
        return
    
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    
    if user_id in game_state.players:
        await query.edit_message_text(
            f"✅ أنت مسجل بالفعل كـ **{game_state.player_names.get(user_id, username)}**",
            reply_markup=main_menu_keyboard()
        )
        return
    
    game_state.players[user_id] = username
    game_state.player_names[user_id] = username
    game_state.save_state()
    
    await query.edit_message_text(
        f"✅ تم تسجيل **{username}** في اللعبة\n"
        f"👥 عدد اللاعبين: {len(game_state.players)}\n\n"
        f"📋 **الحد الأدنى: 3 لاعبين**",
        reply_markup=main_menu_keyboard()
    )

async def select_imposters_menu(query, context):
    """عرض قائمة اختيار عدد الإمبوستر"""
    if len(game_state.players) < 3:
        await query.edit_message_text(
            "❌ تحتاج على الأقل 3 لاعبين لتحديد عدد الإمبوستر",
            reply_markup=main_menu_keyboard()
        )
        return
    
    max_imposters = min(3, len(game_state.players) - 2)
    await query.edit_message_text(
        f"👥 **اختر عدد الإمبوستر**\n\n"
        f"عدد اللاعبين: {len(game_state.players)}\n"
        f"الحد الأقصى: {max_imposters} إمبوستر\n\n"
        f"💡 الموصى به:\n"
        f"• 3 لاعبين: 1 إمبوستر\n"
        f"• 4-5 لاعبين: 1-2 إمبوستر\n"
        f"• 6+ لاعبين: 2-3 إمبوستر",
        reply_markup=imposters_count_keyboard()
    )

async def set_imposters_count(query, context):
    """تعيين عدد الإمبوستر"""
    num = int(query.data.replace("imposters_", ""))
    game_state.num_imposters = num
    game_state.imposters_selected = True
    game_state.save_state()
    
    await query.edit_message_text(
        f"✅ تم اختيار **{num} إمبوستر**\n\n"
        f"👥 عدد اللاعبين: {len(game_state.players)}\n"
        f"👤 اللاعبون العاديون: {len(game_state.players) - num}\n"
        f"🎭 الإمبوستر: {num}",
        reply_markup=main_menu_keyboard()
    )

async def choose_topic_menu(query, context):
    """عرض قائمة المواضيع"""
    await query.edit_message_text(
        "🎯 **اختر موضوع الأسئلة:**\n\n"
        "سيختار البوت عنصراً عشوائياً من القائمة المختارة",
        reply_markup=topics_keyboard()
    )

async def choose_topic(query, context):
    """اختيار موضوع محدد"""
    topic = query.data.replace("topic_", "")
    game_state.topic = topic
    select_secret_item()
    game_state.save_state()
    
    description = TOPICS_DESCRIPTION.get(topic, '')
    await query.edit_message_text(
        f"✅ تم اختيار موضوع: **{topic}**\n"
        f"📝 الوصف: {description}\n"
        f"🔢 عدد العناصر: {len(TOPICS_DATA[topic])}\n\n"
        f"🎲 البوت سيختار عنصراً عشوائياً من هذه القائمة",
        reply_markup=main_menu_keyboard()
    )

async def set_round_time_menu(query, context):
    """عرض قائمة أوقات الجولة"""
    await query.edit_message_text(
        f"⏰ **حدد وقت الجولة الحالي:** {game_state.round_time} دقيقة\n\n"
        f"🕒 **اختر من الأوقات المتاحة:**\n"
        f"أو اختر وقتاً مخصصاً بإدخال عدد الدقائق",
        reply_markup=round_time_keyboard()
    )

async def set_round_time(query, context):
    """تعيين وقت الجولة من القائمة"""
    time_min = int(query.data.replace("round_time_", ""))
    game_state.round_time = time_min
    game_state.save_state()
    
    await query.edit_message_text(
        f"✅ **تم تحديد وقت الجولة:** {time_min} دقيقة\n\n"
        f"⏰ سيتم إنهاء الجولة بعد {time_min} دقيقة\n"
        f"ثم يبدأ التصويت لاكتشاف الإمبوستر",
        reply_markup=main_menu_keyboard()
    )

async def custom_time_input(query, context):
    """طلب إدخال وقت مخصص"""
    await query.edit_message_text(
        "🕒 **أدخل وقت الجولة المطلوب:**\n\n"
        "أرسل عدد الدقائق (مثال: 3، 7، 15)\n"
        "📝 الحد الأدنى: 1 دقيقة\n"
        "📝 الحد الأقصى: 60 دقيقة\n\n"
        "أو /cancel للإلغاء"
    )
    
    context.user_data['awaiting_custom_time'] = True

async def start_game(query, context):
    """بدء اللعبة"""
    # التحقق من الشروط
    if len(game_state.players) < 3:
        await query.edit_message_text(
            "❌ تحتاج على الأقل 3 لاعبين لبدء اللعبة",
            reply_markup=main_menu_keyboard()
        )
        return
    
    if not game_state.imposters_selected:
        await query.edit_message_text(
            "❌ يجب اختيار عدد الإمبوستر أولاً",
            reply_markup=main_menu_keyboard()
        )
        return
    
    if not game_state.topic:
        await query.edit_message_text(
            "❌ يجب اختيار موضوع أولاً",
            reply_markup=main_menu_keyboard()
        )
        return
    
    game_state.started = True
    select_imposters()
    game_state.question_start_time = datetime.datetime.now()
    game_state.save_state()
    
    # إرسال الأدوار للجميع
    for user_id in game_state.players.keys():
        try:
            player_name = game_state.player_names.get(user_id, "لاعب")
            
            if user_id in game_state.imposters:
                message = (
                    f"🎭 **{player_name}، أنت الإمبوستر!**\n\n"
                    f"**مهمتك:**\n"
                    f"• حاول ألا يكتشفك اللاعبون\n"
                    f"• أنت لا تعرف العنصر السري\n"
                    f"• الموضوع: {game_state.topic}\n"
                    f"• العنصر السري: ❓\n"
                    f"• وقت الجولة: {game_state.round_time} دقيقة\n\n"
                    f"💡 **نصيحة:**\n"
                    f"• استمع لوصف اللاعبين الآخرين\n"
                    f"• حاول تخمين العنصر السري\n"
                    f"• لا تكشف أنك إمبوستر\n\n"
                    f"🏆 **الفوز:** إذا لم يتم اكتشافك"
                )
            else:
                message = (
                    f"✅ **{player_name}، أنت لاعب عادي**\n\n"
                    f"**الموضوع هو:** {game_state.topic}\n"
                    f"**العنصر السري هو:** **{game_state.secret_item}**\n"
                    f"**وقت الجولة:** {game_state.round_time} دقيقة\n\n"
                    f"**مهمتك:**\n"
                    f"• اكتشف الإمبوستر من خلال الأسئلة\n"
                    f"• سيقوم البوت بسؤالك مع لاعب آخر\n"
                    f"• عند سؤالك، استخدم زر إنهاء الإجابة\n"
                    f"• صف العنصر دون ذكر اسمه مباشرة\n\n"
                    f"🏆 **الفوز:** إذا تم اكتشاف الإمبوستر"
                )
            
            await context.bot.send_message(chat_id=user_id, text=message)
            
        except Exception as e:
            logger.error(f"فشل إرسال الدور: {e}")
    
    # إرسال رسالة البدء
    chat_id = game_state.game_chat_id or query.message.chat.id
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🚀 **بدأت اللعبة!**\n\n"
            f"👥 عدد اللاعبين: {len(game_state.players)}\n"
            f"🎯 الموضوع: {game_state.topic}\n"
            f"🎭 عدد الإمبوستر: {len(game_state.imposters)}\n"
            f"⏰ وقت الجولة: {game_state.round_time} دقيقة\n"
            f"✅ تم إرسال الأدوار للجميع في الخاص\n\n"
            f"⏰ ستبدأ الأسئلة بعد 5 ثوانٍ..."
        )
    )
    
    # بدء الأسئلة
    game_state.question_task = asyncio.create_task(start_questions(chat_id, context))

async def start_questions(chat_id, context):
    """بدء جولة الأسئلة"""
    await asyncio.sleep(5)
    
    # بدء عملية السؤال العشوائي للزوجين
    game_state.discovery_task = asyncio.create_task(start_discovery_timer(chat_id, context))
    
    # طرح أول سؤال لزوجين
    await ask_random_pair(chat_id, context)

async def ask_random_pair(chat_id, context):
    """سؤال زوجين عشوائيين"""
    if not game_state.started:
        return
    
    pair = select_random_pair()
    if len(pair) < 2:
        return
    
    player1_id, player2_id = pair[0], pair[1]
    player1_name = game_state.player_names.get(player1_id, "لاعب")
    player2_name = game_state.player_names.get(player2_id, "لاعب")
    
    game_state.current_pair = pair
    game_state.question_asked = True
    game_state.asked_players.extend(pair)
    game_state.answered_players.clear()
    game_state.save_state()
    
    # إرسال السؤال للجميع
    question_msg = await context.bot.send_message(
        chat_id=chat_id,
        text=format_pair_question_message(player1_name, player2_name, game_state.secret_item, game_state.topic)
    )
    
    # إرسال زر إنهاء السؤال لكل لاعب في الزوج
    for player_id in pair:
        try:
            player_name = game_state.player_names.get(player_id, "لاعب")
            
            if player_id in game_state.imposters:
                message_text = (
                    f"🎤 **{player_name}، دورك للإجابة الآن!**\n\n"
                    f"⚠️ **أنت الإمبوستر!**\n"
                    f"لا تعرف العنصر السري، حاول التظاهر بأنك تعرفه.\n"
                    f"الموضوع: {game_state.topic}"
                )
            else:
                message_text = (
                    f"🎤 **{player_name}، دورك للإجابة الآن!**\n\n"
                    f"🔒 **العنصر السري هو:** **{game_state.secret_item}**\n"
                    f"💡 **وصفه دون ذكر اسمه!**"
                )
            
            await context.bot.send_message(
                chat_id=player_id,
                text=message_text,
                reply_markup=end_question_keyboard(player_id)
            )
        except Exception as e:
            logger.error(f"فشل إرسال زر الإجابة: {e}")
    
    # انتظار 30 ثانية ثم التالي
    await asyncio.sleep(30)
    
    # إذا لم يتم إنهاء السؤال من الجميع، ننتقل للزوج التالي
    if game_state.question_asked:
        await ask_random_pair(chat_id, context)

async def end_player_question(query, context):
    """إنهاء إجابة اللاعب"""
    player_id = int(query.data.replace("end_question_", ""))
    
    if query.from_user.id != player_id:
        await query.answer("❌ هذا الزر لك فقط!", show_alert=True)
        return
    
    if player_id not in game_state.current_pair:
        await query.answer("❌ ليس دورك الآن!", show_alert=True)
        return
    
    if player_id not in game_state.answered_players:
        game_state.answered_players.append(player_id)
        game_state.save_state()
    
    player_name = game_state.player_names.get(player_id, "لاعب")
    await query.answer(f"✅ تم إنهاء إجابتك، {player_name}")
    
    # إذا انتهى الجميع، ننتقل للزوج التالي
    if len(game_state.answered_players) == len(game_state.current_pair):
        game_state.question_asked = False
        game_state.save_state()
        
        chat_id = game_state.game_chat_id or query.message.chat_id
        await asyncio.sleep(2)
        await ask_random_pair(chat_id, context)

async def start_discovery_timer(chat_id, context):
    """مؤقت وقت الجولة لاكتشاف الإمبوستر"""
    # تحويل الدقائق إلى ثواني
    wait_time = game_state.round_time * 60
    
    await asyncio.sleep(wait_time)  # انتظار الوقت المحدد
    
    if game_state.started:
        # إرسال زر اكتشاف الإمبوستر للجميع
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"⏰ **انتهى وقت الجولة ({game_state.round_time} دقيقة)!**\n\n"
                f"🏁 **حان وقت اكتشاف الإمبوستر!**\n\n"
                f"اضغط على الزر الذي يشير إلى من تعتقد أنه الإمبوستر:"
            ),
            reply_markup=discovery_keyboard()
        )

async def discover_imposter(query, context):
    """اكتشاف الإمبوستر"""
    if not game_state.started:
        await query.answer("❌ اللعبة انتهت!", show_alert=True)
        return
    
    suspect_id = int(query.data.replace("discover_", ""))
    voter_id = query.from_user.id
    
    if voter_id not in game_state.players:
        await query.answer("❌ أنت لست لاعباً في هذه الجولة!", show_alert=True)
        return
    
    game_state.votes[voter_id] = suspect_id
    suspect_name = game_state.player_names.get(suspect_id, "لاعب")
    
    await query.answer(f"✅ تم اختيار {suspect_name} كإمبوستر مشتبه به")
    
    # تحديث عدد الأصوات
    vote_counts = {}
    for voted_id in game_state.votes.values():
        vote_counts[voted_id] = vote_counts.get(voted_id, 0) + 1
    
    # إذا صوت الجميع، ننهي الاكتشاف
    if len(game_state.votes) == len(game_state.players):
        await end_discovery(query.message.chat.id, context)

async def end_discovery(chat_id, context):
    """إنهاء عملية الاكتشاف"""
    game_state.started = False
    game_state.voting = True
    
    if not game_state.votes:
        result_msg = "❌ **لم يصوت أحد!**\n\n🎭 **الإمبوستر يفوز!**"
        for imp_id in game_state.imposters:
            game_state.add_score(imp_id, 20)
    else:
        # حساب الأصوات
        vote_counts = {}
        for voted_id in game_state.votes.values():
            vote_counts[voted_id] = vote_counts.get(voted_id, 0) + 1
        
        # العثور على الأعلى تصويتاً
        max_votes = max(vote_counts.values())
        most_voted = [uid for uid, votes in vote_counts.items() if votes == max_votes]
        
        if len(most_voted) > 1:
            eliminated_id = random.choice(most_voted)
        else:
            eliminated_id = most_voted[0]
        
        eliminated_name = game_state.player_names.get(eliminated_id, "لاعب")
        
        # عرض النتائج
        result_msg = "📊 **نتائج الاكتشاف:**\n\n"
        for user_id, username in game_state.player_names.items():
            count = vote_counts.get(user_id, 0)
            result_msg += f"• {username}: {count} تصويت\n"
        
        result_msg += f"\n🗳 **الأكثر اشتباهاً:** {eliminated_name}\n\n"
        
        # تحديد الفائز
        if eliminated_id in game_state.imposters:
            result_msg += "🎉 **تم اكتشاف الإمبوستر!**\n\n✅ **اللاعبون العاديون يفوزون!**"
            for user_id in game_state.players:
                if user_id not in game_state.imposters:
                    game_state.add_score(user_id, 15)
        else:
            imposters_names = [game_state.player_names.get(imp, "لاعب") for imp in game_state.imposters]
            result_msg += (
                f"💀 **للأسف! كان لاعباً عادياً**\n\n"
                f"🎭 **الإمبوستر كانوا:** {', '.join(imposters_names)}\n"
                f"🔒 **العنصر السري كان:** {game_state.secret_item}\n\n"
                f"🏆 **الإمبوستر يفوزون!**"
            )
            for imp_id in game_state.imposters:
                game_state.add_score(imp_id, 25)
    
    await context.bot.send_message(chat_id=chat_id, text=result_msg)
    
    # جولة جديدة بعد تأخير
    await asyncio.sleep(5)
    await new_round(None, context, chat_id)

async def end_voting(query, context):
    """إنهاء التصويت (للتوافق)"""
    await discover_imposter(query, context)

async def new_round(query, context, chat_id=None):
    """بدء جولة جديدة"""
    if query:
        await query.answer()
        chat_id = query.message.chat.id
    
    game_state.reset_game()
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "🔄 **جولة جديدة!**\n\n"
            "يمكن للاعبين التسجيل من جديد\n"
            "اختر عدد الإمبوستر ثم الموضوع\n\n"
            "📊 النقاط محفوظة ومتراكمة"
        ),
        reply_markup=main_menu_keyboard()
    )

async def show_stats(query, context):
    """عرض إحصائيات اللاعبين"""
    if not game_state.scores:
        await query.edit_message_text(
            "📊 **لا توجد إحصائيات بعد**\n\nابدأ اللعبة لتراكم النقاط",
            reply_markup=main_menu_keyboard()
        )
        return
    
    sorted_scores = sorted(game_state.scores.items(), key=lambda x: x[1], reverse=True)[:10]
    
    stats_text = "🏆 **أعلى 10 لاعبين:**\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    for i, (user_id, score) in enumerate(sorted_scores):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        
        user_data = game_state.users.get(user_id, {})
        username = user_data.get('username') or game_state.player_names.get(user_id, "لاعب")
        
        stats_text += f"{medal} {username}: **{score}** نقطة\n"
    
    stats_text += f"\n👥 **إجمالي اللاعبين:** {len(game_state.scores)}"
    
    await query.edit_message_text(stats_text, reply_markup=main_menu_keyboard())

async def show_dev_info(query, context):
    """عرض معلومات المطور"""
    dev_info = (
        "👑 **معلومات المطور:**\n\n"
        f"✉️ **تليجرام:** {OWNER_TELEGRAM}\n"
        f"📱 **تيك توك:** {OWNER_TIKTOK}\n"
        f"🆔 **الرقم التعريفي:** {OWNER_ID}\n\n"
        "🎮 **لعبة الإمبوستر النصية**\n"
        "إصدار كامل مع جميع المميزات\n\n"
        "📊 **إحصائيات البوت:**\n"
        f"• عدد اللاعبين: {len(game_state.scores)}\n"
        f"• عدد المستخدمين: {len(game_state.users)}\n"
        f"• عدد الجولات: {game_state.total_games}"
    )
    
    await query.edit_message_text(dev_info, reply_markup=main_menu_keyboard())

# ==================== ADMIN HANDLERS ====================
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /admin للمطور"""
    if update.effective_user.id == OWNER_ID:
        await update.message.reply_text(
            "👑 **لوحة تحكم المطور**",
            reply_markup=admin_keyboard()
        )
    else:
        await update.message.reply_text("❌ ليس لديك صلاحية الوصول")

async def admin_reset(query, context):
    """إعادة ضبط كاملة من المطور"""
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ ليس لديك صلاحية!", show_alert=True)
        return
    
    game_state.reset_game()
    await query.edit_message_text(
        "✅ **تمت إعادة الضبط الكاملة**\n\n"
        "تم حذف جميع بيانات اللعبة الحالية\n"
        "النقاط التراكمية محفوظة",
        reply_markup=admin_keyboard()
    )

async def bot_stats(query, context):
    """إحصائيات البوت"""
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ ليس لديك صلاحية!", show_alert=True)
        return
    
    uptime = datetime.datetime.now() - game_state.bot_start_time
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    stats_text = (
        "📊 **إحصائيات البوت:**\n\n"
        f"⏰ **مدة التشغيل:** {uptime.days} يوم, {hours} ساعة, {minutes} دقيقة\n"
        f"👥 **عدد المستخدمين:** {len(game_state.users)}\n"
        f"🏆 **عدد اللاعبين:** {len(game_state.scores)}\n"
        f"🎮 **عدد الجولات:** {game_state.total_games}\n"
        f"📢 **القنوات المفعلة:** {len(game_state.channels)}\n"
        f"🔔 **الإشعارات:** {'✅ مفعل' if game_state.notifications_enabled else '❌ معطل'}\n"
        f"⏰ **وقت الجولة الافتراضي:** {game_state.round_time} دقيقة\n\n"
        f"💾 **حالة الحفظ:** ✅ جميع البيانات محفوظة"
    )
    
    await query.edit_message_text(stats_text, reply_markup=admin_keyboard())

async def manage_channels(query, context):
    """إدارة القنوات"""
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ ليس لديك صلاحية!", show_alert=True)
        return
    
    status = "✅ مفعل" if game_state.channels_enabled else "❌ معطل"
    await query.edit_message_text(
        f"📢 **إدارة القنوات**\n\n"
        f"الحالة: {status}\n"
        f"عدد القنوات: {len(game_state.channels)}",
        reply_markup=channels_management_keyboard()
    )

async def manage_notifications(query, context):
    """إدارة الإشعارات"""
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ ليس لديك صلاحية!", show_alert=True)
        return
    
    await query.edit_message_text(
        "🔔 **إدارة الإشعارات والإعدادات**",
        reply_markup=notifications_management_keyboard()
    )

async def manage_users(query, context):
    """إدارة المستخدمين"""
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ ليس لديك صلاحية!", show_alert=True)
        return
    
    users_text = "👥 **إدارة المستخدمين:**\n\n"
    if game_state.users:
        sorted_users = sorted(game_state.users.items(), 
                            key=lambda x: x[1].get('last_seen', ''), 
                            reverse=True)[:10]
        
        for user_id, user_data in sorted_users:
            username = user_data.get('username', 'بدون اسم')
            games = user_data.get('games_played', 0)
            users_text += f"• {username}: {games} جولة\n"
        
        users_text += f"\n📊 **إجمالي المستخدمين:** {len(game_state.users)}"
    else:
        users_text += "لا يوجد مستخدمين مسجلين بعد"
    
    await query.edit_message_text(users_text, reply_markup=admin_keyboard())

async def toggle_subscription(query, context):
    """تفعيل/تعطيل الإشتراك الإجباري"""
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ ليس لديك صلاحية!", show_alert=True)
        return
    
    game_state.channels_enabled = not game_state.channels_enabled
    game_state.save_state()
    
    status = "✅ تم تفعيل" if game_state.channels_enabled else "❌ تم تعطيل"
    await query.edit_message_text(
        f"{status} **الإشتراك الإجباري**",
        reply_markup=channels_management_keyboard()
    )

async def add_channel_menu(query, context):
    """إضافة قناة جديدة"""
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ ليس لديك صلاحية!", show_alert=True)
        return
    
    await query.edit_message_text(
        "➕ **إضافة قناة جديدة:**\n\n"
        "أرسل رابط القناة أو المعرف:\n"
        "مثال: @channel أو https://t.me/channel\n\n"
        "أو أرسل /cancel للإلغاء"
    )
    
    context.user_data['awaiting_channel'] = True

async def remove_channel_menu(query, context):
    """حذف قناة"""
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ ليس لديك صلاحية!", show_alert=True)
        return
    
    if not game_state.channels:
        await query.answer("❌ لا توجد قنوات!", show_alert=True)
        return
    
    keyboard = []
    for i, channel in enumerate(game_state.channels):
        name = channel.get('name', f'قناة {i+1}')
        keyboard.append([
            InlineKeyboardButton(f"🗑 {name}", callback_data=f"remove_channel_{i}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="manage_channels")])
    
    await query.edit_message_text(
        "🗑 **اختر القناة للحذف:**",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def remove_channel(query, context):
    """حذف قناة محددة"""
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ ليس لديك صلاحية!", show_alert=True)
        return
    
    channel_index = int(query.data.replace("remove_channel_", ""))
    
    if 0 <= channel_index < len(game_state.channels):
        removed = game_state.channels.pop(channel_index)
        game_state.save_state()
        
        await query.edit_message_text(
            f"✅ **تم حذف القناة:** {removed.get('name', 'قناة')}",
            reply_markup=channels_management_keyboard()
        )
    else:
        await query.answer("❌ رقم القناة غير صحيح!", show_alert=True)

async def list_channels(query, context):
    """عرض قائمة القنوات"""
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ ليس لديك صلاحية!", show_alert=True)
        return
    
    if not game_state.channels:
        channels_text = "📢 **لا توجد قنوات مضافة**"
    else:
        channels_text = "📢 **قائمة القنوات:**\n\n"
        for i, channel in enumerate(game_state.channels, 1):
            name = channel.get('name', f'قناة {i}')
            username = channel.get('username', 'لا يوجد')
            channels_text += f"{i}. {name} - {username}\n"
    
    await query.edit_message_text(channels_text, reply_markup=channels_management_keyboard())

async def toggle_welcome(query, context):
    """تفعيل/تعطيل رسالة الترحيب"""
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ ليس لديك صلاحية!", show_alert=True)
        return
    
    game_state.welcome_message_enabled = not game_state.welcome_message_enabled
    game_state.save_state()
    
    status = "✅ مفعل" if game_state.welcome_message_enabled else "❌ معطل"
    await query.edit_message_text(
        f"🔔 **رسالة الترحيب:** {status}",
        reply_markup=notifications_management_keyboard()
    )

async def toggle_notifications(query, context):
    """تفعيل/تعطيل الإشعارات"""
    if query.from_user.id != OWNER_ID:
        await query.answer("❌ ليس لديك صلاحية!", show_alert=True)
        return
    
    game_state.notifications_enabled = not game_state.notifications_enabled
    game_state.save_state()
    
    status = "✅ مفعل" if game_state.notifications_enabled else "❌ معطل"
    await query.edit_message_text(
        f"📢 **إشعارات البدء:** {status}",
        reply_markup=notifications_management_keyboard()
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرسائل النصية"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # التحقق من إضافة قناة
    if user_id == OWNER_ID and context.user_data.get('awaiting_channel'):
        if text.lower() == '/cancel':
            context.user_data.pop('awaiting_channel', None)
            await update.message.reply_text("❌ تم إلغاء إضافة القناة", reply_markup=admin_keyboard())
            return
        
        # محاولة استخراج معلومات القناة
        channel_info = {}
        
        if text.startswith('@'):
            channel_info['username'] = text
            channel_info['name'] = text[1:]
        elif 't.me/' in text:
            parts = text.split('/')
            if parts[-1]:
                channel_info['username'] = '@' + parts[-1]
                channel_info['name'] = parts[-1]
        
        if channel_info:
            game_state.channels.append(channel_info)
            game_state.save_state()
            
            context.user_data.pop('awaiting_channel', None)
            await update.message.reply_text(
                f"✅ **تمت إضافة القناة:** {channel_info['username']}",
                reply_markup=channels_management_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ **رابط غير صحيح!**\n"
                "يرجى إرسال رابط صحيح أو @معرف_القناة\n"
                "أو /cancel للإلغاء"
            )
        return
    
    # تسجيل اسم اللاعب
    if context.user_data.get('awaiting_name'):
        player_name = text
        
        if player_name.lower() == '/cancel':
            context.user_data.pop('awaiting_name', None)
            await update.message.reply_text("❌ تم إلغاء التسجيل", reply_markup=main_menu_keyboard())
            return
        
        if game_state.started:
            await update.message.reply_text(
                "❌ اللعبة قد بدأت بالفعل!\nلا يمكن تسجيل لاعبين جدد",
                reply_markup=main_menu_keyboard()
            )
            return
        
        user_id = context.user_data.get('user_id', update.effective_user.id)
        
        if user_id in game_state.players:
            await update.message.reply_text(
                f"✅ أنت مسجل بالفعل كـ **{game_state.player_names.get(user_id, player_name)}**",
                reply_markup=main_menu_keyboard()
            )
            return
        
        game_state.players[user_id] = player_name
        game_state.player_names[user_id] = player_name
        game_state.save_state()
        
        context.user_data.pop('awaiting_name', None)
        context.user_data.pop('user_id', None)
        
        await update.message.reply_text(
            f"✅ تم تسجيلك باسم **{player_name}**\n"
            f"👥 عدد اللاعبين: {len(game_state.players)}\n\n"
            f"📋 **الحد الأدنى: 3 لاعبين**",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # إدخال وقت مخصص للجولة
    if context.user_data.get('awaiting_custom_time'):
        if text.lower() == '/cancel':
            context.user_data.pop('awaiting_custom_time', None)
            await update.message.reply_text("❌ تم إلغاء تحديد الوقت", reply_markup=main_menu_keyboard())
            return
        
        try:
            time_min = int(text)
            if time_min < 1:
                await update.message.reply_text("❌ الوقت يجب أن يكون 1 دقيقة على الأقل")
                return
            if time_min > 60:
                await update.message.reply_text("❌ الوقت يجب أن لا يزيد عن 60 دقيقة")
                return
            
            game_state.round_time = time_min
            game_state.save_state()
            
            context.user_data.pop('awaiting_custom_time', None)
            
            await update.message.reply_text(
                f"✅ **تم تحديد وقت الجولة:** {time_min} دقيقة\n\n"
                f"⏰ سيتم إنهاء الجولة بعد {time_min} دقيقة\n"
                f"ثم يبدأ التصويت لاكتشاف الإمبوستر",
                reply_markup=main_menu_keyboard()
            )
        except ValueError:
            await update.message.reply_text(
                "❌ **يرجى إدخال رقم صحيح!**\n"
                "مثال: 3، 7، 15\n\n"
                "أو /cancel للإلغاء"
            )
        return
    
    # رد افتراضي
    await update.message.reply_text(
        "🎮 **لعبة الإمبوستر النصية**\n\n"
        "استخدم /start لبدء اللعبة",
        reply_markup=main_menu_keyboard()
    )

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /reset للمطور"""
    if update.effective_user.id == OWNER_ID:
        game_state.reset_game()
        await update.message.reply_text("✅ تم إعادة ضبط اللعبة")
    else:
        await update.message.reply_text("❌ ليس لديك صلاحية")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /stats"""
    if not game_state.scores:
        await update.message.reply_text("📊 لا توجد إحصائيات بعد")
        return
    
    sorted_scores = sorted(game_state.scores.items(), key=lambda x: x[1], reverse=True)[:5]
    
    stats_text = "🏆 **أفضل 5 لاعبين:**\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    
    for i, (user_id, score) in enumerate(sorted_scores):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        
        user_data = game_state.users.get(user_id, {})
        username = user_data.get('username') or game_state.player_names.get(user_id, "لاعب")
        
        stats_text += f"{medal} {username}: {score} نقطة\n"
    
    await update.message.reply_text(stats_text)

async def dev_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /dev لعرض معلومات المطور"""
    dev_info = (
        "👑 **معلومات المطور:**\n\n"
        f"✉️ **تليجرام:** {OWNER_TELEGRAM}\n"
        f"📱 **تيك توك:** {OWNER_TIKTOK}\n"
        f"🆔 **الرقم التعريفي:** {OWNER_ID}\n\n"
        "🎮 **لعبة الإمبوستر النصية**\n"
        "إصدار كامل مع جميع المميزات"
    )
    
    await update.message.reply_text(dev_info)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأخطاء العام"""
    logger.error(f"حدث خطأ: {context.error}", exc_info=True)

def main():
    """الدالة الرئيسية لتشغيل البوت"""
    print("=" * 50)
    print("🎮 **جارٍ تشغيل بوت لعبة الإمبوستر...**")
    
    # التحقق من التوكن
    if "YOUR_BOT_TOKEN" in TOKEN or len(TOKEN) < 30:
        print("❌ **يجب تغيير التوكن أولاً!**")
        print(f"التوكن الحالي: {TOKEN}")
        print("افتح الملف وابحث عن السطر:")
        print('TOKEN = "8518772401:AAFCuB_hXhDnsr8jIufDfG5N76lDKS81xyA"')
        print("وضع توكن البوت الخاص بك بدلاً منه")
        print("=" * 50)
        return
    
    try:
        # إنشاء التطبيق
        application = Application.builder().token(TOKEN).build()
        
        # إضافة المعالجات
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("play", play_group))
        application.add_handler(CommandHandler("admin", admin_command))
        application.add_handler(CommandHandler("reset", reset_command))
        application.add_handler(CommandHandler("stats", stats_command))
        application.add_handler(CommandHandler("dev", dev_info_command))
        
        # معالج أزرار الإنلاين
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # معالج الرسائل النصية
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
        
        # معالج الأخطاء
        application.add_error_handler(error_handler)
        
        print(f"👑 المطور: {OWNER_USERNAME}")
        print(f"📱 تيك توك: {OWNER_TIKTOK}")
        print(f"📁 البيانات محفوظة في: data/")
        print(f"⏰ وقت الجولة الافتراضي: {game_state.round_time} دقيقة")
        print("=" * 50)
        print("✅ البوت جاهز للاستخدام!")
        print("=" * 50)
        
        # تشغيل البوت
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            close_loop=False
        )
        
    except Exception as e:
        logger.error(f"خطأ فادح: {e}")
        print(f"❌ خطأ فادح: {e}")
        print("🔧 المشكلة:")
        print("1. التوكن غير صحيح - تأكد من نسخ التوكن كاملاً من BotFather")
        print("2. اتصال الإنترنت - تأكد من اتصال الإنترنت")
        print("3. تأكد من أن البوت مفعل في BotFather")

if __name__ == "__main__":
    # حفظ حالة البوت عند الإغلاق
    import atexit
    atexit.register(game_state.save_state)
    
    # تشغيل البوت
    main()