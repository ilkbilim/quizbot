import os
import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

import database as db
from handlers.quiz_create import newquiz_conv, pdfquiz_conv, post_question_handlers
from handlers.quiz_take import quiz_take_handlers, text_answer_received
from handlers.quiz_manage import myquizzes_handlers

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")


async def start_command(update, context):
    await update.message.reply_text(
        "👋 Salom! Men Quiz Bot.\n\n"
        "📌 Buyruqlar:\n"
        "/newquiz — yangi test yaratish\n"
        "/pdfquiz — PDF fayldan avtomatik test tuzish\n"
        "/myquizzes — testlaringiz ro'yxati\n"
        "/startquiz <id> — testni boshlash\n"
        "/stopquiz — faol testni to'xtatish\n"
        "/cancel — joriy amalni bekor qilish"
    )


async def help_command(update, context):
    await start_command(update, context)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable o'rnatilmagan!")

    db.init_db()
    logger.info("Baza tayyor.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(newquiz_conv)
    app.add_handler(pdfquiz_conv)

    for h in post_question_handlers:
        app.add_handler(h)

    for h in quiz_take_handlers:
        app.add_handler(h)

    for h in myquizzes_handlers:
        app.add_handler(h)

    # Matnli/sonli javoblarni umumiy ushlovchi (eng oxirida bo'lishi kerak)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_answer_received))

    logger.info("Bot ishga tushdi.")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
