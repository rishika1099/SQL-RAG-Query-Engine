export default function DataTable({ columns, rows }) {
  if (!columns || columns.length === 0) return null

  const exportCSV = () => {
    const all = [columns, ...rows]
    const csv = all.map(r => r.map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'apollo_results.csv'
    a.click()
  }

  return (
    <div style={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: '12px', overflow: 'hidden', marginBottom: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderBottom: '1px solid var(--border)', background: 'var(--bg3)' }}>
        <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px', color: 'var(--dim)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
          Results
        </span>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button
            onClick={exportCSV}
            style={{
              fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px', color: 'var(--muted)',
              background: 'var(--bg3)', border: '1px solid var(--border)', borderRadius: '4px',
              padding: '2px 8px', cursor: 'pointer',
            }}
            onMouseEnter={e => { e.target.style.color = 'var(--accent)'; e.target.style.borderColor = 'var(--border-hi)' }}
            onMouseLeave={e => { e.target.style.color = 'var(--muted)'; e.target.style.borderColor = 'var(--border)' }}
          >
            ↓ CSV
          </button>
          <span style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px', color: 'var(--accent)', background: 'rgba(99,179,237,.1)', padding: '2px 8px', borderRadius: '4px' }}>
            {rows.length} rows
          </span>
        </div>
      </div>
      <div style={{ overflowX: 'auto', maxHeight: '280px', overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              {columns.map((col, i) => (
                <th key={i} style={{
                  textAlign: 'left', padding: '8px 14px',
                  fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px',
                  color: 'var(--muted)', fontWeight: 500, letterSpacing: '0.05em',
                  textTransform: 'uppercase', whiteSpace: 'nowrap',
                  background: 'var(--bg3)', position: 'sticky', top: 0,
                }}>
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                {row.map((val, j) => (
                  <td key={j} style={{
                    padding: '8px 14px', whiteSpace: 'nowrap',
                    color: j === 0 ? 'var(--text)' : 'var(--muted)',
                  }}>
                    {String(val ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
