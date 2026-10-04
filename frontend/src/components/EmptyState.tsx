import type { ReactNode } from 'react'

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state" role="status">
      <h4>{title}</h4>
      {children && <div>{children}</div>}
      {action}
    </div>
  )
}
