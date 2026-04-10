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

# Configuração para versão alemã (bilíngue)
ENABLE_GERMAN = os.environ.get("ENABLE_GERMAN", "true").lower() == "true"
GERMAN_LANG = "de"
GERMAN_VERSION = "schlachter"

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
    """
    Carrega a leitura do dia de hoje a partir do CSV.
    
    Usa uma lógica baseada no dia do ano (1-365) para lidar corretamente com anos bissextos:
    - Em anos bissextos, 29/02 usa a mesma leitura de 28/02
    - A partir de 01/03, volta ao alinhamento normal
    - Isso garante que o plano sempre se repita corretamente, independente de anos bissextos
    """
    today = dt.date.today().isoformat()
    
    with open(PLAN_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    # Primeiro tenta encontrar por data exata
    for row in rows:
        if (row.get("date") or "").strip() == today:
            return today, (row.get("reading") or "").strip()
    
    # Se não encontrou por data exata, usa o dia do ano
    if not rows:
        raise RuntimeError("CSV vazio ou sem dados")
    
    try:
        today_date = dt.date.today()
        
        # Pega o dia do ano (1-366)
        day_of_year = today_date.timetuple().tm_yday
        
        # Em anos bissextos, após 29/02 (dia 60), ajusta para alinhar com ano comum
        # 29/02 em ano bissexto usa a mesma leitura de 28/02
        # A partir de 01/03, volta ao alinhamento normal
        if today_date.year % 4 == 0 and (today_date.year % 100 != 0 or today_date.year % 400 == 0):
            # É ano bissexto
            if day_of_year == 60:  # 29 de fevereiro
                # Usa a mesma leitura de 28/02
                cycle_index = 58  # Dia 59 (índice 58) = 28/02
                print(f"Ano bissexto: 29/02 usando leitura de 28/02 (dia {cycle_index + 1})")
            elif day_of_year > 60:  # Após 29/02
                # Subtrai 1 para alinhar com plano de 365 dias
                cycle_index = day_of_year - 2
            else:  # Antes de 29/02
                cycle_index = day_of_year - 1
        else:
            # Ano comum (365 dias)
            cycle_index = day_of_year - 1
        
        # Garante que o índice está dentro do range
        cycle_index = cycle_index % len(rows)
        
        reading = (rows[cycle_index].get("reading") or "").strip()
        
        print(f"Data não encontrada no CSV. Usando dia do ano: {day_of_year} → dia {cycle_index + 1} do plano")
        
        return today, reading
        
    except Exception as e:
        raise RuntimeError(f"Erro ao calcular dia do ciclo: {e}")


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

def fetch_book(book_id: str, lang: str = None, version: str = None):
    """
    Faz cache e busca do livro da Bíblia via API do GitHub.
    Se lang e version não forem especificados, usa as configurações padrão.
    """
    if lang is None:
        lang = BIBLE_LANG
    if version is None:
        version = BIBLE_VERSION
    
    key = f"{lang}/{version}/{book_id}"
    if key in _cache:
        return _cache[key]

    url = f"{RAW_BASE}/{lang}/{version}/{book_id}/{book_id}.json"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()

    # Normaliza estrutura
    if isinstance(data, list):
        data = {"name": book_id, "chapters": data}

    _cache[key] = data
    return data


def chapter_text(book_id: str, chapter: int, lang: str = None, version: str = None) -> str:
    """
    Retorna o texto formatado de um capítulo completo.
    Se lang e version não forem especificados, usa as configurações padrão.
    """
    data = fetch_book(book_id, lang, version)
    chapters = data.get("chapters", [])
    
    if chapter > len(chapters):
        raise RuntimeError(f"Capítulo {chapter} não existe em {book_id}")
    
    ch = chapters[chapter - 1]
    
    lines = [f"{data.get('name', book_id)} {chapter}"]
    
    for i, v in enumerate(ch, start=1):
        if v.strip():
            lines.append(f"{i}. {v.strip()}")
    
    return "\n".join(lines)


def get_verse_text(book_id: str, chapter: int, verse_num: int, lang: str = None, version: str = None) -> str:
    """
    Retorna o texto de um versículo específico.
    """
    data = fetch_book(book_id, lang, version)
    chapters = data.get("chapters", [])
    
    if chapter > len(chapters):
        return ""
    
    ch = chapters[chapter - 1]
    
    if verse_num > len(ch):
        return ""
    
    return ch[verse_num - 1].strip() if ch[verse_num - 1] else ""


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
            # Busca texto em português
            data_pt = fetch_book(book_id, BIBLE_LANG, BIBLE_VERSION)
            chapters_pt = data_pt.get("chapters", [])
            
            if chapter > len(chapters_pt):
                continue
            
            ch_pt = chapters_pt[chapter - 1]
            book_name_pt = data_pt.get('name', book_id)
            
            # Busca texto em alemão (se habilitado)
            if ENABLE_GERMAN:
                try:
                    data_de = fetch_book(book_id, GERMAN_LANG, GERMAN_VERSION)
                    chapters_de = data_de.get("chapters", [])
                    ch_de = chapters_de[chapter - 1] if chapter <= len(chapters_de) else []
                    book_name_de = data_de.get('name', book_id)
                except:
                    # Se falhar ao buscar alemão, desabilita para este trecho
                    ch_de = []
                    book_name_de = book_id
            else:
                ch_de = []
                book_name_de = book_id
            
            # Monta o texto bilíngue
            if verses:
                # Com versículos específicos
                if ENABLE_GERMAN and ch_de:
                    # Título bilíngue
                    header = f"{book_name_de} {chapter} / {book_name_pt} {chapter}"
                else:
                    header = f"{book_name_pt} {chapter}"
                
                selected = [header]
                
                for vnum in verses:
                    if vnum <= len(ch_pt):
                        verse_pt = ch_pt[vnum - 1].strip()
                        
                        if ENABLE_GERMAN and ch_de and vnum <= len(ch_de):
                            verse_de = ch_de[vnum - 1].strip()
                            # Formato: número. [DE] texto alemão [PT] texto português
                            selected.append(f"{vnum}. 🇩🇪 {verse_de}")
                            selected.append(f"   🇧🇷 {verse_pt}")
                        else:
                            selected.append(f"{vnum}. {verse_pt}")
                
                text = "\n".join(selected)
            else:
                # Capítulo completo
                if ENABLE_GERMAN and ch_de:
                    header = f"{book_name_de} {chapter} / {book_name_pt} {chapter}"
                else:
                    header = f"{book_name_pt} {chapter}"
                
                lines = [header]
                
                for i, verse_pt in enumerate(ch_pt, start=1):
                    if verse_pt.strip():
                        if ENABLE_GERMAN and ch_de and i <= len(ch_de):
                            verse_de = ch_de[i - 1].strip()
                            lines.append(f"{i}. 🇩🇪 {verse_de}")
                            lines.append(f"   🇧🇷 {verse_pt.strip()}")
                        else:
                            lines.append(f"{i}. {verse_pt.strip()}")
                
                text = "\n".join(lines)
            
            text = sanitize_text(text)
            blocks.append(text)
        
        # Monta email em texto plano
        body_text = f"Leitura Bíblica do Dia\n{date_str}\n{reading}\n\n" + "\n\n".join(blocks)
        
        # Formata a data em formato legível (ex: 28 de março de 2026)
        try:
            from datetime import datetime
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", 
                    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
            data_formatada = f"{date_obj.day} de {meses[date_obj.month - 1]} de {date_obj.year}"
        except:
            data_formatada = date_str
        
        # Formata blocos para HTML com tipografia melhorada
        html_blocks = []
        for block in blocks:
            lines = block.split('\n')
            if lines:
                # Primeira linha é o título do livro/capítulo
                title = lines[0]
                verses = lines[1:]
                
                html_block = f'<h2 style="font-family: Georgia, serif; font-size: 18px; font-weight: normal; color: #333; margin: 30px 0 20px 0; text-align: center;">{title}</h2>\n'
                
                # Versículos formatados (bilíngue ou monolíngue)
                i = 0
                while i < len(verses):
                    verse = verses[i].strip()
                    if not verse:
                        i += 1
                        continue
                    
                    # Verifica se é versículo alemão (🇩🇪)
                    if "🇩🇪" in verse:
                        # Extrai número e texto alemão
                        match_de = re.match(r'^(\d+)\.\s*🇩🇪\s+(.+)$', verse)
                        if match_de and i + 1 < len(verses):
                            num = match_de.group(1)
                            text_de = match_de.group(2)
                            
                            # Próxima linha deve ser português
                            next_verse = verses[i + 1].strip()
                            match_pt = re.match(r'^\s*🇧🇷\s+(.+)$', next_verse)
                            
                            if match_pt:
                                text_pt = match_pt.group(1)
                                
                                # Formata versículo bilíngue
                                html_block += f'''
<div style="margin: 16px 0; padding: 12px; background-color: #f9f9f9; border-left: 3px solid #d4af37; border-radius: 4px;">
    <p style="font-family: Georgia, serif; font-size: 14px; color: #1a5490; margin: 0 0 8px 0; font-weight: 600;">
        <strong>{num}.</strong> 🇩🇪 Deutsch
    </p>
    <p style="font-family: Georgia, serif; font-size: 15px; line-height: 1.7; color: #333; margin: 0 0 12px 0; text-align: justify; font-style: italic;">
        {text_de}
    </p>
    <p style="font-family: Georgia, serif; font-size: 14px; color: #0d7d3f; margin: 0 0 4px 0; font-weight: 600;">
        🇧🇷 Português
    </p>
    <p style="font-family: Georgia, serif; font-size: 15px; line-height: 1.7; color: #333; margin: 0; text-align: justify;">
        {text_pt}
    </p>
</div>
'''
                                i += 2  # Pula as duas linhas processadas
                                continue
                    
                    # Versículo normal (só português)
                    match = re.match(r'^(\d+)\.\s+(.+)$', verse)
                    if match:
                        num = match.group(1)
                        text = match.group(2)
                        html_block += f'<p style="font-family: Georgia, serif; font-size: 16px; line-height: 1.8; color: #333; margin: 12px 0; text-align: justify;"><strong>{num}.</strong> {text}</p>\n'
                    else:
                        html_block += f'<p style="font-family: Georgia, serif; font-size: 16px; line-height: 1.8; color: #333; margin: 12px 0; text-align: justify;">{verse}</p>\n'
                    
                    i += 1
                
                html_blocks.append(html_block)
        
        # Monta o HTML completo com cabeçalho
        body_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; background-color: #fafafa;">
            <div style="max-width: 700px; margin: 0 auto; padding: 40px 20px; background-color: #ffffff;">
                
                <!-- Cabeçalho -->
                <div style="text-align: center; padding-bottom: 30px; border-bottom: 1px solid #e0e0e0; margin-bottom: 30px;">
                    <h1 style="font-family: Georgia, serif; font-size: 28px; font-weight: normal; color: #1a1a1a; margin: 0 0 10px 0;">
                        Leitura Bíblica do Dia
                    </h1>
                    <p style="font-family: Georgia, serif; font-size: 14px; color: #666; margin: 0;">
                        {data_formatada} • Versão: <strong>NVI</strong>
                    </p>
                </div>
                
                <!-- Introdução -->
                <div style="background-color: #f9f9f9; border-left: 4px solid #d4af37; padding: 20px 25px; margin-bottom: 30px; border-radius: 4px;">
                    <p style="font-family: Georgia, serif; font-size: 13px; color: #888; text-transform: uppercase; letter-spacing: 1px; margin: 0 0 8px 0; font-weight: 600;">
                        LEITURA DE HOJE
                    </p>
                    <h3 style="font-family: Georgia, serif; font-size: 20px; font-weight: 600; color: #1a1a1a; margin: 0 0 12px 0;">
                        {reading}
                    </h3>
                    <p style="font-family: Georgia, serif; font-size: 15px; line-height: 1.6; color: #555; margin: 0;">
                        Bom dia. Aqui está a sua porção bíblica de hoje. Leia com calma, tentando sempre aplicar à sua vida.
                    </p>
                </div>
                
                <!-- Conteúdo Bíblico -->
                {''.join(html_blocks)}
                
                <!-- Rodapé -->
                <div style="margin-top: 50px; padding-top: 30px; border-top: 1px solid #e0e0e0;">
                    <p style="font-family: Georgia, serif; font-size: 14px; color: #999; text-align: center; line-height: 1.6; margin: 0;">
                        Tenha um bom dia. Que Deus o abençoe maravilhosamente hoje e sempre.
                    </p>
                </div>
                
            </div>
        </body>
        </html>
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
