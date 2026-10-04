import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'

export default function AdminDataView() {
  const [locations, setLocations] = useState([])
  const [edges, setEdges] = useState([])
  const [loc, setLoc] = useState({ code: '', name: '' })
  const [edge, setEdge] = useState({
    code: '', from_code: '', to_code: '', length_m: '', wheelchair: true, note: '',
  })
  const [error, setError] = useState('')
  const [ok, setOk] = useState('')

  const refresh = useCallback(async () => {
    const [ls, es] = await Promise.all([api.locations(), api.edges()])
    setLocations(ls)
    setEdges(es)
  }, [])

  useEffect(() => { refresh().catch((e) => setError(e.message)) }, [refresh])

  const flash = (msg) => { setOk(msg); setError(''); setTimeout(() => setOk(''), 3500) }

  const addLocation = async () => {
    setError('')
    try {
      if (!loc.code.trim() || !loc.name.trim()) throw new Error('地点编号与名称都必填')
      await api.addLocation(loc)
      setLoc({ code: '', name: '' })
      await refresh()
      flash(`地点 ${loc.code} 已创建`)
    } catch (e) { setError(e.message) }
  }

  const addEdge = async () => {
    setError('')
    try {
      if (!edge.code.trim()) throw new Error('通道编号必填')
      const length = Number(edge.length_m)
      if (!Number.isFinite(length) || length <= 0) throw new Error('通道长度必须为正数（米）')
      if (!edge.from_code || !edge.to_code) throw new Error('请选择起点和终点')
      if (edge.from_code === edge.to_code) throw new Error('定向通道的起点与终点不能相同')
      await api.addEdge({
        code: edge.code.trim(),
        from_code: edge.from_code,
        to_code: edge.to_code,
        length_m: length,
        wheelchair: edge.wheelchair,
        note: edge.note,
      })
      setEdge({ code: '', from_code: '', to_code: '', length_m: '', wheelchair: true, note: '' })
      await refresh()
      flash('定向通道已创建（需再次发布后才影响访客路线）')
    } catch (e) { setError(e.message) }
  }

  return (
    <>
      {error && <div className="message error">⚠️ {error}</div>}
      {ok && <div className="message ok">✅ {ok}</div>}

      <div className="card">
        <h2>📍 新增地点</h2>
        <div className="grid cols-2">
          <div>
            <label>地点编号（唯一，访客查询使用）</label>
            <input value={loc.code} placeholder="例如 GATE-A"
              onChange={(e) => setLoc({ ...loc, code: e.target.value.toUpperCase() })} />
          </div>
          <div>
            <label>地点名称</label>
            <input value={loc.name} placeholder="例如 东门"
              onChange={(e) => setLoc({ ...loc, name: e.target.value })} />
          </div>
        </div>
        <div className="row-actions"><button className="btn" onClick={addLocation}>新增地点</button></div>
      </div>

      <div className="card">
        <h2>🛣️ 新增定向通道（正长度，可标注轮椅属性）</h2>
        <div className="grid cols-3">
          <div>
            <label>通道编号</label>
            <input value={edge.code} placeholder="例如 E-N"
              onChange={(e) => setEdge({ ...edge, code: e.target.value })} />
          </div>
          <div>
            <label>起点</label>
            <select value={edge.from_code} onChange={(e) => setEdge({ ...edge, from_code: e.target.value })}>
              <option value="">请选择</option>
              {locations.map((l) => <option key={l.id} value={l.code}>{l.name}（{l.code}）</option>)}
            </select>
          </div>
          <div>
            <label>终点（通道有方向，反向需另建）</label>
            <select value={edge.to_code} onChange={(e) => setEdge({ ...edge, to_code: e.target.value })}>
              <option value="">请选择</option>
              {locations.map((l) => <option key={l.id} value={l.code}>{l.name}（{l.code}）</option>)}
            </select>
          </div>
          <div>
            <label>长度（米，须 &gt; 0）</label>
            <input type="number" min="0" step="0.1" value={edge.length_m}
              onChange={(e) => setEdge({ ...edge, length_m: e.target.value })} />
          </div>
          <div>
            <label>备注</label>
            <input value={edge.note} onChange={(e) => setEdge({ ...edge, note: e.target.value })} />
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <label className="switch">
              <input type="checkbox" checked={edge.wheelchair}
                onChange={(e) => setEdge({ ...edge, wheelchair: e.target.checked })} />
              ♿ 轮椅可通行
            </label>
          </div>
        </div>
        <div className="row-actions"><button className="btn" onClick={addEdge}>新增通道</button></div>
      </div>

      <div className="card">
        <h2>📍 地点列表（{locations.length}）</h2>
        <table>
          <thead><tr><th>ID</th><th>编号</th><th>名称</th></tr></thead>
          <tbody>
            {locations.map((l) => (
              <tr key={l.id}><td>{l.id}</td><td className="mono">{l.code}</td><td>{l.name}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>🛣️ 通道列表（{edges.length}）</h2>
        <table>
          <thead>
            <tr><th>编号</th><th>方向</th><th className="num">长度(米)</th><th>轮椅</th><th>备注</th></tr>
          </thead>
          <tbody>
            {edges.map((e) => (
              <tr key={e.id}>
                <td className="mono">{e.code}</td>
                <td>{e.from.name} → {e.to.name} <span className="muted-text mono">({e.from.code}→{e.to.code})</span></td>
                <td className="num">{e.length_m}</td>
                <td>{e.wheelchair
                  ? <span className="tag yes">♿ 可通行</span>
                  : <span className="tag no">台阶/不可通行</span>}</td>
                <td>{e.note || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
