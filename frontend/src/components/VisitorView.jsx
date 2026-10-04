import React, { useEffect, useMemo, useState } from 'react'
import { api, withOffset } from '../api.js'
import RouteResult from './RouteResult.jsx'

const OFFSETS = [-12, -9, -8, -7, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 5.5, 6, 7, 8, 9, 9.5, 10, 11, 12]

function nowLocal(offsetMinutes) {
  const d = new Date(Date.now() + offsetMinutes * 60000)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())}T${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`
}

const offsetLabel = (m) => {
  const sign = m >= 0 ? '+' : '-'
  const h = Math.floor(Math.abs(m) / 60)
  const mm = Math.abs(m) % 60
  return `UTC${sign}${h}${mm ? `:${String(mm).padStart(2, '0')}` : ''}`
}

export default function VisitorView() {
  const [locations, setLocations] = useState([])
  const [offset, setOffset] = useState(480) // 默认 UTC+8
  const [form, setForm] = useState({ origin: '', destination: '', ts: '', wheelchair: false })
  const [result, setResult] = useState(null)
  const [lookupNo, setLookupNo] = useState('')
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.locations().then((ls) => {
      setLocations(ls)
      setForm((f) => ({ ...f, ts: nowLocal(480), origin: ls[0]?.code || '', destination: ls[1]?.code || '' }))
    }).catch((e) => setError(e.message))
  }, [])

  const offsetMinutes = useMemo(() => offset * 60, [offset])

  const compute = async () => {
    setError(''); setInfo(''); setResult(null); setBusy(true)
    try {
      if (!form.origin || !form.destination) throw new Error('请选择起点与终点')
      if (form.origin === form.destination) throw new Error('起点与终点不能相同')
      const r = await api.route({
        origin: form.origin,
        destination: form.destination,
        travel_ts: withOffset(form.ts, offsetMinutes),
        wheelchair: form.wheelchair,
      })
      setResult(r)
      setInfo(`已生成指引 ${r.guidance_no}，可凭该编号随时复核本次路线（版本 v${r.version}）`)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const lookup = async () => {
    setError(''); setInfo(''); setResult(null)
    const no = lookupNo.trim()
    if (!no) { setError('请输入指引编号，例如 G-000001'); return }
    try {
      const r = await api.guidance(no)
      setResult(r)
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <>
      <div className="card">
        <h2>🧭 路线查询</h2>
        <div className="grid cols-3">
          <div>
            <label>起点</label>
            <select value={form.origin} onChange={(e) => setForm({ ...form, origin: e.target.value })}>
              {!form.origin && <option value="">请选择</option>}
              {locations.map((l) => <option key={l.id} value={l.code}>{l.name}（{l.code}）</option>)}
            </select>
          </div>
          <div>
            <label>终点</label>
            <select value={form.destination} onChange={(e) => setForm({ ...form, destination: e.target.value })}>
              {!form.destination && <option value="">请选择</option>}
              {locations.map((l) => <option key={l.id} value={l.code}>{l.name}（{l.code}）</option>)}
            </select>
          </div>
          <div>
            <label>出行时刻（{offsetLabel(offsetMinutes)}）</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input type="datetime-local" value={form.ts}
                onChange={(e) => setForm({ ...form, ts: e.target.value })} style={{ flex: 1 }} />
              <select value={offset} onChange={(e) => setOffset(Number(e.target.value))} style={{ width: 110 }}
                title="时刻所在时区">
                {OFFSETS.map((h) => <option key={h} value={h * 60}>{offsetLabel(h * 60)}</option>)}
              </select>
            </div>
          </div>
        </div>
        <div className="row-actions">
          <label className="switch">
            <input type="checkbox" checked={form.wheelchair}
              onChange={(e) => setForm({ ...form, wheelchair: e.target.checked })} />
            ♿ 使用轮椅（仅计算轮椅可通行通道）
          </label>
          <button className="btn" disabled={busy} onClick={compute}>{busy ? '计算中…' : '计算最短路线'}</button>
          <button className="btn ghost" onClick={() => setForm((f) => ({ ...f, ts: nowLocal(offsetMinutes) }))}>
            填入当前时刻
          </button>
        </div>
        {error && <div className="message error">⚠️ {error}</div>}
        {info && <div className="message info">ℹ️ {info}</div>}
      </div>

      <div className="card">
        <h2>🔎 凭指引编号复核原路线</h2>
        <p className="muted-text" style={{ marginTop: 0 }}>
          指引与生成时的发布版本永久绑定，后续即使公告撤回、新版本发布，看到的仍是当时的路线。
        </p>
        <div style={{ display: 'flex', gap: 10, maxWidth: 420 }}>
          <input placeholder="G-000001" value={lookupNo} onChange={(e) => setLookupNo(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && lookup()} className="mono" />
          <button className="btn ghost" onClick={lookup}>查看原路线</button>
        </div>
      </div>

      {result && <RouteResult r={result} />}
    </>
  )
}
