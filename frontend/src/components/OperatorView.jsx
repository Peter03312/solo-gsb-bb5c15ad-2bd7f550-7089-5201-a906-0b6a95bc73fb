import { useEffect, useState, useCallback } from 'react'
import { api, fmtDistance, zonedToISO } from '../api.js'

function useReload() {
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((t) => t + 1), [])
  return [tick, reload]
}

function Msg({ error, ok, onClear }) {
  return (
    <>
      {error && <div className="alert alert-error"><b>[{error.code}]</b> {error.message}</div>}
      {ok && <div className="alert alert-success">{ok}</div>}
    </>
  )
}

function Locations({ locations, reload, notify }) {
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [ok, setOk] = useState(null)

  async function add() {
    setBusy(true); setError(null); setOk(null)
    try {
      const r = await api.post('/api/locations', { code: code.trim(), name: name.trim() })
      setOk(r.message); setCode(''); setName(''); reload()
    } catch (e) { setError(e) } finally { setBusy(false) }
  }
  async function remove(c) {
    setError(null); setOk(null)
    if (!window.confirm(`确认删除地点 ${c}？（仅删除草稿，需发布后生效）`)) return
    try { setOk((await api.del(`/api/locations/${encodeURIComponent(c)}`)).message); reload() }
    catch (e) { setError(e) }
  }

  return (
    <div className="card">
      <h2>① 地点维护</h2>
      <Msg error={error} ok={ok} />
      <table>
        <thead><tr><th>编号</th><th>名称</th><th></th></tr></thead>
        <tbody>
          {locations.map((l) => (
            <tr key={l.code}><td className="mono">{l.code}</td><td>{l.name}</td>
              <td style={{ textAlign: 'right' }}>
                <button className="btn btn-danger btn-sm" onClick={() => remove(l.code)}>删除</button>
              </td></tr>
          ))}
          {locations.length === 0 && <tr><td colSpan={3} className="muted">暂无地点</td></tr>}
        </tbody>
      </table>
      <h3>新增地点</h3>
      <div className="row">
        <label className="field"><span>编号（英文标识）</span>
          <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="如 NORTH" /></label>
        <label className="field"><span>名称</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="如 北门" /></label>
      </div>
      <button className="btn btn-primary" disabled={busy} onClick={add}>{busy ? '保存中…' : '保存地点'}</button>
    </div>
  )
}

function Passages({ locations, passages, reload }) {
  const blank = { code: '', name: '', from_location: '', to_location: '', length_m: '', wheelchair: true }
  const [f, setF] = useState(blank)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [ok, setOk] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })

  async function add() {
    setBusy(true); setError(null); setOk(null)
    const length = Number(f.length_m)
    try {
      if (!(length > 0)) {
        const err = new Error('通道长度必须为正数'); err.code = 'INVALID_LENGTH'; throw err
      }
      const r = await api.post('/api/passages', {
        code: f.code.trim(), name: f.name.trim(),
        from_location: f.from_location, to_location: f.to_location,
        length_m: length, wheelchair: f.wheelchair,
      })
      setOk(r.message); setF(blank); reload()
    } catch (e) { setError(e) } finally { setBusy(false) }
  }
  async function remove(c) {
    setError(null); setOk(null)
    if (!window.confirm(`确认删除通道 ${c}？（仅删除草稿，需发布后生效）`)) return
    try { setOk((await api.del(`/api/passages/${encodeURIComponent(c)}`)).message); reload() }
    catch (e) { setError(e) }
  }

  return (
    <div className="card">
      <h2>② 定向通道维护（有向，长度必须为正）</h2>
      <Msg error={error} ok={ok} />
      <table>
        <thead><tr><th>编号</th><th>名称</th><th>方向</th><th>长度</th><th>轮椅</th><th></th></tr></thead>
        <tbody>
          {passages.map((p) => (
            <tr key={p.code}>
              <td className="mono">{p.code}</td><td>{p.name}</td>
              <td>{p.from_location} → {p.to_location}</td>
              <td>{fmtDistance(p.length_m)}</td>
              <td>{p.wheelchair ? <span className="badge badge-ok">可通行</span> : <span className="badge badge-no">台阶/不可</span>}</td>
              <td style={{ textAlign: 'right' }}>
                <button className="btn btn-danger btn-sm" onClick={() => remove(p.code)}>删除</button>
              </td>
            </tr>
          ))}
          {passages.length === 0 && <tr><td colSpan={6} className="muted">暂无通道</td></tr>}
        </tbody>
      </table>
      <h3>新增定向通道（双向请分别建两条）</h3>
      <div className="row">
        <label className="field"><span>编号</span><input value={f.code} onChange={set('code')} placeholder="如 N-S" /></label>
        <label className="field"><span>名称</span><input value={f.name} onChange={set('name')} placeholder="如 北门连廊" /></label>
      </div>
      <div className="row">
        <label className="field"><span>起点</span>
          <select value={f.from_location} onChange={set('from_location')}>
            <option value="">选择地点…</option>
            {locations.map((l) => <option key={l.code} value={l.code}>{l.name}（{l.code}）</option>)}
          </select></label>
        <label className="field"><span>终点</span>
          <select value={f.to_location} onChange={set('to_location')}>
            <option value="">选择地点…</option>
            {locations.map((l) => <option key={l.code} value={l.code}>{l.name}（{l.code}）</option>)}
          </select></label>
        <label className="field"><span>长度（米，正数）</span>
          <input type="number" min="0" step="0.1" value={f.length_m} onChange={set('length_m')} /></label>
        <label className="field" style={{ alignSelf: 'flex-end' }}>
          <label className="checkbox">
            <input type="checkbox" checked={f.wheelchair} onChange={set('wheelchair')} />
            轮椅可通行
          </label>
        </label>
      </div>
      <button className="btn btn-primary" disabled={busy} onClick={add}>{busy ? '保存中…' : '保存通道'}</button>
    </div>
  )
}

function Announcements({ locations, passages, announcements, timezones, reload }) {
  const now = new Date(); now.setMinutes(now.getMinutes() - now.getTimezoneOffset())
  const [f, setF] = useState({
    title: '', start: now.toISOString().slice(0, 16), end: '', tz: 'Asia/Shanghai', picked: [],
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [ok, setOk] = useState(null)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  function toggle(code) {
    setF((s) => ({
      ...s,
      picked: s.picked.includes(code) ? s.picked.filter((c) => c !== code) : [...s.picked, code],
    }))
  }

  async function add() {
    setBusy(true); setError(null); setOk(null)
    try {
      if (!f.picked.length) { const e = new Error('请至少选择一条封闭通道'); e.code = 'EMPTY_PASSAGES'; throw e }
      const r = await api.post('/api/announcements', {
        title: f.title.trim(),
        start_time: zonedToISO(f.start, f.tz),
        end_time: zonedToISO(f.end, f.tz),
        passage_codes: f.picked,
      })
      setOk(r.message); setF((s) => ({ ...s, title: '', picked: [] })); reload()
    } catch (e) { setError(e) } finally { setBusy(false) }
  }

  async function revoke(id, title) {
    setError(null); setOk(null)
    if (!window.confirm(`撤回公告「${title}」？\n撤回会立即发布一个新版本，只影响此后的查询；既有指引保持原路线。`)) return
    setBusy(true)
    try { setOk((await api.post(`/api/announcements/${id}/revoke`)).message); reload() }
    catch (e) { setError(e) } finally { setBusy(false) }
  }

  return (
    <div className="card">
      <h2>③ 封闭公告编排（起止时刻带时区，区间左闭右开）</h2>
      <Msg error={error} ok={ok} />
      <table>
        <thead><tr><th>#</th><th>标题</th><th>开始 (UTC)</th><th>结束 (UTC)</th><th>封闭通道</th><th>状态</th><th></th></tr></thead>
        <tbody>
          {announcements.map((a) => (
            <tr key={a.id} style={a.revoked ? { opacity: 0.55 } : undefined}>
              <td>{a.id}</td><td>{a.title}</td>
              <td className="mono">{a.start_time_utc}</td>
              <td className="mono">{a.end_time_utc}</td>
              <td>{a.passage_codes.join(', ')}</td>
              <td>{a.revoked
                ? <span className="badge badge-warn">已撤回</span>
                : <span className="badge badge-ok">待发布/生效</span>}</td>
              <td style={{ textAlign: 'right' }}>
                {!a.revoked && <button className="btn btn-danger btn-sm" disabled={busy} onClick={() => revoke(a.id, a.title)}>撤回并发布</button>}
              </td>
            </tr>
          ))}
          {announcements.length === 0 && <tr><td colSpan={7} className="muted">暂无公告</td></tr>}
        </tbody>
      </table>
      <p className="muted">注意：公告保存或撤回后，需「发布新版本」才会进入访客所用快照（撤回会自动发布）。同一通道的重叠公告其封闭区间自动取并集。</p>

      <h3>新增封闭公告</h3>
      <label className="field"><span>标题</span><input value={f.title} onChange={set('title')} placeholder="如 中心广场活动封路" /></label>
      <div className="row">
        <label className="field"><span>开始时间（当地）</span>
          <input type="datetime-local" step="60" value={f.start} onChange={set('start')} /></label>
        <label className="field"><span>结束时间（当地，左闭右开不含此刻）</span>
          <input type="datetime-local" step="60" value={f.end} onChange={set('end')} /></label>
        <label className="field"><span>时区</span>
          <select value={f.tz} onChange={set('tz')}>{timezones.map((z) => <option key={z}>{z}</option>)}</select></label>
      </div>
      <label className="field"><span>封闭通道（可多选）</span></label>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
        {passages.map((p) => (
          <label key={p.code} className="checkbox" style={{
            border: '1px solid #cbd2d9', borderRadius: 6, padding: '4px 10px',
            background: f.picked.includes(p.code) ? '#d1e7dd' : '#fff', cursor: 'pointer',
          }}>
            <input type="checkbox" checked={f.picked.includes(p.code)} onChange={() => toggle(p.code)} />
            {p.code}（{p.from_location}→{p.to_location}）
          </label>
        ))}
        {passages.length === 0 && <span className="muted">请先维护通道</span>}
      </div>
      <button className="btn btn-primary" disabled={busy} onClick={add}>{busy ? '保存中…' : '保存公告'}</button>
    </div>
  )
}

function Publish({ reload, notify }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [ok, setOk] = useState(null)

  async function publish() {
    setBusy(true); setError(null); setOk(null)
    try {
      const r = await api.post('/api/publish', { note })
      setOk(`${r.message}，含 ${r.active_announcements} 条生效公告。此后访客查询将使用版本 #${r.version_id}；正在进行的查询仍使用旧版本，不会混用。`)
      setNote(''); reload()
    } catch (e) { setError(e) } finally { setBusy(false) }
  }
  return (
    <div className="card">
      <h2>④ 发布版本</h2>
      <Msg error={error} ok={ok} />
      <p className="muted">发布会把当前全部地点、定向通道与未撤回公告冻结为一个不可变快照。撤回公告时系统会自动发布新版本。</p>
      <div className="row">
        <label className="field"><span>版本备注（可选）</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="如 国庆首日封路方案" /></label>
      </div>
      <button className="btn btn-primary" disabled={busy} onClick={publish}>{busy ? '发布中…' : '发布新版本'}</button>
    </div>
  )
}

function Versions({ tick }) {
  const [versions, setVersions] = useState([])
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/api/versions').then(setVersions).catch(setError)
  }, [tick])

  async function show(id) {
    setError(null)
    try { setDetail(await api.get(`/api/versions/${id}`)) } catch (e) { setError(e) }
  }

  return (
    <div className="card">
      <h2>⑤ 已发布版本</h2>
      {error && <Msg error={error} />}
      <table>
        <thead><tr><th>版本</th><th>备注</th><th>发布时间 (UTC)</th><th>生效公告</th><th></th></tr></thead>
        <tbody>
          {versions.map((v) => (
            <tr key={v.id}>
              <td>#{v.id} {v.is_latest && <span className="badge badge-info">最新</span>}</td>
              <td>{v.note}</td><td className="mono">{v.published_at}</td>
              <td>{v.announcement_count}</td>
              <td style={{ textAlign: 'right' }}>
                <button className="btn btn-ghost btn-sm" onClick={() => show(v.id)}>查看快照</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {detail && (
        <div style={{ marginTop: 12 }}>
          <h3>版本 #{detail.id} 快照：{detail.note}</h3>
          <p className="muted">地点 {detail.locations.length} 个 · 通道 {detail.passages.length} 条 · 公告 {detail.announcements.length} 条</p>
          <table>
            <thead><tr><th>通道</th><th>封闭并集区间（左闭右开，UTC）</th><th>来源公告</th></tr></thead>
            <tbody>
              {detail.closures.map((c) => (
                <tr key={c.passage_code}>
                  <td>{c.passage_name} <span className="muted">({c.passage_code})</span></td>
                  <td>
                    {c.segments.map((s, i) => (
                      <div key={i} className="mono">{s.start_utc} ～ {s.end_utc}</div>
                    ))}
                  </td>
                  <td>{c.segments.flatMap((s) => s.announcement_titles).join('；')}</td>
                </tr>
              ))}
              {detail.closures.length === 0 && <tr><td colSpan={3} className="muted">该版本无封闭公告</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function OperatorView() {
  const [tick, reload] = useReload()
  const [locations, setLocations] = useState([])
  const [passages, setPassages] = useState([])
  const [announcements, setAnnouncements] = useState([])
  const [timezones, setTimezones] = useState(['Asia/Shanghai', 'UTC'])

  useEffect(() => {
    Promise.all([
      api.get('/api/locations'),
      api.get('/api/passages'),
      api.get('/api/announcements'),
      api.get('/api/timezones'),
    ]).then(([l, p, a, t]) => { setLocations(l); setPassages(p); setAnnouncements(a); setTimezones(t) })
      .catch(() => {})
  }, [tick])

  return (
    <>
      <Locations locations={locations} passages={passages} reload={reload} />
      <Passages locations={locations} passages={passages} reload={reload} />
      <Announcements locations={locations} passages={passages} announcements={announcements}
        timezones={timezones} reload={reload} />
      <Publish reload={reload} />
      <Versions tick={tick} />
    </>
  )
}
