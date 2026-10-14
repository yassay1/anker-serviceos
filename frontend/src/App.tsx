import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { ServicePage } from './app/ServicePage'
import { Headphones, MessagesSquare, MonitorSmartphone, ShieldCheck } from 'lucide-react'

export function App() {
  return <>
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <header className="site-header"><div className="header-inner">
      <NavLink className="brand" to="/support"><ShieldCheck aria-hidden="true" /><span>售后通</span><small>Anker ServiceOS</small></NavLink>
      <nav aria-label="主要导航"><NavLink to="/support"><Headphones aria-hidden="true" />用户服务</NavLink><NavLink to="/desk"><MessagesSquare aria-hidden="true" />客服工作区</NavLink><NavLink to="/cases">服务案例</NavLink><NavLink to="/devices"><MonitorSmartphone aria-hidden="true" />设备档案</NavLink></nav>
    </div></header>
    <main id="main-content" tabIndex={-1}>
      <Routes>
        <Route path="/" element={<Navigate to="/support" replace />} />
        <Route path="/support" element={<ServicePage />} />
        <Route path="/desk" element={<ServicePage desk />} />
        <Route path="/devices" element={<ServicePage devices />} />
        <Route path="/devices/:id" element={<ServicePage devices />} />
        <Route path="/cases" element={<ServicePage cases />} />
        <Route path="/cases/:id" element={<ServicePage cases />} />
        <Route path="*" element={<section><h1>未找到这个页面</h1><NavLink to="/support">返回用户服务</NavLink></section>} />
      </Routes>
    </main>
    <footer><ShieldCheck size={14} aria-hidden="true" />售后通 · 服务记录按当前账号授权展示</footer>
  </>
}
