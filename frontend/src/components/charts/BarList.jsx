/*
  A list of labelled horizontal bars: the simplest honest chart.

  Used for: reply speed vs win rate, the funnel, top services and cars.

  <BarList items={[{ key, label, value, display, sub }]} max={100} highlight="under 5 min" />

  - One series = one colour. `highlight` paints one bar in the brand
    colour and the rest grey ("emphasis"), when one bar is the story.
  - The value is written at the end of each bar, in text colour (not the
    bar colour), so it's readable without hovering.
  - Bars are thin (max 24px), rounded at the far end, square at the start.
*/
import clsx from 'clsx'
import { motion } from 'motion/react'

import { duration, ease } from '@/animations/presets'

export function BarList({ items, max, highlight, color = 'var(--brand)', className }) {
  const top = max ?? Math.max(1, ...items.map((i) => i.value))

  return (
    <ul className={clsx('space-y-3', className)}>
      {items.map((item, index) => {
        const pct = Math.max(0, Math.min(100, (item.value / top) * 100))
        // A per-item colour (e.g. the channel's own colour) keeps identity the same on every chart.
        const own = item.color ?? color
        const fill = highlight == null || highlight === item.key ? own : 'var(--line-strong)'
        return (
          <li key={item.key} title={item.title}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-sm">
              <span className="min-w-0 truncate text-ink-2">
                {item.color && <span aria-hidden className="mr-1.5 inline-block size-2.5 rounded-full align-middle" style={{ backgroundColor: item.color }} />}
                {item.label}
              </span>
              <span className="shrink-0 num font-semibold text-ink">
                {item.display ?? item.value}
                {item.sub && <span className="ml-1.5 font-normal text-ink-3">{item.sub}</span>}
              </span>
            </div>
            <div className="h-2.5 overflow-hidden rounded-r-md bg-surface-sunken">
              <motion.div
                className="h-full rounded-r-md"
                style={{ backgroundColor: fill, transformOrigin: 'left' }}
                initial={{ scaleX: 0 }}
                animate={{ scaleX: pct / 100 }}
                transition={{ duration: duration.slow, ease: ease.out, delay: index * 0.05 }}
              />
            </div>
          </li>
        )
      })}
    </ul>
  )
}
