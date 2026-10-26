/*
  Everything about one enquiry, sliding in from the right (full screen on phones).

  - The AI's verdict: score, tone, and WHY (every point of the score as a
    +/- bar, from the backend's breakdown), so the owner can trust or
    question it.
  - Which post brought them, if it came from social media.
  - A follow-up reminder with a ready message, when the enquiry has gone quiet (Task 30).
  - Payments: request an advance with a UPI link, and see what's paid (Task 31).
  - The full conversation and a reply box.
  - Actions: call or WhatsApp in one tap, change status (a won sale needs
    its ₹ value), ask the AI team to re-score.

  Closes with Esc, the ✕ button, or a click on the dimmed background.
*/
import clsx from 'clsx'
import { ArrowUpRight, Bot, RefreshCw, Send, X } from 'lucide-react'
import { motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'

import { drawer, fadeIn } from '@/animations/presets'
import { ContactButtons } from '@/components/leads/ContactButtons'
import { FollowUpPanel } from '@/components/leads/FollowUpPanel'
import { LeadPayments } from '@/components/payments/LeadPayments'
import { ScoreRing } from '@/components/leads/ScoreRing'
import { WhyNote } from '@/components/ui/AiNote'
import { ChannelBadge, PriorityBadge, SentimentBadge, StatusBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Skeleton, SkeletonText } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ui/States'
import { useAddMessage, useAnalyzeLead, useLead, useUpdateLead } from '@/hooks/useLeads'
import { useLockScroll } from '@/hooks/useLockScroll'
import { inr, leadTitle, minutes, pillar, platform, scoreRuleLabel, serviceLabel, STATUSES, timeAgo, when } from '@/styles/tokens'

function Section({ title, children, action }) {
  return (
    <section className="border-t border-line px-5 py-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold tracking-wide text-ink-3 uppercase">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  )
}

function WhyThisScore({ analysis }) {
  const entries = Object.entries(analysis.score_breakdown ?? {}).filter(([, pts]) => pts !== 0)
  const biggest = Math.max(1, ...entries.map(([, pts]) => Math.abs(pts)))
  return (
    <ul className="space-y-2">
      {entries.map(([rule, pts]) => (
        <li key={rule} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1 text-sm">
          <span className="text-ink-2">{scoreRuleLabel(rule)}</span>
          <span className={clsx('num font-semibold', pts < 0 ? 'text-critical-ink' : 'text-ink')}>
            {pts > 0 ? '+' : ''}
            {pts}
          </span>
          <span className="col-span-2 h-1.5 rounded-full bg-surface-sunken">
            <span
              className="block h-full rounded-full"
              style={{
                width: `${(Math.abs(pts) / biggest) * 100}%`,
                backgroundColor: pts < 0 ? 'var(--critical)' : rule === 'ai_adjustment' ? 'var(--accent)' : 'var(--brand)',
              }}
            />
          </span>
        </li>
      ))}
    </ul>
  )
}

function StatusEditor({ lead }) {
  const update = useUpdateLead()
  const [status, setStatus] = useState(lead.status)
  const [value, setValue] = useState(lead.job_value ?? '')
  const changed = status !== lead.status || (status === 'won' && Number(value) !== lead.job_value)

  function save(event) {
    event.preventDefault()
    const changes = { status }
    if (status === 'won') changes.job_value = Number(value)
    update.mutate({ id: lead.id, changes })
  }

  return (
    <form onSubmit={save} className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink-3">Status</span>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="h-11 cursor-pointer rounded-control border border-line bg-surface-raised px-3 text-ink"
          >
            {Object.entries(STATUSES).map(([key, s]) => (
              <option key={key} value={key}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        {status === 'won' && (
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink-3">Sale value (₹)</span>
            <input
              type="number"
              min="1"
              step="100"
              required
              value={value}
              onChange={(e) => setValue(e.target.value)}
              className="num h-11 w-36 rounded-control border border-line bg-surface-raised px-3 text-ink"
            />
          </label>
        )}
        <Button type="submit" variant="primary" disabled={!changed} loading={update.isPending}>
          Save
        </Button>
      </div>
      {update.isError && (
        <p role="alert" className="text-sm text-critical-ink">
          {update.error.message}
        </p>
      )}
      {update.isSuccess && !changed && <p className="text-sm text-good-ink">Saved.</p>}
    </form>
  )
}

function Conversation({ messages }) {
  return (
    <ol className="space-y-3">
      {messages.map((m) => {
        const shop = m.direction === 'out'
        return (
          <li key={m.id} className={clsx('flex', shop ? 'justify-end' : 'justify-start')}>
            <div
              className={clsx(
                'max-w-[85%] rounded-2xl px-3.5 py-2 text-sm',
                shop ? 'rounded-br-md bg-brand text-on-brand' : 'rounded-bl-md bg-surface-sunken text-ink',
              )}
            >
              <p className="whitespace-pre-wrap">{m.text}</p>
              <p className={clsx('mt-1 text-[11px]', shop ? 'text-on-brand/75' : 'text-ink-3')}>
                {shop ? (m.auto_reply ? '🤖 Auto-reply' : m.followup ? 'You · follow-up' : 'You') : 'Customer'} · {when(m.sent_at)}
                {shop && m.delivery === 'failed' && ' · not sent'}
              </p>
            </div>
          </li>
        )
      })}
    </ol>
  )
}

function ReplyBox({ leadId }) {
  const add = useAddMessage()
  const [text, setText] = useState('')

  function send(event) {
    event.preventDefault()
    if (!text.trim()) return
    add.mutate({ id: leadId, direction: 'out', text: text.trim() }, { onSuccess: () => setText('') })
  }

  return (
    <form onSubmit={send} className="space-y-2">
      <label className="block text-sm">
        <span className="text-ink-3">Your reply</span>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder="e.g. Haan ji, 4 baje aa jaiye. Rs 14,500 installed."
          className="mt-1 w-full resize-y rounded-control border border-line bg-surface-raised px-3 py-2 text-ink"
        />
      </label>
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs text-ink-3">Saves your reply to this conversation (and how fast you replied).</p>
        <Button type="submit" size="sm" icon={Send} loading={add.isPending} disabled={!text.trim()}>
          Save reply
        </Button>
      </div>
      {add.isError && <p role="alert" className="text-sm text-critical-ink">{add.error.message}</p>}
    </form>
  )
}

function DrawerBody({ leadId }) {
  const query = useLead(leadId)
  const analyze = useAnalyzeLead()

  if (query.isPending) {
    return (
      <div className="space-y-4 p-5">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-20 w-full" />
        <SkeletonText lines={5} />
      </div>
    )
  }
  if (query.isError) return <div className="p-5"><ErrorState error={query.error} onRetry={() => query.refetch()} /></div>

  const lead = query.data
  const a = lead.analysis
  const replyMinutes = lead.first_response_at
    ? (new Date(lead.first_response_at) - new Date(lead.created_at)) / 60000
    : null

  const post = lead.source_post
  const PostPlatform = post ? platform(post.platform) : null

  return (
    <>
      <div className="px-5 pb-5">
        <div className="flex flex-wrap items-center gap-2">
          <ChannelBadge source={lead.source} />
          <StatusBadge status={lead.status} />
          {a?.priority === 'hot' && <PriorityBadge priority="hot" />}
        </div>
        {lead.phone && (
          <div className="mt-4 flex items-center justify-between gap-3 rounded-control border border-line bg-surface-raised px-3 py-2">
            <div className="text-sm">
              <p className="text-ink-3">Phone</p>
              <p className="num font-medium text-ink">+91 {lead.phone}</p>
            </div>
            <ContactButtons lead={lead} />
          </div>
        )}
        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
          <div>
            <dt className="text-ink-3">Wants</dt>
            <dd className="font-medium text-ink">{serviceLabel(lead.service) ?? '—'}</dd>
          </div>
          {lead.car_model && (
            <div>
              <dt className="text-ink-3">Car</dt>
              <dd className="font-medium text-ink">{lead.car_model}</dd>
            </div>
          )}
          <div>
            <dt className="text-ink-3">Received</dt>
            <dd className="font-medium text-ink" title={when(lead.created_at)}>{when(lead.created_at)}</dd>
          </div>
          <div>
            <dt className="text-ink-3">First reply</dt>
            <dd className={clsx('font-medium', replyMinutes == null ? 'text-critical-ink' : 'text-ink')}>
              {replyMinutes == null ? 'Not replied yet' : `after ${minutes(replyMinutes)}`}
            </dd>
          </div>
          {lead.job_value != null && (
            <div>
              <dt className="text-ink-3">Sale value</dt>
              <dd className="font-medium text-ink">{inr(lead.job_value)}</dd>
            </div>
          )}
        </dl>
      </div>

      <FollowUpPanel leadId={lead.id} />

      {post && (
        <Section title="Came from this post">
          <Link
            to="/content/performance"
            className="group flex items-start gap-3 rounded-control border border-line bg-surface-raised p-3 transition-colors hover:border-line-strong"
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-control bg-surface-sunken">
              <PostPlatform.icon aria-hidden className="size-5 text-ink-2" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block font-medium text-ink group-hover:text-brand">{post.title}</span>
              <span className="block text-xs text-ink-3">
                {pillar(post.pillar).label} · {PostPlatform.label} · posted {when(post.published_at)}
              </span>
            </span>
            <ArrowUpRight aria-hidden className="size-4 shrink-0 text-ink-3 group-hover:text-brand" />
          </Link>
        </Section>
      )}

      <Section
        title="AI verdict"
        action={
          <Button size="sm" variant="ghost" icon={RefreshCw} loading={analyze.isPending} onClick={() => analyze.mutate(lead.id)}>
            Re-score
          </Button>
        }
      >
        {a ? (
          <div className="space-y-5">
            <div className="flex items-center gap-4">
              <ScoreRing score={a.score} size={72} stroke={6} />
              <div className="min-w-0 space-y-1.5">
                <SentimentBadge sentiment={a.sentiment} />
                <WhyNote label="Tone">{a.sentiment_reason}</WhyNote>
                <p className="text-xs text-ink-3">Scored {timeAgo(a.analyzed_at)}</p>
              </div>
            </div>
            <div>
              <h4 className="mb-1 text-sm font-semibold text-ink">Why this score</h4>
              <p className="mb-3 text-xs text-ink-3">Each line adds or takes away points. Red lines lower the score.</p>
              <WhyThisScore analysis={a} />
            </div>
          </div>
        ) : (
          <p className="flex items-center gap-2 text-sm text-ink-2">
            <Bot aria-hidden className="size-4" /> Not scored yet. Press Re-score.
          </p>
        )}
        {analyze.isError && <p role="alert" className="mt-2 text-sm text-critical-ink">{analyze.error.message}</p>}
      </Section>

      <Section title="Status">
        <StatusEditor key={`${lead.id}-${lead.status}-${lead.job_value}`} lead={lead} />
      </Section>

      <LeadPayments leadId={lead.id} />

      <Section title={`Conversation · ${lead.messages.length}`}>
        <Conversation messages={lead.messages} />
        <div className="mt-4">
          <ReplyBox leadId={lead.id} />
        </div>
      </Section>
    </>
  )
}

export function LeadDrawer({ leadId, onClose }) {
  const lead = useLead(leadId).data // same cached request as the body: no extra call
  const title = lead ? leadTitle(lead) : 'Enquiry'
  useLockScroll()

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <>
      <motion.div
        variants={fadeIn}
        initial="hidden"
        animate="show"
        exit="exit"
        onClick={onClose}
        className="fixed inset-0 z-40 bg-black/30 backdrop-blur-[2px]"
      />
      <motion.aside
        role="dialog"
        aria-modal="true"
        aria-label={`Enquiry details: ${title}`}
        variants={drawer}
        initial="hidden"
        animate="show"
        exit="exit"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-lg flex-col bg-surface shadow-pop"
      >
        <header className="flex items-start justify-between gap-3 px-5 pt-5 pb-3">
          <div className="min-w-0">
            <p className="text-xs text-ink-3">Enquiry #{leadId}</p>
            <h2 className="truncate text-xl font-semibold">{title}</h2>
          </div>
          <button
            type="button"
            autoFocus
            onClick={onClose}
            aria-label="Close"
            className="flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-control text-ink-2 hover:bg-surface-sunken"
          >
            <X aria-hidden className="size-5" />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto">
          <DrawerBody leadId={leadId} />
        </div>
      </motion.aside>
    </>
  )
}
