#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import logging
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ParseMode
from telegram.error import Forbidden, BadRequest, NetworkError, RetryAfter, TimedOut
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://xplusy.netlify.app/").strip()

# Eski admin ham ishlayversin, lekin endi operatorlar ro'yxati asosiy
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "2049065724").strip())

# Misol:
# OPERATORS_JSON='[2049065724,123456789,987654321]'
# yoki
# OPERATORS=2049065724,123456789,987654321
OPERATORS_JSON = os.getenv("OPERATORS_JSON", "").strip()
OPERATORS_CSV = os.getenv("OPERATORS", "").strip()

# Operatorlarga xabar qayerga ketadi:
# 1) OPERATOR_GROUP_ID bo'lsa -> bitta guruhga yuboriladi
# 2) bo'lmasa -> har bir operatorga alohida yuboriladi
OPERATOR_GROUP_ID_RAW = os.getenv("OPERATOR_GROUP_ID", "").strip()

# ================== LOGGING ==================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("OrzuMallBot")

CHAT_MODE_KEY = "chat_mode"
ACTIVE_CHAT_USER_KEY = "active_chat_user_id"   # operator user bilan gaplashayotgan current session
SESSIONS_KEY = "sessions"                      # user_id -> session info
NOTIF_MAP_KEY = "notif_map"                    # operator/group message_id -> user_id


# ================== HELPERS ==================
def parse_operators() -> list[int]:
    operators = set()

    if OPERATORS_JSON:
        try:
            arr = json.loads(OPERATORS_JSON)
            for x in arr:
                operators.add(int(x))
        except Exception as e:
            logger.warning("OPERATORS_JSON parse xato: %s", e)

    if OPERATORS_CSV:
        for x in OPERATORS_CSV.split(","):
            x = x.strip()
            if x:
                try:
                    operators.add(int(x))
                except ValueError:
                    logger.warning("OPERATORS CSV noto'g'ri qiymat: %s", x)

    operators.add(ADMIN_CHAT_ID)
    return sorted(operators)


OPERATORS = parse_operators()
OPERATOR_GROUP_ID = int(OPERATOR_GROUP_ID_RAW) if OPERATOR_GROUP_ID_RAW else None


def is_operator(chat_id: int) -> bool:
    return chat_id in OPERATORS


def main_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton("🛍 OrzuMall.uz", web_app=WebAppInfo(url=WEB_APP_URL))],
        [KeyboardButton("📞 Bog'lanish"), KeyboardButton("ℹ️ Ma'lumot")],
        [KeyboardButton("💬 Chat")],
    ]
    return ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Tugmalardan tanlang…",
    )


ABOUT_TEXT = (
    "<b>🛒 OrzuMall.uz</b> — qulay va tezkor online xaridlar markazi.\n\n"
    "✅ Mahsulotlar\n"
    "🚚 Yetkazib berish\n"
    "💳 Xavfsiz to‘lov\n"
    "📲 Barchasi bitta bot orqali"
)

CONTACT_TEXT = (
    "<b>📞 Bog'lanish</b>\n"
    "Admin: @OrzuMallUZ_bot\n"
    "Telefon: +998 XX XXX XX XX\n"
    "Ish vaqti: 09:00–21:00"
)

WELCOME_TEXT = (
    "Assalomu alaykum! 👋\n"
    "OrzuMall botiga xush kelibsiz.\n\n"
    "Pastdagi tugmalar orqali davom eting 👇"
)


def get_sessions(app) -> dict:
    if SESSIONS_KEY not in app.bot_data:
        app.bot_data[SESSIONS_KEY] = {}
    return app.bot_data[SESSIONS_KEY]


def get_notif_map(app) -> dict:
    if NOTIF_MAP_KEY not in app.bot_data:
        app.bot_data[NOTIF_MAP_KEY] = {}
    return app.bot_data[NOTIF_MAP_KEY]


def session_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🙋 Men javob beraman", callback_data=f"claim:{user_id}"),
            InlineKeyboardButton("✅ Suhbatni yakunlash", callback_data=f"close:{user_id}"),
        ]
    ])


def session_status_text(session: dict) -> str:
    status = session.get("status", "waiting")
    operator_id = session.get("operator_id")

    if status == "assigned" and operator_id:
        return f"🟢 Holat: operator biriktirilgan (<code>{operator_id}</code>)"
    if status == "closed":
        return "⚪ Holat: yopilgan"
    return "🟡 Holat: navbatda"


# ================== SAFE SEND HELPERS ==================
async def safe_send_message(bot, chat_id: int, text: str, **kwargs):
    try:
        sent = await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        return sent
    except Forbidden:
        logger.warning("Forbidden: chat_id=%s bot blocked or no permission.", chat_id)
        return None
    except BadRequest as e:
        logger.error("BadRequest: chat_id=%s error=%s", chat_id, e)
        return None
    except RetryAfter as e:
        logger.warning("RetryAfter: %s seconds. chat_id=%s", e.retry_after, chat_id)
        return None
    except (TimedOut, NetworkError) as e:
        logger.warning("Network/Timeout: chat_id=%s error=%s", chat_id, e)
        return None
    except Exception as e:
        logger.exception("Unexpected error while sending message: chat_id=%s error=%s", chat_id, e)
        return None


async def safe_reply(update: Update, text: str, **kwargs):
    if not update.message:
        return None
    try:
        return await update.message.reply_text(text, **kwargs)
    except Forbidden:
        logger.warning("Forbidden on reply: user blocked bot. user=%s", update.effective_user.id if update.effective_user else None)
        return None
    except BadRequest as e:
        logger.error("BadRequest on reply: %s", e)
        return None
    except (TimedOut, NetworkError) as e:
        logger.warning("Network/Timeout on reply: %s", e)
        return None
    except Exception as e:
        logger.exception("Unexpected error on reply: %s", e)
        return None


async def notify_operators(context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None, user_id: int | None = None):
    """
    Operator group bo'lsa o'sha yerga yuboradi.
    Bo'lmasa barcha operatorlarga alohida yuboradi.
    """
    notif_map = get_notif_map(context.application)

    if OPERATOR_GROUP_ID:
        sent = await safe_send_message(
            context.bot,
            OPERATOR_GROUP_ID,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )
        if sent and user_id:
            notif_map[f"{OPERATOR_GROUP_ID}:{sent.message_id}"] = user_id
        return

    for op_id in OPERATORS:
        sent = await safe_send_message(
            context.bot,
            op_id,
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )
        if sent and user_id:
            notif_map[f"{op_id}:{sent.message_id}"] = user_id


# ================== COMMANDS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data[CHAT_MODE_KEY] = False
    await safe_reply(update, WELCOME_TEXT, reply_markup=main_keyboard())


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update, "Menyu 👇", reply_markup=main_keyboard())


async def chat_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not update.effective_user:
        return

    user_id = update.effective_user.id
    sessions = get_sessions(context.application)
    session = sessions.get(user_id)

    # Agar aktiv session bo'lsa, yangi ochmaymiz
    if session and session.get("status") in ("waiting", "assigned"):
        context.user_data[CHAT_MODE_KEY] = True
        await safe_reply(
            update,
            "💬 Sizning chat sessiyangiz allaqachon ochiq.\nSavolingizni yozing, operatorga yuboraman.",
            reply_markup=main_keyboard(),
        )
        return

    sessions[user_id] = {
        "user_id": user_id,
        "user_name": update.effective_user.full_name,
        "username": update.effective_user.username,
        "status": "waiting",
        "operator_id": None,
        "messages": [],
    }

    context.user_data[CHAT_MODE_KEY] = True
    await safe_reply(
        update,
        "💬 Chat rejimi yoqildi.\nSavolingizni yozing — operatorga yuboraman.",
        reply_markup=main_keyboard(),
    )


async def chat_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data[CHAT_MODE_KEY] = False
    await safe_reply(update, "✅ Chat rejimi o‘chirildi.", reply_markup=main_keyboard())


async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not is_operator(update.effective_chat.id):
        return

    sessions = get_sessions(context.application)
    waiting = [s for s in sessions.values() if s.get("status") == "waiting"]

    if not waiting:
        await safe_reply(update, "Navbatda chat yo‘q.")
        return

    lines = ["<b>🟡 Navbatdagi chatlar:</b>"]
    for s in waiting[:20]:
        lines.append(f"• {s.get('user_name', 'User')} — <code>{s['user_id']}</code>")

    await safe_reply(update, "\n".join(lines), parse_mode=ParseMode.HTML)


async def my_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not is_operator(update.effective_chat.id):
        return

    op_id = update.effective_chat.id
    sessions = get_sessions(context.application)
    mine = [s for s in sessions.values() if s.get("status") == "assigned" and s.get("operator_id") == op_id]

    if not mine:
        await safe_reply(update, "Sizga biriktirilgan chat yo‘q.")
        return

    lines = ["<b>🟢 Sizga biriktirilgan chatlar:</b>"]
    for s in mine[:20]:
        lines.append(f"• {s.get('user_name', 'User')} — <code>{s['user_id']}</code>")

    await safe_reply(update, "\n".join(lines), parse_mode=ParseMode.HTML)


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or not is_operator(update.effective_chat.id):
        return

    op_id = update.effective_chat.id
    user_id = context.user_data.get(ACTIVE_CHAT_USER_KEY)

    if not user_id:
        await safe_reply(update, "Avval biror chatni oling. Tugma orqali yoki /my dan tekshiring.")
        return

    sessions = get_sessions(context.application)
    session = sessions.get(user_id)

    if not session or session.get("status") != "assigned" or session.get("operator_id") != op_id:
        context.user_data.pop(ACTIVE_CHAT_USER_KEY, None)
        await safe_reply(update, "Bu chat sizga biriktirilmagan yoki yopilgan.")
        return

    session["status"] = "closed"
    session["operator_id"] = None
    context.user_data.pop(ACTIVE_CHAT_USER_KEY, None)

    await safe_send_message(
        context.bot,
        user_id,
        "✅ Suhbat yakunlandi.\nYana savolingiz bo‘lsa, <b>💬 Chat</b> tugmasini bosing.",
        parse_mode=ParseMode.HTML,
    )
    await safe_reply(update, f"✅ Chat yakunlandi: <code>{user_id}</code>", parse_mode=ParseMode.HTML)


# ================== CALLBACKS ==================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not update.effective_chat:
        return

    operator_id = update.effective_chat.id
    if not is_operator(operator_id) and (OPERATOR_GROUP_ID is None or update.effective_chat.id != OPERATOR_GROUP_ID):
        await query.answer("Ruxsat yo‘q", show_alert=True)
        return

    # Guruhda tugma bosilsa, haqiqiy operator user id query.from_user.id bo'ladi
    real_operator_id = query.from_user.id if query.from_user else operator_id
    if not is_operator(real_operator_id):
        await query.answer("Siz operator emassiz", show_alert=True)
        return

    data = query.data or ""
    sessions = get_sessions(context.application)

    if ":" not in data:
        await query.answer()
        return

    action, raw_user_id = data.split(":", 1)
    try:
        user_id = int(raw_user_id)
    except ValueError:
        await query.answer("Noto‘g‘ri user_id", show_alert=True)
        return

    session = sessions.get(user_id)
    if not session:
        await query.answer("Sessiya topilmadi", show_alert=True)
        return

    if action == "claim":
        if session.get("status") == "closed":
            await query.answer("Bu chat yopilgan", show_alert=True)
            return

        assigned_operator = session.get("operator_id")
        if assigned_operator and assigned_operator != real_operator_id:
            await query.answer("Bu chatni boshqa operator oldi", show_alert=True)
            return

        session["status"] = "assigned"
        session["operator_id"] = real_operator_id

        # Operatorga shu chatni aktiv qilamiz
        if context.application.user_data.get(real_operator_id) is None:
            context.application.user_data[real_operator_id] = {}
        context.application.user_data[real_operator_id][ACTIVE_CHAT_USER_KEY] = user_id

        user_text = (
            "👨‍💼 Operator ulandi.\n"
            "Savolingizni yozishingiz mumkin."
        )
        await safe_send_message(context.bot, user_id, user_text)

        new_text = build_operator_ticket_text(session)
        new_markup = session_keyboard(user_id)

        try:
            await query.edit_message_text(
                text=new_text,
                parse_mode=ParseMode.HTML,
                reply_markup=new_markup,
            )
        except Exception:
            pass

        await query.answer("Chat sizga biriktirildi")
        return

    if action == "close":
        if session.get("status") == "closed":
            await query.answer("Allaqachon yopilgan")
            return

        assigned_operator = session.get("operator_id")
        if assigned_operator and assigned_operator != real_operator_id:
            await query.answer("Faqat biriktirilgan operator yopishi mumkin", show_alert=True)
            return

        session["status"] = "closed"
        session["operator_id"] = None

        # operator current active chat ni tozalaymiz
        if context.application.user_data.get(real_operator_id):
            if context.application.user_data[real_operator_id].get(ACTIVE_CHAT_USER_KEY) == user_id:
                context.application.user_data[real_operator_id].pop(ACTIVE_CHAT_USER_KEY, None)

        await safe_send_message(
            context.bot,
            user_id,
            "✅ Suhbat yakunlandi.\nYana savolingiz bo‘lsa, <b>💬 Chat</b> tugmasini bosing.",
            parse_mode=ParseMode.HTML,
        )

        new_text = build_operator_ticket_text(session)
        try:
            await query.edit_message_text(
                text=new_text,
                parse_mode=ParseMode.HTML,
                reply_markup=session_keyboard(user_id),
            )
        except Exception:
            pass

        await query.answer("Suhbat yopildi")
        return

    await query.answer()


# ================== TICKET TEXT ==================
def build_operator_ticket_text(session: dict) -> str:
    user_id = session["user_id"]
    user_name = session.get("user_name", "User")
    username = session.get("username")
    status_line = session_status_text(session)

    uname = f"@{username}" if username else "yo‘q"
    last_messages = session.get("messages", [])[-5:]

    body = [
        "<b>💬 Yangi / faol chat</b>",
        f"👤 {user_name}",
        f"🔗 Username: {uname}",
        f"🆔 USER_ID: <code>{user_id}</code>",
        status_line,
        "",
        "<b>Oxirgi xabarlar:</b>",
    ]

    if last_messages:
        for m in last_messages:
            body.append(f"• {m}")
    else:
        body.append("• Hozircha xabar yo‘q")

    body.append("")
    body.append("<i>Operator tugma orqali chatni olishi yoki yopishi mumkin</i>")

    return "\n".join(body)


# ================== MAIN TEXT HANDLER ==================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return

    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id

    # 1) Operator xabarlari
    if is_operator(chat_id):
        # operatorning ayni paytdagi aktiv useri
        active_user_id = context.user_data.get(ACTIVE_CHAT_USER_KEY)

        # reply orqali ham ishlasin
        if update.message.reply_to_message:
            notif_map = get_notif_map(context.application)
            key = f"{chat_id}:{update.message.reply_to_message.message_id}"
            group_key = f"{OPERATOR_GROUP_ID}:{update.message.reply_to_message.message_id}" if OPERATOR_GROUP_ID else None

            mapped_user = notif_map.get(key) or (notif_map.get(group_key) if group_key else None)
            if mapped_user:
                active_user_id = mapped_user
                context.user_data[ACTIVE_CHAT_USER_KEY] = mapped_user

        # operator buyruq tugma matnlarini userga yubormasligi uchun
        if text in ("📞 Bog'lanish", "ℹ️ Ma'lumot", "💬 Chat", "🛍 OrzuMall.uz"):
            await safe_reply(update, "Operator panelida oddiy xabar yozsangiz userga yuboriladi.")
            return

        if active_user_id:
            sessions = get_sessions(context.application)
            session = sessions.get(active_user_id)

            if not session:
                context.user_data.pop(ACTIVE_CHAT_USER_KEY, None)
                await safe_reply(update, "Chat topilmadi.")
                return

            if session.get("status") == "closed":
                context.user_data.pop(ACTIVE_CHAT_USER_KEY, None)
                await safe_reply(update, "Bu chat yopilgan.")
                return

            if session.get("operator_id") not in (None, chat_id):
                await safe_reply(update, "Bu chat boshqa operatorga biriktirilgan.")
                return

            # agar hali claim qilmagan bo'lsa, avtomatik claim
            if session.get("operator_id") is None:
                session["operator_id"] = chat_id
                session["status"] = "assigned"

            sent = await safe_send_message(
                context.bot,
                active_user_id,
                f"👨‍💼 Operator:\n{text}",
            )
            if sent:
                await safe_reply(update, "✅ Foydalanuvchiga yuborildi.")
            else:
                await safe_reply(update, "⚠️ Yuborilmadi.")
            return

        # Aktiv chat yo'q bo'lsa
        await safe_reply(
            update,
            "Sizda aktiv chat yo‘q.\nTugma orqali chatni oling yoki /queue va /my ni tekshiring."
        )
        return

    # 2) Oddiy user tugmalari
    if text == "📞 Bog'lanish":
        context.user_data[CHAT_MODE_KEY] = False
        await safe_reply(update, CONTACT_TEXT, parse_mode=ParseMode.HTML, reply_markup=main_keyboard())
        return

    if text == "ℹ️ Ma'lumot":
        context.user_data[CHAT_MODE_KEY] = False
        await safe_reply(update, ABOUT_TEXT, parse_mode=ParseMode.HTML, reply_markup=main_keyboard())
        return

    if text == "💬 Chat":
        await chat_on(update, context)
        return

    # 3) User chat mode
    if context.user_data.get(CHAT_MODE_KEY) is True and text not in (
        "🛍 OrzuMall.uz",
        "📞 Bog'lanish",
        "ℹ️ Ma'lumot",
        "💬 Chat",
    ):
        user = update.effective_user
        user_id = user.id if user else chat_id

        sessions = get_sessions(context.application)
        session = sessions.get(user_id)

        if not session:
            sessions[user_id] = {
                "user_id": user_id,
                "user_name": user.full_name if user else "User",
                "username": user.username if user else None,
                "status": "waiting",
                "operator_id": None,
                "messages": [],
            }
            session = sessions[user_id]

        # yopilgan chat bo'lsa, qayta ochamiz
        if session.get("status") == "closed":
            session["status"] = "waiting"
            session["operator_id"] = None
            session["messages"] = []

        session["messages"].append(text)

        ticket_text = build_operator_ticket_text(session)
        await notify_operators(
            context,
            ticket_text,
            reply_markup=session_keyboard(user_id),
            user_id=user_id,
        )

        await safe_reply(
            update,
            "✅ Xabaringiz operatorga yuborildi.\nJavob kelishini kuting.",
            reply_markup=main_keyboard(),
        )
        return

    # 4) Default
    await safe_reply(update, "Tugmalardan foydalaning 👇", reply_markup=main_keyboard())


# ================== ERROR HANDLER ==================
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Global error handler: %s", context.error)


def main():
    if not BOT_TOKEN:
        print("\n❌ BOT_TOKEN topilmadi.")
        print("PowerShell:  $env:BOT_TOKEN=\"YOUR_TOKEN\"  ;  python bot.py\n")
        raise SystemExit(1)

    logger.info("Operators: %s", OPERATORS)
    logger.info("Operator group: %s", OPERATOR_GROUP_ID)

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("chat_on", chat_on))
    app.add_handler(CommandHandler("chat_off", chat_off))
    app.add_handler(CommandHandler("queue", queue_command))
    app.add_handler(CommandHandler("my", my_command))
    app.add_handler(CommandHandler("done", done_command))

    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_error_handler(on_error)

    logger.info("✅ OrzuMall bot ishga tushdi. CTRL+C bilan to'xtatasiz.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
