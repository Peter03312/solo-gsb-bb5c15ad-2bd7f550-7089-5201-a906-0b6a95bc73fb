import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import VisitorView from './components/VisitorView.jsx'
import AdminDataView from './components/AdminDataView.jsx'
import AdminPublishView from './components/AdminPublishView.jsx'
import './styles.css'

const TABS = [
  { key: 'visitor', label: '🧭 访客指引查询' },
  { key: 'data', label: '🗺️ 地点与通道维护' },
  { key: 'publish', label: '📢 封闭公告与发布' },
]

function App() {
  const [tab, setTab] = useState('visitor')
  return (
    <>
      <header className="topbar">
        <h1>场馆临时封路 · 无障碍通行指引</h1>
        <p>按发布版本与出行时刻计算最短可行路线 · 支持轮椅通行属性 · 指引可凭编号复核</p>
      </header>
      <div className="container">
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.key} className={tab === t.key ? 'active' : ''} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </nav>
        {tab === 'visitor' && <VisitorView />}
        {tab === 'data' && <AdminDataView onChanged={() => {}} />}
        {tab === 'publish' && <AdminPublishView />}
      </div>
    </>
  )
}

createRoot(document.getElementById('root')).render(<App />)
