/*
  Is the server up, is the AI real or practice (mock), and how new
  enquiries arrive: instantly over the live feed, or by checking every
  30 seconds when the feed isn't available. Each state has a word, not
  just a coloured dot.
*/
import clsx from 'clsx'

import { useAiStatus, useHealth } from '@/hooks/useAnalytics'
import { useLanguage } from '@/hooks/useLanguage'
import { useLiveFeed } from '@/hooks/useLiveFeed'

function Row({ dot, pulse, label, value }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="text-ink-3">{label}</span>
      <span className="inline-flex items-center gap-1.5 font-medium text-ink-2">
        <span className="relative flex size-2">
          {pulse && <span className={clsx('absolute inline-flex size-full animate-ping rounded-full opacity-60 motion-reduce:hidden', dot)} />}
          <span className={clsx('relative inline-flex size-2 rounded-full', dot)} />
        </span>
        {value}
      </span>
    </div>
  )
}

export function StatusFooter() {
  const health = useHealth()
  const ai = useAiStatus()
  const { status } = useLiveFeed()
  const { t } = useLanguage()

  const server = health.isError
    ? { dot: 'bg-critical', value: t('status.unreachable') }
    : health.data
      ? { dot: 'bg-good', value: t('status.online') }
      : { dot: 'bg-warning', value: t('status.checking') }

  const mode = ai.data?.mode === 'real' ? { dot: 'bg-good', value: t('status.claude') } : { dot: 'bg-warning', value: t('status.practice') }

  const updates =
    status === 'live'
      ? { dot: 'bg-good', value: t('status.live'), pulse: true }
      : status === 'connecting'
        ? { dot: 'bg-warning', value: t('status.connecting') }
        : { dot: 'bg-ink-3', value: t('status.every30s') }

  return (
    <div className="space-y-2 rounded-control border border-line bg-surface-sunken/60 p-3">
      <Row label={t('status.server')} dot={server.dot} value={server.value} />
      <Row label={t('status.ai')} dot={mode.dot} value={ai.data ? mode.value : '—'} />
      <Row label={t('status.newEnquiries')} dot={updates.dot} pulse={updates.pulse} value={updates.value} />
    </div>
  )
}
