from typing import List, Dict, Tuple
import json
import time
from pathlib import Path


RESPONSIBLE_MAP = {
    ("2", "9"): "CHRISTIANE",
    ("3", "6"): "BÁRBARA",
    ("1", "0"): "SÍLVIA",
    ("4", "5"): "LEONORA",
}

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


def _get_reference_digit(process_number: str) -> str:
    """
    Obtém o dígito de referência conforme a regra:

    - Considera a parte antes do hífen (7 dígitos).
    - Se o último dígito for 7 ou 8, usa o dígito imediatamente anterior.
    - Caso contrário, usa o próprio último dígito.
    """
    before_hyphen = process_number.split("-", 1)[0]
    if len(before_hyphen) < 2:
        # Formato inesperado: retorna último dígito disponível
        return before_hyphen[-1]

    last_digit = before_hyphen[-1]
    if last_digit in ("7", "8"):
        return before_hyphen[-2]
    return last_digit


def _get_responsible_by_digit(digit: str) -> str:
    """
    Mapeia o dígito de referência para o responsável.
    """
    for digits, name in RESPONSIBLE_MAP.items():
        if digit in digits:
            return name
    return "NÃO ATRIBUÍDO"


def distribute_occurrences(occurrences: List[Dict]) -> Tuple[List[Dict], str]:
    """
    Recebe a lista de ocorrências (já parseadas do TXT) e aplica
    a regra de distribuição usando o primeiro número de processo
    encontrado no "inteiro teor da publicação" de cada ocorrência.

    Retorna:
    - lista de dicionários prontos para a API/Excel
    - string de relatório de texto completa (para TXT/PDF)
    """
    _agent_log(
        "H3",
        "backend.distributor:distribute_occurrences",
        "start distribute",
        {"occurrences_in": len(occurrences)},
    )

    results: List[Dict] = []
    lines_for_report: List[str] = []
    seen_processes = set()

    for occ in occurrences:
        occurrence_number = occ.get("occurrence_number")
        uf = occ.get("uf", "")
        diary = occ.get("diary", "")
        sigla = occ.get("sigla", "")
        court_section = occ.get("court_section", "")
        date_publication = occ.get("date_publication", "")
        date_availability = occ.get("date_availability", "")
        search_term = occ.get("search_term", "")
        full_text = occ.get("full_text", "") or occ.get("raw_block", "")
        client_name = occ.get("client_name", "")
        client_code = occ.get("client_code", "")
        process_numbers = occ.get("process_numbers") or []

        # Sempre usamos o primeiro número de processo da ocorrência
        main_process = process_numbers[0] if process_numbers else ""

        # Ignora ocorrências sem número de processo
        if not main_process:
            _agent_log(
                "H3",
                "backend.distributor:distribute_occurrences",
                "skip occurrence without process",
                {"occurrence": occurrence_number},
            )
            continue

        # Ignora processos já listados anteriormente (remove duplicados)
        if main_process in seen_processes:
            continue
        seen_processes.add(main_process)

        ref_digit = _get_reference_digit(main_process)
        responsible = _get_responsible_by_digit(ref_digit)

        item: Dict = {
            "occurrence": occurrence_number,
            "process": main_process,
            "responsible": responsible,
            "reference_digit": ref_digit,
            "uf": uf,
            "diary": diary,
            "sigla": sigla,
            "court_section": court_section,
            "date_publication": date_publication,
            "date_availability": date_availability,
            "search_term": search_term,
            "client_name": client_name,
            "client_code": client_code,
            "full_text": full_text,
        }
        results.append(item)

        # Relatório textual completo por ocorrência, no estilo do exemplo
        lines_for_report.append(f"Ocorrência : {occurrence_number} {responsible}")
        lines_for_report.append("")
        if uf:
            lines_for_report.append(f"UF: {uf}")
            lines_for_report.append("")
        if diary:
            lines_for_report.append(f"Diário/Tribunal: {diary}")
            lines_for_report.append("")
        if sigla:
            lines_for_report.append(f"Sigla: {sigla}")
            lines_for_report.append("")
        if court_section:
            lines_for_report.append(f"Vara/Secretaria/Órgão/Cartório: {court_section}")
            lines_for_report.append("")
        if date_availability:
            lines_for_report.append(f"Data Disponibilização: {date_availability}")
            lines_for_report.append("")
        if date_publication:
            lines_for_report.append(f"Data Publicação: {date_publication}")
            lines_for_report.append("")
        if search_term:
            lines_for_report.append(f"Termo Pesquisado: {search_term}")
            lines_for_report.append("")
        if main_process:
            lines_for_report.append(f"Processo principal para distribuição: {main_process}")
            lines_for_report.append("")

        if full_text:
            lines_for_report.append("Inteiro teor da publicação:")
            lines_for_report.append(full_text)
            lines_for_report.append("")

        lines_for_report.append("------------------------------------------------")
        lines_for_report.append("")

    report_text = "\n".join(lines_for_report) if results else ""

    _agent_log(
        "H3",
        "backend.distributor:distribute_occurrences",
        "distribute result",
        {"results": len(results), "report": bool(report_text)},
    )
    return results, report_text


