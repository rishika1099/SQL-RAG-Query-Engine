import { useState, useCallback } from 'react'
import axios from 'axios'
import QueryPanel from './components/QueryPanel'

// Auto-detects local vs deployed environment
const API = import.meta.env.VITE_API_URL || ''
import ResultPanel from './components/ResultPanel'

const SUGGESTED_QUERIES = [
  'Who had the highest workload?',
  'Avg sprint distance by position',
  'Show fatigue scores for all athletes',
  'Match vs training distance comparison',
  'Which athletes have low sleep scores?',
  'Total high intensity efforts per athlete',
  'Top 5 athletes by sprint distance',
  'Who is trending above baseline?',
]

const LOADING_STEPS = [
  'Classifying intent...',
  'Retrieving relevant KPIs...',
  'Generating SQL with Claude...',
  'Validating & executing query...',
  'Verifying result & building chart...',
]

export default function App() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingStep, setLoadingStep] = useState(0)
  const [history, setHistory] = useState([])
  const [question, setQuestion] = useState('')

  const submitQuery = useCallback(async (q) => {
    const query = q || question
    if (!query.trim()) return

    setLoading(true)
    setResult(null)
    setLoadingStep(0)

    // Animate loading steps
    const interval = setInterval(() => {
      setLoadingStep(prev => Math.min(prev + 1, LOADING_STEPS.length - 1))
    }, 700)

    try {
      const { data } = await axios.post(`${API}/query`, { question: query })
      setResult(data)
      setHistory(prev => [{ question: query, rowCount: data.row_count, hasError: !!data.error }, ...prev.slice(0, 19)])
    } catch (err) {
      setResult({
        question: query, sql: '', columns: [], rows: [], row_count: 0,
        error: `Network error: ${err.message}. Is the backend running on port 8000?`
      })
      setHistory(prev => [{ question: query, rowCount: 0, hasError: true }, ...prev.slice(0, 19)])
    } finally {
      clearInterval(interval)
      setLoading(false)
    }
  }, [question])

  const sendFeedback = useCallback(async (rating) => {
    if (!result) return
    try {
      await axios.post(`${API}/feedback`, {
        question: result.question,
        sql: result.sql,
        verdict: result.verification?.verdict || 'unknown',
        rating
      })
    } catch (e) {
      console.warn('Feedback failed', e)
    }
  }, [result])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Topbar */}
      <header style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 1.5rem', height: '52px',
        borderBottom: '1px solid var(--border)', background: 'var(--bg2)',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: '8px', height: '8px', borderRadius: '50%',
            background: 'var(--accent2)',
            animation: 'pulse 2s ease-in-out infinite',
          }} />
          <span style={{ fontFamily: 'Syne, sans-serif', fontSize: '17px', fontWeight: 700, color: '#fff', letterSpacing: '-0.01em' }}>
            Apollo AI Coach
          </span>
        </div>
        <div style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '11px', color: 'var(--dim)', display: 'flex', gap: '1.5rem' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent2)', display: 'inline-block' }} />
            Connected
          </span>
          <span>SQLite · Claude Sonnet · RAG</span>
        </div>
      </header>

      {/* Main split */}
      <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', flex: 1, overflow: 'hidden' }}>
        <QueryPanel
          question={question}
          setQuestion={setQuestion}
          onSubmit={submitQuery}
          loading={loading}
          history={history}
          suggestedQueries={SUGGESTED_QUERIES}
        />
        <ResultPanel
          result={result}
          loading={loading}
          loadingStep={loadingStep}
          loadingSteps={LOADING_STEPS}
          onFeedback={sendFeedback}
          onFollowup={submitQuery}
        />
      </div>

      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
        @keyframes spin { to{transform:rotate(360deg)} }
      `}</style>
    </div>
  )
}