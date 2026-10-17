import { NavLink, Route, Routes } from 'react-router-dom'
import { AccountHeader, ServicePage } from './app/ServicePage'
import { ShieldCheck } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { readActor } from './api/client'
import { queryKeys } from './app/queryKeys'

export function App() {
  const actor = useQuery({ queryKey: queryKeys.actor, queryFn: readActor, retry: false, staleTime: 0 })
  const staff = actor.data?.kind === 'STAFF'
  return <div className={staff ? 'app staff-app' : 'app'}>
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <header className="site-header"><div className="header-inner">
      <NavLink className="brand" to="/" aria-label="售后通首页"><span>售后通</span><small>AI 驱动的售后服务平台</small></NavLink>
      {actor.data && <AccountHeader key={`${actor.data.tenant_id}:${actor.data.actor_id}`} actor={actor.data} />}
    </div></header>
    <main id="main-content" tabIndex={-1}>
      <Routes>
        <Route path="/" element={<ServicePage home />} />
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
  </div>
}
