import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

export function CustomerAvatar({ id, label = '客' }: { id: string, label?: string }) {
  const tone = [...id].reduce((value, char) => value + char.charCodeAt(0), 0) % 4
  return <span className={`customer-avatar avatar-tone-${tone}`} aria-hidden="true">{label.slice(0, 1)}</span>
}

export function SummaryCard({ icon: Icon, title, value, note, tone = 'blue' }: {
  icon: LucideIcon, title: string, value: ReactNode, note?: string, tone?: string,
}) {
  return <section className={`staff-summary-card tone-${tone}`}><span className="summary-icon"><Icon size={25} strokeWidth={1.8} /></span>
    <div><h2>{title}</h2><strong>{value}</strong>{note && <small>{note}</small>}</div>
  </section>
}

export function StaffCard({ icon: Icon, title, children, action, className = '' }: {
  icon?: LucideIcon, title: string, children: ReactNode, action?: ReactNode, className?: string,
}) {
  return <section className={`staff-card ${className}`}><header className="staff-card-heading"><h2>{Icon && <Icon size={20} aria-hidden="true" />}{title}</h2>{action}</header>{children}</section>
}

export const customerLabel = (id: string) => `客户 #${id.slice(0, 8)}`
