/*
  Is the server up, is the AI real or practice (mock), and how new
  enquiries arrive: instantly over the live feed, or by checking every
  30 seconds when the feed isn't available. Each state has a word, not
  just a coloured dot.
*/
import clsx from 'clsx'

import { useAiStatus, useHealth } from '@/hooks/useAnalytics'
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

  const server = health.isError
    ? { dot: 'bg-critical', value: 'Unreachable' }
    : health.data
      ? { dot: 'bg-good', value: 'Online' }
      : { dot: 'bg-warning', value: 'Checking…' }

  const mode = ai.data?.mode === 'real' ? { dot: 'bg-good', value: 'Claude' } : { dot: 'bg-warning', value: 'Practice' }

  const updates =
    status === 'live'
      ? { dot: 'bg-good', value: 'Live', pulse: true }
      : status === 'connecting'
        ? { dot: 'bg-warning', value: 'Connecting…' }
        : { dot: 'bg-ink-3', value: 'Every 30 s' }

  return (
    <div className="space-y-2 rounded-control border border-line bg-surface-sunken/60 p-3">
      <Row label="Server" dot={server.dot} value={server.value} />
      <Row label="AI" dot={mode.dot} value={ai.data ? mode.value : '—'} />
      <Row label="New enquiries" dot={updates.dot} pulse={updates.pulse} value={updates.value} />
    </div>
  )
}
