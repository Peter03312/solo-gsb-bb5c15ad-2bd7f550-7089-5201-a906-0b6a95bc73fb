// 与后端 REST API 交互的统一封装，错误提取 {code, message}
async function request(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 204) return null
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = data.detail || {}
    const err = new Error(detail.message || `请求失败（HTTP ${res.status}）`)
    err.code = detail.code || 'ERROR'
    err.status = res.status
    throw err
  }
  return data
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b),
  del: (p) => request('DELETE', p),
}

// 浏览器本地时间转 ISO（带时区偏移）
export function localToISO(d) {
  const pad = (n) => String(n).padStart(2, '0')
  const off = -d.getTimezoneOffset()
  const sign = off >= 0 ? '+' : '-'
  const oh = Math.floor(Math.abs(off) / 60)
  const om = Math.abs(off) % 60
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours()
  )}:${pad(d.getMinutes())}${sign}${pad(oh)}:${pad(om)}`
}

export function fmtDistance(m) {
  return `${Math.round(m * 10) / 10} 米`
}

// 给定 IANA 时区与本地日期时间字符串（yyyy-MM-ddTHH:mm），生成带偏移的 ISO 串。
// 用迭代法求偏移，可正确处理夏令时；对不存在/重复的墙钟时间就近取有效时刻。
export function zonedToISO(dateTimeLocal, timeZone) {
  if (!dateTimeLocal) return ''
  const [datePart, timePart = '00:00'] = dateTimeLocal.split('T')
  const [y, mo, d] = datePart.split('-').map(Number)
  const [hh, mi] = timePart.split(':').map(Number)
  const wallUtcMs = Date.UTC(y, mo - 1, d, hh || 0, mi || 0, 0)

  const tzWallMs = (utcMs) => {
    const p = Object.fromEntries(
      new Intl.DateTimeFormat('en-US', {
        timeZone,
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
      }).formatToParts(new Date(utcMs)).map((x) => [x.type, x.value])
    )
    return Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute, +p.second)
  }

  // 迭代：actualUtc = wallUtc - offset
  let actualUtc = wallUtcMs
  let offset = tzWallMs(actualUtc) - actualUtc
  for (let i = 0; i < 3; i++) {
    actualUtc = wallUtcMs - offset
    const next = tzWallMs(actualUtc) - actualUtc
    if (next === offset) break
    offset = next
  }
  const offMin = offset / 60000 // offset = 本地墙钟 − UTC，即 UTC 偏移（分钟）
  const sign = offMin >= 0 ? '+' : '-'
  const oh = String(Math.floor(Math.abs(offMin) / 60)).padStart(2, '0')
  const om = String(Math.abs(offMin) % 60).padStart(2, '0')
  return `${datePart}T${timePart.length === 5 ? timePart : timePart + ':00'}${sign}${oh}:${om}`
}

