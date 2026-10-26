/*
  Style guide: a living catalogue of the design system.

  Every token and base component on one page, in the current theme, so
  you can check colours, contrast and motion in light AND dark mode
  before using them in real pages. Kept as a route (/style-guide) for
  future reference.
*/
import { useGSAP } from '@gsap/react'
import { Play, RefreshCw, Trash2, TrendingUp } from 'lucide-react'
import { motion } from 'motion/react'
import { useRef, useState } from 'react'

import { fadeUp, listItem, revealGrid, stagger } from '@/animations/presets'
import { Badge, ChannelBadge, PriorityBadge, SentimentBadge, StatusBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { CountUp } from '@/components/ui/CountUp'
import { Skeleton, SkeletonText } from '@/components/ui/Skeleton'
import { CHANNELS, inr, SENTIMENTS, STATUSES } from '@/styles/tokens'

const SWATCHES = [
  { group: 'Surfaces', items: ['canvas', 'surface', 'surface-raised', 'surface-sunken', 'line', 'line-strong'] },
  { group: 'Ink', items: ['ink', 'ink-2', 'ink-3'] },
  { group: 'Brand & accent', items: ['brand', 'brand-strong', 'brand-soft', 'accent', 'accent-ink', 'accent-soft'] },
  { group: 'Status', items: ['good', 'warning', 'serious', 'critical'] },
]

const KPIS = [
  { label: 'Leads (30 days)', value: 157, format: undefined },
  { label: 'Jobs won', value: 38, format: undefined },
  { label: 'Revenue', value: 1090000, format: (n) => inr(Math.round(n), { short: true }) },
  { label: 'Hot leads waiting', value: 20, format: undefined },
]

function Swatch({ token }) {
  return (
    <div className="flex items-center gap-3">
      <span
        className="size-9 shrink-0 rounded-control border border-line"
        style={{ backgroundColor: `var(--${token})` }}
      />
      <code className="text-xs text-ink-2">{token}</code>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <motion.section variants={fadeUp} className="space-y-3">
      <h2 className="text-sm font-semibold tracking-wide text-ink-3 uppercase">{title}</h2>
      {children}
    </motion.section>
  )
}

export default function StyleGuide() {
  const kpiRef = useRef(null)
  const [replay, setReplay] = useState(0)
  const [loading, setLoading] = useState(false)

  useGSAP(() => revealGrid(kpiRef.current.children), { dependencies: [replay], scope: kpiRef })

  return (
    <motion.div variants={stagger(0.08)} initial="hidden" animate="show" className="space-y-10">
      <motion.p variants={fadeUp} className="max-w-prose text-ink-2">
        Every colour, font and component the dashboard uses. Switch the theme (top right) to check both modes.
      </motion.p>

      <Section title="KPI cards · GSAP count-up + grid reveal">
        <div ref={kpiRef} className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {KPIS.map((kpi) => (
            <Card key={kpi.label} interactive>
              <p className="text-sm text-ink-3">{kpi.label}</p>
              <p className="mt-1 text-3xl font-bold text-ink">
                <CountUp key={replay} value={kpi.value} format={kpi.format} />
              </p>
              <p className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-good-ink">
                <TrendingUp aria-hidden className="size-3.5" /> 9% vs last period
              </p>
            </Card>
          ))}
        </div>
        <Button size="sm" icon={Play} onClick={() => setReplay((n) => n + 1)}>
          Replay animation
        </Button>
      </Section>

      <Section title="Colour tokens">
        <Card>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {SWATCHES.map(({ group, items }) => (
              <div key={group} className="space-y-2">
                <h3 className="text-sm font-semibold">{group}</h3>
                {items.map((token) => (
                  <Swatch key={token} token={token} />
                ))}
              </div>
            ))}
          </div>
        </Card>
      </Section>

      <Section title="Channels · validated colour order (always shown with the name)">
        <Card>
          <div className="flex flex-wrap gap-x-6 gap-y-3">
            {CHANNELS.map((c) => (
              <ChannelBadge key={c.key} source={c.key} />
            ))}
          </div>
          <div className="mt-5 flex h-3 overflow-hidden rounded-full" aria-hidden>
            {CHANNELS.map((c) => (
              <span key={c.key} className="h-full flex-1 border-r-2 border-surface last:border-r-0" style={{ backgroundColor: c.color }} />
            ))}
          </div>
        </Card>
      </Section>

      <Section title="Typography · DM Sans">
        <Card className="space-y-3">
          <p className="text-3xl font-bold tracking-tight text-ink">Rs 21.0 lakh revenue · 3xl bold</p>
          <p className="text-xl font-semibold text-ink">Instagram brings the most leads · xl semibold</p>
          <p className="text-base text-ink-2">
            Body text: leads answered within 5 minutes won 54% of the time, versus 9% when the reply took 2-24
            hours. · base regular
          </p>
          <p className="text-sm text-ink-3">Caption / label text · sm, ink-3</p>
          <p className="num text-sm text-ink-2">Table numbers line up: 1,314,000 · 351,000 · 42,000 (tabular)</p>
        </Card>
      </Section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Buttons">
          <Card className="flex flex-wrap items-center gap-3">
            <Button variant="primary" icon={RefreshCw}>Run review</Button>
            <Button>Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger" icon={Trash2}>Mark lost</Button>
            <Button
              variant="primary"
              loading={loading}
              onClick={() => {
                setLoading(true)
                setTimeout(() => setLoading(false), 1500)
              }}
            >
              {loading ? 'Working…' : 'Try loading state'}
            </Button>
          </Card>
        </Section>

        <Section title="Badges · word + icon, never colour alone">
          <Card className="space-y-3">
            <div className="flex flex-wrap gap-2">
              {Object.keys(SENTIMENTS).map((s) => (
                <SentimentBadge key={s} sentiment={s} />
              ))}
              <PriorityBadge priority="hot" />
              <Badge tone="brand">Brand</Badge>
            </div>
            <div className="flex flex-wrap gap-2">
              {Object.keys(STATUSES).map((s) => (
                <StatusBadge key={s} status={s} />
              ))}
            </div>
          </Card>
        </Section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section title="Loading skeletons">
          <Card>
            <CardHeader title="Leads by channel" subtitle="Placeholder while data loads" />
            <div className="flex items-end gap-3">
              <Skeleton className="h-10 w-28" />
              <Skeleton className="h-6 w-16" />
            </div>
            <SkeletonText className="mt-4" />
          </Card>
        </Section>

        <Section title="List motion · stagger, no bounce">
          <Card>
            <motion.ul key={replay} variants={stagger(0.05)} initial="hidden" animate="show" className="divide-y divide-line">
              {['Rahul Sharma · Creta android screen', 'Priya Kapoor · Swift dashcam', 'Bansal Cabs · 15 GPS trackers'].map((row, i) => (
                <motion.li key={row} variants={listItem} className="flex items-center justify-between py-2.5 text-sm">
                  <span className="text-ink">{row}</span>
                  <SentimentBadge sentiment={['urgent', 'casual', 'frustrated'][i]} />
                </motion.li>
              ))}
            </motion.ul>
          </Card>
        </Section>
      </div>
    </motion.div>
  )
}
