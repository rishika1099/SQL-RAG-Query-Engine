import { BarChart, Bar, LineChart, Line, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'

const PALETTE = ['#63b3ed','#76e4c4','#f6ad55','#b794f4','#fc8181','#68d391','#f687b3','#90cdf4']

export default function ChartView({ chart, columns, rows }) {
  if (!chart || !chart.chart_type || !rows || rows.length < 2) return null

  const { chart_type, x_key, y_key, title, reasoning } = chart
  const xIdx = columns.indexOf(x_key)
  const yIdx = columns.indexOf(y_key)
  if (xIdx === -1 || yIdx === -1) return null

  const data = rows.map(row => ({
    x: row[xIdx],
    y: parseFloat(row[yIdx]) || 0,
  }))

  const axisStyle = { fill: '#8892a4', fontSize: 11, fontFamily: 'IBM Plex Mono, monospace' }
  const gridStyle = { stroke: 'rgba(255,255,255,0.04)' }
  const tooltipStyle = {
    backgroundColor: '#1d2230', border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: '8px', fontSize: '12px', fontFamily: 'Inter, sans-serif',
    color: '#e8ecf4',
  }

  return (
    <div style={{
      background: 'var(--bg2)', border: '1px solid var(--border)',
      borderRadius: '12px', padding: '1.25rem', marginBottom: '1rem',
    }}>
      <div style={{ marginBottom: '4px', fontFamily: 'Syne, sans-serif', fontSize: '13px', fontWeight: 600, color: 'var(--text)' }}>
        {title}
      </div>
      <div style={{ fontSize: '11px', color: 'var(--dim)', fontStyle: 'italic', marginBottom: '1rem' }}>
        {reasoning}
      </div>

      <ResponsiveContainer width="100%" height={240}>
        {chart_type === 'line' ? (
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" {...gridStyle} />
            <XAxis dataKey="x" tick={axisStyle} />
            <YAxis tick={axisStyle} />
            <Tooltip contentStyle={tooltipStyle} />
            <Line type="monotone" dataKey="y" stroke="#63b3ed" strokeWidth={2} dot={{ r: 4, fill: '#63b3ed' }} name={y_key} />
          </LineChart>
        ) : chart_type === 'scatter' ? (
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" {...gridStyle} />
            <XAxis dataKey="x" name={x_key} tick={axisStyle} />
            <YAxis dataKey="y" name={y_key} tick={axisStyle} />
            <Tooltip contentStyle={tooltipStyle} cursor={{ strokeDasharray: '3 3' }} />
            <Scatter data={data} fill="#63b3ed" />
          </ScatterChart>
        ) : (
          <BarChart data={data} layout={data.length > 6 ? 'vertical' : 'horizontal'}>
            <CartesianGrid strokeDasharray="3 3" {...gridStyle} />
            {data.length > 6 ? (
              <>
                <XAxis type="number" tick={axisStyle} />
                <YAxis type="category" dataKey="x" tick={axisStyle} width={100} />
              </>
            ) : (
              <>
                <XAxis dataKey="x" tick={axisStyle} />
                <YAxis tick={axisStyle} />
              </>
            )}
            <Tooltip contentStyle={tooltipStyle} />
            <Bar dataKey="y" name={y_key} radius={[4, 4, 0, 0]}>
              {data.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
            </Bar>
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}
