import React from 'react'
import { fmtDistance } from '../api.js'

// 路线结果（当场计算或凭编号复核均渲染此组件）
export default function RouteResult({ r }) {
  return (
    <div className="card">
      <div className="result-head">
        <div>
          <div className="muted-text">指引编号</div>
          <div className="guidance-no mono">{r.guidance_no}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div className="muted-text">总距离</div>
          <div className="big-distance">{fmtDistance(r.distance_m)}</div>
        </div>
      </div>

      <p className="muted-text" style={{ margin: '10px 0 0' }}>
        发布版本 <strong>v{r.version}</strong>
        {r.published_at ? `（发布于 ${r.published_at} UTC）` : ''}
        {r.archived ? '　·　历史指引，按当时版本快照展示，不受后续发布/撤回影响' : ''}
      </p>
      <p className="muted-text" style={{ margin: '4px 0' }}>
        {r.origin.name}（{r.origin.code}） → {r.destination.name}（{r.destination.code}）
        　|　出行时刻（UTC）{r.travel_ts}　|　{r.wheelchair ? '♿ 使用轮椅' : '🚶 步行'}
      </p>

      <div className="path-flow">
        {r.path.map((code, i) => (
          <React.Fragment key={i}>
            {i > 0 && <span className="sep">→</span>}
            <span className="mono">{code}</span>
          </React.Fragment>
        ))}
      </div>

      <ol className="steps">
        {r.steps.map((s) => (
          <li key={s.seq}>
            <div>{s.instruction}</div>
            <div className="step-meta">
              通道 <span className="mono">{s.edge_code}</span> · {fmtDistance(s.length_m)}
              　{s.wheelchair ? <span className="tag yes">♿ 可通行</span> : <span className="tag no">♿ 不可通行</span>}
            </div>
          </li>
        ))}
      </ol>

      {!r.archived && r.active_announcements && (
        <h3>出行时刻生效的封闭公告（{r.active_announcements.length} 条，左闭右开）</h3>
      )}
      {!r.archived && r.active_announcements && r.active_announcements.length === 0 && (
        <p className="muted-text">无</p>
      )}
      {!r.archived && r.active_announcements && r.active_announcements.length > 0 && (
        <table>
          <thead><tr><th>#</th><th>标题</th><th>封闭通道</th><th>起（UTC）</th><th>止（UTC）</th></tr></thead>
          <tbody>
            {r.active_announcements.map((a, i) => (
              <tr key={a.id}>
                <td>{i + 1}</td>
                <td>{a.title}</td>
                <td className="mono">#{a.edge_id}</td>
                <td className="mono">{a.start_ts}</td>
                <td className="mono">{a.end_ts}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
