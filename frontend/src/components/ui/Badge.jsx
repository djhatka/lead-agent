/*
  Small labels: a lead's channel, mood, priority and status.

  Meaning is never carried by colour alone: every badge has a word, and
  moods and priorities also have an icon (for colour-blind users, and for
  printing in black and white).
*/
import clsx from 'clsx'

import { channel, PRIORITIES, SENTIMENTS, STATUSES } from '@/styles/tokens'

// Written out in full so Tailwind can find every class.
const TONES = {
  neutral: 'bg-surface-sunken text-ink-2',
  brand: 'bg-brand-soft text-brand',
  accent: 'bg-accent-soft text-accent-ink',
  good: 'bg-good-soft text-good-ink',
  warning: 'bg-warning-soft text-warning-ink',
  serious: 'bg-serious-soft text-serious-ink',
  critical: 'bg-critical-soft text-critical-ink',
}

export function Badge({ tone = 'neutral', icon: Icon, className, children }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        TONES[tone],
        className,
      )}
    >
      {Icon && <Icon aria-hidden className="size-3.5" />}
      {children}
    </span>
  )
}

/** Channel: coloured dot + icon + name. The colour marks identity; the text stays in ink. */
export function ChannelBadge({ source, className }) {
  const ch = channel(source)
  const Icon = ch.icon
  return (
    <span className={clsx('inline-flex items-center gap-1.5 text-sm text-ink-2 whitespace-nowrap', className)}>
      <span aria-hidden className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: ch.color }} />
      <Icon aria-hidden className="size-3.5 text-ink-3" />
      {ch.label}
    </span>
  )
}

export function SentimentBadge({ sentiment }) {
  const s = SENTIMENTS[sentiment]
  if (!s) return null
  return (
    <Badge tone={s.tone} icon={s.icon}>
      {s.label}
    </Badge>
  )
}

/** 🔥 Hot breathes gently so it always stands out (still, if the device asks for less motion). */
export function PriorityBadge({ priority }) {
  const p = PRIORITIES[priority]
  if (!p) return null
  return (
    <Badge tone={p.tone} icon={p.icon} className={priority === 'hot' ? 'hot-pulse' : undefined}>
      {p.label}
    </Badge>
  )
}

export function StatusBadge({ status }) {
  const s = STATUSES[status] ?? { label: status, tone: 'neutral' }
  return <Badge tone={s.tone}>{s.label}</Badge>
}

/** Any status from a { key: { label, tone, icon } } map, e.g. POST_STATUSES. */
export function StateBadge({ map, value, className }) {
  const s = map[value] ?? { label: value, tone: 'neutral' }
  return (
    <Badge tone={s.tone} icon={s.icon} className={className}>
      {s.label}
    </Badge>
  )
}
