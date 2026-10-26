/*
  Leads and jobs won per day, as two lines (leads with a soft wash).

  - One y-axis only (both series are counts of leads).
  - Hover anywhere: a thin vertical line snaps to the nearest day and the
    tooltip lists both numbers for that day, value first.
  - Legend always shown (2 series). Gridlines are faint solid hairlines.
*/
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { useChartColors } from '@/hooks/useChartColors'

const day = (iso) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })

function TrendTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-control border border-line bg-surface-raised px-3 py-2 text-xs shadow-pop">
      <p className="mb-1 font-medium text-ink-3">{day(label)}</p>
      {payload.map((p) => (
        <p key={p.dataKey} className="flex items-center gap-2">
          <span className="h-0.5 w-3 rounded" style={{ backgroundColor: p.color }} />
          <span className="num font-semibold text-ink">{p.value}</span>
          <span className="text-ink-3">{p.name}</span>
        </p>
      ))}
    </div>
  )
}

export function TrendChart({ points }) {
  const c = useChartColors()
  const tick = { fill: c.ink3, fontSize: 12 }

  return (
    <div>
      <div className="h-60">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
            <defs>
              <linearGradient id="leads-wash" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={c.brand} stopOpacity={0.18} />
                <stop offset="100%" stopColor={c.brand} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke={c.grid} />
            <XAxis
              dataKey="date"
              tickFormatter={day}
              tick={tick}
              tickLine={false}
              axisLine={{ stroke: c.axis }}
              minTickGap={24}
            />
            <YAxis allowDecimals={false} tick={tick} tickLine={false} axisLine={false} width={40} />
            <Tooltip content={<TrendTooltip />} cursor={{ stroke: c.axis, strokeWidth: 1 }} />
            <Area
              type="monotone"
              dataKey="leads"
              name="Enquiries"
              stroke={c.brand}
              strokeWidth={2}
              fill="url(#leads-wash)"
              activeDot={{ r: 4, stroke: c.surface, strokeWidth: 2 }}
              animationDuration={700}
            />
            <Line
              type="monotone"
              dataKey="won"
              name="Sales"
              stroke={c.accent}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, stroke: c.surface, strokeWidth: 2 }}
              animationDuration={700}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <ul className="mt-3 flex gap-4 text-xs text-ink-2">
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden className="h-0.5 w-4 rounded" style={{ backgroundColor: c.brand }} /> Enquiries
        </li>
        <li className="inline-flex items-center gap-1.5">
          <span aria-hidden className="h-0.5 w-4 rounded" style={{ backgroundColor: c.accent }} /> Sales
        </li>
      </ul>
    </div>
  )
}
