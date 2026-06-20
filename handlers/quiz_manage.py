from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import database as db


async def myquizzes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quizzes = db.get_user_quizzes(update.effective_user.id)
    if not quizzes:
        await update.message.reply_text(
            "Sizda hali testlar yo'q.\n"
            "Yangi test yaratish: /newquiz\n"
            "PDF'dan test yaratish: /pdfquiz"
        )
        return

    text = "📋 Sizning testlaringiz:\n\n"
    keyboard = []
    for q in quizzes:
        questions = db.get_questions(q["id"])
        text += f"• {q['title']} (ID: {q['id']}, {len(questions)} savol)\n"
        keyboard.append([
            InlineKeyboardButton(f"▶️ {q['title']}", callback_data=f"info_{q['id']}")
        ])

    text += "\nBoshlash uchun: /startquiz <ID>"
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)


async def quiz_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    quiz_id = int(query.data.replace("info_", ""))
    quiz = db.get_quiz(quiz_id)
    questions = db.get_questions(quiz_id)

    text = f"📝 {quiz['title']}\nSavollar soni: {len(questions)}\n\n"
    for i, q in enumerate(questions, 1):
        text += f"{i}. {q['question_text'][:60]}\n"

    keyboard = [
        [InlineKeyboardButton("▶️ Boshlash", callback_data=f"start_{quiz_id}")],
        [InlineKeyboardButton("🗑 O'chirish", callback_data=f"delete_{quiz_id}")],
    ]
    await query.edit_message_text(text[:4000], reply_markup=InlineKeyboardMarkup(keyboard))


async def quiz_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    quiz_id = int(query.data.replace("delete_", ""))
    db.delete_quiz(quiz_id)
    await query.edit_message_text("🗑 Test o'chirildi.")


async def quiz_start_from_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.quiz_take import send_question
    query = update.callback_query
    await query.answer()
    quiz_id = int(query.data.replace("start_", ""))
    chat_id = query.message.chat_id

    session_id = db.create_session(quiz_id, chat_id)
    context.chat_data["active_session_id"] = session_id

    quiz = db.get_quiz(quiz_id)
    await context.bot.send_message(chat_id, f"🎬 \"{quiz['title']}\" testi boshlandi!")
    await send_question(context, chat_id, session_id, quiz_id, 0)


myquizzes_handlers = [
    CommandHandler("myquizzes", myquizzes_command),
    CallbackQueryHandler(quiz_info_callback, pattern="^info_"),
    CallbackQueryHandler(quiz_delete_callback, pattern="^delete_"),
    CallbackQueryHandler(quiz_start_from_info_callback, pattern="^start_"),
]
