import { useEffect, useState } from 'react'
import { api, zonedToISO } from '../api.js'
import RouteResult from './RouteResult.jsx'

function nowLocalInput() {
  const d = new Date()
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset())
  return d.toISOString().slice(0, 16)
}

export default function VisitorView() {
  const [version, setVersion] = useState(null)
  const [timezones, setTimezones] = useState(['Asia/Shanghai', 'UTC'])
  const [origin, setOrigin] = useState('')
  const [destination, setDestination] = useState('')
  const [travelLocal, setTravelLocal] = useState(nowLocalInput())
  const [tz, setTz] = useState('Asia/Shanghai')
  const [wheelchair, setWheelchair] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  const [lookupId, setLookupId] = useState('')
  const [lookupResult, setLookupResult] = useState(null)
  const [lookupError, setLookupError] = useState(null)

  async function refreshMeta() {
    try {
      const [v, tzs] = await Promise.all([
        api.get('/api/versions/latest'),
        api.get('/api/timezones'),
      ])
      setVersion(v)
      setTimezones(tzs)
      setError(null)
    } catch (e) {
      setError(e)
    }
  }

  useEffect(() => {
    refreshMeta()
  }, [])

  const locations = version ? version.locations : []
  const previewISO = travelLocal ? zonedToISO(travelLocal, tz) : ''

  async function submit() {
    setLoading(true); setError(null); setResult(null)
    try {
      if (!origin || !destination) {
        throw Object.assign(new Error('请选择起点和终点'), { code: 'MISSING_INPUT' })
      }
      if (!travelLocal) {
        throw Object.assign(new Error('请选择出行日期与时间'), { code: 'MISSING_INPUT' })
      }
      const r = await api.post('/api/routes', {
        origin,
        destination,
        travel_time: zonedToISO(travelLocal, tz),
        wheelchair,
      })
      setResult(r)
      setLookupId(String(r.guidance_number))
    } catch (e) {
      setError(e)
    } finally {
      setLoading(false)
    }
  }

  async function lookup() {
    setLookupError(null); setLookupResult(null)
    const id = Number(lookupId)
    if (!Number.isInteger(id) || id <= 0) {
      setLookupError(Object.assign(new Error('请输入正整数指引编号'), { code: 'BAD_NUMBER' }))
      return
    }
    try {
      setLookupResult(await api.get(`/api/guidance/${id}`))
    } catch (e) {
      setLookupError(e)
    }
  }

  return (
    <>
      <div className="card">
        <h2>查询可行最短路线</h2>
        {version && (
          <p className="muted">
            当前发布版本 <b>#{version.id}</b>（{version.note}，发布于 {version.published_at}）。
            路线仅依据同一版本快照计算，运营并发发布不会影响本次查询。
          </p>
        )}
        {error && (
          <div className="alert alert-error">
            <b>[{error.code}]</b> {error.message}
            <div><button className="btn btn-ghost btn-sm" style={{ marginTop: 6 }} onClick={refreshMeta}>重试加载</button></div>
          </div>
        )}
        <div className="row">
          <label className="field">
            <span>起点</span>
            <select value={origin} onChange={(e) => setOrigin(e.target.value)}>
              <option value="">请选择起点…</option>
              {locations.map((l) => <option key={l.code} value={l.code}>{l.name}（{l.code}）</option>)}
            </select>
          </label>
          <label className="field">
            <span>终点</span>
            <select value={destination} onChange={(e) => setDestination(e.target.value)}>
              <option value="">请选择终点…</option>
              {locations.map((l) => <option key={l.code} value={l.code}>{l.name}（{l.code}）</option>)}
            </select>
          </label>
        </div>
        <div className="row">
          <label className="field">
            <span>出行日期与时间（当地墙钟时间）</span>
            <input type="datetime-local" step="60" value={travelLocal} onChange={(e) => setTravelLocal(e.target.value)} />
          </label>
          <label className="field">
            <span>时区</span>
            <select value={tz} onChange={(e) => setTz(e.target.value)}>
              {timezones.map((z) => <option key={z} value={z}>{z}</option>)}
            </select>
          </label>
          <label className="field" style={{ alignSelf: 'flex-end' }}>
            <span>出行方式</span>
            <label className="checkbox">
              <input type="checkbox" checked={wheelchair} onChange={(e) => setWheelchair(e.target.checked)} />
              使用轮椅（仅走轮椅可通行通道）
            </label>
          </label>
        </div>
        {previewISO && <p className="muted">将以带时区时刻提交：<span className="mono">{previewISO}</span>（系统内部按 UTC 计算）</p>}
        <button className="btn btn-primary" disabled={loading || !version} onClick={submit}>
          {loading ? '计算中…' : '计算最短路线'}
        </button>
      </div>

      {result && <RouteResult result={result} />}

      <div className="card">
        <h2>凭指引编号查看原路线</h2>
        <p className="muted">指引保存了生成时的版本与完整路径；后续公告撤回、重新发布都不改变既有指引内容。</p>
        <div className="row">
          <label className="field">
            <span>指引编号</span>
            <input value={lookupId} onChange={(e) => setLookupId(e.target.value)} placeholder="例如 1" inputMode="numeric" />
          </label>
          <div style={{ alignSelf: 'flex-end' }}>
            <button className="btn btn-ghost" onClick={lookup}>查看原指引</button>
          </div>
        </div>
        {lookupError && <div className="alert alert-error"><b>[{lookupError.code}]</b> {lookupError.message}</div>}
        {lookupResult && <RouteResult result={lookupResult} snapshot />}
      </div>
    </>
  )
}
