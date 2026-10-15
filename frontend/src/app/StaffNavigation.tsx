import { Link, NavLink, useLocation } from 'react-router-dom'
import { Home, MessagesSquare, ClipboardList, MonitorSmartphone, ShieldCheck } from 'lucide-react'

export function StaffNavigation() {
  const location = useLocation()
  const overview = location.pathname === '/' || (location.pathname === '/desk' && new URLSearchParams(location.search).get('view') === 'overview')
  return <aside className="staff-navigation" aria-label="客服导航"><h2>客服工作台</h2><nav>
    <Link to="/desk?view=overview" aria-current={overview ? 'page' : undefined} className={overview ? 'selected' : ''}><Home size={20} />工作台</Link>
    <Link to="/desk" aria-current={location.pathname === '/desk' && !overview ? 'page' : undefined} className={location.pathname === '/desk' && !overview ? 'selected' : ''}><MessagesSquare size={20} />服务会话</Link>
    <NavLink to="/cases"><ClipboardList size={20} />服务案例</NavLink>
    <NavLink to="/devices"><MonitorSmartphone size={20} />设备管理</NavLink>
  </nav><div className="staff-rail-note"><ShieldCheck size={25} /><strong>服务有人接续</strong><p>授权访问 · 真实记录<br />人工审阅 · 持续协作</p></div></aside>
}
