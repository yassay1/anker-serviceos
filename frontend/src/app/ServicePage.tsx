import { useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { NavLink, useSearchParams } from 'react-router-dom'
import { type Actor, loginLocal, logout, readActor } from '../api/client'
import { ConversationWorkspace } from '../features/conversation/ConversationWorkspace'
import { readableError } from '../shared/errors'
import { ConnectionStatus } from '../shared/ConnectionStatus'
import { queryKeys } from './queryKeys'
import { DevicesWorkspace } from '../features/devices/DevicesWorkspace'
import { CasesWorkspace } from '../features/cases/CasesWorkspace'
import { LogOut, ShieldCheck } from 'lucide-react'
import { CustomerHome } from '../features/overview/CustomerHome'
import { DeskOverview } from '../features/overview/DeskOverview'
import { StaffNavigation } from './StaffNavigation'

function LoginPanel() {
  const queryClient = useQueryClient()
  const [username, setUsername] = useState('customer-a')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const actor = await loginLocal(username, password)
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'actor' })
      queryClient.setQueryData(queryKeys.actor, actor)
      setPassword('')
    } catch (failure) {
      setError(readableError(failure))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="login-card" aria-labelledby="login-title">
      <div className="login-symbol"><ShieldCheck size={28} aria-hidden="true" /></div>
      <h1 id="login-title">进入售后通</h1>
      <p>使用本地测试身份查看真实保存的会话。此登录入口仅在开发环境启用。</p>
      <form onSubmit={(event) => void submit(event)}>
        <label htmlFor="account">体验身份</label>
        <select id="account" value={username} onChange={(event) => setUsername(event.target.value)}>
          <option value="customer-a">客户 A</option>
          <option value="customer-b">客户 B</option>
          <option value="staff">客服</option>
          <option value="supervisor">主管</option>
          <option value="other-tenant">另一租户客户</option>
        </select>
        <label htmlFor="password">本地体验密码</label>
        <input id="password" type="password" autoComplete="current-password" value={password}
          onChange={(event) => setPassword(event.target.value)} required />
        {error && <p className="form-error" role="alert">{error}</p>}
        <button type="submit" className="primary-button" disabled={busy}>{busy ? '正在进入…' : '进入工作区'}</button>
      </form>
      <p className="form-hint">体验密码见本项目本地配置说明。请勿输入真实客户或设备资料。</p>
      <ConnectionStatus />
    </section>
  )
}

export function AccountHeader({ actor }: { actor: Actor }) {
  const queryClient = useQueryClient()
  const [error, setError] = useState('')

  async function signOut() {
    try {
      await logout()
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'actor' })
      queryClient.setQueryData(queryKeys.actor, null)
    } catch (failure) {
      setError(readableError(failure))
    }
  }

  return (
    <div className="account-strip">
      <span className="account-avatar" aria-hidden="true">{actor.display_name.slice(0, 1)}</span>
      <span>{actor.display_name}<small>{actor.kind === 'STAFF' ? '客服' : '客户'}</small></span>
      <button type="button" onClick={() => void signOut()}><LogOut size={15} aria-hidden="true" />退出登录</button>
      {error && <span className="form-error" role="alert">{error}</span>}
    </div>
  )
}

export function ServicePage({ desk = false, devices = false, cases = false, home = false }: { desk?: boolean, devices?: boolean, cases?: boolean, home?: boolean }) {
  const [searchParams] = useSearchParams()
  const actor = useQuery({ queryKey: queryKeys.actor, queryFn: readActor, retry: false, staleTime: 0 })
  if (actor.isPending) return <p className="loading-state">正在确认登录状态…</p>
  if (actor.isError) return <section className="access-note" role="alert">
    <h1>暂时无法确认登录状态</h1>
    <p>{readableError(actor.error)}</p>
    <button type="button" onClick={() => void actor.refetch()}>重新检查</button>
    <ConnectionStatus />
  </section>
  if (!actor.data) return <LoginPanel />
  if (desk && actor.data.kind !== 'STAFF') return <section className="access-note">
    <h1>此页面仅供客服使用</h1><p>当前身份是客户，请使用用户服务入口。</p><NavLink to="/support">返回用户服务</NavLink>
  </section>
  if (!home && !desk && !devices && !cases && actor.data.kind === 'STAFF') return <section className="access-note">
    <h1>已以客服身份登录</h1><p>请到客服工作区查看会话。</p><NavLink to="/desk">前往客服工作区</NavLink>
  </section>
  const identity = `${actor.data.tenant_id}:${actor.data.actor_id}:${actor.data.kind}`
  return <div className={`service-shell ${actor.data.kind === 'STAFF' ? 'staff-shell' : 'customer-shell'}`}>
    {actor.data.kind === 'STAFF' && <StaffNavigation />}
    <div className="service-content">{home ? actor.data.kind === 'STAFF' ? <DeskOverview key={identity} actor={actor.data} /> : <CustomerHome key={identity} actor={actor.data} /> : desk && searchParams.get('view') === 'overview' ? <DeskOverview key={identity} actor={actor.data} /> : cases ? <CasesWorkspace key={`cases:${identity}`} actor={actor.data} /> : devices ? <DevicesWorkspace key={`devices:${identity}`} actor={actor.data} /> : <ConversationWorkspace key={`conversation:${identity}:${desk}`} actor={actor.data} desk={desk} />}</div>
  </div>
}
