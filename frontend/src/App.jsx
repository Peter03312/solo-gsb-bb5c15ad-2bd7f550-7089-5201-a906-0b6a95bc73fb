import { useState } from 'react'
import VisitorView from './components/VisitorView.jsx'
import OperatorView from './components/OperatorView.jsx'

export default function App() {
  const [tab, setTab] = useState('visitor')
  return (
    <>
      <header className="topbar">
        <h1>♿ 场馆临时封路 · 无障碍通行指引</h1>
        <p>按发布版本与出行时刻计算可行最短路线 · 封闭区间左闭右开，重叠公告取并集</p>
      </header>
      <div className="container">
        <div className="tabs">
          <button className={tab === 'visitor' ? 'active' : ''} onClick={() => setTab('visitor')}>
            访客问路
          </button>
          <button className={tab === 'operator' ? 'active' : ''} onClick={() => setTab('operator')}>
            运营管理
          </button>
        </div>
        {tab === 'visitor' ? <VisitorView /> : <OperatorView />}
      </div>
    </>
  )
}
