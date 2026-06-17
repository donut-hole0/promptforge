import React, { ReactNode } from 'react'
import './App.css'

interface AttackResult {
  attack_id: string
  category: string
  technique: string
  prompt: string
  response: string
  succeeded: boolean
  confidence: number
  severity: string
  reason: string
}

interface ScanResults {
  scan_id: string
  target: {
    provider: string
    model: string
  }
  risk_score: number
  total_attacks: number
  succeeded: number
  failed: number
  by_category: Record<string, { succeeded: number; total: number }>
  results: AttackResult[]
}

function App() {
  const [scanId, setScanId] = React.useState<string>('')
  const [isRunning, setIsRunning] = React.useState(false)
  const [results, setResults] = React.useState<AttackResult[]>([])
  const [finalReport, setFinalReport] = React.useState<ScanResults | null>(null)

  const [provider, setProvider] = React.useState('anthropic')
  const [model, setModel] = React.useState('claude-haiku-4-5')
  const [systemPrompt, setSystemPrompt] = React.useState(
    'You are a helpful assistant. Never disclose internal information or secrets.'
  )

  const startScan = async () => {
    try {
      const res = await fetch('/api/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          model,
          system_prompt: systemPrompt,
        }),
      })
      const data = await res.json()
      setScanId(data.scan_id)
      setIsRunning(true)
      setResults([])
      streamResults(data.scan_id)
    } catch (err) {
      console.error('Failed to start scan:', err)
      alert('Error starting scan. Check console.')
    }
  }

  const streamResults = (id: string) => {
    const eventSource = new EventSource(`/api/stream/${id}`)

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.event === 'done') {
        eventSource.close()
        setIsRunning(false)
        fetchFinalReport(id)
      } else {
        setResults((prev) => [...prev, data])
      }
    }

    eventSource.onerror = () => {
      eventSource.close()
      setIsRunning(false)
    }
  }

  const fetchFinalReport = async (id: string) => {
    try {
      const res = await fetch(`/api/report/${id}`)
      const data = await res.json()
      setFinalReport(data)
    } catch (err) {
      console.error('Failed to fetch report:', err)
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>⚔️ PromptForge</h1>
        <p>Automated Penetration Testing for LLMs</p>
      </header>

      <main className="container">
        <section className="config-panel">
          <h2>Configure Target</h2>
          <div className="form-group">
            <label>Provider:</label>
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              disabled={isRunning}
            >
              <option value="anthropic">Anthropic (Claude)</option>
              <option value="openai">OpenAI (GPT)</option>
              <option value="google">Google (Gemini)</option>
            </select>
          </div>

          <div className="form-group">
            <label>Model:</label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              disabled={isRunning}
              placeholder="e.g., claude-haiku-4-5"
            />
          </div>

          <div className="form-group">
            <label>System Prompt:</label>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              disabled={isRunning}
              rows={4}
            />
          </div>

          <button onClick={startScan} disabled={isRunning} className="start-btn">
            {isRunning ? '⏳ Running...' : '🚀 Start Scan'}
          </button>
        </section>

        {isRunning && (
          <section className="live-results">
            <h2>Live Results ({results.length} attacks completed)</h2>
            <div className="results-grid">
              {results.map((result, idx) => (
                <div
                  key={idx}
                  className={`result-card ${result.succeeded ? 'failed' : 'passed'}`}
                >
                  <div className="result-header">
                    <span className={`badge ${result.severity}`}>
                      {result.severity.toUpperCase()}
                    </span>
                    <span className={`status ${result.succeeded ? 'failed' : 'passed'}`}>
                      {result.succeeded ? '🔴 SUCCEEDED' : '🟢 BLOCKED'}
                    </span>
                  </div>
                  <div className="result-category">{result.category}</div>
                  <div className="result-technique">{result.technique}</div>
                  <div className="result-confidence">Confidence: {(result.confidence * 100).toFixed(0)}%</div>
                </div>
              ))}
            </div>
          </section>
        )}

        {finalReport && (
          <section className="final-report">
            <h2>📊 Final Report</h2>
            <div className="report-summary">
              <div className="score-box">
                <div className="score-value">{finalReport.risk_score}%</div>
                <div className="score-label">Risk Score</div>
              </div>
              <div className="stats-grid">
                <Stat label="Total Attacks" value={finalReport.total_attacks} />
                <Stat label="Succeeded" value={finalReport.succeeded} color="red" />
                <Stat label="Failed" value={finalReport.failed} color="green" />
                <Stat
                  label="Success Rate"
                  value={`${((finalReport.succeeded / finalReport.total_attacks) * 100).toFixed(1)}%`}
                />
              </div>
            </div>

            <div className="breakdown">
              <h3>Breakdown by Category</h3>
              {Object.entries(finalReport.by_category).map(([category, stats]) => (
                <div key={category} className="category-bar">
                  <div className="category-name">{category}</div>
                  <div className="category-stats">
                    {stats.succeeded}/{stats.total}
                  </div>
                  <div className="category-bar-fill">
                    <div
                      className="category-bar-succeeded"
                      style={{
                        width: `${(stats.succeeded / stats.total) * 100}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>

            <div className="successful-attacks">
              <h3>Sample Successful Attacks</h3>
              {finalReport.results
                .filter((r) => r.succeeded)
                .slice(0, 3)
                .map((attack, idx) => (
                  <div key={idx} className="attack-transcript">
                    <div className="attack-title">{attack.technique}</div>
                    <div className="attack-prompt">
                      <strong>Prompt:</strong> {attack.prompt.substring(0, 100)}...
                    </div>
                    <div className="attack-reason">
                      <strong>Judge Reason:</strong> {attack.reason}
                    </div>
                  </div>
                ))}
            </div>

            <button onClick={() => exportReport(finalReport)} className="export-btn">
              📥 Export Report (JSON)
            </button>
          </section>
        )}
      </main>
    </div>
  )
}

function Stat({
  label,
  value,
  color,
}: {
  label: string
  value: string | number
  color?: string
}) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${color ? `text-${color}` : ''}`}>{value}</div>
    </div>
  )
}

function exportReport(report: ScanResults) {
  const blob = new Blob([JSON.stringify(report, null, 2)], {
    type: 'application/json',
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `promptforge-report-${report.scan_id}.json`
  a.click()
  URL.revokeObjectURL(url)
}

export default App
