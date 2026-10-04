import { fmtDistance } from '../api.js'

export default function RouteResult({ result, snapshot }) {
  const isZero = result.distance_m === 0 && (!result.path || result.path.length === 0)
  return (
    <div className="card route-result">
      {snapshot ? (
        <div className="alert alert-info">
          {result.message || '此为指引生成时的原始路线快照'}
          {result.is_latest_version === false && <> · 当前已有更新版本，但本指引仍保持版本 #{result.version_id} 的原路线</>}
        </div>
      ) : null}
      <h2>
        指引编号 <span className="number">#{result.guidance_number}</span>
        <span className="badge badge-info" style={{ marginLeft: 10 }}>版本 #{result.version_id}</span>
        {result.wheelchair && <span className="badge badge-ok" style={{ marginLeft: 6 }}>♿ 轮椅</span>}
      </h2>
      <p>
        {result.origin_name || result.origin}（<span className="mono">{result.origin}</span>）
        {' → '}
        {result.destination_name || result.destination}（<span className="mono">{result.destination}</span>）
      </p>
      <p className="muted">出行时刻（UTC）：<span className="mono">{result.travel_time_utc}</span> · 生成于 {result.created_at}</p>

      <h3>总距离：{fmtDistance(result.distance_m)}</h3>

      {isZero ? (
        <div className="alert alert-success">起点与终点相同，无需移动（距离 0 米）。</div>
      ) : (
        <>
          <h3>路径（{result.nodes?.length || 0} 个节点）</h3>
          <div className="flow">
            {(result.node_names || result.nodes || []).map((n, i) => (
              <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="node">{n}</span>
                {i < (result.nodes || []).length - 1 && <span className="arrow">→</span>}
              </span>
            ))}
          </div>
          <h3>分段指引</h3>
          <table>
            <thead>
              <tr><th>#</th><th>通道</th><th>走向</th><th>长度</th><th>轮椅</th></tr>
            </thead>
            <tbody>
              {(result.path || []).map((s) => (
                <tr key={s.seq}>
                  <td>{s.seq}</td>
                  <td>{s.passage_name} <span className="muted mono">({s.passage_code})</span></td>
                  <td>{s.from_name || s.from} → {s.to_name || s.to}</td>
                  <td>{fmtDistance(s.length_m)}</td>
                  <td>
                    {s.wheelchair
                      ? <span className="badge badge-ok">可通行</span>
                      : <span className="badge badge-no">不可通行</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {!snapshot && result.blocked_now && result.blocked_now.length > 0 && (
        <>
          <h3>该时刻正被封闭的通道（未计入路径）</h3>
          <ul className="muted">
            {[...new Set(result.blocked_now.map((b) => b.passage_code))].map((c) => (
              <li key={c} className="mono">{c}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
