import { type FormEvent, type ReactNode, useEffect, useRef, useState } from 'react'
import { Send, LockKeyhole, Mic, Square, ImagePlus, Zap } from 'lucide-react'

const replyTemplates = [
  ['补充问题信息', '请描述设备型号、出现问题的具体情况，以及已经尝试过的处理方法。'],
  ['请求设备照片', '请补充设备外观、接口和型号标签的清晰照片，方便我们核对设备信息。'],
  ['确认处理结果', '请问按照刚才的方法操作后，问题是否已解决？如果仍有异常，请告诉我们实际情况。'],
]

type Recognition = {
  lang: string, continuous: boolean, interimResults: boolean,
  onresult: ((event: { results: ArrayLike<{ 0?: { transcript: string } }> }) => void) | null,
  onerror: ((event: { error: string }) => void) | null, onend: (() => void) | null,
  start: () => void, stop: () => void, abort: () => void,
}
type RecognitionWindow = Window & {
  SpeechRecognition?: new () => Recognition,
  webkitSpeechRecognition?: new () => Recognition,
}

export function MessageComposer({ desk, active, draft, internal, onDraft, onInternal, onSubmit, onAttach,
  className = '', draftLabel, draftReadOnly = false, footNote, footerLink, submitLabel }: {
  desk: boolean
  active: boolean
  draft: string
  internal: boolean
  onDraft: (value: string) => void
  onInternal: (value: boolean) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onAttach?: () => void
  className?: string
  draftLabel?: string
  draftReadOnly?: boolean
  footNote?: string
  footerLink?: ReactNode
  submitLabel?: string
}) {
  const recognition = useRef<Recognition | null>(null)
  const [listening, setListening] = useState(false)
  const [voiceError, setVoiceError] = useState('')
  const nativeWindow = window as RecognitionWindow
  const Speech = nativeWindow.SpeechRecognition ?? nativeWindow.webkitSpeechRecognition
  useEffect(() => () => {
    const current = recognition.current
    if (current) {
      current.onresult = null; current.onerror = null; current.onend = null
      current.abort()
    }
  }, [])
  useEffect(() => {
    if (!active) recognition.current?.stop()
  }, [active])

  function toggleVoice() {
    if (recognition.current) { recognition.current.stop(); return }
    if (!Speech || !active) return
    const current = new Speech()
    const before = draft.trimEnd()
    current.lang = 'zh-CN'; current.continuous = true; current.interimResults = true
    current.onresult = event => {
      const text = Array.from(event.results).map(result => result[0]?.transcript ?? '').join('')
      onDraft((before + (before ? '\n' : '') + text).slice(0, 8000))
    }
    current.onerror = event => {
      if (event.error !== 'aborted') setVoiceError(event.error === 'not-allowed' || event.error === 'service-not-allowed'
        ? '麦克风或语音服务未获授权，请在浏览器中允许后重试。'
        : event.error === 'no-speech' ? '没有听清声音，请靠近麦克风重试。'
          : '浏览器语音识别暂不可用，请检查麦克风和网络，或直接输入文字。')
    }
    current.onend = () => { recognition.current = null; setListening(false) }
    setVoiceError(''); recognition.current = current
    try { current.start(); setListening(true) }
    catch { recognition.current = null; setVoiceError('无法启动语音识别，请检查浏览器权限后重试。') }
  }

  return <form className={`composer ${className} ${desk && internal ? 'is-internal' : ''}`} onSubmit={event => {
    if (recognition.current) { event.preventDefault(); return }
    onSubmit(event)
  }}>
    <div className="composer-heading">{desk ? <div className="composer-tabs"><button type="button" aria-pressed={!internal} onClick={() => onInternal(false)}>回复客户</button><button type="button" aria-pressed={internal} onClick={() => onInternal(true)}>内部备注</button></div> : <label htmlFor="message-draft">{draftLabel ?? '描述你的问题'}</label>}{internal && desk && <span className="private-tag"><LockKeyhole size={12} aria-hidden="true" />仅客服可见</span>}</div>
    <textarea id="message-draft" aria-label={desk ? '回复客户' : draftLabel ?? '描述你的问题'} value={draft} maxLength={8000} rows={3}
      onChange={(event) => onDraft(event.target.value)} disabled={!active} readOnly={listening || draftReadOnly}
      placeholder={desk ? internal ? '输入内部备注，仅授权客服可见…' : '请输入回复内容，可上传图片，或使用快捷回复…' : '例如：充电器连接后指示灯没有亮…'} />
    <div className="composer-tools">
      <button type="button" onClick={toggleVoice} disabled={!active || draftReadOnly || !Speech} aria-pressed={listening}
        title={Speech ? '将语音识别为文字，确认后再发送' : '当前浏览器不支持语音识别，可尝试 Chrome 或 Edge'}>
        {listening ? <Square size={16} /> : <Mic size={17} />}{listening ? '停止识别' : '语音输入'}</button>
      {onAttach && <button type="button" disabled={!active || listening || draftReadOnly} onClick={onAttach}><ImagePlus size={17} />上传图片</button>}
      {desk && <details className="reply-templates"><summary><Zap size={17} />快捷回复</summary><div>{replyTemplates.map(([label, text]) => <button type="button" key={label} disabled={!active || listening} onClick={event => { onDraft(draft ? `${draft}\n${text}`.slice(0, 8000) : text); event.currentTarget.closest('details')?.removeAttribute('open'); document.getElementById('message-draft')?.focus() }}>{label}</button>)}<small>填入草稿，确认后发送</small></div></details>}
      <span role="status" className={`voice-status ${listening ? 'is-listening' : ''}`}>{listening ? '正在听，请说话…停止后可编辑并发送' : !Speech ? '当前浏览器不支持语音识别' : '语音由浏览器识别，部分浏览器需联网处理'}</span>
    </div>
    {voiceError && <p className="form-error" role="alert">{voiceError}</p>}
    <div className="composer-foot">
      <p>{!active ? '此会话已归档，无法继续发送。' : footNote ?? (desk ? internal ? '此消息仅客服可见。' : '公开回复会显示给客户。' : '保存后可继续查看；回复以实际服务处理结果为准。')}</p>
      {footerLink}
      <button type="submit" className="primary-button" disabled={!draft.trim() || !active || listening}><Send size={15} aria-hidden="true" />{submitLabel ?? (desk ? internal ? '保存内部备注' : '发送回复' : '发送消息')}</button>
    </div>
  </form>
}
