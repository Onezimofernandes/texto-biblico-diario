import csv
import datetime as dt
import os
import re
import smtplib
from email.message import EmailMessage
from typing import Dict, List, Tuple

import requests

PLAN_CSV = os.environ.get("PLAN_CSV", "plan.csv")
BIBLE_VERSION = os.environ.get("BIBLE_VERSION", "acf")  # ex: acf, ra, nvi (se disponível na API)
ABIBLIA_TOKEN = os.environ.get("ABIBLIA_TOKEN", "").strip()

ABIBLIA_BASE = "https://www.abibliadigital.com.br/api"


def smtp_send(subject: str, body: str) -> None:
    email_user = os.environ["EMAIL_USER"]
    email_pass = os.environ["EMAIL_PASS"]
    email_to = os.environ["EMAIL_TO"]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email_user
    msg["To"] = email_to
    msg.set_content(body)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(email_user, email_pass)
        smtp.send_message(msg)


def http_get(url: str) -> dict:
    headers = {"Accept": "application/json"}
    if ABIBLIA_TOKEN:
        headers["Authorization"] = f"Bearer {ABIBLIA_TOKEN}"
    r = requests.get(url, headers=headers, timeout=45)
    r.raise_for_status()
    return r.json()


def load_today_reading() -> Tuple[str, str]:
    today = dt.date.today().isoformat()
    with open(PLAN_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("date") or "").strip() == today:
                return today, (row.get("reading") or "").strip()
    raise RuntimeError(f"Nenhuma leitura encontrada no CSV para a data {today}.")


def normalize_book_key(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^([1-3])\s*([A-Za-zÀ-ÿ])", r"\1 \2", s)  # "2Samuel" -> "2 Samuel"
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def build_book_map() -> Dict[str, str]:
    data = http_get(f"{ABIBLIA_BASE}/books")
    m: Dict[str, str] = {}
    for b in data:
        name = (b.get("name") or "").strip()
        abbrev_pt = (b.get("abbrev", {}).get("pt") or "").strip()
        if name and abbrev_pt:
            m[normalize_book_key(name)] = abbrev_pt
    return m


def expand_chapter_spec(spec: str) -> List[int]:
    spec = spec.strip().replace(" ", "")
    chunks = [c for c in spec.split(",") if c]
    chapters: List[int] = []
    for c in chunks:
        if "-" in c:
            a, b = c.split("-", 1)
            a_i, b_i = int(a), int(b)
            if b_i < a_i:
                raise RuntimeError(f"Range inválido: {c}")
            chapters.extend(list(range(a_i, b_i + 1)))
        else:
            chapters.append(int(c))

    # remove duplicados preservando ordem
    seen = set()
    uniq = []
    for x in chapters:
        if x not in seen:
            uniq.append(x)
            seen.add(x)
    return uniq


def parse_reading(reading: str, book_map: Dict[str, str]) -> List[Tuple[str, List[int]]]:
    if not reading:
        return []

    parts = [p.strip() for p in reading.split(";") if p.strip()]
    out: List[Tuple[str, List[int]]] = []

    for part in parts:
        m = re.match(r"^(.+?)\s+([\d,\-\s]+)$", part)
        if not m:
            raise RuntimeError(f"Não consegui interpretar este trecho: '{part}'")

        book_raw, ch_raw = m.group(1), m.group(2)
        book_key = normalize_book_key(book_raw)

        if book_key not in book_map:
            raise RuntimeError(
                f"Livro não reconhecido: '{book_raw}' (normalizado: '{book_key}'). "
                f"Isso geralmente significa diferença de grafia/acentuação."
            )

        abbrev = book_map[book_key]
        chapters = expand_chapter_spec(ch_raw)
        out.append((abbrev, chapters))

    return out


def fetch_chapter_text(version: str, abbrev: str, chapter: int) -> str:
    payload = http_get(f"{ABIBLIA_BASE}/verses/{version}/{abbrev}/{chapter}")
    book = payload.get("book", {}).get("name", abbrev)
    verses = payload.get("verses", [])
    lines = [f"{book} {chapter}"]
    for v in verses:
        n = v.get("number")
        t = (v.get("text") or "").strip()
        if n is not None and t:
            lines.append(f"{n}. {t}")
    return "\n".join(lines)


def main() -> None:
    try:
        date_str, reading = load_today_reading()
        book_map = build_book_map()
        plan = parse_reading(reading, book_map)

        if not plan:
            raise RuntimeError("Leitura do dia vazia.")

        blocks = []
        for abbrev, chapters in plan:
            for ch in chapters:
                blocks.append(fetch_chapter_text(BIBLE_VERSION, abbrev, ch))

        body = (
            f"Data: {date_str}\n"
            f"Leitura: {reading}\n"
            f"Versão: {BIBLE_VERSION}\n\n"
            + "\n\n".join(blocks)
        )
        subject = f"Leitura Bíblica ({date_str}) — {reading}"
        smtp_send(subject, body)

    except Exception as e:
        # Se algo falhar, você recebe um e-mail de erro (facilita depurar)
        smtp_send("ERRO — Leitura Bíblica diária", f"Falha ao gerar/enviar leitura.\n\nDetalhes:\n{e}")


if __name__ == "__main__":
    main()
