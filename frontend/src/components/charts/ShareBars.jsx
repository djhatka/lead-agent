/*
  "Share of leads" vs "share of revenue", one thin 100% bar each, split by channel.

  It answers the shop's key question in one look: a channel with a wide
  slice on top but a thin slice below brings many enquiries but little
  money (e.g. Instagram).

  - Channels always in the validated colour order, separated by a 2px gap.
  - A percentage is written inside a slice only when it fits; otherwise it
    is in the tooltip, the legend and the table.
  - Hover or keyboard-focus any slice for its exact numbers.
  - "Table" switch shows the same numbers as a plain table.
*/
import clsx from 'clsx'
import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'

import { duration, ease } from '@/animations/presets'
import { channel, CHANNELS, inr } from '@/styles/tokens'

const MIN_LABEL_PCT = 9 // narrower slices keep their number in the tooltip

function Segment({ c, pct, index, detail, onShow, onHide }) {
  return (
    <motion.button
      type="button"
      initial={{ scaleX: 0 }}
      animate={{ scaleX: 1 }}
      transition={{ duration: duration.slow, ease: ease.out, delay: index * 0.04 }}
      style={{ flexGrow: pct, flexBasis: 0, backgroundColor: c.color, transformOrigin: 'left' }}
      onPointerEnter={onShow}
      onPointerLeave={onHide}
      onFocus={onShow}
      onBlur={onHide}
      aria-label={`${c.label}: ${pct.toFixed(1)}% ${detail}`}
      className="relative h-full min-w-[3px] cursor-default transition-[filter] duration-150 first:rounded-l-md last:rounded-r-md hover:brightness-110 focus-visible:brightness-110"
    >
      {pct >= MIN_LABEL_PCT && (
        <span className="pointer-events-none absolute inset-0 flex items-center justify-center text-xs font-semibold text-white [text-shadow:0_1px_2px_rgb(0_0_0/0.35)]">
          {Math.round(pct)}%
        </span>
      )}
    </motion.button>
  )
}

function Row({ title, total, shareKey, valueOf, sources, onShow, onHide }) {
  const rows = CHANNELS.map((c) => ({ c, s: sources.find((s) => s.source === c.key) })).filter(
    ({ s }) => s && s[shareKey] > 0,
  )
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between text-sm">
        <span className="font-medium text-ink">{title}</span>
        <span className="text-ink-3">{total}</span>
      </div>
      <div className="flex h-9 gap-[2px]">
        {rows.map(({ c, s }, i) => (
          <Segment
            key={c.key}
            c={c}
            pct={s[shareKey]}
            index={i}
            detail={title.toLowerCase()}
            onShow={() => onShow({ c, s, title, value: valueOf(s), pct: s[shareKey] })}
            onHide={onHide}
          />
        ))}
      </div>
    </div>
  )
}

export function ShareBars({ sources, totalLeads, totalRevenue }) {
  const [tip, setTip] = useState(null)
  const [asTable, setAsTable] = useState(false)

  return (
    <div>
      <div className="mb-4 flex justify-end">
        <button
          type="button"
          onClick={() => setAsTable((v) => !v)}
          aria-pressed={asTable}
          className="cursor-pointer rounded-full border border-line px-3 py-1 text-xs font-medium text-ink-2 hover:bg-surface-sunken"
        >
          {asTable ? 'Show chart' : 'Show table'}
        </button>
      </div>

      {asTable ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-ink-3">
              <th className="py-2 font-medium">Channel</th>
              <th className="py-2 text-right font-medium">Enquiries</th>
              <th className="py-2 text-right font-medium">Share</th>
              <th className="py-2 text-right font-medium">Revenue</th>
              <th className="py-2 text-right font-medium">Share</th>
            </tr>
          </thead>
          <tbody className="num divide-y divide-line">
            {sources.map((s) => (
              <tr key={s.source}>
                <td className="py-2 text-ink">{channel(s.source).label}</td>
                <td className="py-2 text-right">{s.leads}</td>
                <td className="py-2 text-right">{s.lead_share_pct}%</td>
                <td className="py-2 text-right">{inr(s.revenue)}</td>
                <td className="py-2 text-right">{s.revenue_share_pct}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="relative space-y-5">
          <Row
            title="Enquiries"
            total={`${totalLeads.toLocaleString('en-IN')} enquiries`}
            shareKey="lead_share_pct"
            valueOf={(s) => `${s.leads} ${s.leads === 1 ? 'enquiry' : 'enquiries'}`}
            sources={sources}
            onShow={setTip}
            onHide={() => setTip(null)}
          />
          <Row
            title="Revenue"
            total={inr(totalRevenue, { short: true })}
            shareKey="revenue_share_pct"
            valueOf={(s) => inr(s.revenue)}
            sources={sources}
            onShow={setTip}
            onHide={() => setTip(null)}
          />

          <AnimatePresence>
            {tip && (
              <motion.div
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: duration.fast }}
                role="status"
                className="pointer-events-none absolute -top-12 left-1/2 z-10 -translate-x-1/2 rounded-control border border-line bg-surface-raised px-3 py-2 text-xs shadow-pop"
              >
                <span className="font-semibold text-ink">{tip.value}</span>
                <span className="text-ink-3"> · {tip.pct.toFixed(1)}% of {tip.title.toLowerCase()}</span>
                <span className="ml-2 inline-flex items-center gap-1.5 text-ink-2">
                  <span className="h-0.5 w-3 rounded" style={{ backgroundColor: tip.c.color }} />
                  {tip.c.label}
                </span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Legend: always shown, so colour is never the only key */}
      {!asTable && (
        <ul className={clsx('mt-5 flex flex-wrap gap-x-4 gap-y-2 text-xs text-ink-2')}>
          {CHANNELS.filter((c) => sources.some((s) => s.source === c.key)).map((c) => (
            <li key={c.key} className="inline-flex items-center gap-1.5">
              <span aria-hidden className="size-2.5 rounded-sm" style={{ backgroundColor: c.color }} />
              {c.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
