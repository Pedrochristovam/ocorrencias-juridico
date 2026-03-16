import { useState } from 'react'

const apiBase = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')

function triggerDownload(url) {
  const a = document.createElement('a')
  a.href = url
  a.target = '_blank'
  a.rel = 'noopener noreferrer'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

function OccurrenceCard({ item }) {
  const fields = [
    ['Nome do Cliente', item.client_name],
    ['Código Cliente', item.client_code],
    ['UF', item.uf],
    ['Diário/Tribunal', item.diary],
    ['Sigla', item.sigla],
    ['Vara/Secretaria/Órgão/Cartório', item.court_section],
    ['Data Disponibilização', item.date_availability],
    ['Data Publicação', item.date_publication],
    ['Termo Pesquisado', item.search_term],
    ['Processo', item.process],
    ['Dígito de Referência', item.reference_digit],
  ]

  return (
    <div className="occurrence-card">
      <div className="occurrence-card-header">
        {`Ocorrência : ${item.occurrence} ${item.responsible || ''}`.trim()}
      </div>

      {fields.map(([label, value]) => {
        if (value === undefined || value === null || String(value).trim() === '') {
          return null
        }
        return (
          <div key={label} className="occurrence-field">
            <span className="occurrence-field-label">{label}:</span>
            <span className="occurrence-field-value">{String(value).trim()}</span>
          </div>
        )
      })}

      {item.full_text && String(item.full_text).trim() !== '' && (
        <>
          <div className="occurrence-divider" />
          <div className="occurrence-field">
            <span className="occurrence-field-label">Inteiro teor da publicação:</span>
          </div>
          <div className="occurrence-inteiro-teor">{item.full_text.trim()}</div>
        </>
      )}
    </div>
  )
}

function App() {
  const [file, setFile] = useState(null)
  const [fileName, setFileName] = useState('Nenhum arquivo selecionado.')
  const [status, setStatus] = useState(
    'Envie um arquivo TXT do Diário do TJMG para iniciar.',
  )
  const [statusType, setStatusType] = useState('')
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [items, setItems] = useState([])

  const onFileChange = (event) => {
    const selected = event.target.files && event.target.files[0]
    if (selected) {
      setFile(selected)
      setFileName(`Arquivo selecionado: ${selected.name}`)
    } else {
      setFile(null)
      setFileName('Nenhum arquivo selecionado.')
    }
  }

  const handleSubmit = async (event) => {
    event.preventDefault()

    if (!file) {
      setStatus('Selecione um arquivo TXT antes de processar.')
      setStatusType('error')
      return
    }

    if (!file.name.toLowerCase().endsWith('.txt')) {
      setStatus('O arquivo deve ter extensão .txt.')
      setStatusType('error')
      return
    }

    const formData = new FormData()
    formData.append('file', file)

    setStatus('')
    setStatusType('')
    setLoading(true)

    // #region agent log (debug instrumentation)
    fetch('http://127.0.0.1:7242/ingest/34dede9a-a95b-4547-b72c-bc7b0c65a150', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: `log_${Date.now()}`,
        timestamp: Date.now(),
        runId: 'run1',
        hypothesisId: 'H1',
        location: 'App.jsx:handleSubmit',
        message: 'upload start',
        data: { filename: file.name, size: file.size },
      }),
    }).catch(() => {})
    // #endregion

    try {
      const uploadUrl = apiBase ? `${apiBase}/upload` : '/upload'
      const response = await fetch(uploadUrl, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        const detail = errorData.detail || 'Erro ao processar o arquivo.'

        // #region agent log (debug instrumentation)
        fetch('http://127.0.0.1:7242/ingest/34dede9a-a95b-4547-b72c-bc7b0c65a150', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: `log_${Date.now()}`,
            timestamp: Date.now(),
            runId: 'run1',
            hypothesisId: 'H1',
            location: 'App.jsx:handleSubmit',
            message: 'upload failed',
            data: { status: response.status, detail },
          }),
        }).catch(() => {})
        // #endregion

        throw new Error(detail)
      }

      const data = await response.json()

      // #region agent log (debug instrumentation)
      fetch('http://127.0.0.1:7242/ingest/34dede9a-a95b-4547-b72c-bc7b0c65a150', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: `log_${Date.now()}`,
          timestamp: Date.now(),
          runId: 'run1',
          hypothesisId: 'H1',
          location: 'App.jsx:handleSubmit',
          message: 'upload success',
          data: { status: response.status, total: data.total },
        }),
      }).catch(() => {})
      // #endregion
      setTotal(data.total ?? 0)
      setItems(data.items || [])

      if (data.message) {
        setStatus(data.message)
        setStatusType(data.total > 0 ? 'success' : 'error')
      } else {
        setStatus('Processamento concluído com sucesso.')
        setStatusType('success')
      }
    } catch (error) {
      console.error(error)
      setStatus(error.message || 'Erro inesperado ao processar o arquivo.')
      setStatusType('error')
      setTotal(0)
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  const hasResults = items && items.length > 0

  return (
    <div className="app-container">
      <header>
        <h1>Distribuidor de Processos TJMG</h1>
        <p className="subtitle">
          Faça upload do arquivo TXT do Diário do TJMG e veja automaticamente a
          distribuição dos processos por responsável.
        </p>
      </header>

      <main>
        <section className="upload-section">
          <form id="upload-form" onSubmit={handleSubmit}>
            <label htmlFor="file-input" className="file-label">
              <span>Selecionar arquivo TXT</span>
              <input
                type="file"
                id="file-input"
                accept=".txt"
                onChange={onFileChange}
              />
            </label>
            <button type="submit" id="upload-button" disabled={loading}>
              {loading ? 'Processando...' : 'Processar arquivo'}
            </button>
          </form>
          <p id="file-name" className="file-name">
            {fileName}
          </p>
          <p
            id="status-message"
            className={`status-message ${statusType ? statusType : ''}`}
          >
            {status}
          </p>
          <div
            id="loading-indicator"
            className={`loading ${loading ? '' : 'hidden'}`}
          >
            Processando, aguarde...
          </div>
        </section>

        <section className="summary-section">
          <div className="summary-card">
            <span className="summary-label">Total de processos:</span>
            <span id="total-count" className="summary-value">
              {total}
            </span>
          </div>
        </section>

        <section className="results-section">
          <h2>Resultados detalhados</h2>
          <div id="results-container" className="results-container">
            {!hasResults && (
              <p id="results-empty" className="results-empty">
                Nenhum processo processado ainda.
              </p>
            )}
            {hasResults && (
              <div id="results-list" className="results-list">
                {items.map((item) => (
                  <OccurrenceCard
                    key={`${item.occurrence}-${item.process}`}
                    item={item}
                  />
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="export-section">
          <h2>Exportar Relatório</h2>
          <div className="export-buttons">
            <button
              id="export-txt"
              type="button"
              onClick={() =>
                triggerDownload(apiBase ? `${apiBase}/export/txt` : '/export/txt')
              }
              disabled={!hasResults}
            >
              Exportar TXT
            </button>
            <button
              id="export-excel"
              type="button"
              onClick={() =>
                triggerDownload(apiBase ? `${apiBase}/export/excel` : '/export/excel')
              }
              disabled={!hasResults}
            >
              Exportar Excel
            </button>
          </div>
          <p className="export-hint">
            Os botões de exportação só funcionam após o processamento de um arquivo.
          </p>
        </section>
      </main>

      <footer>
        <span>Sistema de distribuição automática de processos - Exemplo didático</span>
      </footer>
    </div>
  )
}

export default App
