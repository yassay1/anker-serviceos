const labels: Record<string, string> = {
  ACTIVE: '进行中', ARCHIVED: '已归档', OPEN: '待处理', ASSIGNED: '已接管',
  IN_PROGRESS: '处理中', WAITING_CUSTOMER: '等待客户', WAITING_EXTERNAL: '等待外部处理',
  RESOLVED: '已解决', CLOSED: '已关闭', DRAFT: '待审阅', APPROVED: '已批准',
  REJECTED: '已拒绝', COMPLETED: '已完成', CANCELLED: '已取消',
  VERIFIED: '已核验', UNVERIFIED: '待核验', CANDIDATE: '待核验', RETRACTED: '已撤销',
  AI_LEAD: 'AI 主导', CO_SERVICE: '共同服务', HUMAN_LEAD: '真人主导',
  AI_AUTO: '授权自动回复', AI_REVIEW_REQUIRED: '人工审阅后回复', HUMAN_ONLY: '仅人工回复',
}

export const statusLabel = (value: string) => labels[value] ?? value

export function StatusBadge({ value, label }: { value: string, label?: string }) {
  const tone = ['VERIFIED', 'RESOLVED', 'COMPLETED', 'APPROVED'].includes(value) ? 'success'
    : ['UNVERIFIED', 'CANDIDATE', 'WAITING_CUSTOMER', 'WAITING_EXTERNAL', 'DRAFT', 'OPEN'].includes(value) ? 'warning'
    : ['REJECTED', 'RETRACTED'].includes(value) ? 'danger' : 'neutral'
  return <span className={`status-badge ${tone}`}>{label ?? statusLabel(value)}</span>
}
