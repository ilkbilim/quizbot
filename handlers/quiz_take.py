import asyncio
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

import database as db


def _options_keyboard(session_id, question_id, options, question_type, selected=None):
    selected = selected or []
    keyboard = []
    for opt in options:
        prefix = "✅ " if opt in selected else ""
        keyboard.append([InlineKeyboardButton(
            f"{prefix}{opt}",
            callback_data=f"ans_{session_id}_{question_id}_{opt}"
        )])
    if question_type == "multiple":
        keyboard.append([InlineKeyboardButton(
            "📨 Yuborish", callback_data=f"submit_{session_id}_{question_id}"
        )])
    return InlineKeyboardMarkup(keyboard)


async def send_question(context: ContextTypes.DEFAULT_TYPE, chat_id, session_id, quiz_id, q_index):
    questions = db.get_questions(quiz_id)

    if q_index >= len(questions):
        await finish_session(context, chat_id, session_id)
        return

    question = questions[q_index]
    db.update_session_progress(session_id, q_index)

    text = f"❓ Savol {q_index + 1}/{len(questions)}\n\n{question['question_text']}"
    qtype = question["question_type"]
    options = question["options"] if question["options"] else []

    if qtype in ("single", "multiple", "truefalse"):
        markup = _options_keyboard(session_id, question["id"], options, qtype)
    else:
        markup = None
        text += "\n\n✏️ Javobni yozib yuboring (chatga matn sifatida)."

    if question.get("image_file_id"):
        await context.bot.send_photo(
            chat_id=chat_id, photo=question["image_file_id"], caption=text, reply_markup=markup
        )
    else:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)

    time_limit = question.get("time_limit") or 30
    context.job_queue.run_once(
        _time_up_callback,
        when=time_limit,
        data={"chat_id": chat_id, "session_id": session_id, "quiz_id": quiz_id, "q_index": q_index},
        name=f"timeup_{session_id}_{q_index}"
    )


async def _time_up_callback(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    session = db.get_session(job_data["session_id"])
    # Faqat hali shu savolda turgan bo'lsa o'tkazamiz (foydalanuvchilar allaqachon javob berib bo'lgan bo'lishi mumkin)
    if session and session["current_question"] == job_data["q_index"] and session["is_active"]:
        await context.bot.send_message(job_data["chat_id"], "⏰ Vaqt tugadi! Keyingi savolga o'tamiz.")
        await send_question(
            context, job_data["chat_id"], job_data["session_id"],
            job_data["quiz_id"], job_data["q_index"] + 1
        )


async def startquiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Foydalanish: /startquiz <test_id>\nTest ID'ni /myquizzes orqali ko'rishingiz mumkin.")
        return

    try:
        quiz_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Test ID raqam bo'lishi kerak.")
        return

    quiz = db.get_quiz(quiz_id)
    if not quiz:
        await update.message.reply_text("Bunday test topilmadi.")
        return

    questions = db.get_questions(quiz_id)
    if not questions:
        await update.message.reply_text("Bu testda hali savollar yo'q.")
        return

    chat_id = update.effective_chat.id
    session_id = db.create_session(quiz_id, chat_id)
    context.chat_data["active_session_id"] = session_id

    await update.message.reply_text(
        f"🎬 \"{quiz['title']}\" testi boshlandi!\n"
        f"Savollar soni: {len(questions)}\n"
        "Omad!"
    )
    await send_question(context, chat_id, session_id, quiz_id, 0)


async def answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data  # ans_{session_id}_{question_id}_{option}

    parts = data.split("_", 3)
    _, session_id, question_id, option = parts
    session_id, question_id = int(session_id), int(question_id)

    session = db.get_session(session_id)
    if not session or not session["is_active"]:
        await query.answer("Bu test allaqachon tugagan.", show_alert=True)
        return

    questions = db.get_questions(session["quiz_id"])
    question = next((q for q in questions if q["id"] == question_id), None)
    if not question:
        return

    user = query.from_user
    db.get_or_create_result(session_id, user.id, user.username or user.first_name)

    if question["question_type"] == "multiple":
        # Vaqtinchalik tanlovni saqlaymiz (chat_data ichida user bo'yicha)
        key = f"multi_{session_id}_{question_id}_{user.id}"
        selected = context.chat_data.get(key, [])
        if option in selected:
            selected.remove(option)
        else:
            selected.append(option)
        context.chat_data[key] = selected

        options = question["options"]
        markup = _options_keyboard(session_id, question_id, options, "multiple", selected=selected)
        await query.edit_message_reply_markup(reply_markup=markup)
        return

    # single yoki truefalse -- darhol baholaymiz
    correct = question["correct_answer"]
    is_correct = (option == correct)
    score_delta = 10 if is_correct else 0
    db.update_result(session_id, user.id, score_delta, is_correct)

    feedback = "✅ To'g'ri!" if is_correct else f"❌ Noto'g'ri. To'g'ri javob: {correct}"
    await context.bot.send_message(query.from_user.id, feedback) if query.message.chat.type == "private" else None

    await query.answer(feedback, show_alert=False)


async def submit_multiple_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data  # submit_{session_id}_{question_id}
    _, session_id, question_id = data.split("_")
    session_id, question_id = int(session_id), int(question_id)

    user = query.from_user
    key = f"multi_{session_id}_{question_id}_{user.id}"
    selected = context.chat_data.get(key, [])

    session = db.get_session(session_id)
    questions = db.get_questions(session["quiz_id"])
    question = next((q for q in questions if q["id"] == question_id), None)

    correct = set(question["correct_answer"])
    is_correct = set(selected) == correct
    score_delta = 10 if is_correct else 0
    db.update_result(session_id, user.id, score_delta, is_correct)

    feedback = "✅ To'g'ri!" if is_correct else f"❌ Noto'g'ri. To'g'ri javob(lar): {', '.join(correct)}"
    await query.answer(feedback, show_alert=True)
    context.chat_data.pop(key, None)


async def text_answer_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Matnli/sonli javoblar uchun (faqat conversation tashqarisida ishlaydi)."""
    session_id = context.chat_data.get("active_session_id")
    if not session_id:
        return

    session = db.get_session(session_id)
    if not session or not session["is_active"]:
        return

    questions = db.get_questions(session["quiz_id"])
    q_index = session["current_question"]
    if q_index >= len(questions):
        return

    question = questions[q_index]
    if question["question_type"] not in ("text", "number"):
        return

    user = update.effective_user
    db.get_or_create_result(session_id, user.id, user.username or user.first_name)

    user_answer = update.message.text.strip()
    correct = str(question["correct_answer"]).strip()

    is_correct = user_answer.lower() == correct.lower()
    score_delta = 10 if is_correct else 0
    db.update_result(session_id, user.id, score_delta, is_correct)

    feedback = "✅ To'g'ri!" if is_correct else f"❌ Noto'g'ri. To'g'ri javob: {correct}"
    await update.message.reply_text(feedback)


async def finish_session(context: ContextTypes.DEFAULT_TYPE, chat_id, session_id):
    db.end_session(session_id)
    leaderboard = db.get_leaderboard(session_id)

    if not leaderboard:
        await context.bot.send_message(chat_id, "Test tugadi. Hech kim javob bermadi.")
        return

    text = "🏆 Test tugadi! Natijalar:\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, row in enumerate(leaderboard):
        medal = medals[i] if i < 3 else f"{i+1}."
        name = row["username"] or "Foydalanuvchi"
        text += f"{medal} {name} — {row['score']} ball ({row['correct_count']}/{row['total_answered']} to'g'ri)\n"

    await context.bot.send_message(chat_id, text)


async def stopquiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_id = context.chat_data.get("active_session_id")
    if not session_id:
        await update.message.reply_text("Hozir faol test yo'q.")
        return
    await finish_session(context, update.effective_chat.id, session_id)
    context.chat_data.pop("active_session_id", None)


quiz_take_handlers = [
    CommandHandler("startquiz", startquiz_command),
    CommandHandler("stopquiz", stopquiz_command),
    CallbackQueryHandler(submit_multiple_callback, pattern="^submit_"),
    CallbackQueryHandler(answer_callback, pattern="^ans_"),
  ]
