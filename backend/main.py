from io import BytesIO
from pathlib import Path
from typing import List, Optional
import json
import time

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .parser import extract_process_numbers, parse_occurrences
from .distributor import distribute_occurrences


class ProcessItem(BaseModel):
    occurrence: int
    process: str
    responsible: str
    reference_digit: str

    # Metadados da ocorrência
    client_name: Optional[str] = ""
    client_code: Optional[str] = ""
    uf: Optional[str] = ""
    diary: Optional[str] = ""
    sigla: Optional[str] = ""
    court_section: Optional[str] = ""
    date_publication: Optional[str] = ""
    date_availability: Optional[str] = ""
    search_term: Optional[str] = ""
    full_text: Optional[str] = ""


class ProcessResult(BaseModel):
    total: int
    items: List[ProcessItem]
    message: Optional[str] = None


app = FastAPI(title="Distribuidor de Processos TJMG")

# Permitir acesso do frontend (mesma origem ou arquivo local)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Armazenamento simples em memória do último processamento
LAST_ITEMS: List[dict] = []
LAST_REPORT_TEXT: str = ""


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
        # evita quebrar fluxo principal
        pass


# #endregion


@app.post("/upload", response_model=ProcessResult)
async def upload_file(file: UploadFile = File(...)):
    """
    Recebe o arquivo TXT, extrai os processos, distribui e
    retorna o resultado já estruturado.
    """
    if not file.filename.lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="Envie um arquivo .txt")

    content_bytes = await file.read()
    _agent_log(
        "H1",
        "backend.main:upload_file",
        "upload received",
        {"filename": file.filename, "size": len(content_bytes)},
    )
    try:
        text = content_bytes.decode("utf-8", errors="ignore")
    except Exception as exc:  # pragma: no cover - proteção extra
        _agent_log(
            "H1",
            "backend.main:upload_file",
            "decode failed",
            {"error": str(exc)},
        )
        raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo: {exc}")

    # Primeiro, tenta parsear por ocorrências estruturadas
    occurrences = parse_occurrences(text)

    if not occurrences:
        # Fallback para o comportamento antigo: apenas números de processo soltos
        process_numbers = extract_process_numbers(text)
        if not process_numbers:
            global LAST_ITEMS, LAST_REPORT_TEXT
            LAST_ITEMS = []
            LAST_REPORT_TEXT = ""
            return ProcessResult(
                total=0, items=[], message="Nenhum processo encontrado no arquivo."
            )

        # Constrói ocorrências mínimas a partir dos processos encontrados
        occurrences = [
            {
                "occurrence_number": idx,
                "process_numbers": [proc],
                "uf": "",
                "diary": "",
                "sigla": "",
                "court_section": "",
                "date_publication": "",
                "date_availability": "",
                "search_term": "",
                "full_text": "",
            }
            for idx, proc in enumerate(process_numbers, start=1)
        ]

    items, report_text = distribute_occurrences(occurrences)
    _agent_log(
        "H1",
        "backend.main:upload_file",
        "distribute result",
        {"total_items": len(items), "has_report": bool(report_text)},
    )

    # Atualiza cache em memória
    LAST_ITEMS = items
    LAST_REPORT_TEXT = report_text

    return ProcessResult(total=len(items), items=[ProcessItem(**i) for i in items])


@app.get("/results", response_model=ProcessResult)
async def get_results():
    """
    Retorna o último resultado processado na sessão.
    """
    if not LAST_ITEMS:
        return ProcessResult(total=0, items=[], message="Nenhum processamento realizado ainda.")

    return ProcessResult(
        total=len(LAST_ITEMS),
        items=[ProcessItem(**i) for i in LAST_ITEMS],
    )


@app.get("/export/txt")
async def export_txt():
    """
    Exporta o relatório em TXT.
    """
    if not LAST_ITEMS or not LAST_REPORT_TEXT:
        raise HTTPException(status_code=400, detail="Não há dados processados para exportar.")

    buffer = BytesIO()
    buffer.write(LAST_REPORT_TEXT.encode("utf-8"))
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="relatorio_processos.txt"'},
    )


@app.get("/export/pdf")
async def export_pdf():
    """
    Exporta o relatório em PDF usando reportlab.
    """
    if not LAST_ITEMS or not LAST_REPORT_TEXT:
        raise HTTPException(status_code=400, detail="Não há dados processados para exportar.")

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Margens simples
    x_margin = 40
    y = height - 40
    line_height = 14

    for line in LAST_REPORT_TEXT.splitlines():
        p.drawString(x_margin, y, line)
        y -= line_height
        if y < 40:
            p.showPage()
            y = height - 40

    p.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="relatorio_processos.pdf"'},
    )

@app.get("/export/excel")
async def export_excel():
    """
    Exporta o relatório em Excel (XLSX) usando pandas + openpyxl.
    """
    if not LAST_ITEMS:
        raise HTTPException(status_code=400, detail="Não há dados processados para exportar.")

    df = pd.DataFrame(
        [
            {
                "Ocorrência": item.get("occurrence"),
                "Processo": item.get("process"),
                "Responsável": item.get("responsible"),
                "Dígito de Referência": item.get("reference_digit"),
                "UF": item.get("uf"),
                "Diário/Tribunal": item.get("diary"),
                "Sigla": item.get("sigla"),
                "Vara/Secretaria/Órgão/Cartório": item.get("court_section"),
                "Data Disponibilização": item.get("date_availability"),
                "Data Publicação": item.get("date_publication"),
                "Termo Pesquisado": item.get("search_term"),
            }
            for item in LAST_ITEMS
        ]
    )

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Processos")
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="relatorio_processos.xlsx"'},
    )


# Servir frontend estático (index.html, CSS e JS)
BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "frontend"

if FRONTEND_DIR.exists():
    app.mount(
        "/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend"
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

