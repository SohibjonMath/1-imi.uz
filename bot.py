#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from telegram.constants import ParseMode
from telegram.error import Forbidden, BadRequest, NetworkError, RetryAfter, TimedOut
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================== CONFIG ==================
# Tokenni endi ENV dan olamiz (xavfsiz):
# Windows PowerShell:  $env:BOT_TOKEN="XXXX"
# CMD:                set BOT_TOKEN=XXXX
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

WEB_APP_URL = os.getenv("WEB_APP_URL", "https://xplusy.netlify.app/").strip()

# Admin chat id (raqam)
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "2049065724").strip())

# ================== LOGGING ==================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("OrzuMallBot")

CHAT_MODE_KEY = "chat_mode"
MAP_KEY = "admin_msg_to_user_id"  # admin_message_id -> user_id


# ================== UI ==================
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


# ================== SAFE SEND HELPERS ==================
async def safe_send_message(bot, chat_id: int, text: str, **kwargs) -> bool:
    """
    Xabar yuborishda eng ko‘p uchraydigan xatolarni ushlab,
    bot yiqilmasdan davom etishini ta'minlaydi.
    """
    try:
        await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        return True
    except Forbidden:
        logger.warning("Forbidden: chat_id=%s bot blocked or no permission.", chat_id)
        return False
    except BadRequest as e:
        logger.error("BadRequest: chat_id=%s error=%s", chat_id, e)
        return False
    except RetryAfter as e:
        logger.warning("RetryAfter: %s seconds. chat_id=%s", e.retry_after, chat_id)
        return False
    except (TimedOut, NetworkError) as e:
        logger.warning("Network/Timeout: chat_id=%s error=%s", chat_id, e)
        return False
    except Exception as e:
        logger.exception("Unexpected error while sending message: chat_id=%s error=%s", chat_id, e)
        return False


async def safe_reply(update: Update, text: str, **kwargs) -> bool:
    if not update.message:
        return False
    try:
        await update.message.reply_text(text, **kwargs)
        return True
    except Forbidden:
        logger.warning("Forbidden on reply: user blocked bot. user=%s", update.effective_user.id if update.effective_user else None)
        return False
    except BadRequest as e:
        logger.error("BadRequest on reply: %s", e)
        return False
    except (TimedOut, NetworkError) as e:
        logger.warning("Network/Timeout on reply: %s", e)
        return False
    except Exception as e:
        logger.exception("Unexpected error on reply: %s", e)
        return False


# ================== HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data[CHAT_MODE_KEY] = False
    await safe_reply(update, WELCOME_TEXT, reply_markup=main_keyboard())


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(update, "Menyu 👇", reply_markup=main_keyboard())


async def chat_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data[CHAT_MODE_KEY] = True
    await safe_reply(
        update,
        "💬 Chat rejimi yoqildi.\nSavolingizni yozing — operatorga yuboraman.",
        reply_markup=main_keyboard(),
    )


async def chat_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data[CHAT_MODE_KEY] = False
    await safe_reply(update, "✅ Chat rejimi o‘chirildi.", reply_markup=main_keyboard())


async def admin_reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /reply USER_ID matn..."""
    if not update.effective_chat or update.effective_chat.id != ADMIN_CHAT_ID:
        return

    if not context.args or len(context.args) < 2:
        await safe_reply(update, "Foydalanish: <code>/reply USER_ID matn...</code>", parse_mode=ParseMode.HTML)
        return

    try:
        user_id = int(context.args[0])
    except ValueError:
        await safe_reply(update, "USER_ID raqam bo‘lishi kerak. Misol: <code>/reply 123456789 Salom</code>", parse_mode=ParseMode.HTML)
        return

    text = " ".join(context.args[1:]).strip()
    if not text:
        await safe_reply(update, "Matn kiriting. Misol: <code>/reply 123456789 Salom</code>", parse_mode=ParseMode.HTML)
        return

    ok = await safe_send_message(context.bot, user_id, f"👨‍💼 Operator:\n{text}")
    await safe_reply(update, "✅ Yuborildi." if ok else "⚠️ Yuborilmadi (user botni block qilgan bo‘lishi mumkin).")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return

    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id

    # 1) Admin reply (reply-to orqali)
    if chat_id == ADMIN_CHAT_ID and update.message.reply_to_message:
        mapping = context.application.bot_data.get(MAP_KEY, {})
        replied_admin_msg_id = update.message.reply_to_message.message_id
        user_id = mapping.get(replied_admin_msg_id)
        if user_id:
            ok = await safe_send_message(context.bot, user_id, f"👨‍💼 Operator:\n{text}")
            await safe_reply(update, "✅ Javob foydalanuvchiga yuborildi." if ok else "⚠️ Yuborilmadi (user block qilgan).")
        else:
            await safe_reply(
                update,
                "⚠️ Bu xabar userga bog‘lanmagan.\nUserga yozish uchun: <code>/reply USER_ID matn...</code>",
                parse_mode=ParseMode.HTML,
            )
        return

    # 2) Tugmalar
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

    # 3) Chat mode: foydalanuvchidan kelgan xabarni adminga yuborish
    if context.user_data.get(CHAT_MODE_KEY) is True and text not in (
        "🛍 OrzuMall.uz",
        "📞 Bog'lanish",
        "ℹ️ Ma'lumot",
        "💬 Chat",
    ):
        user = update.effective_user
        user_id = user.id if user else chat_id

        msg = (
            "<b>💬 Yangi chat xabari</b>\n"
            f"👤 {user.full_name if user else 'User'} (<code>{user_id}</code>)\n"
            f"🆔 USER_ID: <code>{user_id}</code>\n\n"
            f"{text}\n\n"
            "<i>Javob berish uchun shu xabarga Reply qiling</i>"
        )

        # Adminga yuborish
        try:
            sent = await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=msg,
                parse_mode=ParseMode.HTML,
            )
            mapping = context.application.bot_data.get(MAP_KEY, {})
            mapping[sent.message_id] = user_id
            context.application.bot_data[MAP_KEY] = mapping
            await safe_reply(update, "✅ Xabaringiz operatorga yuborildi. Yana yozishingiz mumkin.", reply_markup=main_keyboard())
        except Forbidden:
            # Admin botni block qilgan / noto‘g‘ri admin id
            logger.warning("Admin chat forbidden. Check ADMIN_CHAT_ID=%s", ADMIN_CHAT_ID)
            await safe_reply(update, "⚠️ Operatorga yuborib bo‘lmadi. ADMIN_CHAT_ID ni tekshiring.", reply_markup=main_keyboard())
        except Exception as e:
            logger.exception("Failed to forward message to admin: %s", e)
            await safe_reply(update, "⚠️ Xatolik. Keyinroq urinib ko‘ring.", reply_markup=main_keyboard())
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

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("chat_on", chat_on))
    app.add_handler(CommandHandler("chat_off", chat_off))
    app.add_handler(CommandHandler("reply", admin_reply_command))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_error_handler(on_error)

    logger.info("✅ OrzuMall bot ishga tushdi. CTRL+C bilan to'xtatasiz.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()