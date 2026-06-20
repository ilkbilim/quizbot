import os
import tempfile

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, CallbackQueryHandler, filters
)

import database as db
from utils.pdf_parser import extract_text_from_pdf, generate_questions_from_text

# Conversation bosqichlari
(
    QUIZ_TITLE,
    Q_TEXT, Q_TYPE, Q_OPTIONS, Q_CORRECT, Q_IMAGE,
    PDF_WAITING,
) = range(7)


# ---------------- /newquiz ----------------

async def newquiz_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Yangi test yaratamiz.\n\nTest nomini kiriting:"
    )
    return QUIZ_TITLE


async def newquiz_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    quiz_id = db.create_quiz(update.effective_user.id, title)
    context.user_data["current_quiz_id"] = quiz_id

    await update.message.reply_text(
        f"✅ \"{title}\" testi yaratildi.\n\n"
        "Endi savol qo'shamiz. Savol matnini yozing:\n"
        "(Bekor qilish uchun /cancel)"
    )
    return Q_TEXT


# ---------------- Savol qo'shish oqimi ----------------

async def question_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["q_text"] = update.message.text.strip()

    keyboard = [
        [InlineKeyboardButton("Bitta to'g'ri javob", callback_data="type_single")],
        [InlineKeyboardButton("Bir nechta to'g'ri javob", callback_data="type_multiple")],
        [InlineKeyboardButton("Ha/Yo'q", callback_data="type_truefalse")],
        [InlineKeyboardButton("Matnli javob", callback_data="type_text")],
        [InlineKeyboardButton("Sonli javob", callback_data="type_number")],
    ]
    await update.message.reply_text(
        "Savol turini tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return Q_TYPE


async def question_type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    qtype = query.data.replace("type_", "")
    context.user_data["q_type"] = qtype

    if qtype in ("single", "multiple"):
        await query.edit_message_text(
            "Javob variantlarini yuboring, har birini vergul bilan ajrating.\n"
            "Masalan: Toshkent, Samarqand, Buxoro, Andijon"
        )
        return Q_OPTIONS

    elif qtype == "truefalse":
        context.user_data["q_options"] = ["Ha", "Yo'q"]
        keyboard = [
            [InlineKeyboardButton("Ha", callback_data="correct_Ha")],
            [InlineKeyboardButton("Yo'q", callback_data="correct_Yo'q")],
        ]
        await query.edit_message_text(
            "To'g'ri javobni tanlang:", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return Q_CORRECT

    elif qtype in ("text", "number"):
        await query.edit_message_text("To'g'ri javobni yozing:")
        return Q_CORRECT


async def question_options_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    options = [o.strip() for o in update.message.text.split(",") if o.strip()]
    if len(options) < 2:
        await update.message.reply_text(
            "Kamida 2 ta variant kerak. Qaytadan yuboring (vergul bilan ajrating):"
        )
        return Q_OPTIONS

    context.user_data["q_options"] = options
    qtype = context.user_data["q_type"]

    if qtype == "single":
        keyboard = [[InlineKeyboardButton(o, callback_data=f"correct_{o}")] for o in options]
        await update.message.reply_text(
            "To'g'ri javobni tanlang:", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return Q_CORRECT
    else:  # multiple
        context.user_data["q_correct_multi"] = []
        await update.message.reply_text(
            "Bir nechta to'g'ri javob bo'lsa, ularni vergul bilan ajratib yozing.\n"
            f"Variantlar: {', '.join(options)}"
        )
        return Q_CORRECT


async def question_correct_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    answer = query.data.replace("correct_", "")
    context.user_data["q_correct"] = answer

    await query.edit_message_text(
        "Savolga rasm biriktirmoqchimisiz?\n"
        "Rasm yuboring, yoki /skip buyrug'ini bosing."
    )
    return Q_IMAGE


async def question_correct_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    qtype = context.user_data["q_type"]
    text = update.message.text.strip()

    if qtype == "multiple":
        chosen = [a.strip() for a in text.split(",") if a.strip()]
        valid_options = context.user_data.get("q_options", [])
        invalid = [c for c in chosen if c not in valid_options]
        if invalid or not chosen:
            await update.message.reply_text(
                f"Variantlar orasidan tanlang: {', '.join(valid_options)}\n"
                "Qaytadan yuboring (vergul bilan ajratib):"
            )
            return Q_CORRECT
        context.user_data["q_correct"] = chosen
    else:
        context.user_data["q_correct"] = text

    await update.message.reply_text(
        "Savolga rasm biriktirmoqchimisiz?\n"
        "Rasm yuboring, yoki /skip buyrug'ini bosing."
    )
    return Q_IMAGE


async def question_image_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _save_question_and_ask_next(update, context, image_file_id=None)


async def question_image_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    return await _save_question_and_ask_next(update, context, image_file_id=photo.file_id)


async def _save_question_and_ask_next(update, context, image_file_id):
    quiz_id = context.user_data["current_quiz_id"]
    qtype = context.user_data["q_type"]
    options = context.user_data.get("q_options")
    correct = context.user_data["q_correct"]

    db.add_question(
        quiz_id=quiz_id,
        question_text=context.user_data["q_text"],
        question_type=qtype,
        options=options,
        correct_answer=correct,
        image_file_id=image_file_id,
    )

    # Tozalash
    for key in ("q_text", "q_type", "q_options", "q_correct", "q_correct_multi"):
        context.user_data.pop(key, None)

    keyboard = [
        [InlineKeyboardButton("➕ Yana savol qo'shish", callback_data="add_more")],
        [InlineKeyboardButton("✅ Testni tugatish", callback_data="finish_quiz")],
    ]
    await update.effective_message.reply_text(
        "Savol saqlandi!", reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


async def add_more_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Savol matnini yozing:")
    return Q_TEXT


async def finish_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    quiz_id = context.user_data.get("current_quiz_id")
    quiz = db.get_quiz(quiz_id)
    questions = db.get_questions(quiz_id)

    await query.edit_message_text(
        f"🎉 Test tayyor: \"{quiz['title']}\"\n"
        f"Savollar soni: {len(questions)}\n\n"
        f"Boshlash uchun: /startquiz {quiz_id}\n"
        "(Buni guruhda yoki shaxsiy chatda yuboring)"
    )
    context.user_data.pop("current_quiz_id", None)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


# ---------------- PDF -> Quiz ----------------

async def pdf_quiz_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "PDF faylni yuboring, men undan avtomatik test tuzaman.\n"
        "(Eslatma: avtomatik savollar oddiy usulda tuziladi, ba'zilari "
        "noaniq chiqishi mumkin -- keyin ularni tahrirlashingiz mumkin.)"
    )
    return PDF_WAITING


async def pdf_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith(".pdf"):
        await update.message.reply_text("Iltimos, .pdf fayl yuboring.")
        return PDF_WAITING

    await update.message.reply_text("📄 PDF qayta ishlanmoqda, biroz kuting...")

    file = await context.bot.get_file(doc.file_id)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name
    await file.download_to_drive(tmp_path)

    try:
        text = extract_text_from_pdf(tmp_path)
    except Exception as e:
        await update.message.reply_text(f"PDF o'qishda xatolik: {e}")
        os.remove(tmp_path)
        return ConversationHandler.END
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    generated = generate_questions_from_text(text, max_questions=10)

    if not generated:
        await update.message.reply_text(
            "PDF'dan savol tuza olmadim. Matn juda qisqa yoki formatlash "
            "murakkab bo'lishi mumkin. Boshqa fayl bilan urinib ko'ring."
        )
        return ConversationHandler.END

    title = doc.file_name.replace(".pdf", "")
    quiz_id = db.create_quiz(update.effective_user.id, title)

    for q in generated:
        db.add_question(
            quiz_id=quiz_id,
            question_text=q["question_text"],
            question_type="single",
            options=q["options"],
            correct_answer=q["correct_answer"],
        )

    await update.message.reply_text(
        f"✅ \"{title}\" testi {len(generated)} ta savol bilan tuzildi!\n\n"
        f"Boshlash uchun: /startquiz {quiz_id}\n"
        "Savollarni ko'rish/tahrirlash uchun: /myquizzes"
    )
    return ConversationHandler.END


# ---------------- Conversation Handler yig'indisi ----------------

newquiz_conv = ConversationHandler(
    entry_points=[CommandHandler("newquiz", newquiz_start)],
    states={
        QUIZ_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, newquiz_title)],
        Q_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, question_text_received)],
        Q_TYPE: [CallbackQueryHandler(question_type_chosen, pattern="^type_")],
        Q_OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, question_options_received)],
        Q_CORRECT: [
            CallbackQueryHandler(question_correct_callback, pattern="^correct_"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, question_correct_text),
        ],
        Q_IMAGE: [
            CommandHandler("skip", question_image_skip),
            MessageHandler(filters.PHOTO, question_image_received),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

pdfquiz_conv = ConversationHandler(
    entry_points=[CommandHandler("pdfquiz", pdf_quiz_start)],
    states={
        PDF_WAITING: [MessageHandler(filters.Document.PDF, pdf_received)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

post_question_handlers = [
    CallbackQueryHandler(add_more_question, pattern="^add_more$"),
    CallbackQueryHandler(finish_quiz, pattern="^finish_quiz$"),
  ]
