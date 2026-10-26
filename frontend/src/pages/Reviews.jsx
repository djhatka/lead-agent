/*
  Reviews: the business's reputation.

  1. Rating summary: average, star bars, what people praise and complain about
  2. Every review, unhappy ones first (they always stand out). Each unanswered
     review shows the AI's draft reply in a dashed "Draft by AI" box: edit it,
     then press "Post reply". Nothing is posted without that click.
  3. Review requests: the "please review us" WhatsApp messages sent after a
     sale. Waiting ones can be skipped.
*/
import clsx from 'clsx'
import { MessageSquareReply, PenLine, SkipForward, Star, ThumbsDown, ThumbsUp } from 'lucide-react'
import { motion } from 'motion/react'
import { useState } from 'react'

import { fadeUp, listItem, stagger } from '@/animations/presets'
import { BarList } from '@/components/charts/BarList'
import { PageHeader } from '@/components/layout/PageHeader'
import { AiLabel } from '@/components/ui/AiNote'
import { Badge, StateBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { CountUp } from '@/components/ui/CountUp'
import { QueryCard } from '@/components/ui/QueryCard'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState, InlineError } from '@/components/ui/States'
import { toast } from '@/components/ui/toast'
import { useDraftAll, usePostReply, useReviewRequests, useReviews, useReviewSummary, useSkipRequest } from '@/hooks/useReviews'
import { plural, REQUEST_STATUSES, serviceLabel, shortDate, timeAgo, when } from '@/styles/tokens'

const REVIEW_SITES = { google: 'Google', justdial: 'Justdial', facebook: 'Facebook' }

function Stars({ rating, size = 'size-4' }) {
  return (
    <span className="inline-flex items-center gap-0.5" role="img" aria-label={`${rating} out of 5 stars`}>
      {Array.from({ length: 5 }, (_, i) => (
        <Star
          key={i}
          aria-hidden
          className={clsx(size, i < Math.round(rating) ? 'fill-accent text-accent' : 'fill-surface-sunken text-line-strong')}
        />
      ))}
    </span>
  )
}

function Summary() {
  const summary = useReviewSummary()
  if (summary.isPending) {
    return (
      <Card>
        <div className="grid gap-6 md:grid-cols-3">
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </div>
      </Card>
    )
  }
  if (summary.isError) return <Card><InlineError error={summary.error} onRetry={() => summary.refetch()} /></Card>
  const s = summary.data
  if (!s.total) {
    return (
      <Card>
        <EmptyState icon={Star} title="No reviews yet">They'll appear here as soon as customers leave them on Google.</EmptyState>
      </Card>
    )
  }

  return (
    <Card>
      <div className="grid gap-8 md:grid-cols-[auto_1fr_1fr]">
        <div className="flex flex-col items-start gap-1 md:pr-4">
          <p className="text-sm font-medium text-ink-3">Average rating</p>
          <p className="text-5xl font-bold tracking-tight text-ink">
            <CountUp value={s.average_rating} format={(n) => n.toFixed(1)} />
          </p>
          <Stars rating={s.average_rating} size="size-5" />
          <p className="mt-1 text-sm text-ink-2">from {plural(s.total, 'review')}</p>
          {s.last_30_days?.count > 0 && (
            <p className="text-xs text-ink-3">
              {s.last_30_days.count} in the last 30 days · avg {s.last_30_days.average_rating}
            </p>
          )}
          {s.replied_pct != null && <p className="text-xs text-ink-3">You've replied to {s.replied_pct}%</p>}
        </div>
        <div>
          <h3 className="mb-3 text-xs font-semibold tracking-wide text-ink-3 uppercase">Stars</h3>
          <BarList
            items={[5, 4, 3, 2, 1].map((n) => ({ key: String(n), label: `${n} ★`, value: s.stars?.[n] ?? 0 }))}
            color="var(--accent)"
          />
        </div>
        <div className="space-y-5">
          <div>
            <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-ink-3 uppercase">
              <ThumbsUp aria-hidden className="size-3.5" /> Praised for
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {s.praised_for?.length ? s.praised_for.map((t) => (
                <Badge key={t.topic} tone="good">
                  {t.topic} <span className="num opacity-70">{t.count}</span>
                </Badge>
              )) : <span className="text-sm text-ink-3">Nothing yet</span>}
            </div>
          </div>
          <div>
            <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-ink-3 uppercase">
              <ThumbsDown aria-hidden className="size-3.5" /> Complaints
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {s.complaints?.length ? s.complaints.map((t) => (
                <Badge key={t.topic} tone="critical">
                  {t.topic} <span className="num opacity-70">{t.count}</span>
                </Badge>
              )) : <span className="text-sm text-ink-3">None. Well done!</span>}
            </div>
          </div>
        </div>
      </div>
    </Card>
  )
}

function ReplyEditor({ review }) {
  const post = usePostReply()
  const [text, setText] = useState(review.draft_reply ?? '')
  const [open, setOpen] = useState(Boolean(review.draft_reply) || review.needs_attention)
  const edited = review.draft_reply && text !== review.draft_reply

  if (!open) {
    return (
      <Button size="sm" variant="ghost" icon={MessageSquareReply} onClick={() => setOpen(true)}>
        Write a reply
      </Button>
    )
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        post.mutate(
          { id: review.id, text },
          { onSuccess: () => toast({ title: 'Reply posted', body: `Your reply to ${review.author} is live.`, tone: 'good' }) },
        )
      }}
      className={clsx('rounded-control p-3', review.draft_reply && !edited ? 'ai-draft' : 'border border-line bg-surface-sunken/50')}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        {review.draft_reply && !edited ? <AiLabel>Draft by AI · edit it if you like</AiLabel> : <span className="text-xs font-semibold text-ink-2">Your reply</span>}
      </div>
      <label className="sr-only" htmlFor={`reply-${review.id}`}>
        Reply to {review.author}
      </label>
      <textarea
        id={`reply-${review.id}`}
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Thank them by name, mention what they said, and invite them back."
        className="w-full resize-y rounded-control border border-line bg-surface-raised px-3 py-2 text-sm leading-relaxed text-ink outline-none focus-visible:border-brand"
      />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-ink-3">Posted publicly on {REVIEW_SITES[review.platform] ?? 'Google'} under your business name.</p>
        <Button type="submit" size="sm" variant="primary" icon={MessageSquareReply} loading={post.isPending} disabled={!text.trim()}>
          Post reply
        </Button>
      </div>
      {post.isError && <p role="alert" className="mt-2 text-sm text-critical-ink">{post.error.message}</p>}
    </form>
  )
}

function ReviewItem({ review }) {
  return (
    <motion.li
      variants={listItem}
      className={clsx(
        'rounded-card border p-4',
        review.needs_attention ? 'border-critical/40 bg-critical-soft/40' : 'border-line bg-surface-raised',
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Stars rating={review.rating} />
          <span className="font-semibold text-ink">{review.author}</span>
          {review.needs_attention && <Badge tone="critical">Needs a reply</Badge>}
        </div>
        <span className="text-xs text-ink-3" title={when(review.created_at)}>
          {REVIEW_SITES[review.platform] ?? review.platform} · {timeAgo(review.created_at)}
        </span>
      </div>
      {review.text ? <p className="mt-2 text-sm text-ink-2">{review.text}</p> : <p className="mt-2 text-sm text-ink-3 italic">Rated without a comment.</p>}

      <div className="mt-3">
        {review.reply_text ? (
          <div className="border-l-2 border-brand/40 pl-3">
            <p className="text-xs font-semibold text-ink-2">Your reply · {shortDate(review.replied_at)}</p>
            <p className="mt-0.5 text-sm text-ink-2">{review.reply_text}</p>
          </div>
        ) : (
          <ReplyEditor key={review.draft_reply ?? 'none'} review={review} />
        )}
      </div>
    </motion.li>
  )
}

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'needs_attention', label: 'Unhappy, no reply' },
  { key: 'unreplied', label: 'No reply yet' },
  { key: 'replied', label: 'Replied' },
]

function ReviewList() {
  const [filter, setFilter] = useState('all')
  const reviews = useReviews(filter === 'all' ? {} : { status: filter })
  const draftAll = useDraftAll()
  const list = reviews.data ?? []
  // Unhappy ones first, whatever order the server sends.
  const sorted = [...list].sort((a, b) => Number(Boolean(b.needs_attention)) - Number(Boolean(a.needs_attention)))

  return (
    <Card>
      <CardHeader
        title="Reviews"
        subtitle="Unhappy ones first. Replies are only posted when you press Post reply."
        action={
          <Button
            icon={PenLine}
            loading={draftAll.isPending}
            onClick={() =>
              draftAll.mutate(undefined, {
                onSuccess: (r) =>
                  toast(r?.drafted
                    ? { title: `Drafted ${plural(r.drafted, 'reply', 'replies')}`, body: 'Nothing is posted. Check each one, then press Post reply.', tone: 'good' }
                    : { title: 'Nothing to draft', body: 'Every review already has a reply or a draft.' }),
                onError: (error) => toast({ title: "Couldn't draft replies", body: error.message, tone: 'critical' }),
              })
            }
          >
            Draft all replies
          </Button>
        }
      />
      <div role="tablist" aria-label="Show" className="-mx-1 mb-4 flex gap-1 overflow-x-auto px-1">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            role="tab"
            aria-selected={filter === f.key}
            onClick={() => setFilter(f.key)}
            className={clsx(
              'h-9 shrink-0 cursor-pointer rounded-full px-3.5 text-sm font-medium transition-colors',
              filter === f.key ? 'bg-ink text-surface' : 'bg-surface-sunken text-ink-2 hover:text-ink',
            )}
          >
            {f.label}
          </button>
        ))}
      </div>
      {reviews.isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-28 rounded-card" />
          ))}
        </div>
      ) : reviews.isError ? (
        <InlineError error={reviews.error} onRetry={() => reviews.refetch()} />
      ) : sorted.length === 0 ? (
        <EmptyState icon={Star} title={filter === 'all' ? 'No reviews yet' : 'Nothing here'}>
          {filter === 'all' ? "They'll appear here as soon as customers leave them." : 'No reviews match this filter.'}
        </EmptyState>
      ) : (
        <motion.ul key={filter} variants={stagger(0.04)} initial="hidden" animate="show" className="space-y-3">
          {sorted.map((review) => (
            <ReviewItem key={review.id} review={review} />
          ))}
        </motion.ul>
      )}
    </Card>
  )
}

function Requests() {
  const requests = useReviewRequests()
  const skip = useSkipRequest()
  return (
    <QueryCard
      query={requests}
      title="Review requests"
      subtitle="A WhatsApp message asking happy customers for a Google review, sent the day after a sale"
      empty="No review requests yet"
      isEmpty={(d) => !d.length}
    >
      {(list) => (
        <ul className="divide-y divide-line">
          {list.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-ink">{r.customer_name}</p>
                <p className="truncate text-xs text-ink-3">
                  {[serviceLabel(r.service), r.status === 'pending' ? `sends ${when(r.send_at)}` : r.status === 'reviewed' ? `reviewed ${shortDate(r.reviewed_at)}` : r.sent_at ? `sent ${shortDate(r.sent_at)}` : null]
                    .filter(Boolean)
                    .join(' · ')}
                </p>
              </div>
              {r.status === 'reviewed' && r.rating ? <Stars rating={r.rating} size="size-3.5" /> : null}
              <StateBadge map={REQUEST_STATUSES} value={r.status} />
              {r.status === 'pending' && (
                <Button
                  size="sm"
                  variant="ghost"
                  icon={SkipForward}
                  loading={skip.isPending && skip.variables === r.id}
                  onClick={() => skip.mutate(r.id, { onSuccess: () => toast({ title: 'Skipped', body: `${r.customer_name} won't be asked for a review.` }) })}
                >
                  Skip
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </QueryCard>
  )
}

export default function Reviews() {
  return (
    <div>
      <PageHeader />
      <motion.div variants={stagger(0.07)} initial="hidden" animate="show" className="space-y-6">
        <motion.div variants={fadeUp}>
          <Summary />
        </motion.div>
        <div className="grid gap-6 xl:grid-cols-[3fr_2fr]">
          <motion.div variants={fadeUp}>
            <ReviewList />
          </motion.div>
          <motion.div variants={fadeUp}>
            <Requests />
          </motion.div>
        </div>
      </motion.div>
    </div>
  )
}
