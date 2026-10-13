import { type FormEvent } from 'react'
import { Send, LockKeyhole } from 'lucide-react'

export function MessageComposer({ desk, active, draft, internal, onDraft, onInternal, onSubmit }: {
  desk: boolean
  active: boolean
  draft: string
  internal: boolean
  onDraft: (value: string) => void
  onInternal: (value: boolean) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}) {
  return <form className="composer" onSubmit={onSubmit}>
    <div className="composer-heading"><label htmlFor="message-draft">{desk ? '回复客户' : '描述你的问题'}</label>{internal && desk && <span className="private-tag"><LockKeyhole size={12} aria-hidden="true" />内部备注</span>}</div>
    <textarea id="message-draft" value={draft} maxLength={8000} rows={3}
      onChange={(event) => onDraft(event.target.value)} disabled={!active}
      placeholder={desk ? '输入回复；可勾选为内部备注' : '例如：充电器连接后指示灯没有亮…'} />
    {desk && <label className="checkbox-label"><input type="checkbox" checked={internal}
      onChange={(event) => onInternal(event.target.checked)} /> 仅客服可见的内部备注</label>}
    <div className="composer-foot">
      <p>{!active ? '此会话已归档，无法继续发送。' : desk ? internal ? '此消息仅客服可见。' : '公开回复会显示给客户。' : '保存后可继续查看；回复以实际服务处理结果为准。'}</p>
      <button type="submit" className="primary-button" disabled={!draft.trim() || !active}><Send size={15} aria-hidden="true" />发送消息</button>
    </div>
  </form>
}
