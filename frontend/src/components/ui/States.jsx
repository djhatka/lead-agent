/*
  What a page shows when there's nothing to show yet, or something failed.
  Both always say what happened and what to do next.
*/
import clsx from 'clsx'
import { CloudOff, Inbox, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { useLanguage } from '@/hooks/useLanguage'

export function ErrorState({ error, onRetry, title }) {
  const { t } = useLanguage()
  return (
    <Card role="alert" className="flex flex-col items-center gap-3 py-10 text-center">
      <CloudOff aria-hidden className="size-9 text-critical-ink" />
      <div>
        <h2 className="font-semibold text-ink">{title ?? t('common.couldntLoad')}</h2>
        <p className="mt-1 max-w-md text-sm text-ink-2">{error?.message ?? t('common.somethingWrong')}</p>
      </div>
      {onRetry && (
        <Button icon={RefreshCw} onClick={onRetry}>
          {t('common.tryAgain')}
        </Button>
      )}
    </Card>
  )
}

/** The same, for a part of a card (a card inside a card would look broken). */
export function InlineError({ error, onRetry, className }) {
  const { t } = useLanguage()
  return (
    <div role="alert" className={clsx('flex flex-col items-center gap-2 py-6 text-center', className)}>
      <CloudOff aria-hidden className="size-7 text-critical-ink" />
      <p className="max-w-sm text-sm text-ink-2">{error?.message ?? t('common.somethingWrong')}</p>
      {onRetry && (
        <Button size="sm" icon={RefreshCw} onClick={onRetry}>
          {t('common.tryAgain')}
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
