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
    """Envia email via SMTP do Gmail"""
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
    """Carrega a leitura do dia de hoje a partir do CSV"""
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
    """Normaliza string removendo acentos e convertendo para minúsculas"""
    s = s.strip()
    # Mantém números de livros (1, 2, 3) com espaço
    s = re.sub(r"^([1-3])\s*([A-Za-zÀ-ÿ])", r"\1 \2", s)
    s = re.sub(r"\s+", " ", s).lower()
    # Remove acentos
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s


def book_name_to_id_map() -> Dict[str, str]:
    """Mapeamento completo de nomes de livros para IDs da API"""
    raw = {
        # Antigo Testamento
        "genesis": "gn", "gênesis": "gn",
        "exodo": "ex", "êxodo": "ex",
        "levitico": "lv", "levítico": "lv",
        "numeros": "nm", "números": "nm",
        "deuteronomio": "dt", "deuteronômio": "dt",
        "josue": "js", "josué": "js",
        "juizes": "jud", "juízes": "jud",
        "rute": "rt",
        "1 samuel": "1sm", "1samuel": "1sm",
        "2 samuel": "2sm", "2samuel": "2sm",
        "1 reis": "1ki", "1reis": "1ki",
        "2 reis": "2ki", "2reis": "2ki",
        "1 cronicas": "1ch", "1 crônicas": "1ch", "1crônicas": "1ch",
        "2 cronicas": "2ch", "2 crônicas": "2ch", "2crônicas": "2ch",
        "esdras": "ezr",
        "neemias": "ne",
        "ester": "es",
        "jo": "jb", "jó": "jb",
        "salmos": "ps", "salmo": "ps",
        "proverbios": "pr", "provérbios": "pr",
        "eclesiastes": "ec",
        "cantares": "ss", "canticos": "ss", "cântico dos cânticos": "ss",
        "isaias": "is", "isaías": "is",
        "jeremias": "jr",
        "lamentacoes": "lm", "lamentações": "lm",
        "ezequiel": "ez",
        "daniel": "dn",
        "oseias": "ho", "oséias": "ho",
        "joel": "jl",
        "amos": "am", "amós": "am",
        "obadias": "ob",
        "jonas": "jh",
        "miqueias": "mi", "miquéias": "mi",
        "naum": "na",
        "habacuque": "hk",
        "sofonias": "zp",
        "ageu": "hg",
        "zacarias": "zc",
        "malaquias": "ml",
        
        # Novo Testamento
        "mateus": "mt",
        "marcos": "mk",
        "lucas": "lk",
        "joao": "jo", "joão": "jo",
        "atos": "ac",
        "romanos": "rm",
        "1 corintios": "1co", "1coríntios": "1co", "1 coríntios": "1co",
        "2 corintios": "2co", "2coríntios": "2co", "2 coríntios": "2co",
        "galatas": "gl", "gálatas": "gl",
        "efesios": "ep", "efésios": "ep",
        "filipenses": "pp",
        "colossenses": "cl",
        "1 tessalonicenses": "1th", "1tessalonicenses": "1th",
        "2 tessalonicenses": "2th", "2tessalonicenses": "2th",
        "1 timoteo": "1tm", "1 timóteo": "1tm", "1timóteo": "1tm",
        "2 timoteo": "2tm", "2 timóteo": "2tm", "2timóteo": "2tm",
        "tito": "tt",
        "filemom": "pm", "filemon": "pm",
        "hebreus": "hb",
        "tiago": "jm",
        "1 pedro": "1pe", "1pedro": "1pe",
        "2 pedro": "2pe", "2pedro": "2pe",
        "1 joao": "1jo", "1 joão": "1jo", "1joão": "1jo",
        "2 joao": "2jo", "2 joão": "2jo", "2joão": "2jo",
        "3 joao": "3jo", "3 joão": "3jo", "3joão": "3jo",
        "judas": "jd",
        "apocalipse": "re"
    }
    return {norm(k): v for k, v in raw.items()}


# =========================
# PARSER MELHORADO
# =========================
def parse_reading(reading: str, name_to_id: Dict[str, str]):
    """
    Parser robusto para diferentes formatos de leitura bíblica.
    
    Exemplos suportados:
    - "Gênesis 1,2" → Gênesis capítulos 1 e 2
    - "Gênesis 3-5" → Gênesis capítulos 3, 4 e 5
    - "Salmo 11, 59" → Salmo capítulos 11 e 59
    - "Levítico 20-22, Salmo 95" → Levítico caps 20-22, depois Salmo 95
    - "Números 11-12:16, Salmo 90" → Números caps 11-12:16, depois Salmo 90
    - "1Samuel 19:1-18; Salmo 11, 59" → múltiplas referências
    - "Ester 4:10-17; 5-7" → Ester cap 4 vers 10-17, depois caps 5-7
    - "2 João; 3 João" → livros sem números de capítulos
    """
    # Primeiro, normaliza separadores: transforma vírgulas entre livros em ponto-e-vírgula
    # Detecta padrões como ", Livro" e substitui por "; Livro"
    reading_normalized = re.sub(
        r',\s+([1-3]?\s*[A-ZÀÂÃÉÊÍÓÔÕÚ][a-zàâãéêíóôõúç]+)',
        r'; \1',
        reading
    )
    
    # Separa por ponto-e-vírgula para múltiplas referências
    parts = [p.strip() for p in reading_normalized.split(";") if p.strip()]
    plan = []
    
    # Variável para manter o livro anterior (para casos como "Ester 4:10-17; 5-7")
    last_book_id = None

    for part in parts:
        # Tenta match com livro + referências
        match = re.match(r'^([1-3]?\s*[A-Za-zÀ-ÿ\s]+?)\s+([\d,:;\-\s]+)$', part.strip())
        
        # Caso especial: apenas nome do livro sem capítulos (ex: "2 João", "Judas")
        if not match:
            # Tenta match apenas com nome do livro
            book_only_match = re.match(r'^([1-3]?\s*[A-Za-zÀ-ÿ\s]+)$', part.strip())
            if book_only_match:
                book_raw = book_only_match.group(1).strip()
                key = norm(book_raw)
                if key in name_to_id:
                    book_id = name_to_id[key]
                    plan.append((book_id, 1, None))  # Assume capítulo 1
                    last_book_id = book_id
                    continue
            
            # Caso especial: apenas números (continuação do livro anterior)
            # Ex: "Ester 4:10-17; 5-7" onde "5-7" refere-se a Ester
            number_only_match = re.match(r'^([\d,:\-\s]+)$', part.strip())
            if number_only_match and last_book_id:
                refs_raw = number_only_match.group(1).strip()
                book_id = last_book_id
            else:
                raise RuntimeError(f"Formato não reconhecido: '{part}'")
        else:
            book_raw = match.group(1).strip()
            refs_raw = match.group(2).strip()
            
            # Verifica se o livro existe
            key = norm(book_raw)
            if key not in name_to_id:
                raise RuntimeError(f"Livro não reconhecido: '{book_raw}'")
            
            book_id = name_to_id[key]
            last_book_id = book_id
        
        # Processa as referências (capítulos e versículos)
        # Primeiro verifica se tem range com dois-pontos no meio (ex: "11-12:16")
        # Esse é um caso especial: cap 11 completo, cap 12 até versículo 16
        if re.search(r'(\d+)-(\d+):(\d+)', refs_raw):
            match_special = re.search(r'(\d+)-(\d+):(\d+)', refs_raw)
            start_ch = int(match_special.group(1))
            end_ch = int(match_special.group(2))
            end_verse = int(match_special.group(3))
            
            # Adiciona capítulos completos antes do último
            for ch in range(start_ch, end_ch):
                plan.append((book_id, ch, None))
            
            # Adiciona o último capítulo com versículos específicos
            verses = list(range(1, end_verse + 1))
            plan.append((book_id, end_ch, verses))
            
            # Remove a parte já processada
            refs_raw = re.sub(r'\d+-\d+:\d+', '', refs_raw).strip().strip(',').strip()
        
        # Separa por vírgula
        if refs_raw:
            refs = [r.strip() for r in refs_raw.split(",") if r.strip()]
            
            for ref in refs:
                # Verifica se tem versículos específicos (tem dois-pontos)
                if ":" in ref:
                    ch_part, vs_part = ref.split(":", 1)
                    ch = int(ch_part.strip())
                    
                    # Verifica se é range de versículos
                    if "-" in vs_part:
                        start, end = vs_part.split("-", 1)
                        verses = list(range(int(start.strip()), int(end.strip()) + 1))
                    else:
                        verses = [int(vs_part.strip())]
                    
                    plan.append((book_id, ch, verses))
                
                # Se não tem dois-pontos, são apenas capítulos
                else:
                    # Verifica se é range de capítulos
                    if "-" in ref:
                        start, end = ref.split("-", 1)
                        for ch in range(int(start.strip()), int(end.strip()) + 1):
                            plan.append((book_id, ch, None))
                    else:
                        plan.append((book_id, int(ref.strip()), None))
    
    return plan


# =========================
# FETCH BÍBLIA
# =========================
_cache = {}

def fetch_book(book_id: str):
    """Faz cache e busca do livro da Bíblia via API do GitHub"""
    key = f"{BIBLE_LANG}/{BIBLE_VERSION}/{book_id}"
    if key in _cache:
        return _cache[key]

    url = f"{RAW_BASE}/{BIBLE_LANG}/{BIBLE_VERSION}/{book_id}/{book_id}.json"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()

    # Normaliza estrutura
    if isinstance(data, list):
        data = {"name": book_id, "chapters": data}

    _cache[key] = data
    return data


def chapter_text(book_id: str, chapter: int) -> str:
    """Retorna o texto formatado de um capítulo completo"""
    data = fetch_book(book_id)
    chapters = data.get("chapters", [])
    
    if chapter > len(chapters):
        raise RuntimeError(f"Capítulo {chapter} não existe em {book_id}")
    
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
    """Remove artefatos e normaliza espaçamento do texto"""
    # Remove strings problemáticas conhecidas
    text = text.replace("full-versionmente", "completamente")
    text = text.replace("full-version", "")
    
    # Normaliza espaços
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    
    return text.strip()


# =========================
# CONTROLE DE ENVIO
# =========================
def already_sent_today(date_str: str) -> bool:
    """Verifica se já foi enviado email para esta data"""
    try:
        with open(SENT_MARKER_FILE) as f:
            return f.read().strip() == date_str
    except FileNotFoundError:
        return False


def mark_sent(date_str: str):
    """Marca a data como enviada"""
    with open(SENT_MARKER_FILE, "w") as f:
        f.write(date_str)


# =========================
# MAIN
# =========================
def main():
    """Função principal de execução"""
    try:
        date_str, reading = load_today_reading()
        
        # Evita envio duplicado
        if already_sent_today(date_str):
            print(f"Email já foi enviado para {date_str}")
            return
        
        # Parser com mapeamento de livros
        name_to_id = book_name_to_id_map()
        plan = parse_reading(reading, name_to_id)
        
        blocks = []
        
        # Processa cada referência bíblica
        for book_id, chapter, verses in plan:
            full_text = chapter_text(book_id, chapter)
            
            # Se tem versículos específicos, filtra
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
        
        # 1. Preparação dos blocos (melhor separação sem poluir o HTML)
content_html = "".join([f'<p style="margin-bottom: 1.5em;">{block}</p>' for block in blocks])

body_html = f"""
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #f9f9f9; -webkit-text-size-adjust: 100%;">
    <div style="font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; 
                max-width: 650px; 
                margin: 40px auto; 
                padding: 40px; 
                background-color: #ffffff; 
                border-radius: 8px; 
                box-shadow: 0 4px 12px rgba(0,0,0,0.05);
                color: #2c3e50;
                line-height: 1.8;">
        
        <h2 style="color: #1a2a3a; 
                   font-size: 28px; 
                   margin-bottom: 8px; 
                   font-weight: 700;
                   letter-spacing: -0.5px;">
            Leitura Bíblica Diária
        </h2>
        
        <p style="color: #7f8c8d; 
                  font-size: 16px; 
                  margin-top: 0; 
                  margin-bottom: 24px;
                  text-transform: uppercase;
                  letter-spacing: 1px;">
            <strong>{date_str}</strong>
        </p>
        
        <div style="background-color: #f8fbfd; 
                    border-left: 4px solid #3498db; 
                    padding: 15px 25px; 
                    margin-bottom: 35px;
                    font-style: italic;
                    color: #34495e;
                    font-size: 18px;">
            {reading}
        </div>

        <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">

        <div style="font-size: 19px; 
                    color: #333333; 
                    text-align: justify; 
                    hyphens: auto;">
            {content_html}
        </div>
        
        <footer style="margin-top: 50px; 
                       text-align: center; 
                       font-size: 12px; 
                       color: #bdc3c7;">
            Gerado automaticamente para sua meditação diária.
        </footer>
    </div>
</body>
</html>
"""
        """
        
        # Envia email
        smtp_send(f"Leitura Bíblica ({date_str})", body_text, body_html)
        
        # Marca como enviado
        mark_sent(date_str)
        
        print(f"Email enviado com sucesso para {date_str}")
        
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Erro: {tb}")
        
        # Tenta enviar email de erro
        try:
            smtp_send(
                "ERRO - Leitura Bíblica Diária",
                f"Erro ao processar leitura:\n\n{tb}",
                f"<pre style='background: #f8d7da; padding: 15px; border-radius: 5px;'>{tb}</pre>"
            )
        except:
            print("Falha ao enviar email de erro")


if __name__ == "__main__":
    main()
