import { type FormEvent } from 'react'

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
    <label htmlFor="message-draft">{desk ? '回复客户' : '描述你的问题'}</label>
    <textarea id="message-draft" value={draft} maxLength={8000} rows={3}
      onChange={(event) => onDraft(event.target.value)} disabled={!active}
      placeholder={desk ? '输入回复；可勾选为内部备注' : '例如：充电器连接后指示灯没有亮…'} />
    {desk && <label className="checkbox-label"><input type="checkbox" checked={internal}
      onChange={(event) => onInternal(event.target.checked)} /> 仅客服可见的内部备注</label>}
    <div className="composer-foot">
      <p>{desk ? '公开回复会显示给客户。' : '消息保存后可刷新查看；自动回复取决于本地 Worker 与模型配置。'}</p>
      <button type="submit" className="primary-button" disabled={!draft.trim() || !active}>发送消息</button>
    </div>
  </form>
}
