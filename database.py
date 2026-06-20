import os
import psycopg2
from psycopg2.extras import RealDictCursor
import json

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_conn():
    """Bazaga ulanish ochadi."""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    """Kerakli jadvallarni yaratadi (agar mavjud bo'lmasa)."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS quizzes (
            id SERIAL PRIMARY KEY,
            owner_id BIGINT NOT NULL,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            quiz_id INTEGER REFERENCES quizzes(id) ON DELETE CASCADE,
            question_text TEXT NOT NULL,
            question_type TEXT NOT NULL,  -- single, multiple, truefalse, text, number
            options JSONB,                -- variantlar ro'yxati (JSON)
            correct_answer JSONB NOT NULL,-- to'g'ri javob(lar)
            image_file_id TEXT,           -- agar rasm biriktirilgan bo'lsa
            time_limit INTEGER DEFAULT 30,-- soniyalarda
            position INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            quiz_id INTEGER REFERENCES quizzes(id) ON DELETE CASCADE,
            chat_id BIGINT NOT NULL,
            current_question INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            started_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id SERIAL PRIMARY KEY,
            session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL,
            username TEXT,
            score INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            total_answered INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


# ---------- QUIZ ----------

def create_quiz(owner_id, title):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO quizzes (owner_id, title) VALUES (%s, %s) RETURNING id",
        (owner_id, title)
    )
    quiz_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return quiz_id


def get_user_quizzes(owner_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM quizzes WHERE owner_id = %s ORDER BY created_at DESC", (owner_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_quiz(quiz_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM quizzes WHERE id = %s", (quiz_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def delete_quiz(quiz_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM quizzes WHERE id = %s", (quiz_id,))
    conn.commit()
    cur.close()
    conn.close()


# ---------- QUESTIONS ----------

def add_question(quiz_id, question_text, question_type, options, correct_answer,
                  image_file_id=None, time_limit=30):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(position), -1) + 1 AS next_pos FROM questions WHERE quiz_id = %s", (quiz_id,))
    position = cur.fetchone()["next_pos"]
    cur.execute("""
        INSERT INTO questions
        (quiz_id, question_text, question_type, options, correct_answer, image_file_id, time_limit, position)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
    """, (
        quiz_id, question_text, question_type,
        json.dumps(options) if options is not None else None,
        json.dumps(correct_answer),
        image_file_id, time_limit, position
    ))
    qid = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return qid


def get_questions(quiz_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM questions WHERE quiz_id = %s ORDER BY position ASC", (quiz_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def delete_question(question_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM questions WHERE id = %s", (question_id,))
    conn.commit()
    cur.close()
    conn.close()


# ---------- SESSIONS ----------

def create_session(quiz_id, chat_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sessions (quiz_id, chat_id) VALUES (%s, %s) RETURNING id",
        (quiz_id, chat_id)
    )
    sid = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()
    return sid


def get_session(session_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def update_session_progress(session_id, current_question):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE sessions SET current_question = %s WHERE id = %s", (current_question, session_id))
    conn.commit()
    cur.close()
    conn.close()


def end_session(session_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE sessions SET is_active = FALSE WHERE id = %s", (session_id,))
    conn.commit()
    cur.close()
    conn.close()


# ---------- RESULTS ----------

def get_or_create_result(session_id, user_id, username):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM results WHERE session_id = %s AND user_id = %s", (session_id, user_id))
    row = cur.fetchone()
    if row:
        cur.close()
        conn.close()
        return row
    cur.execute("""
        INSERT INTO results (session_id, user_id, username) VALUES (%s, %s, %s) RETURNING *
    """, (session_id, user_id, username))
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return row


def update_result(session_id, user_id, score_delta, is_correct):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE results
        SET score = score + %s,
            correct_count = correct_count + %s,
            total_answered = total_answered + 1
        WHERE session_id = %s AND user_id = %s
    """, (score_delta, 1 if is_correct else 0, session_id, user_id))
    conn.commit()
    cur.close()
    conn.close()


def get_leaderboard(session_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM results WHERE session_id = %s
        ORDER BY score DESC, correct_count DESC
    """, (session_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows
