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
BIBLE_VERSION = os.environ.get("BIBLE_VERSION", "acf")  # acf, nvi, arc, aa, kja etc. :contentReference[oaicite:1]{index=1}

RAW_BASE = "https://raw.githubusercontent.com/maatheusgois/bible/main/versions"


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


def load_today_reading() -> Tuple[str, str]:
    today = dt.date.today().isoformat()
    with open(PLAN_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("date") or "").strip() == today:
                return today, (row.get("reading") or "").strip()
    raise RuntimeError(f"Nenhuma leitura encontrada no CSV para a data {today}.")


def norm(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^([1-3])\s*([A-Za-zÀ-ÿ])", r"\1 \2", s)  # "2Samuel" -> "2 Samuel"
    s = re.sub(r"\s+", " ", s).lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s


def book_name_to_id_map() -> Dict[str, str]:
    # IDs conforme README do repositório MaatheusGois/bible :contentReference[oaicite:2]{index=2}
    raw = {
        "genesis": "gn",
        "exodo": "ex",
        "levitico": "lv",
        "numeros": "nm",
        "deuteronomio": "dt",
        "josue": "js",
        "juizes": "jud",
        "rute": "rt",
        "1 samuel": "1sm",
        "2 samuel": "2sm",
        "1 reis": "1kgs",
        "2 reis": "2kgs",
        "1 cronicas": "1ch",
        "2 cronicas": "2ch",
        "esdras": "ezr",
        "neemias": "ne",
        "ester": "et",
        "jo": "job",
        "job": "job",
        "salmo": "ps",
        "salmos": "ps",
        "proverbios": "prv",
        "eclesiastes": "ec",
        "cantares": "so",
        "isaias": "is",
        "jeremias": "jr",
        "lamentacoes": "lm",
        "ezequiel": "ez",
        "daniel": "dn",
        "oseias": "ho",
        "joel": "jl",
        "amos": "am",
        "obadias": "ob",
        "jonas": "jn",
        "miqueias": "mi",
        "naum": "na",
        "habacuque": "hk",
        "sofonias": "zp",
        "ageu": "hg",
        "zacarias": "zc",
        "malaquias": "ml",
        "mateus": "mt",
        "marcos": "mk",
        "lucas": "lk",
        "joao": "jo",
        "atos": "act",
        "romanos": "rm",
        "1 corintios": "1co",
        "2 corintios": "2co",
        "galatas": "gl",
        "efesios": "eph",
        "filipenses": "ph",
        "colossenses": "cl",
        "1 tessalonicenses": "1ts",
        "2 tessalonicenses": "2ts",
        "1 timoteo": "1tm",
        "2 timoteo": "2tm",
        "tito": "tt",
        "filemom": "phm",
        "hebreus": "hb",
        "tiago": "jm",
        "1 pedro": "1pe",
        "2 pedro": "2pe",
        "1 joao": "1jo",
        "2 joao": "2jo",
        "3 joao": "3jo",
        "judas": "jd",
        "apocalipse": "re",
    }
    return {norm(k): v for k, v in raw.items()}


def expand_chapter_spec(spec: str) -> List[int]:
    spec = spec.strip().replace(" ", "")
    chunks = [c for c in spec.split(",") if c]
    out: List[int] = []
    for c in chunks:
        if "-" in c:
            a, b = c.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(c))
    # unique preserving order
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            uniq.append(x)
            seen.add(x)
    return uniq


def parse_reading(reading: str, name_to_id: Dict[str, str]) -> List[Tuple[str, List[int]]]:
    parts = [p.strip() for p in reading.split(";") if p.strip()]
    plan: List[Tuple[str, List[int]]] = []
    for part in parts:
        m = re.match(r"^(.+?)\s+([\d,\-\s]+)$", part)
        if not m:
            raise RuntimeError(f"Não consegui interpretar este trecho: '{part}'")
        book_raw, ch_raw = m.group(1), m.group(2)
        key = norm(book_raw)
        if key not in name_to_id:
            raise RuntimeError(f"Livro não reconhecido: '{book_raw}' (normalizado: '{key}')")
        book_id = name_to_id[key]
        chapters = expand_chapter_spec(ch_raw)
        plan.append((book_id, chapters))
    return plan


_book_cache: Dict[str, dict] = {}


def fetch_book(book_id: str) -> dict:
    # Baixa o livro inteiro 1x por execução
    cache_key = f"{BIBLE_LANG}/{BIBLE_VERSION}/{book_id}"
    if cache_key in _book_cache:
        return _book_cache[cache_key]

    url = f"{RAW_BASE}/{BIBLE_LANG}/{BIBLE_VERSION}/{book_id}/{book_id}.json"
    r = requests.get(url, timeout=60, headers={"User-Agent": "texto-biblico-diario/1.0"})
    r.raise_for_status()
    data = r.json()

    # Alguns arquivos vêm como LISTA direto (em vez de dict com name/chapters)
    if isinstance(data, list):
        data = {"name": book_id, "chapters": data}

    _book_cache[cache_key] = data
    return data

    url = f"{RAW_BASE}/{BIBLE_LANG}/{BIBLE_VERSION}/{book_id}/{book_id}.json"
    r = requests.get(url, timeout=60, headers={"User-Agent": "texto-biblico-diario/1.0"})
    r.raise_for_status()
    data = r.json()
    _book_cache[cache_key] = data
    return data


def chapter_text(book_id: str, chapter: int) -> str:
    data = fetch_book(book_id)

    # Formato esperado no repo: data é dict e data["chapters"] é lista de capítulos,
    # cada capítulo é uma lista de strings (versos).
    if isinstance(data, list):
        # fallback raro: livro veio como lista de capítulos diretamente
        chapters = data
        book_name = book_id
    else:
        book_name = data.get("name", book_id)
        chapters = data.get("chapters", [])

    if not isinstance(chapters, list) or len(chapters) == 0:
        raise RuntimeError(f"Livro sem capítulos: {book_id}")

    idx = chapter - 1
    if idx < 0 or idx >= len(chapters):
        raise RuntimeError(f"Capítulo não encontrado: {book_id} {chapter}")

    ch_obj = chapters[idx]

    lines = [f"{book_name} {chapter}"]

    # Caso 1 (NVI pt-br): capítulo é LISTA de STRINGS (versos)
    if isinstance(ch_obj, list) and (len(ch_obj) == 0 or isinstance(ch_obj[0], str)):
        for i, verse_text in enumerate(ch_obj, start=1):
            t = str(verse_text).strip()
            if t:
                lines.append(f"{i}. {t}")
        return "\n".join(lines)

    # Caso 2: capítulo pode vir como dict com "verses"
    if isinstance(ch_obj, dict):
        verses = ch_obj.get("verses", ch_obj.get("verse", []))
        for v in verses:
            if isinstance(v, dict):
                n = v.get("number", v.get("verse"))
                t = (v.get("text") or v.get("content") or "").strip()
                if n is not None and t:
                    lines.append(f"{n}. {t}")
            else:
                t = str(v).strip()
                if t:
                    lines.append(t)
        return "\n".join(lines)

    # Caso 3: qualquer outro formato
    raise RuntimeError(f"Formato inesperado para capítulo: {book_id} {chapter} ({type(ch_obj)})")


def main() -> None:
    try:
        date_str, reading = load_today_reading()
        name_to_id = book_name_to_id_map()
        plan = parse_reading(reading, name_to_id)

        blocks = []
        for book_id, chapters in plan:
            for ch in chapters:
                blocks.append(chapter_text(book_id, ch))

        body = f"Data: {date_str}\nLeitura: {reading}\nVersão: {BIBLE_VERSION}\n\n" + "\n\n".join(blocks)
        subject = f"Leitura Bíblica ({date_str}) — {reading}"
        smtp_send(subject, body)

    except Exception as e:
        smtp_send("ERRO — Leitura Bíblica diária", f"Falha ao gerar/enviar leitura.\n\nDetalhes:\n{e}")


if __name__ == "__main__":
    main()
