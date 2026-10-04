import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api, withOffset, utcToLocalInput } from '../api.js'

const OFFSETS = [-12, -9, -8, -7, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 5.5, 6, 7, 8, 9, 9.5, 10, 11, 12]
const offsetLabel = (m) => {
  const sign = m >= 0 ? '+' : '-'
  const h = Math.floor(Math.abs(m) / 60)
  const mm = Math.abs(m) % 60
  return `UTC${sign}${h}${mm ? `:${String(mm).padStart(2, '0')}` : ''}`
}
function blank() {
  return { edge_id: '', title: '', start: '', end: '' }
}

export default function AdminPublishView() {
  const [edges, setEdges] = useState([])
  const [anns, setAnns] = useState([])
  const [versions, setVersions] = useState([])
  const [offset, setOffset] = useState(480)
  const [form, setForm] = useState(blank())
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    const [es, as_, vs] = await Promise.all([api.edges(), api.announcements(), api.versions()])
    setEdges(es); setAnns(as_); setVersions(vs)
  }, [])
  useEffect(() => { refresh().catch((e) => setError(e.message)) }, [refresh])

  const edgeById = useMemo(() => Object.fromEntries(edges.map((e) => [e.id, e])), [edges])
  const flash = (msg) => { setOk(msg); setError(''); setTimeout(() => setOk(''), 4000) }

  const addAnnouncement = async () => {
    setError('')
    try {
      if (!form.edge_id) throw new Error('请选择封闭通道')
      if (!form.title.trim()) throw new Error('公告标题必填')
      if (!form.start || !form.end) throw new Error('请填写带时区的起止时刻')
      if (form.end <= form.start) throw new Error('封闭区间无效：起始必须严格早于结束（区间左闭右开）')
      await api.addAnnouncement({
        title: form.title.trim(),
        edge_id: Number(form.edge_id),
        start_ts: withOffset(form.start, offset),
        end_ts: withOffset(form.end, offset),
      })
      setForm(blank())
      await refresh()
      flash('公告草稿已创建；发布后才会对访客生效')
    } catch (e) { setError(e.message) }
  }

  const withdraw = async (id) => {
    setError('')
    try {
      await api.withdraw(id)
      await refresh()
      flash('公告已撤回：只影响之后的发布与查询，历史版本与既有指引不变')
    } catch (e) { setError(e.message) }
  }

  const publish = async () => {
    setError(''); setBusy(true)
    try {
      const r = await api.publish(note.trim())
      setNote('')
      await refresh()
      flash(`已发布版本 v${r.version}：快照 ${r.announcement_count} 条公告、${r.closed_edge_count} 条封闭通道`)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const activeCount = anns.filter((a) => !a.withdrawn).length

  return (
    <>
      {error && <div className="message error">⚠️ {error}</div>}
      {ok && <div className="message ok">✅ {ok}</div>}

      <div className="card">
        <h2>📢 编排封闭公告（区间左闭右开 [起, 止)）</h2>
        <div className="grid cols-2">
          <div>
            <label>封闭通道（定向）</label>
            <select value={form.edge_id} onChange={(e) => setForm({ ...form, edge_id: e.target.value })}>
              <option value="">请选择</option>
              {edges.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.code}：{e.from.name} → {e.to.name}（{e.length_m}米{e.wheelchair ? '，♿可通行' : '，台阶'}）
                </option>
              ))}
            </select>
          </div>
          <div>
            <label>公告标题</label>
            <input value={form.title} placeholder="例如 中庭通道设备进场封闭"
              onChange={(e) => setForm({ ...form, title: e.target.value })} />
          </div>
          <div>
            <label>起始时刻（{offsetLabel(offset)}，含此刻）</label>
            <input type="datetime-local" value={form.start}
              onChange={(e) => setForm({ ...form, start: e.target.value })} />
          </div>
          <div>
            <label>结束时刻（{offsetLabel(offset)}，不含此刻）</label>
            <input type="datetime-local" value={form.end}
              onChange={(e) => setForm({ ...form, end: e.target.value })} />
          </div>
        </div>
        <div className="row-actions">
          <label style={{ margin: 0 }}>时区</label>
          <select value={offset} onChange={(e) => setOffset(Number(e.target.value) * 60)} style={{ width: 120 }}>
            {OFFSETS.map((h) => <option key={h} value={h}>{offsetLabel(h * 60)}</option>)}
          </select>
          <button className="btn" onClick={addAnnouncement}>加入公告草稿</button>
        </div>
        <p className="muted-text">
          多条公告时间重叠时，封闭边取并集去重；同一通道的正反方向互不影响。
        </p>
      </div>

      <div className="card">
        <h2>📋 公告草稿（{anns.length}，生效中 {activeCount}）</h2>
        <table>
          <thead>
            <tr><th>#</th><th>标题</th><th>通道</th><th>起（{offsetLabel(offset)}）</th><th>止（{offsetLabel(offset)}）</th><th>状态</th><th></th></tr>
          </thead>
          <tbody>
            {anns.map((a) => {
              const e = edgeById[a.edge_id]
              return (
                <tr key={a.id}>
                  <td>{a.id}</td>
                  <td>{a.title}</td>
                  <td className="mono">{a.edge_code} {e ? `${e.from.code}→${e.to.code}` : ''}</td>
                  <td className="mono">{utcToLocalInput(a.start_ts, offset)}</td>
                  <td className="mono">{utcToLocalInput(a.end_ts, offset)}</td>
                  <td>{a.withdrawn ? <span className="tag muted">已撤回</span> : <span className="tag warn">待发布/生效</span>}</td>
                  <td>{!a.withdrawn && (
                    <button className="btn danger small" onClick={() => withdraw(a.id)}>撤回</button>
                  )}</td>
                </tr>
              )
            })}
            {anns.length === 0 && <tr><td colSpan={7} className="muted-text">暂无公告</td></tr>}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>🚀 发布版本</h2>
        <p className="muted-text" style={{ marginTop: 0 }}>
          发布即把当前全部未撤回公告固化为不可变快照；之后新增/撤回公告不会影响已发布版本。
          访客查询始终绑定「查询那一刻的最新版本」，并发发布不会使一次查询混用版本。
        </p>
        <div style={{ display: 'flex', gap: 10, maxWidth: 520 }}>
          <input placeholder="版本备注（可选）" value={note} onChange={(e) => setNote(e.target.value)} />
          <button className="btn" disabled={busy} onClick={publish}>{busy ? '发布中…' : `发布当前公告（${activeCount}）`}</button>
        </div>
      </div>

      <div className="card">
        <h2>🗂️ 已发布版本（{versions.length}）</h2>
        <table>
          <thead>
            <tr><th>版本</th><th>发布时间（UTC）</th><th className="num">公告数</th><th className="num">封闭通道</th><th className="num">已发指引</th><th>备注</th></tr>
          </thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.version}>
                <td className="mono">v{v.version}</td>
                <td className="mono">{v.published_at}</td>
                <td className="num">{v.announcement_count}</td>
                <td className="num">{v.closed_edge_count}</td>
                <td className="num">{v.guidance_count}</td>
                <td>{v.note || '—'}</td>
              </tr>
            ))}
            {versions.length === 0 && <tr><td colSpan={6} className="muted-text">尚未发布任何版本</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  )
}
