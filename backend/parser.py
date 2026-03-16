import re
import json
import time
from pathlib import Path
from typing import Dict, List


PROCESS_REGEX = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")

# Cabeçalho de ocorrência - bem permissivo para pegar variações:
# "Ocorrência: 1", "Ocorrencia: 1", "Ocorrência : 3 LEONORA", etc.
OCCURRENCE_HEADER_REGEX = re.compile(
    r"^Ocorr\w*?\s*:\s*(\d+)", re.IGNORECASE | re.MULTILINE
)

# Cabeçalho geral com nome do cliente e código (ex. MGI MINAS ... / Código Cliente: 11)
CLIENT_HEADER_REGEX = re.compile(
    r"^(?P<client_name>.+?)\s*(?:\r?\n)+\s*Código Cliente:\s*(?P<client_code>.+)$",
    re.IGNORECASE | re.MULTILINE,
)

# #region agent log helper (debug instrumentation)
DEBUG_LOG_PATH = Path("c:/Users/teste/Desktop/validador juridico/.cursor/debug.log")


def _agent_log(hypothesis_id: str, location: str, message: str, data=None, run_id: str = "run1"):
    entry = {
        "id": f"log_{int(time.time() * 1000)}",
        "timestamp": int(time.time() * 1000),
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
    }
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# #endregion


def extract_process_numbers(text: str) -> List[str]:
    """
    Extrai todos os números de processo do texto usando a regex fornecida.

    Mantém a ordem de ocorrência e inclui repetições, caso existam.
    """
    if not text:
        return []
    found = PROCESS_REGEX.findall(text)
    _agent_log(
        "H2",
        "backend.parser:extract_process_numbers",
        "process numbers extracted",
        {"count": len(found)},
    )
    return found


def parse_occurrences(text: str) -> List[Dict]:
    """
    Faz o parsing do TXT estruturado em blocos de "Ocorrência" e
    devolve uma lista de dicionários, cada um representando uma ocorrência
    com todos os metadados relevantes extraídos das linhas.

    Campos esperados (quando existirem no texto):
    - occurrence_number
    - uf
    - diary
    - sigla
    - court_section
    - date_publication
    - date_availability
    - search_term
    - full_text (inteiro teor da publicação)
    - process_numbers (lista de processos encontrados no inteiro teor)
    - raw_block (texto bruto do bloco)
    """
    if not text:
        return []

    occurrences: List[Dict] = []

    # Tenta obter nome e código do cliente a partir do cabeçalho
    m_client = CLIENT_HEADER_REGEX.search(text)
    client_name = m_client.group("client_name").strip() if m_client else ""
    client_code = m_client.group("client_code").strip() if m_client else ""

    # Localiza o início de cada ocorrência
    matches = list(OCCURRENCE_HEADER_REGEX.finditer(text))
    if not matches:
        _agent_log(
            "H2",
            "backend.parser:parse_occurrences",
            "no occurrence headers found",
            {},
        )
        return []

    process_counts: List[int] = []
    fulltext_lengths: List[int] = []
    fallback_used = 0

    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end].strip()

        occurrence_number = int(match.group(1))

        # Extrai linhas chave dentro do bloco
        def extract_line(pattern: str) -> str:
            m = re.search(pattern, block, re.IGNORECASE)
            if not m:
                return ""
            return m.group(1).strip()

        uf = extract_line(r"UF:\s*(.+)")
        diary = extract_line(r"Di[áa]rio\s*/?\s*Tribunal:\s*(.+)")
        sigla = extract_line(r"Sigla:\s*(.+)")
        court_section = extract_line(r"Vara\s*/?\s*Secretaria\s*/?\s*Órg[aã]o\s*/?\s*Cart[óo]rio:\s*(.+)")
        if not court_section:
            # Variação enxuta que aparece no exemplo do TJMG
            court_section = extract_line(r"Vara/Secretaria/Órgão/Cartório:\s*(.+)")

        date_publication = extract_line(r"Data Publica[çc][ãa]o:\s*(.+)")
        date_availability = extract_line(r"Data Disponibiliza[çc][ãa]o:\s*(.+)")
        search_term = extract_line(r"Termo Pesquisado:\s*(.+)")

        # Inteiro teor da publicação: pega tudo após "Inteiro teor da publicação"
        full_text = ""
        m_full = re.search(
            r"Inteiro teor da publica[çc][ãa]o:?\s*(.*)",
            block,
            re.IGNORECASE | re.DOTALL,
        )
        if m_full:
            full_text = m_full.group(1).strip()
            # Remove possível marcador final de separação, como "##########"
            full_text = re.sub(r"#+\s*$", "", full_text).strip()

        process_numbers = extract_process_numbers(full_text)
        if not process_numbers:
            # fallback: tenta no bloco bruto se o inteiro teor não trouxe nada
            process_numbers = extract_process_numbers(block)
            if process_numbers:
                fallback_used += 1

        process_counts.append(len(process_numbers))
        fulltext_lengths.append(len(full_text))

        occurrence_data: Dict = {
            "occurrence_number": occurrence_number,
            "uf": uf,
            "diary": diary,
            "sigla": sigla,
            "court_section": court_section,
            "date_publication": date_publication,
            "date_availability": date_availability,
            "search_term": search_term,
            "full_text": full_text,
            "process_numbers": process_numbers,
            "client_name": client_name,
            "client_code": client_code,
            "raw_block": block,
        }

        occurrences.append(occurrence_data)

    _agent_log(
        "H2",
        "backend.parser:parse_occurrences",
        "occurrences parsed",
        {
            "count": len(occurrences),
            "zero_process": sum(1 for c in process_counts if c == 0),
            "total_process_numbers": sum(process_counts),
            "sample_counts": process_counts[:10],
            "sample_fulltext_lengths": fulltext_lengths[:10],
            "fallback_used": fallback_used,
        },
    )

    return occurrences


