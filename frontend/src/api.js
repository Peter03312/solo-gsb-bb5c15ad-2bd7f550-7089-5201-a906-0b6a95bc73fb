// 统一 API 调用：把后端 {error:{message}} 转为可直接展示的 Error
async function request(path, options = {}) {
  const resp = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  let data = null
  try {
    data = await resp.json()
  } catch {
    /* 非 JSON 响应 */
  }
  if (!resp.ok) {
    const message = data?.error?.message || `请求失败（HTTP ${resp.status}）`
    const err = new Error(message)
    err.status = resp.status
    err.code = data?.error?.code
    throw err
  }
  return data
}

export const api = {
  health: () => request('/api/health'),
  locations: () => request('/api/locations'),
  edges: () => request('/api/edges'),
  announcements: () => request('/api/announcements'),
  versions: () => request('/api/versions'),
  addLocation: (payload) => request('/api/locations', { method: 'POST', body: JSON.stringify(payload) }),
  addEdge: (payload) => request('/api/edges', { method: 'POST', body: JSON.stringify(payload) }),
  addAnnouncement: (payload) =>
    request('/api/announcements', { method: 'POST', body: JSON.stringify(payload) }),
  withdraw: (id) => request(`/api/announcements/${id}/withdraw`, { method: 'POST' }),
  publish: (note) => request('/api/publish', { method: 'POST', body: JSON.stringify({ note }) }),
  route: (payload) => request('/api/route', { method: 'POST', body: JSON.stringify(payload) }),
  guidance: (no) => request(`/api/guidance/${encodeURIComponent(no)}`),
}

// datetime-local 值（无时区）+ 偏移量（分钟）→ 带偏移 ISO8601
export function withOffset(localValue, offsetMinutes) {
  if (!localValue) return ''
  const sign = offsetMinutes >= 0 ? '+' : '-'
  const abs = Math.abs(offsetMinutes)
  const hh = String(Math.floor(abs / 60)).padStart(2, '0')
  const mm = String(abs % 60).padStart(2, '0')
  return `${localValue}:00${sign}${hh}:${mm}`
}

// UTC ISO → 指定偏移量的 datetime-local 值（供回填展示）
export function utcToLocalInput(utcIso, offsetMinutes) {
  if (!utcIso) return ''
  const norm = utcIso.endsWith('Z') ? utcIso.replace('Z', '+00:00') : utcIso
  const dt = new Date(norm)
  if (Number.isNaN(dt.getTime())) return utcIso
  const shifted = new Date(dt.getTime() + offsetMinutes * 60000)
  const p = (n) => String(n).padStart(2, '0')
  return `${shifted.getUTCFullYear()}-${p(shifted.getUTCMonth() + 1)}-${p(shifted.getUTCDate())}T${p(shifted.getUTCHours())}:${p(shifted.getUTCMinutes())}`
}

export const fmtDistance = (m) =>
  m >= 1000 ? `${(m / 1000).toFixed(2).replace(/\.?0+$/, '')} 公里` : `${m} 米`
