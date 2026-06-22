import re
import random

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None


def extract_text_from_pdf(file_path):
    if PdfReader is None:
        raise RuntimeError("PyPDF2 o'rnatilmagan")
    reader = PdfReader(file_path)
    full_text = []
    for page in reader.pages:
        text = page.extract_text() or ""
        full_text.append(text)
    return "\n".join(full_text)


def _clean_sentences(text):
    text = re.sub(r"\s+", " ", text)
    raw_sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = []
    for s in raw_sentences:
        s = s.strip()
        word_count = len(s.split())
        if 6 <= word_count <= 25:
            sentences.append(s)
    return sentences


def _pick_keyword(sentence):
    stopwords = {
        "va", "lekin", "ammo", "yoki", "bu", "shu", "uchun", "bilan",
        "ham", "esa", "edi", "deb", "qachon", "qanday", "nima", "kim",
        "the", "and", "is", "are", "of", "to", "in", "a", "an"
    }
    words = re.findall(r"[A-Za-zА-Яа-яЎўҚқҒғҲҳЁё']+", sentence)
    candidates = [w for w in words if len(w) > 3 and w.lower() not in stopwords]
    if not candidates:
        return None
    candidates.sort(key=len, reverse=True)
    return candidates[0]


def generate_questions_from_text(text, max_questions=10):
    sentences = _clean_sentences(text)
    if len(sentences) < 4:
        return []

    pool = []
    for s in sentences:
        kw = _pick_keyword(s)
        if kw:
            pool.append((s, kw))

    if len(pool) < 4:
        return []

    random.shuffle(pool)
    all_keywords = [kw for _, kw in pool]

    questions = []
    used_sentences = set()

    for sentence, keyword in pool:
        if len(questions) >= max_questions:
            break
        if sentence in used_sentences:
            continue
        used_sentences.add(sentence)

        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        question_text = pattern.sub("_____", sentence, count=1)

        if "_____" not in question_text:
            continue

        distractors_pool = [kw for kw in all_keywords if kw.lower() != keyword.lower()]
        if len(distractors_pool) < 3:
            continue
        distractors = random.sample(distractors_pool, 3)

        options = distractors + [keyword]
        random.shuffle(options)

        questions.append({
            "question_text": question_text,
            "options": options,
            "correct_answer": keyword
        })

    return questions
