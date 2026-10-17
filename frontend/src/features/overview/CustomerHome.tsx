import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, ChevronRight, ClipboardList, Headphones, MonitorSmartphone } from 'lucide-react'
import { type Actor, listCases, listConversations } from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { StatusBadge, statusLabel } from '../../shared/StatusBadge'
import { isDemoRecord } from '../../shared/servicePresentation'
import { readableError } from '../../shared/errors'

export function CustomerHome({ actor }: { actor: Actor }) {
  const cases = useQuery({ queryKey: queryKeys.cases(actor.tenant_id, actor.actor_id), queryFn: listCases })
  const conversations = useQuery({ queryKey: queryKeys.conversations(actor.tenant_id, actor.actor_id), queryFn: listConversations })

  return <div className="customer-home customer-home-mobile-first">
    <section className="home-hero home-entry-hero">
      <div className="hero-copy">
        <span className="home-eyebrow">ANKER SERVICE</span>
        <h1>售后服务，<br />从对话开始。</h1>
        <p>进入服务后继续已有会话，或明确开始一个新问题。</p>
        <Link className="primary-button home-enter-service" to="/support">
          <Headphones size={19} aria-hidden="true" />进入对话<ArrowRight size={18} aria-hidden="true" />
        </Link>
      </div>
    </section>

    <div className="home-history-grid">
      <section className="surface home-history-section" aria-labelledby="home-conversations-title">
        <div className="panel-title"><div><h2 id="home-conversations-title">历史对话</h2><p>继续查看已保存的 Conversation</p></div>
          <Link to="/support">全部对话<ChevronRight size={15} aria-hidden="true" /></Link></div>
        {conversations.isPending && <p className="empty-note" role="status">正在读取历史对话…</p>}
        {conversations.isError && <p role="alert" className="form-error">{readableError(conversations.error)} <button type="button" onClick={() => void conversations.refetch()}>重试</button></p>}
        {conversations.data?.length === 0 && <div className="overview-empty"><Headphones size={26} aria-hidden="true" /><p>还没有历史对话。</p><Link to="/support">进入对话</Link></div>}
        <ul className="home-record-list">{conversations.data?.slice(0, 3).map(item => <li key={item.id}>
          <Link to={`/support?conversation=${item.id}`}>
            <span className="home-record-icon"><Headphones size={18} aria-hidden="true" /></span>
            <span className="home-record-copy"><strong>{item.title || '新会话'}</strong><small>{statusLabel(item.status)} · {new Date(item.created_at).toLocaleDateString('zh-CN')}</small></span>
            <ChevronRight size={17} aria-hidden="true" />
          </Link>
        </li>)}</ul>
      </section>

      <section className="surface home-history-section" aria-labelledby="home-cases-title">
        <div className="panel-title"><div><h2 id="home-cases-title">服务记录</h2><p>每条记录对应一次 Service Case</p></div>
          <Link to="/cases">全部记录<ChevronRight size={15} aria-hidden="true" /></Link></div>
        {cases.isPending && <p className="empty-note" role="status">正在读取服务记录…</p>}
        {cases.isError && <p role="alert" className="form-error">{readableError(cases.error)} <button type="button" onClick={() => void cases.refetch()}>重试</button></p>}
        {cases.data?.length === 0 && <div className="overview-empty"><ClipboardList size={26} aria-hidden="true" /><p>还没有服务记录。</p><Link to="/support">进入对话后描述问题</Link></div>}
        <ul className="home-record-list">{cases.data?.slice(0, 3).map(item => <li key={item.id}>
          <Link to={`/cases/${item.id}`}>
            <span className="home-record-icon"><ClipboardList size={18} aria-hidden="true" /></span>
            <span className="home-record-copy"><strong>{item.problem_text}</strong><small><StatusBadge value={item.status} /> · {new Date(item.created_at).toLocaleDateString('zh-CN')}{isDemoRecord(item.problem_text) ? ' · 演示' : ''}</small></span>
            <ChevronRight size={17} aria-hidden="true" />
          </Link>
        </li>)}</ul>
      </section>
    </div>

    <Link className="home-device-shortcut" to="/devices">
      <span className="home-device-icon"><MonitorSmartphone size={19} aria-hidden="true" /></span>
      <span><strong>设备档案</strong><small>查看已保存的设备与核验事实</small></span>
      <ChevronRight size={17} aria-hidden="true" />
    </Link>
  </div>
}
