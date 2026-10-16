// Guidance describes the saved status, without inventing milestones or completion percentages.
export function caseGuidance(status: string) {
  switch (status) {
    case 'RESOLVED': return { title: '问题已解决，查看处理结果', body: '可回看本工单的处理记录，并核对已有的结果信息。', action: '查看结果与核验', anchor: 'case-result' }
    case 'CLOSED': return { title: '服务已关闭，记录仍可回看', body: '查看本次问题、处理记录与已有的核验信息。', action: '回看服务记录', anchor: 'case-progress' }
    case 'WAITING_CUSTOMER': return { title: '等待您补充信息', body: '请查看会话中的具体要求，补充问题描述或图片后继续处理。', action: '补充图片证据', anchor: 'case-evidence' }
    case 'WAITING_EXTERNAL': return { title: '等待外部处理', body: '当前处理结果尚未确认，后续进展以实际服务记录为准。', action: '查看处理记录', anchor: 'case-progress' }
    case 'IN_PROGRESS': return { title: '您的问题正在处理中', body: '可查看处理记录，也可补充有助于定位问题的图片。', action: '查看服务进展', anchor: 'case-progress' }
    default: return { title: '问题已记录，等待进一步处理', body: '您可以补充设备现象与图片，帮助服务人员了解问题。', action: '补充图片证据', anchor: 'case-evidence' }
  }
}

export const isDemoRecord = (text: string | null | undefined) => /演示|模拟|合成|\bmock\b/i.test(text ?? '')
export const shortDate = (value: string) => new Date(value).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
