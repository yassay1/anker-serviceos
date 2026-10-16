import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react'
import {
  type Actor, listGuardDecisions, listServicePolicies, overrideGuardDecision, readGuardStats,
} from '../../api/client'
import { queryKeys } from '../../app/queryKeys'
import { readableError } from '../../shared/errors'
import { StatusBadge } from '../../shared/StatusBadge'

function entitySummary(entities: Record<string, unknown>): string {
  const items = (entities.items ?? []) as Array<{ raw: string, grounded: boolean, echoed: boolean }>
  return items.map(e => `${e.raw}${e.echoed ? '(客户原话)' : e.grounded ? '✓' : '✗无据'}`).join('；') || '无硬实体'
}

function verifierSummary(verifier: Record<string, unknown>): string {
  const v = verifier as { status?: string, unaddressed?: string[], promises?: string[] }
  return v.status === 'ok'
    ? `未交代: ${(v.unaddressed ?? []).join('；') || '无'}；无据承诺: ${(v.promises ?? []).join('；') || '无'}`
    : String(v.status)
}

export function GuardPanel({ actor }: { actor: Actor }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState<string | null>(null)
  const key = queryKeys.guard(actor.tenant_id, actor.actor_id)
  const stats = useQuery({ queryKey: [...key, 'stats'], queryFn: readGuardStats, refetchInterval: 5_000 })
  const decisions = useQuery({ queryKey: key, queryFn: listGuardDecisions, refetchInterval: 5_000 })
  const policies = useQuery({ queryKey: [...key, 'policies'], queryFn: listServicePolicies })
  const override = useMutation({
    mutationFn: overrideGuardDecision,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: key })
      void queryClient.invalidateQueries({ queryKey: [...key, 'stats'] })
    },
  })
  const canOverride = actor.role === 'SUPERVISOR' || actor.role === 'ADMIN'
  return <section className="surface knowledge-panel guard-panel">
    <div className="table-toolbar"><span>发布守卫</span>
      <small>答复发布前的接地/覆盖检查；被拦草稿须人工复核</small></div>
    <div className="guard-stats">
      <span><ShieldCheck size={16} /> 放行 {stats.data?.passed ?? '—'}</span>
      <span><ShieldAlert size={16} /> 拦截 {stats.data?.blocked ?? '—'}</span>
      <span><ShieldQuestion size={16} /> 复核发布 {stats.data?.overridden ?? '—'}</span>
    </div>
    {decisions.isError && <p className="form-error" role="alert">{readableError(decisions.error)}</p>}
    <div className="table-scroll" tabIndex={0}><table className="case-table"><thead><tr>
      <th>时间</th><th>判定</th><th>原因</th><th>会话</th><th><span className="visually-hidden">操作</span></th>
    </tr></thead><tbody>
      {decisions.data?.items.map(item => <tr key={item.id}>
        <td><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</time></td>
        <td><StatusBadge value={item.decision} /></td>
        <td><small>{item.reason_codes.join(', ') || '—'}</small></td>
        <td><small>#{item.conversation_id.slice(0, 8)}</small></td>
        <td><button type="button" aria-expanded={open === item.id}
          onClick={() => setOpen(open === item.id ? null : item.id)}>详情</button></td>
        {open === item.id && <tr className="guard-detail"><td colSpan={5}>
          <p><strong>被检答复：</strong>{item.reply_text}</p>
          <p><strong>实体接地：</strong>{entitySummary(item.entities)}</p>
          <p><strong>覆盖检查：</strong>{verifierSummary(item.verifier)}</p>
          {item.decision === 'BLOCKED' && canOverride
            && <button type="button" disabled={override.isPending}
              onClick={() => override.mutate(item.id)}>复核并发布（主管）</button>}
          {item.decision === 'OVERRIDDEN' && <p><small>已由主管复核发布（{item.override_by?.slice(0, 8)}）</small></p>}
        </td></tr>}
      </tr>)}
    </tbody></table></div>
    {override.isError && <p className="form-error" role="alert">{readableError(override.error)}</p>}
    <h4>服务政策表（DMN 式，命中带 rule_id@version）</h4>
    <div className="table-scroll" tabIndex={0}><table className="case-table"><thead><tr>
      <th>规则</th><th>国家</th><th>渠道</th><th>品类</th><th>质保</th><th>允许结局</th><th>状态</th>
    </tr></thead><tbody>
      {policies.data?.map(policy => <tr key={policy.id}>
        <td><small>{policy.rule_id}@v{policy.version}</small></td>
        <td><small>{policy.country}</small></td>
        <td><small>{policy.channel}</small></td>
        <td><small>{policy.product_family}</small></td>
        <td><small>{policy.warranty_state}</small></td>
        <td><small>{((policy.remedies.allowed ?? []) as string[]).join('/')}</small></td>
        <td><StatusBadge value={policy.status === 'ACTIVE' ? 'APPROVED' : 'REJECTED'} label={policy.status} /></td>
      </tr>)}
    </tbody></table></div>
    <p className="table-foot">守卫判定与政策命中均为服务器真实记录；复核发布留审计痕。</p>
  </section>
}
