/*
  A headline number: label · value · change vs the previous period.

  <StatTile label="Revenue" value={2101500} format={inrShort}
            change={12.4} goodWhenUp hint="vs previous 30 days" />

  The change is coloured by whether it's GOOD for the shop (leads up =
  good, reply time up = bad), and always has an arrow and a sign, so it
  never depends on colour alone. No earlier data → no fake "0%".
*/
import clsx from 'clsx'
import { Minus, TrendingDown, TrendingUp } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { CountUp } from '@/components/ui/CountUp'

export function StatTile({ label, value, format, change, goodWhenUp = true, hint, icon: Icon, footer, className }) {
  let delta = null
  if (change != null) {
    const flat = Math.abs(change) < 0.5
    const good = flat ? null : change > 0 === goodWhenUp
    const Arrow = flat ? Minus : change > 0 ? TrendingUp : TrendingDown
    delta = (
      <span
        className={clsx(
          'inline-flex items-center gap-1 text-xs font-semibold',
          good === null ? 'text-ink-3' : good ? 'text-good-ink' : 'text-critical-ink',
        )}
      >
        <Arrow aria-hidden className="size-3.5" />
        {change > 0 ? '+' : ''}
        {change.toFixed(1)}%
      </span>
    )
  }

  return (
    <Card className={clsx('flex flex-col', className)}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-ink-3">{label}</p>
        {Icon && <Icon aria-hidden className="size-4 text-ink-3" />}
      </div>
      <p className="mt-2 text-3xl font-bold tracking-tight text-ink">
        {value == null ? '—' : <CountUp value={value} format={format} />}
      </p>
      <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-3">
        {delta}
        {hint && <span>{hint}</span>}
      </p>
      {footer && <div className="mt-3 border-t border-line pt-3 text-sm">{footer}</div>}
    </Card>
  )
}
