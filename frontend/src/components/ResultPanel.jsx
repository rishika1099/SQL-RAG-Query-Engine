import { useState } from 'react'
import { ThumbsUp, ThumbsDown, ChevronDown, ChevronRight } from 'lucide-react'
import ChartView from './ChartView'
import DataTable from './DataTable'
import { Chip } from './QueryPanel'

const VERDICT_CONFIG = {
  correct:   { color: 'var(--success)', icon: '✓', tagClass: 'ok' },
  partial:   { color: 'var(--accent3)', icon: '⚠', tagClass: 'warn' },
  incorrect: { color: 'var(--danger)',  icon: '✗', tagClass: 'err' },
  empty:     { color: 'var(--accent3)', icon: '○', tagClass: 'warn' },
  unknown:   { color: 'var(--dim)',     icon: '?', tagClass: '' },
}

export default function ResultPanel({ result, loading, loadingStep, loadingSteps, onFeedback, onFollowup }) {
  const [sqlOpen, setSqlOpen] = useState(true)
  const [feedback, setFeedback] = useState(null)

  const handleFeedback = (rating) => {
    setFeedback(rating)
    onFeedback(rating)
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: '16px' }}>
        <div style={{ width: '32px', height: '32px', border: '2px solid var(--border)', borderTopColor: 'var(--accent)', borderRadius: '50%', animation: 'spin .7s linear infinite' }} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {loadingSteps.map((step, i) => (
            <div key={i} style={{
              fontFamily: 'IBM Plex Mono, monospace', fontSize: '11px',
              color: i < loadingStep ? 'var(--success)' : i === loadingStep ? 'var(--accent2)' : 'var(--dim)',
              opacity: i > loadingStep ? 0.4 : 1,
              transition: 'all .3s',
            }}>
              {i < loadingStep ? '✓ ' : i === loadingStep ? '→ ' : '  '}{step}
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (!result) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: '12px', color: 'var(--dim)', textAlign: 'center' }}>
        <div style={{ fontSize: '48px', opacity: 0.2 }}>📊</div>
        <h2 style={{ fontFamily: 'Syne, sans-serif', fontSize: '1.4rem', color: 'var(--muted)', fontWeight: 600 }}>Ask a question</h2>
        <p style={{ fontSize: '13px', maxWidth: '340px', color: 'var(--dim)' }}>
          Type or speak a natural language question. Apollo retrieves the relevant KPIs, generates SQL, and visualizes the results.
        </p>
      </div>
    )
  }

  const v = result.verification || {}
  const vc = VERDICT_CONFIG[v.verdict] || VERDICT_CONFIG.unknown

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>

      {/* Header */}
      <div style={{ padding: '1rem 1.5rem 0.75rem', borderBottom: '1px solid var(--border)', flexShrink: 0, background: 'var(--bg2)' }}>
        <div style={{ fontFamily: 'Syne, sans-serif', fontSize: '15px', fontWeight: 600, color: '#fff', marginBottom: '8px' }}>
          {result.question}
        </div>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '8px' }}>
          <Tag color={result.error ? 'var(--danger)' : 'var(--success)'}>{result.error ? 'ERROR' : 'SUCCESS'}</Tag>
          {!result.error && <Tag>{result.row_count} row{result.row_count !== 1 ? 's' : ''}</Tag>}
          {v.verdict && <Tag color={vc.color}>{vc.icon} {v.verdict}</Tag>}
          <Tag>claude-sonnet-4-6</Tag>
        </div>

        {/* Feedback */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '11px', color: 'var(--dim)' }}>Was this helpful?</span>
          <FeedbackBtn active={feedback === 1} onClick={() => handleFeedback(1)} variant="up"><ThumbsUp size={12} /></FeedbackBtn>
          <FeedbackBtn active={feedback === -1} onClick={() => handleFeedback(-1)} variant="down"><ThumbsDown size={12} /></FeedbackBtn>
        </div>
      </div>

      {/* KPI badges */}
      {result.kpis_retrieved?.length > 0 && (
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', padding: '0.5rem 1.5rem', borderBottom: '1px solid var(--border)', background: 'var(--bg2)', flexShrink: 0 }}>
          {result.kpis_retrieved.map(k => (
            <div key={k.kpi_id} style={{
              fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px',
              background: 'rgba(183,148,244,.1)', border: '1px solid rgba(183,148,244,.2)',
              borderRadius: '4px', padding: '2px 8px', color: 'var(--purple)',
              display: 'flex', alignItems: 'center', gap: '4px',
            }}>
              ◈ {k.display_name}
              <span style={{ color: 'var(--dim)', fontSize: '9px' }}>{Math.round(k.similarity * 100)}%</span>
            </div>
          ))}
        </div>
      )}

      {/* SQL block */}
      {result.sql && (
        <div style={{ padding: '0.75rem 1.5rem', borderBottom: '1px solid var(--border)', flexShrink: 0, background: 'var(--bg2)' }}>
          <div
            onClick={() => setSqlOpen(o => !o)}
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', marginBottom: sqlOpen ? '8px' : 0 }}
          >
            <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px', color: 'var(--dim)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Generated SQL</span>
            {sqlOpen ? <ChevronDown size={12} color="var(--accent)" /> : <ChevronRight size={12} color="var(--accent)" />}
          </div>
          {sqlOpen && (
            <pre style={{
              background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: '8px',
              padding: '10px 14px', fontFamily: 'IBM Plex Mono, monospace', fontSize: '12px',
              lineHeight: 1.6, color: '#a8b2c8', overflowX: 'auto', whiteSpace: 'pre',
              maxHeight: '120px', overflowY: 'auto',
            }}>
              {result.sql}
            </pre>
          )}
        </div>
      )}

      {/* Verification warning */}
      {v.verdict && v.verdict !== 'correct' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '0.5rem 1.5rem', borderBottom: '1px solid var(--border)', background: 'var(--bg2)', flexShrink: 0 }}>
          <span style={{ color: vc.color, fontSize: '13px' }}>{vc.icon}</span>
          <span style={{ fontSize: '12px', color: 'var(--muted)' }}>{v.explanation}</span>
          {v.issues?.[0] && <span style={{ fontSize: '11px', color: 'var(--accent3)' }}>· {v.issues[0]}</span>}
        </div>
      )}

      {/* Body */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '1rem 1.5rem' }}>

        {/* Clarification */}
        {result.needs_clarification && (
          <div style={{ background: 'rgba(99,179,237,.06)', border: '1px solid rgba(99,179,237,.2)', borderRadius: '12px', padding: '1.25rem', marginBottom: '1rem' }}>
            <div style={{ fontSize: '14px', color: 'var(--text)', marginBottom: '0.75rem' }}>{result.clarifying_question}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {result.clarifying_options?.map((opt, i) => (
                <button key={i} onClick={() => onFollowup(opt)} style={{
                  background: 'var(--bg3)', border: '1px solid var(--border)', borderRadius: '8px',
                  padding: '8px 12px', cursor: 'pointer', fontSize: '13px', color: 'var(--muted)',
                  textAlign: 'left', fontFamily: 'Inter, sans-serif', transition: 'all .15s',
                }}
                  onMouseEnter={e => { e.target.style.borderColor = 'var(--border-hi)'; e.target.style.color = 'var(--accent)' }}
                  onMouseLeave={e => { e.target.style.borderColor = 'var(--border)'; e.target.style.color = 'var(--muted)' }}
                >
                  {opt}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Error */}
        {result.error && (
          <div style={{ background: 'rgba(252,129,129,.06)', border: '1px solid rgba(252,129,129,.2)', borderRadius: '12px', padding: '1rem 1.25rem', color: 'var(--danger)', fontSize: '13px', marginBottom: '1rem' }}>
            {result.error}
          </div>
        )}

        {/* Chart */}
        {!result.error && <ChartView chart={result.chart} columns={result.columns} rows={result.rows} />}

        {/* Table */}
        {!result.error && <DataTable columns={result.columns} rows={result.rows} />}

        {/* Follow-ups */}
        {result.followups?.length > 0 && (
          <div style={{ marginTop: '0.5rem' }}>
            <div style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px', letterSpacing: '0.08em', color: 'var(--dim)', textTransform: 'uppercase', marginBottom: '8px' }}>
              Suggested follow-ups
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {result.followups.map((f, i) => (
                <Chip key={i} onClick={() => onFollowup(f)} variant="followup">{f}</Chip>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function Tag({ children, color }) {
  return (
    <span style={{
      fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px',
      background: 'var(--bg3)', border: `1px solid ${color ? color + '44' : 'var(--border)'}`,
      borderRadius: '4px', padding: '2px 7px',
      color: color || 'var(--muted)',
    }}>
      {children}
    </span>
  )
}

function FeedbackBtn({ children, active, onClick, variant }) {
  const color = variant === 'up' ? 'var(--success)' : 'var(--danger)'
  return (
    <button onClick={onClick} style={{
      background: active ? `${color}22` : 'var(--bg3)',
      border: `1px solid ${active ? color + '66' : 'var(--border)'}`,
      borderRadius: '6px', padding: '4px 10px', cursor: 'pointer',
      color: active ? color : 'var(--muted)', display: 'flex', alignItems: 'center',
      transition: 'all .15s',
    }}>
      {children}
    </button>
  )
}
