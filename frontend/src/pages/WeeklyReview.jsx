/*
  Weekly review: the AI team's look at the week, written for the owner.

  - The headline, in one sentence.
  - What went well and what didn't (findings), and an online-presence
    checklist (done / could be better / missing).
  - The 3 actions for this week, each with WHY and a link to do it.
  - "Run review now" starts a fresh review and shows the AI helpers working.
  - "Copy WhatsApp message" puts the review on the clipboard, ready to paste.

  Older reviews can be opened from the row of dates.
*/
import clsx from 'clsx'
import { ArrowRight, Check, CircleCheck, Copy, Info, ListChecks, Sparkles, TriangleAlert } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'

import { fadeUp, listItem, stagger } from '@/animations/presets'
import { PageHeader } from '@/components/layout/PageHeader'
import { WhyNote } from '@/components/ui/AiNote'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState, ErrorState } from '@/components/ui/States'
import { toast } from '@/components/ui/toast'
import { useWorkflow } from '@/hooks/useAgentRuns'
import { useCopyWhatsapp, useReport, useReports, useRunReview } from '@/hooks/useGrowth'
import { agentLabel, PRESENCE, shortDate } from '@/styles/tokens'

const FINDING = {
  good: { icon: CircleCheck, className: 'text-good-ink', label: 'Going well' },
  bad: { icon: TriangleAlert, className: 'text-serious-ink', label: 'Needs work' },
  note: { icon: Info, className: 'text-brand', label: 'Noticed' },
}

function Running({ steps }) {
  const workflow = useWorkflow('growth')
  const planned = workflow.data?.steps ?? []
  const done = new Set(steps.map((s) => s.agent))
  // Without live steps from the server, light the helpers up one by one while we wait.
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 700)
    return () => clearInterval(id)
  }, [])
  const current = steps.length ? steps.length : Math.min(tick, Math.max(planned.length - 1, 0))

  return (
    <Card className="border-brand/30">
      <div className="flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-full bg-brand-soft">
          <Sparkles aria-hidden className="size-5 animate-pulse text-brand motion-reduce:animate-none" />
        </span>
        <div>
          <p className="font-semibold text-ink">The AI team is reviewing your week…</p>
          <p className="text-sm text-ink-3">This takes a few seconds in practice mode, up to a minute with Claude.</p>
        </div>
      </div>
      {planned.length > 0 && (
        <ol className="mt-4 grid gap-2 sm:grid-cols-4" aria-live="polite">
          {planned.map((p, i) => {
            const finished = done.has(p.agent) || (!steps.length && i < current)
            const active = !finished && i === current
            return (
              <li
                key={p.agent}
                className={clsx(
                  'rounded-control border p-3 text-sm transition-colors duration-300',
                  finished ? 'border-good/40 bg-good-soft' : active ? 'border-brand/40 bg-brand-soft' : 'border-line bg-surface-raised',
                )}
              >
                <p className="flex items-center gap-1.5 font-medium text-ink">
                  {finished ? <Check aria-hidden className="size-4 text-good-ink" /> : <span className={clsx('size-2 rounded-full', active ? 'animate-pulse bg-brand' : 'bg-line-strong')} />}
                  {p.label ?? agentLabel(p.agent)}
                </p>
                <p className="mt-1 text-xs text-ink-3">{p.does}</p>
              </li>
            )
          })}
        </ol>
      )}
    </Card>
  )
}

function ReportView({ report }) {
  const findings = report.findings ?? []
  const presence = report.presence ?? []
  const actions = report.actions ?? []
  return (
    <motion.div variants={stagger(0.07)} initial="hidden" animate="show" className="space-y-6">
      <motion.div variants={fadeUp}>
        <Card className="relative overflow-hidden">
          <p className="text-xs font-semibold tracking-wide text-ink-3 uppercase">
            Week of {shortDate(report.period_start)} – {shortDate(report.period_end)}
          </p>
          <h2 className="mt-2 max-w-3xl text-2xl font-bold tracking-tight text-balance sm:text-3xl">{report.headline}</h2>
          {report.summary && <p className="mt-3 max-w-3xl text-ink-2">{report.summary}</p>}
        </Card>
      </motion.div>

      <motion.div variants={fadeUp}>
        <Card>
          <CardHeader
            title={
              <span className="inline-flex items-center gap-2">
                <ListChecks aria-hidden className="size-5 text-brand" /> Your 3 actions this week
              </span>
            }
            subtitle="Picked because they'll bring the most customers. Each says why."
          />
          {actions.length ? (
            <ol className="grid gap-3 md:grid-cols-3">
              {actions.slice(0, 3).map((action, i) => (
                <motion.li key={action.title} variants={listItem} className="flex flex-col gap-2 rounded-control border border-line bg-surface-raised p-4">
                  <div className="flex items-start gap-3">
                    <span className="num flex size-7 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-bold text-on-brand">{i + 1}</span>
                    <p className="font-semibold text-ink">{action.title}</p>
                  </div>
                  <WhyNote className="text-[13px]">{action.why}</WhyNote>
                  {action.link && (
                    <Link to={action.link} className="mt-auto inline-flex items-center gap-1 pt-1 text-sm font-semibold text-brand hover:underline">
                      Do it now <ArrowRight aria-hidden className="size-4" />
                    </Link>
                  )}
                </motion.li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-ink-2">No actions this week.</p>
          )}
        </Card>
      </motion.div>

      <div className="grid gap-6 lg:grid-cols-2">
        <motion.div variants={fadeUp}>
          <Card className="h-full">
            <CardHeader title="What happened" subtitle="The good and the bad, with the numbers" />
            {findings.length ? (
              <ul className="space-y-3">
                {[...findings]
                  .sort((a, b) => ['good', 'note', 'bad'].indexOf(a.kind) - ['good', 'note', 'bad'].indexOf(b.kind))
                  .map((f) => {
                    const look = FINDING[f.kind] ?? FINDING.note
                    const Icon = look.icon
                    return (
                      <li key={f.title} className="flex gap-3">
                        <Icon aria-hidden className={clsx('mt-0.5 size-5 shrink-0', look.className)} />
                        <div>
                          <p className="text-sm font-medium text-ink">
                            <span className="sr-only">{look.label}: </span>
                            {f.title}
                          </p>
                          {f.detail && <p className="text-sm text-ink-3">{f.detail}</p>}
                        </div>
                      </li>
                    )
                  })}
              </ul>
            ) : (
              <p className="text-sm text-ink-2">No findings in this review.</p>
            )}
          </Card>
        </motion.div>
        <motion.div variants={fadeUp}>
          <Card className="h-full">
            <CardHeader title="Online presence checklist" subtitle="What new customers see before they call you" />
            {presence.length ? (
              <ul className="divide-y divide-line">
                {presence.map((p) => {
                  const s = PRESENCE[p.status] ?? PRESENCE.warn
                  return (
                    <li key={p.item} className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
                      <s.icon aria-hidden className={clsx('mt-0.5 size-5 shrink-0', s.tone === 'good' ? 'text-good-ink' : s.tone === 'warning' ? 'text-warning-ink' : 'text-critical-ink')} />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-ink">{p.item}</p>
                        {p.detail && <p className="text-sm text-ink-3">{p.detail}</p>}
                      </div>
                      <Badge tone={s.tone}>{s.label}</Badge>
                    </li>
                  )
                })}
              </ul>
            ) : (
              <p className="text-sm text-ink-2">The checklist wasn't part of this review.</p>
            )}
          </Card>
        </motion.div>
      </div>
    </motion.div>
  )
}

export default function WeeklyReview() {
  const reports = useReports(8)
  const [chosen, setChosen] = useState(null)
  const list = reports.data ?? []
  const selectedId = chosen ?? list[0]?.id ?? null
  const detail = useReport(selectedId)
  const report = detail.data ?? list.find((r) => r.id === selectedId)
  const review = useRunReview()
  const copy = useCopyWhatsapp()

  // A fresh review just landed: show it.
  const [wasRunning, setWasRunning] = useState(false)
  if (review.running !== wasRunning) {
    setWasRunning(review.running)
    if (review.running) setChosen(null)
  }

  const actions = (
    <>
      {report && (
        <Button
          icon={copy.isSuccess && copy.variables?.id === report.id ? Check : Copy}
          loading={copy.isPending}
          onClick={() =>
            copy.mutate(report, {
              onSuccess: () => toast({ title: 'Copied', body: 'Paste it into WhatsApp to send it to yourself or your team.', tone: 'good' }),
              onError: (error) => toast({ title: "Couldn't copy", body: error.message, tone: 'critical' }),
            })
          }
        >
          Copy WhatsApp message
        </Button>
      )}
      <Button variant="primary" icon={Sparkles} loading={review.running} onClick={review.start}>
        Run review now
      </Button>
    </>
  )

  let body
  if (reports.isPending) {
    body = (
      <div className="space-y-6">
        <Card>
          <Skeleton className="h-4 w-40" />
          <Skeleton className="mt-3 h-9 w-3/4" />
        </Card>
        <div className="grid gap-3 md:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-36 rounded-card" />
          ))}
        </div>
      </div>
    )
  } else if (reports.isError) {
    body = <ErrorState error={reports.error} onRetry={() => reports.refetch()} />
  } else if (!report) {
    body = review.running ? null : (
      <Card>
        <EmptyState icon={ListChecks} title="No weekly review yet" action={<Button variant="primary" icon={Sparkles} onClick={review.start}>Run your first review</Button>}>
          The AI team looks at your enquiries, sales, posts and reviews, then picks the 3 things that will bring the most customers this week.
        </EmptyState>
      </Card>
    )
  } else {
    body = (
      <>
        {list.length > 1 && (
          <div role="tablist" aria-label="Past reviews" className="-mx-1 mb-5 flex gap-1.5 overflow-x-auto px-1 pb-1">
            {list.map((r, i) => (
              <button
                key={r.id}
                type="button"
                role="tab"
                aria-selected={r.id === selectedId}
                onClick={() => setChosen(r.id)}
                className={clsx(
                  'h-9 shrink-0 cursor-pointer rounded-full px-3.5 text-sm font-medium whitespace-nowrap transition-colors',
                  r.id === selectedId ? 'bg-ink text-surface' : 'bg-surface-sunken text-ink-2 hover:text-ink',
                )}
              >
                {i === 0 ? 'Latest' : shortDate(r.created_at)}
              </button>
            ))}
          </div>
        )}
        <div className={clsx('transition-opacity duration-200', detail.isFetching && !detail.data && 'opacity-60')}>
          <ReportView key={report.id} report={report} />
        </div>
      </>
    )
  }

  return (
    <div>
      <PageHeader actions={actions} />
      <AnimatePresence>
        {review.running && (
          <motion.div key="running" variants={fadeUp} initial="hidden" animate="show" exit="exit" className="mb-6">
            <Running steps={review.steps} />
          </motion.div>
        )}
      </AnimatePresence>
      {review.error && (
        <p role="alert" className="mb-6 rounded-control border border-critical/40 bg-critical-soft p-3 text-sm text-critical-ink">
          The review didn't finish: {review.error}
        </p>
      )}
      {body}
    </div>
  )
}
