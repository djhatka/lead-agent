/*
  AI team: who the AI helpers are and what each one did.

  1. The two workflows as simple flows: every new enquiry, and the weekly review
  2. A timeline of runs, newest first (filter by kind)
  3. Click a run to replay it: each helper appears in turn with whether the
     answer came from Claude or practice mode, how long it took, and what it
     decided. "Replay" plays it again.
*/
import clsx from 'clsx'
import { ArrowRight, Bot, ChevronRight, CircleCheck, CircleX, LoaderCircle, RotateCcw } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useState } from 'react'
import { Link } from 'react-router'

import { duration, ease, fadeUp, listItem, stagger } from '@/animations/presets'
import { PageHeader } from '@/components/layout/PageHeader'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Drawer } from '@/components/ui/Drawer'
import { QueryCard } from '@/components/ui/QueryCard'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState, InlineError } from '@/components/ui/States'
import { useAgentRun, useAgentRuns, useWorkflow } from '@/hooks/useAgentRuns'
import { agentLabel, AI_MODES, channel, scoreRuleLabel, serviceLabel, timeAgo, when, WORKFLOWS } from '@/styles/tokens'

const KINDS = [
  { key: 'all', label: 'Everything', match: () => true },
  { key: 'lead', label: 'Enquiries', match: (r) => r.workflow === 'lead' },
  { key: 'growth', label: 'Weekly reviews', match: (r) => r.workflow === 'growth' || r.workflow === 'insights' },
  { key: 'content', label: 'Posts', match: (r) => r.workflow === 'content' },
  { key: 'reviews', label: 'Review replies', match: (r) => r.workflow === 'reviews' },
]

const RUN_STATUS = {
  done: { label: 'Done', tone: 'good', icon: CircleCheck },
  failed: { label: 'Failed', tone: 'critical', icon: CircleX },
  running: { label: 'Running', tone: 'brand', icon: LoaderCircle },
}

const totalMs = (run) => run.steps.reduce((n, s) => n + (s.ms ?? 0), 0)
const msLabel = (ms) => (ms == null ? '—' : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`)
const list = (items, n = 3) => (Array.isArray(items) ? items.slice(0, n) : [])

/** What a helper decided, in a sentence or a short list, from its output. */
function Decision({ step }) {
  const o = step.output ?? {}
  const lines = (() => {
    switch (step.agent) {
      case 'intake':
        return [
          [serviceLabel(o.service) && `Wants: ${serviceLabel(o.service)}`, o.car_model && `car: ${o.car_model}`].filter(Boolean).join(', ') || 'Read the message.',
          [o.shared_phone && 'Shared a phone number', o.wants_soon && 'Wants it soon', o.asked_price && 'Asked the price'].filter(Boolean).join(' · '),
        ]
      case 'sentiment':
        return [`Tone: ${o.sentiment ?? '—'}`, o.reason]
      case 'scoring':
        return [
          `Score: ${o.score ?? '—'}`,
          o.breakdown &&
            Object.entries(o.breakdown)
              .filter(([, pts]) => pts)
              .map(([rule, pts]) => `${scoreRuleLabel(rule)} ${pts > 0 ? '+' : ''}${pts}`)
              .join(' · '),
          o.adjustment_reason,
        ]
      case 'priority_router':
      case 'hot_lead':
      case 'normal_lead':
        return [o.priority === 'hot' ? '🔥 Hot: call first' : 'Normal follow-up', o.reason]
      case 'data_analyst':
        return [...list(o.findings), o.weak_platforms?.length ? `Weak: ${o.weak_platforms.map((p) => channel(p).label).join(', ')}` : null]
      case 'presence_auditor':
        return list(o.items).map((i) => i.issue ?? i)
      case 'strategy':
        return o.focus ? list(o.focus) : list(o.items).map((i) => (typeof i === 'string' ? i : `${i.day ?? ''} ${i.idea ?? ''}`.trim()))
      case 'report_writer':
        return [o.headline ?? o.summary, ...list(o.top_actions).map((a, i) => `${i + 1}. ${a}`)]
      default: {
        const value = Object.values(o)[0]
        return Array.isArray(value) ? list(value, 4).map(String) : [typeof value === 'object' ? JSON.stringify(value) : String(value ?? 'Done.')]
      }
    }
  })().filter(Boolean)

  return (
    <ul className="space-y-1 text-sm text-ink-2">
      {lines.map((line) => (
        <li key={line}>{line}</li>
      ))}
    </ul>
  )
}

function ModeBadge({ mode }) {
  const m = AI_MODES[mode] ?? { label: mode ?? '—', tone: 'neutral' }
  return <Badge tone={m.tone}>{m.label}</Badge>
}

/** The run's steps appearing one after another, connected by a line. */
function Replay({ run }) {
  return (
    <motion.ol variants={stagger(0.45, 0.1)} initial="hidden" animate="show" className="relative space-y-4">
      {run.steps.map((s, i) => (
        <motion.li
          key={`${s.agent}-${i}`}
          variants={{
            hidden: { opacity: 0, y: 10 },
            show: { opacity: 1, y: 0, transition: { duration: duration.slow, ease: ease.out } },
          }}
          className="relative flex gap-3"
        >
          {i < run.steps.length - 1 && <span aria-hidden className="absolute top-9 bottom-[-1.25rem] left-[17px] w-0.5 bg-line" />}
          <span className="num relative flex size-9 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-bold text-on-brand">{i + 1}</span>
          <div className="min-w-0 flex-1 rounded-control border border-line bg-surface-raised p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-semibold text-ink">{agentLabel(s.agent)}</p>
              <span className="flex items-center gap-2 text-xs text-ink-3">
                <ModeBadge mode={s.mode} />
                <span className="num">{msLabel(s.ms)}</span>
              </span>
            </div>
            <div className="mt-2">
              <Decision step={s} />
            </div>
            {s.note && <p className="mt-2 text-xs text-serious-ink">{s.note}</p>}
          </div>
        </motion.li>
      ))}
    </motion.ol>
  )
}

function RunDrawer({ runId, onClose }) {
  const run = useAgentRun(runId)
  const [round, setRound] = useState(0)
  const data = run.data

  return (
    <Drawer
      eyebrow={data ? `${WORKFLOWS[data.workflow] ?? data.workflow} · ${when(data.started_at)}` : 'AI run'}
      title={data ? `Run #${data.id}` : 'Loading…'}
      onClose={onClose}
      footer={
        <div className="flex justify-between gap-2">
          {data?.lead_id ? (
            <Link to={`/leads/${data.lead_id}`} className="inline-flex h-11 items-center gap-1 text-sm font-semibold text-brand hover:underline">
              Open the enquiry <ArrowRight aria-hidden className="size-4" />
            </Link>
          ) : (
            <span />
          )}
          <Button icon={RotateCcw} onClick={() => setRound((r) => r + 1)} disabled={!data}>
            Replay
          </Button>
        </div>
      }
    >
      <div className="space-y-5 p-5">
        {run.isPending ? (
          <div className="space-y-3">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
        ) : run.isError ? (
          <InlineError error={run.error} onRetry={() => run.refetch()} />
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm text-ink-2">
              <RunStatus status={data.status} />
              <span>{data.steps.length} steps</span>
              <span>· {msLabel(totalMs(data))} in total</span>
            </div>
            {data.error && <p role="alert" className="rounded-control bg-critical-soft p-3 text-sm text-critical-ink">{data.error}</p>}
            <Replay key={round} run={data} />
          </>
        )}
      </div>
    </Drawer>
  )
}

function RunStatus({ status }) {
  const s = RUN_STATUS[status] ?? { label: status, tone: 'neutral' }
  return (
    <Badge tone={s.tone} icon={s.icon} className={status === 'running' ? '[&_svg]:animate-spin' : undefined}>
      {s.label}
    </Badge>
  )
}

function WorkflowFlow({ name }) {
  const workflow = useWorkflow(name)
  return (
    <QueryCard
      query={workflow}
      title={(workflow.data?.name) ?? (name === 'lead' ? 'Every new enquiry' : 'Weekly growth review')}
      subtitle={workflow.data?.trigger}
      skeleton="h-24"
    >
      {(w) => (
        <motion.ol variants={stagger(0.12)} initial="hidden" animate="show" className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
          {w.steps.map((s, i) => (
            <motion.li key={s.agent} variants={listItem} className="flex flex-1 flex-col items-stretch gap-1 sm:flex-row sm:gap-2">
              <div className="flex-1 rounded-control border border-line bg-surface-raised p-3">
                <p className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                  <span className="num flex size-5 items-center justify-center rounded-full bg-brand-soft text-[11px] text-brand">{i + 1}</span>
                  {s.label ?? agentLabel(s.agent)}
                </p>
                <p className="mt-1 text-xs text-ink-3">{s.does}</p>
              </div>
              {i < w.steps.length - 1 && <ChevronRight aria-hidden className="size-4 shrink-0 rotate-90 self-center text-ink-3 sm:rotate-0" />}
            </motion.li>
          ))}
        </motion.ol>
      )}
    </QueryCard>
  )
}

function Timeline({ onOpen }) {
  const [kind, setKind] = useState('all')
  const runs = useAgentRuns({ page_size: 100 })
  const items = (runs.data?.items ?? []).filter(KINDS.find((k) => k.key === kind).match)

  return (
    <Card>
      <CardHeader title="What the AI did" subtitle="Newest first. Click a run to replay it step by step." />
      <div role="tablist" aria-label="Show" className="-mx-1 mb-4 flex gap-1 overflow-x-auto px-1">
        {KINDS.map((k) => (
          <button
            key={k.key}
            type="button"
            role="tab"
            aria-selected={kind === k.key}
            onClick={() => setKind(k.key)}
            className={clsx(
              'h-9 shrink-0 cursor-pointer rounded-full px-3.5 text-sm font-medium transition-colors',
              kind === k.key ? 'bg-ink text-surface' : 'bg-surface-sunken text-ink-2 hover:text-ink',
            )}
          >
            {k.label}
          </button>
        ))}
      </div>
      {runs.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : runs.isError ? (
        <InlineError error={runs.error} onRetry={() => runs.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState icon={Bot} title="Nothing here yet">The AI team's work shows up here as soon as it runs.</EmptyState>
      ) : (
        <motion.ul key={kind} variants={stagger(0.02)} initial="hidden" animate="show" className="divide-y divide-line">
          {items.slice(0, 60).map((run) => (
            <motion.li key={run.id} variants={listItem}>
              <button
                type="button"
                onClick={() => onOpen(run.id)}
                className="group flex w-full cursor-pointer items-center gap-3 rounded-control px-2 py-3 text-left transition-colors hover:bg-surface-sunken/70"
              >
                <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand-soft">
                  <Bot aria-hidden className="size-[18px] text-brand" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-ink group-hover:text-brand">
                    {WORKFLOWS[run.workflow] ?? run.workflow}
                    {run.lead_id ? <span className="font-normal text-ink-3"> · enquiry #{run.lead_id}</span> : null}
                  </p>
                  <p className="truncate text-xs text-ink-3">
                    {run.steps.map((s) => agentLabel(s.agent)).join(' → ')}
                  </p>
                </div>
                <div className="hidden shrink-0 flex-col items-end gap-1 sm:flex">
                  <RunStatus status={run.status} />
                  <span className="num text-xs text-ink-3">{msLabel(totalMs(run))}</span>
                </div>
                <span className="w-20 shrink-0 text-right text-xs text-ink-3" title={when(run.started_at)}>
                  {timeAgo(run.started_at)}
                </span>
              </button>
            </motion.li>
          ))}
        </motion.ul>
      )}
      {items.length > 60 && <p className="mt-3 text-center text-xs text-ink-3">Showing the latest 60.</p>}
    </Card>
  )
}

export default function AgentRuns() {
  const [openId, setOpenId] = useState(null)
  const close = useCallback(() => setOpenId(null), [])
  return (
    <div>
      <PageHeader />
      <motion.div variants={stagger(0.07)} initial="hidden" animate="show" className="space-y-6">
        <div className="grid gap-6 xl:grid-cols-2">
          <motion.div variants={fadeUp}>
            <WorkflowFlow name="lead" />
          </motion.div>
          <motion.div variants={fadeUp}>
            <WorkflowFlow name="growth" />
          </motion.div>
        </div>
        <motion.div variants={fadeUp}>
          <Timeline onOpen={setOpenId} />
        </motion.div>
      </motion.div>
      <AnimatePresence>{openId != null && <RunDrawer key={openId} runId={openId} onClose={close} />}</AnimatePresence>
    </div>
  )
}
