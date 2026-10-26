/*
  What a page shows when there's nothing to show yet, or something failed.
  Both always say what happened and what to do next.
*/
import clsx from 'clsx'
import { CloudOff, Inbox, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'

export function ErrorState({ error, onRetry, title = "Couldn't load this" }) {
  return (
    <Card role="alert" className="flex flex-col items-center gap-3 py-10 text-center">
      <CloudOff aria-hidden className="size-9 text-critical-ink" />
      <div>
        <h2 className="font-semibold text-ink">{title}</h2>
        <p className="mt-1 max-w-md text-sm text-ink-2">{error?.message ?? 'Something went wrong.'}</p>
      </div>
      {onRetry && (
        <Button icon={RefreshCw} onClick={onRetry}>
          Try again
        </Button>
      )}
    </Card>
  )
}

/** The same, for a part of a card (a card inside a card would look broken). */
export function InlineError({ error, onRetry, className }) {
  return (
    <div role="alert" className={clsx('flex flex-col items-center gap-2 py-6 text-center', className)}>
      <CloudOff aria-hidden className="size-7 text-critical-ink" />
      <p className="max-w-sm text-sm text-ink-2">{error?.message ?? 'Something went wrong.'}</p>
      {onRetry && (
        <Button size="sm" icon={RefreshCw} onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

export function EmptyState({ icon: Icon = Inbox, title, children, action, className }) {
  return (
    <div className={clsx('flex flex-col items-center gap-2 py-10 text-center', className)}>
      <Icon aria-hidden className="size-9 text-ink-3" />
      <h3 className="font-semibold text-ink">{title}</h3>
      {children && <p className="max-w-md text-sm text-ink-2">{children}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
