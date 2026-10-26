/*
  One post on the content calendar.

  - Ideas and drafts the AI made look like drafts: dashed border and a
    "Draft by AI" / "Idea by AI" label. Ideas show WHY the AI suggests them.
  - Scheduled posts show when they'll go out (India time).
  - Published posts show what they brought: enquiries and ₹ first, reach second.
  - Posts that couldn't go out are red, with the reason.
*/
import clsx from 'clsx'
import { motion } from 'motion/react'

import { listItem } from '@/animations/presets'
import { AiLabel } from '@/components/ui/AiNote'
import { StateBadge } from '@/components/ui/Badge'
import { count, FORMATS, inr, pillar, platform, POST_STATUSES, timeIST } from '@/styles/tokens'

function PostResults({ post }) {
  const r = post.results
  const m = post.metrics
  if (!r && !m) return null
  return (
    <p className="mt-2 text-xs text-ink-2">
      <span className="font-semibold text-ink">{count(r?.enquiries ?? 0)}</span> enquiries
      {r?.revenue ? (
        <>
          {' · '}
          <span className="font-semibold text-ink">{inr(r.revenue, { short: true })}</span>
        </>
      ) : null}
      {m && <span className="text-ink-3"> · {count(m.reach)} reach</span>}
    </p>
  )
}

export function PostCard({ post, onOpen, compact = false }) {
  const byAi = post.created_by !== 'owner' && (post.status === 'idea' || post.status === 'draft')
  const where = platform(post.platform)
  const Icon = where.icon
  const time =
    post.status === 'scheduled' || post.status === 'published'
      ? timeIST(post.published_at ?? post.scheduled_at)
      : post.suggested_at
        ? `best ${timeIST(post.suggested_at)}`
        : null

  return (
    <motion.button
      type="button"
      layout
      variants={listItem}
      onClick={() => onOpen(post.id)}
      className={clsx(
        'group w-full cursor-pointer rounded-control p-3 text-left transition-shadow hover:shadow-pop focus-visible:shadow-pop',
        byAi ? 'ai-draft' : 'border border-line bg-surface-raised',
        post.status === 'failed' && 'border-critical/50 bg-critical-soft/40',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <StateBadge map={POST_STATUSES} value={post.status} />
        <span className="inline-flex items-center gap-1 text-xs text-ink-3" title={where.label}>
          <Icon aria-hidden className="size-3.5" />
          <span className={clsx(compact && 'sr-only')}>{where.label}</span>
        </span>
      </div>
      <p className="mt-2 line-clamp-3 text-sm font-semibold text-ink group-hover:text-brand">{post.title}</p>
      <p className="mt-1 text-xs text-ink-3">
        {[pillar(post.pillar).label, FORMATS[post.format] ?? post.format, time].filter(Boolean).join(' · ')}
      </p>
      {byAi && <AiLabel className="mt-2">{post.status === 'idea' ? 'Idea by AI' : 'Draft by AI'}</AiLabel>}
      {post.status === 'idea' && post.ai_reason && !compact && <p className="mt-1 line-clamp-3 text-xs text-ink-2">{post.ai_reason}</p>}
      {post.status === 'failed' && post.error && <p className="mt-2 line-clamp-3 text-xs text-critical-ink">{post.error}</p>}
      {post.status === 'published' && <PostResults post={post} />}
    </motion.button>
  )
}
