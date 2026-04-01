import csv
import datetime as dt
import os
import re
import smtplib
import unicodedata
from email.message import EmailMessage
from typing import Dict, List, Tuple, Any

import requests

PLAN_CSV = os.environ.get("PLAN_CSV", "plan.csv")
BIBLE_LANG = os.environ.get("BIBLE_LANG", "pt-br")
BIBLE_VERSION = os.environ.get("BIBLE_VERSION", "nvi")  # ex: nvi
SENT_MARKER_FILE = os.environ.get("SENT_MARKER_FILE", "sent.txt")

RAW_BASE = "https://raw.githubusercontent.com/maatheusgois/bible/main/versions"

# Cache do livro para evitar múltiplos downloads na mesma execução
_book_cache: Dict[str, Any] = {}


def smtp_send(subject: str, body_text: str, body_html: str) -> None:
    email_user = os.environ["EMAIL_USER"]
    email_pass = os.environ["EMAIL_PASS"]
    email_to = os.environ["EMAIL_TO"]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email_user
    msg["To"] = email_to

    # Texto simples (fallback)
    msg.set_content(body_text)

    # HTML (visual devocional)
    msg.add_alternative(body_html, subtype="html")

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


def already_sent_today(date_str: str) -> bool:
    try:
        with open(SENT_MARKER_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() == date_str
    except FileNotFoundError:
        return False


def mark_sent(date_str: str) -> None:
    with open(SENT_MARKER_FILE, "w", encoding="utf-8") as f:
        f.write(date_str)


def norm(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^([1-3])\s*([A-Za-zÀ-ÿ])", r"\1 \2", s)  # "2Samuel" -> "2 Samuel"
    s = re.sub(r"\s+", " ", s).lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s


def book_name_to_id_map() -> Dict[str, str]:
    # IDs usados pelo repositório maatheusgois/bible (pt-br)
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
    # remove duplicados preservando ordem
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            uniq.append(x)
            seen.add(x)
    return uniq


def parse_reading(reading: str, name_to_id: Dict[str, str]):
    parts = [p.strip() for p in reading.split(";") if p.strip()]
    plan = []

    for part in parts:
        # Agora aceita:
        # Livro 19
        # Livro 19:1-18
        m = re.match(r"^(.+?)\s+(\d+)(?::([\d\-]+))?$", part)

        if not m:
            raise RuntimeError(f"Não consegui interpretar este trecho: '{part}'")

        book_raw = m.group(1)
        chapter = int(m.group(2))
        verse_spec = m.group(3)

        key = norm(book_raw)
        if key not in name_to_id:
            raise RuntimeError(f"Livro não reconhecido: '{book_raw}'")

        book_id = name_to_id[key]

        if verse_spec:
            # ex: 1-18
            if "-" in verse_spec:
                start, end = map(int, verse_spec.split("-"))
                verses = list(range(start, end + 1))
            else:
                verses = [int(verse_spec)]

            plan.append((book_id, chapter, verses))
        else:
            plan.append((book_id, chapter, None))  # capítulo inteiro

    return plan


def fetch_book(book_id: str) -> Any:
    """
    Baixa o JSON do livro.
    O repositório pode retornar:
      - dict com chaves como "name" e "chapters"
      - lista diretamente (capítulos)
    Guardamos no cache para reuso na execução.
    """
    cache_key = f"{BIBLE_LANG}/{BIBLE_VERSION}/{book_id}"
    if cache_key in _book_cache:
        return _book_cache[cache_key]

    url = f"{RAW_BASE}/{BIBLE_LANG}/{BIBLE_VERSION}/{book_id}/{book_id}.json"
    r = requests.get(url, timeout=60, headers={"User-Agent": "texto-biblico-diario/1.0"})
    r.raise_for_status()
    data = r.json()

    _book_cache[cache_key] = data
    return data


def chapter_text(book_id: str, chapter: int) -> str:
    data = fetch_book(book_id)

    # Caso A: JSON é lista (capítulos)
    if isinstance(data, list):
        book_name = book_id
        chapters = data
    # Caso B: JSON é dict (normal)
    elif isinstance(data, dict):
        book_name = str(data.get("name", book_id))
        chapters = data.get("chapters", [])
    else:
        raise RuntimeError(f"Formato inesperado do livro {book_id}: {type(data)}")

    if not isinstance(chapters, list) or len(chapters) == 0:
        raise RuntimeError(f"Livro sem capítulos: {book_id}")

    idx = chapter - 1
    if idx < 0 or idx >= len(chapters):
        raise RuntimeError(f"Capítulo não encontrado: {book_id} {chapter}")

    ch_obj = chapters[idx]
    lines = [f"{book_name} {chapter}"]

    # Formato comum na NVI pt-br: capítulo é LISTA de STRINGS (versos)
    if isinstance(ch_obj, list) and (len(ch_obj) == 0 or isinstance(ch_obj[0], str)):
        for i, verse_text in enumerate(ch_obj, start=1):
            t = str(verse_text).strip()
            if t:
                lines.append(f"{i}. {t}")
        return "\n".join(lines)

    # Formatos alternativos: dict com "verses"/"verse"
    if isinstance(ch_obj, dict):
        verses = ch_obj.get("verses", ch_obj.get("verse", []))
        if not isinstance(verses, list):
            verses = []

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

    # Qualquer outro formato
    raise RuntimeError(f"Formato inesperado para capítulo: {book_id} {chapter} ({type(ch_obj)})")

def sanitize_text(text: str) -> str:
    """
    Corrige artefatos conhecidos e normaliza o texto bíblico
    sem alterar o conteúdo legítimo.
    """

    # Correções específicas conhecidas
    replacements = {
        "full-versionmente": "completamente",
        "full-version": "",
    }

    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)

    # Remove espaços duplicados
    text = re.sub(r"[ \t]+", " ", text)

    # Remove quebras excessivas
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove espaços antes de pontuação
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)

    # Corrige possíveis espaços após abertura de parênteses
    text = re.sub(r"\(\s+", "(", text)

    # Corrige espaços antes de fechamento de parênteses
    text = re.sub(r"\s+\)", ")", text)

    return text.strip()


def main() -> None:
    try:
        date_str, reading = load_today_reading()

        # Idempotência: se já enviou hoje, não envia de novo
        if already_sent_today(date_str):
            return

        name_to_id = book_name_to_id_map()
        plan = parse_reading(reading, name_to_id)

        blocks: List[str] = []
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

        body_text = (
            f"Leitura Bíblica do Dia\n"
            f"Data: {date_str}\n"
            f"Leitura: {reading}\n"
            f"Versão: {BIBLE_VERSION}\n\n"
            + "\n\n".join(blocks)
        )

        blocks_html = "".join(
            f"""
            <div style="margin-top:18px; padding:16px 16px; background:#ffffff; border:1px solid #e9edf5; border-radius:14px;">
              <div style="white-space:pre-wrap; font-family: Georgia, 'Times New Roman', serif; font-size:16px; line-height:1.75; color:#111827;">
                {b}
              </div>
            </div>
            """
            for b in blocks
        )

        body_html = f"""
        <!doctype html>
        <html>
          <body style="margin:0; padding:0; background:#f6f7fb;">
            <div style="max-width:760px; margin:0 auto; padding:26px;">
              <div style="text-align:center; margin-bottom:14px; font-family: Georgia, 'Times New Roman', serif;">
                <div style="font-size:22px; font-weight:700; color:#111827;">Leitura Bíblica do Dia</div>
                <div style="margin-top:6px; font-size:14px; color:#6b7280;">
                  {date_str} • Versão: <b style="color:#111827;">{BIBLE_VERSION.upper()}</b>
                </div>
              </div>

              <div style="background:#ffffff; border:1px solid #e9edf5; border-radius:16px; padding:18px;">
                <div style="font-family: Arial, sans-serif; font-size:12px; color:#6b7280; letter-spacing:.06em; text-transform:uppercase;">
                  Leitura de hoje
                </div>
                <div style="margin-top:6px; font-family: Georgia, 'Times New Roman', serif; font-size:20px; font-weight:700; color:#111827;">
                  {reading}
                </div>

                <div style="margin-top:12px; height:1px; background:#eef2f7;"></div>

                <div style="margin-top:14px; font-family: Arial, sans-serif; font-size:13px; color:#6b7280;">
                  Bom dia. Aqui está a sua porção bíblica de hoje. Leia com calma, tentando sempre aplicar à sua vida..
                </div>
              </div>

              {blocks_html}

              <div style="margin-top:18px; text-align:center; font-family: Arial, sans-serif; font-size:12px; color:#9ca3af;">
                Tenha um bom dia. Que Deus o abençoe maravilhosamente hoje e sempre.
              </div>
            </div>
          </body>
        </html>
        """

        subject = f"Leitura Bíblica ({date_str}) — {reading}"
        smtp_send(subject, body_text, body_html)

        # Marca como enviado (para evitar duplicar no mesmo dia)
        mark_sent(date_str)

    except Exception:
        import traceback

        tb = traceback.format_exc()
        try:
            smtp_send(
                "ERRO — Leitura Bíblica diária",
                tb,
                f"<pre style='white-space:pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;'>{tb}</pre>",
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
