import { useRef, useState, useEffect } from 'react'
import { Send, Mic } from 'lucide-react'

export default function QueryPanel({ question, setQuestion, onSubmit, loading, history, suggestedQueries }) {
  const [isRecording, setIsRecording] = useState(false)
  const [audioLevel, setAudioLevel] = useState([1, 1, 1, 1, 1])
  const recognitionRef = useRef(null)
  const animFrameRef = useRef(null)
  const analyserRef = useRef(null)
  const audioCtxRef = useRef(null)

  // Animate sound bars using actual microphone audio levels when recording
  useEffect(() => {
    if (!isRecording) {
      setAudioLevel([1, 1, 1, 1, 1])
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
      return
    }

    const animate = () => {
      if (analyserRef.current) {
        const data = new Uint8Array(analyserRef.current.frequencyBinCount)
        analyserRef.current.getByteFrequencyData(data)
        const slice = Math.floor(data.length / 5)
        const levels = [0,1,2,3,4].map(i => {
          const val = data[i * slice] / 255
          return Math.max(0.15, val)
        })
        setAudioLevel(levels)
      } else {
        // Fallback animation if no mic access
        setAudioLevel(prev => prev.map(() => 0.15 + Math.random() * 0.85))
      }
      animFrameRef.current = requestAnimationFrame(animate)
    }
    animFrameRef.current = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(animFrameRef.current)
  }, [isRecording])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit()
    }
  }

  const toggleVoice = async () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) { alert('Voice input requires Chrome.'); return }

    if (isRecording) {
      recognitionRef.current?.stop()
      if (audioCtxRef.current) { audioCtxRef.current.close(); audioCtxRef.current = null }
      setIsRecording(false)
      return
    }

    // Try to get real audio levels via Web Audio API
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const ctx = new (window.AudioContext || window.webkitAudioContext)()
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 256
      ctx.createMediaStreamSource(stream).connect(analyser)
      analyserRef.current = analyser
      audioCtxRef.current = ctx
    } catch {
      analyserRef.current = null
    }

    const r = new SR()
    r.lang = 'en-US'
    r.interimResults = false
    r.onresult = (e) => {
      setQuestion(e.results[0][0].transcript)
    }
    r.onend = () => {
      if (audioCtxRef.current) { audioCtxRef.current.close(); audioCtxRef.current = null }
      setIsRecording(false)
    }
    r.onerror = () => {
      if (audioCtxRef.current) { audioCtxRef.current.close(); audioCtxRef.current = null }
      setIsRecording(false)
    }
    r.start()
    recognitionRef.current = r
    setIsRecording(true)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--border)', background: 'var(--bg2)', overflow: 'hidden' }}>

      {/* Header */}
      <div style={{ padding: '1.25rem 1.5rem 0.75rem', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: '4px' }}>
          Natural Language Query
        </div>
        <div style={{ fontSize: '12px', color: 'var(--muted)' }}>Ask anything about athlete performance</div>
      </div>

      {/* Input */}
      <div style={{ padding: '1rem 1.5rem', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
          <textarea
            value={question}
            onChange={e => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isRecording ? '🎙 Listening...' : 'e.g. Who had the highest sprint distance?'}
            rows={3}
            style={{
              flex: 1,
              background: isRecording ? 'rgba(252,129,129,0.06)' : 'var(--bg3)',
              border: `1px solid ${isRecording ? 'rgba(252,129,129,0.5)' : 'var(--border)'}`,
              borderRadius: '10px', color: 'var(--text)', fontFamily: 'Inter, sans-serif',
              fontSize: '13px', padding: '10px 12px', resize: 'none',
              minHeight: '72px', maxHeight: '140px', lineHeight: 1.5,
              outline: 'none', transition: 'all 0.2s',
            }}
            onFocus={e => { if (!isRecording) e.target.style.borderColor = 'var(--border-hi)' }}
            onBlur={e => { if (!isRecording) e.target.style.borderColor = 'var(--border)' }}
          />
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <button
              onClick={() => onSubmit()}
              disabled={loading}
              style={{
                background: loading ? 'var(--dim)' : 'var(--accent)',
                border: 'none', borderRadius: '10px', width: '42px', height: '42px',
                cursor: loading ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: '#0a0b0e', transition: 'background .15s',
              }}
            >
              <Send size={16} />
            </button>

            {/* Mic button */}
            <button
              onClick={toggleVoice}
              title={isRecording ? 'Tap to stop' : 'Voice input'}
              style={{
                background: isRecording ? 'rgba(252,129,129,0.18)' : 'var(--bg3)',
                border: `1px solid ${isRecording ? 'rgba(252,129,129,0.6)' : 'var(--border)'}`,
                borderRadius: '10px', width: '42px', height: '42px',
                cursor: 'pointer', display: 'flex', alignItems: 'center',
                justifyContent: 'center', flexDirection: 'column',
                color: isRecording ? '#fc8181' : 'var(--muted)',
                transition: 'all .2s', position: 'relative',
              }}
            >
              {isRecording ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '2px', height: '20px' }}>
                  {audioLevel.map((level, i) => (
                    <div key={i} style={{
                      width: '3px',
                      height: `${Math.round(level * 18)}px`,
                      background: '#fc8181',
                      borderRadius: '2px',
                      transition: 'height 0.08s ease',
                      minHeight: '3px',
                    }} />
                  ))}
                </div>
              ) : (
                <Mic size={16} />
              )}
            </button>
          </div>
        </div>

        {/* Listening label */}
        {isRecording && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            marginTop: '8px', fontSize: '11px', color: '#fc8181',
            fontFamily: 'IBM Plex Mono, monospace',
          }}>
            <div style={{
              width: '6px', height: '6px', borderRadius: '50%',
              background: '#fc8181',
              animation: 'pulseDot 1s ease-in-out infinite',
            }} />
            Listening... tap mic to stop
          </div>
        )}
      </div>

      {/* Suggested chips */}
      <div style={{ padding: '0.75rem 1.5rem', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
        <div style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px', letterSpacing: '0.08em', color: 'var(--dim)', textTransform: 'uppercase', marginBottom: '8px' }}>
          Suggested queries
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {suggestedQueries.map((q, i) => (
            <Chip key={i} onClick={() => { setQuestion(q); onSubmit(q) }}>{q}</Chip>
          ))}
        </div>
      </div>

      {/* History */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0.75rem 1.5rem' }}>
        <div style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '10px', letterSpacing: '0.08em', color: 'var(--dim)', textTransform: 'uppercase', marginBottom: '8px' }}>
          Query history
        </div>
        {history.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '120px', color: 'var(--dim)', fontSize: '12px', gap: '8px' }}>
            <span style={{ fontSize: '28px', opacity: 0.4 }}>⚡</span>
            <span>Run a query to get started</span>
          </div>
        ) : (
          history.map((h, i) => (
            <div
              key={i}
              onClick={() => { setQuestion(h.question); onSubmit(h.question) }}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: '8px',
                padding: '8px 10px', borderRadius: '8px', cursor: 'pointer',
                marginBottom: '4px', transition: 'background .15s',
                borderLeft: i === 0 ? '2px solid var(--accent)' : '2px solid transparent',
                background: i === 0 ? 'rgba(99,179,237,.08)' : 'transparent',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--bg3)'}
              onMouseLeave={e => e.currentTarget.style.background = i === 0 ? 'rgba(99,179,237,.08)' : 'transparent'}
            >
              <span style={{ color: h.hasError ? 'var(--danger)' : 'var(--success)', fontSize: '12px', marginTop: '1px' }}>
                {h.hasError ? '✗' : '✓'}
              </span>
              <div style={{ fontSize: '12px', lineHeight: 1.4 }}>
                <div style={{ color: 'var(--text)', marginBottom: '2px' }}>{h.question}</div>
                <div style={{ color: 'var(--dim)', fontSize: '11px' }}>{h.hasError ? 'Error' : `${h.rowCount} rows`}</div>
              </div>
            </div>
          ))
        )}
      </div>

      <style>{`
        @keyframes pulseDot { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.4;transform:scale(0.7)} }
      `}</style>
    </div>
  )
}

function Chip({ children, onClick, variant = 'default' }) {
  const isFollowup = variant === 'followup'
  return (
    <button
      onClick={onClick}
      style={{
        background: 'var(--bg3)',
        border: `1px solid ${isFollowup ? 'rgba(118,228,196,.25)' : 'var(--border)'}`,
        borderRadius: '100px', padding: '4px 10px',
        fontSize: '11px', color: isFollowup ? 'var(--accent2)' : 'var(--muted)',
        cursor: 'pointer', whiteSpace: 'nowrap', transition: 'all .15s',
        fontFamily: 'Inter, sans-serif',
      }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--border-hi)'; e.currentTarget.style.color = 'var(--accent)' }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = isFollowup ? 'rgba(118,228,196,.25)' : 'var(--border)'; e.currentTarget.style.color = isFollowup ? 'var(--accent2)' : 'var(--muted)' }}
    >
      {children}
    </button>
  )
}

export { Chip }