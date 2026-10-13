import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { ServicePage } from './app/ServicePage'

export function App() {
  return <>
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <header className="site-header"><div className="header-inner">
      <NavLink className="brand" to="/support"><span>售后通</span><small>Anker ServiceOS</small></NavLink>
      <nav aria-label="主要导航"><NavLink to="/support">用户服务</NavLink><NavLink to="/desk">客服工作区</NavLink></nav>
    </div></header>
    <main id="main-content" tabIndex={-1}>
      <Routes>
        <Route path="/" element={<Navigate to="/support" replace />} />
        <Route path="/support" element={<ServicePage />} />
        <Route path="/desk" element={<ServicePage desk />} />
        <Route path="*" element={<section><h1>未找到这个页面</h1><NavLink to="/support">返回用户服务</NavLink></section>} />
      </Routes>
    </main>
    <footer>售后通 · 本地开发体验</footer>
  </>
}
