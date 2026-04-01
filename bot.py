import csv
import datetime as dt
import os
import re
import smtplib
import unicodedata
from email.message import EmailMessage
from typing import Dict, List, Tuple

import requests

PLAN_CSV = os.environ.get("PLAN_CSV", "plan.csv")
BIBLE_LANG = os.environ.get("BIBLE_LANG", "pt-br")
BIBLE_VERSION = os.environ.get("BIBLE_VERSION", "nvi")
SENT_MARKER_FILE = os.environ.get("SENT_MARKER_FILE", "sent.txt")

RAW_BASE = "https://raw.githubusercontent.com/maatheusgois/bible/main/versions"


# =========================
# EMAIL
# =========================
def smtp_send(subject: str, body_text: str, body_html: str) -> None:
    email_user = os.environ["EMAIL_USER"]
    email_pass = os.environ["EMAIL_PASS"]
    email_to = os.environ["EMAIL_TO"]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email_user
    msg["To"] = email_to

    msg.set_content(body_text)
    msg.add_alternative(body_html, subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(email_user, email_pass)
        smtp.send_message(msg)


# =========================
# LEITURA DO CSV
# =========================
def load_today_reading() -> Tuple[str, str]:
    today = dt.date.today().isoformat()
    with open(PLAN_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("date") or "").strip() == today:
                return today, (row.get("reading") or "").strip()
    raise RuntimeError(f"Nenhuma leitura encontrada para {today}")


# =========================
# NORMALIZAÇÃO
# =========================
def norm(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^([1-3])\s*([A-Za-zÀ-ÿ])", r"\1 \2", s)
    s = re.sub(r"\s+", " ", s).lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s


def book_name_to_id_map() -> Dict[str, str]:
    raw = {
        "genesis": "gn", "exodo": "ex", "levitico": "lv", "numeros": "nm",
        "deuteronomio": "dt", "josue": "js", "juizes": "jud", "rute": "rt",
        "1 samuel": "1sm", "2 samuel": "2sm",
        "salmos": "ps", "salmo": "ps",
        "mateus": "mt", "marcos": "mk", "lucas": "lk", "joao": "jo",
        "romanos": "rm", "apocalipse": "re"
    }
    return {norm(k): v for k, v in raw.items()}


# =========================
# PARSER (capítulo + versículo)
# =========================
def parse_reading(reading: str, name_to_id: Dict[str, str]):
    parts = [p.strip() for p in reading.split(";") if p.strip()]
    plan = []

    for part in parts:
        # Ex: "Salmo 11,59" ou "Salmo 11, 59"
        m = re.match(r"^(.+?)\s+([\d,:-]+)$", part)

        if not m:
            raise RuntimeError(f"Não consegui interpretar: '{part}'")

        book_raw = m.group(1)
        ref_raw = m.group(2)

        key = norm(book_raw)
        if key not in name_to_id:
            raise RuntimeError(f"Livro não reconhecido: '{book_raw}'")

        book_id = name_to_id[key]

        # Divide múltiplos capítulos/versículos
        refs = [r.strip() for r in ref_raw.split(",")]

        for ref in refs:
            if ":" in ref:
                # capítulo:versículo
                ch, vs = ref.split(":")
                ch = int(ch)

                if "-" in vs:
                    start, end = map(int, vs.split("-"))
                    verses = list(range(start, end + 1))
                else:
                    verses = [int(vs)]

                plan.append((book_id, ch, verses))

            else:
                # apenas capítulo
                plan.append((book_id, int(ref), None))

    return plan


# =========================
# FETCH BÍBLIA
# =========================
_cache = {}

def fetch_book(book_id: str):
    key = f"{BIBLE_LANG}/{BIBLE_VERSION}/{book_id}"
    if key in _cache:
        return _cache[key]

    url = f"{RAW_BASE}/{BIBLE_LANG}/{BIBLE_VERSION}/{book_id}/{book_id}.json"
    r = requests.get(url)
    r.raise_for_status()
    data = r.json()

    if isinstance(data, list):
        data = {"name": book_id, "chapters": data}

    _cache[key] = data
    return data


def chapter_text(book_id: str, chapter: int) -> str:
    data = fetch_book(book_id)
    chapters = data.get("chapters", [])

    ch = chapters[chapter - 1]

    lines = [f"{data.get('name', book_id)} {chapter}"]

    for i, v in enumerate(ch, start=1):
        if v.strip():
            lines.append(f"{i}. {v.strip()}")

    return "\n".join(lines)


# =========================
# SANITIZAÇÃO
# =========================
def sanitize_text(text: str) -> str:
    text = text.replace("full-versionmente", "completamente")
    text = text.replace("full-version", "")

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)

    return text.strip()


# =========================
# CONTROLE DE ENVIO
# =========================
def already_sent_today(date_str: str) -> bool:
    try:
        with open(SENT_MARKER_FILE) as f:
            return f.read().strip() == date_str
    except:
        return False


def mark_sent(date_str: str):
    with open(SENT_MARKER_FILE, "w") as f:
        f.write(date_str)


# =========================
# MAIN
# =========================
def main():
    try:
        date_str, reading = load_today_reading()

        if already_sent_today(date_str):
            return

        name_to_id = book_name_to_id_map()
        plan = parse_reading(reading, name_to_id)

        blocks = []

        for book_id, chapter, verses in plan:
            full_text = chapter_text(book_id, chapter)

            if verses:
                lines = full_text.split("\n")
                header = lines[0]
                selected = []

                for line in lines[1:]:
                    m = re.match(r"^(\d+)\.\s+(.*)", line)
                    if m:
                        vnum = int(m.group(1))
                        if vnum in verses:
                            selected.append(line)

                text = "\n".join([header] + selected)
            else:
                text = full_text

            text = sanitize_text(text)
            blocks.append(text)

        body_text = f"Leitura Bíblica\n{date_str}\n\n" + "\n\n".join(blocks)

        body_html = f"""
        <html>
        <body style="font-family: Georgia;">
        <h2>Leitura Bíblica do Dia</h2>
        <p><b>{date_str}</b></p>
        <p>{reading}</p>
        <hr>
        <pre>{body_text}</pre>
        </body>
        </html>
        """

        smtp_send(f"Leitura Bíblica ({date_str})", body_text, body_html)

        mark_sent(date_str)

    except Exception:
        import traceback
        tb = traceback.format_exc()
        try:
            smtp_send("ERRO", tb, f"<pre>{tb}</pre>")
        except:
            pass


if __name__ == "__main__":
    main()
