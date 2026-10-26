/*
  Edit one post, then schedule it. Slides in from the right.

  - An idea shows the AI's reason and a "Write with AI" button (or the
    owner writes it themselves).
  - Caption, hashtags, reel script and shot list are all editable. What the
    AI wrote sits in a dashed "Draft by AI" frame until the owner edits it.
  - Nothing goes out until the owner presses Schedule or Post now. Post now
    and Delete ask "Sure?" first.
  - Published posts are read-only and show what they brought: enquiries
    and ₹ first, then reach and likes.

  All times are India time.
*/
import clsx from 'clsx'
import { CalendarClock, PenLine, Plus, Save, Send, Trash2, Undo2, X } from 'lucide-react'
import { useState } from 'react'

import { AiLabel, WhyNote } from '@/components/ui/AiNote'
import { StateBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ConfirmButton } from '@/components/ui/ConfirmButton'
import { Drawer } from '@/components/ui/Drawer'
import { toast } from '@/components/ui/toast'
import {
  useDeletePost,
  usePublishNow,
  useSchedulePost,
  useUnschedulePost,
  useUpdatePost,
  useWritePost,
} from '@/hooks/useContent'
import { count, FORMATS, inr, pillar, platform, PILLARS, POST_STATUSES, when } from '@/styles/tokens'

const IST_MS = 330 * 60_000
/** ISO time → "2026-10-18T19:00" in India time, for <input type="datetime-local">. */
const toIstInput = (value) => new Date(new Date(value).getTime() + IST_MS).toISOString().slice(0, 16)
/** "2026-10-18T19:00" (India time) → ISO time. */
const fromIstInput = (value) => new Date(`${value}:00+05:30`).toISOString()

const POST_PLATFORMS = ['instagram', 'facebook', 'google', 'youtube']
const MAX_CAPTION = 2200 // Instagram's limit

const field = 'w-full rounded-control border border-line bg-surface-raised px-3 py-2 text-sm text-ink outline-none transition-colors focus-visible:border-brand disabled:opacity-70'

const fromPost = (p) => ({
  title: p.title ?? '',
  platform: p.platform,
  format: p.format,
  pillar: p.pillar,
  caption: p.caption ?? '',
  hashtags: p.hashtags ?? [],
  script: p.script ?? '',
  shot_list: p.shot_list ?? [],
})

function Label({ children, hint, htmlFor }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 flex items-baseline justify-between gap-2 text-sm font-medium text-ink">
      {children}
      {hint && <span className="text-xs font-normal text-ink-3">{hint}</span>}
    </label>
  )
}

function HashtagInput({ value, onChange, disabled }) {
  const [text, setText] = useState('')
  function add(raw) {
    const tags = raw
      .split(/[\s,]+/)
      .map((t) => t.trim().replace(/^#*/, ''))
      .filter(Boolean)
      .map((t) => `#${t}`)
    const next = [...value, ...tags.filter((t) => !value.includes(t))]
    if (next.length !== value.length) onChange(next)
    setText('')
  }
  return (
    <div className={clsx(field, 'flex flex-wrap items-center gap-1.5 py-1.5')}>
      {value.map((tag) => (
        <span key={tag} className="inline-flex items-center gap-1 rounded-full bg-brand-soft py-0.5 pr-1 pl-2.5 text-xs font-medium text-brand">
          {tag}
          {!disabled && (
            <button
              type="button"
              onClick={() => onChange(value.filter((t) => t !== tag))}
              aria-label={`Remove ${tag}`}
              className="flex size-5 cursor-pointer items-center justify-center rounded-full hover:bg-brand/15"
            >
              <X aria-hidden className="size-3" />
            </button>
          )}
        </span>
      ))}
      {!disabled && (
        <input
          id="post-hashtags"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (['Enter', ',', ' '].includes(e.key)) {
              e.preventDefault()
              add(text)
            } else if (e.key === 'Backspace' && !text && value.length) onChange(value.slice(0, -1))
          }}
          onBlur={() => text && add(text)}
          placeholder={value.length ? 'Add more…' : '#PuneGym, #DiwaliOffer…'}
          className="min-w-24 flex-1 bg-transparent py-1 outline-none"
        />
      )}
    </div>
  )
}

function ShotList({ value, onChange, disabled }) {
  return (
    <div className="space-y-2">
      {value.map((shot, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="num w-5 shrink-0 text-right text-xs text-ink-3">{i + 1}.</span>
          <input
            value={shot}
            disabled={disabled}
            aria-label={`Shot ${i + 1}`}
            onChange={(e) => onChange(value.map((s, j) => (j === i ? e.target.value : s)))}
            className={field}
          />
          {!disabled && (
            <button
              type="button"
              onClick={() => onChange(value.filter((_, j) => j !== i))}
              aria-label={`Remove shot ${i + 1}`}
              className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-control text-ink-3 hover:bg-surface-sunken hover:text-critical-ink"
            >
              <X aria-hidden className="size-4" />
            </button>
          )}
        </div>
      ))}
      {!disabled && (
        <Button size="sm" variant="ghost" icon={Plus} onClick={() => onChange([...value, ''])}>
          Add a shot
        </Button>
      )}
    </div>
  )
}

function Results({ post }) {
  const r = post.results ?? {}
  const m = post.metrics ?? {}
  const money = [
    { label: 'Enquiries', value: count(r.enquiries ?? 0) },
    { label: 'Customers', value: count(r.customers ?? 0) },
    { label: 'Revenue', value: inr(r.revenue ?? 0) },
  ]
  const reach = [
    { label: 'Reach', value: count(m.reach ?? 0) },
    { label: 'Likes', value: count(m.likes ?? 0) },
    { label: 'Engagement', value: `${m.engagement_pct ?? 0}%` },
  ]
  return (
    <section className="space-y-3">
      <h3 className="text-xs font-semibold tracking-wide text-ink-3 uppercase">What it brought</h3>
      <dl className="grid grid-cols-3 gap-2">
        {money.map((x) => (
          <div key={x.label} className="rounded-control bg-good-soft p-3">
            <dt className="text-xs text-good-ink">{x.label}</dt>
            <dd className="mt-0.5 text-lg font-bold text-ink">{x.value}</dd>
          </div>
        ))}
      </dl>
      <dl className="grid grid-cols-3 gap-2">
        {reach.map((x) => (
          <div key={x.label} className="rounded-control bg-surface-sunken p-3">
            <dt className="text-xs text-ink-3">{x.label}</dt>
            <dd className="mt-0.5 font-semibold text-ink">{x.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

export function PostEditor({ post, onClose }) {
  const update = useUpdatePost()
  const write = useWritePost()
  const schedule = useSchedulePost()
  const unschedule = useUnschedulePost()
  const publish = usePublishNow()
  const remove = useDeletePost()

  const [form, setForm] = useState(() => fromPost(post))
  const [at, setAt] = useState(() => toIstInput(post.scheduled_at ?? post.suggested_at ?? Date.now() + 86_400_000))

  // When the saved post changes (the AI wrote it, a save landed), show the new version.
  const version = JSON.stringify(fromPost(post))
  const [seen, setSeen] = useState(version)
  if (version !== seen) {
    setSeen(version)
    setForm(fromPost(post))
  }

  const set = (key) => (value) => setForm((f) => ({ ...f, [key]: value }))
  const dirty = JSON.stringify(form) !== version
  const live = post.status === 'published'
  const busy = [update, write, schedule, unschedule, publish, remove].some((m) => m.isPending)
  const failed = [update, write, schedule, unschedule, publish, remove].find((m) => m.isError)
  const unwritten = post.status === 'idea' && !post.caption
  const byAi = post.created_by !== 'owner' && !post.edited && post.status === 'draft'
  const isVideo = ['reel', 'story'].includes(form.format)

  async function run(action) {
    try {
      await action()
    } catch {
      // The error is shown under the form.
    }
  }

  const saveIfNeeded = async () => {
    if (dirty) await update.mutateAsync({ id: post.id, changes: form })
  }

  const fields = (
    <div className="space-y-4">
      <div>
        <Label htmlFor="post-title">Title (only you see this)</Label>
        <input id="post-title" value={form.title} disabled={live} onChange={(e) => set('title')(e.target.value)} className={field} />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div>
          <Label htmlFor="post-platform">Where</Label>
          <select id="post-platform" value={form.platform} disabled={live} onChange={(e) => set('platform')(e.target.value)} className={clsx(field, 'cursor-pointer')}>
            {POST_PLATFORMS.map((p) => (
              <option key={p} value={p}>
                {platform(p).label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="post-format">Format</Label>
          <select id="post-format" value={form.format} disabled={live} onChange={(e) => set('format')(e.target.value)} className={clsx(field, 'cursor-pointer')}>
            {Object.entries(FORMATS).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="post-pillar">Type</Label>
          <select id="post-pillar" value={form.pillar} disabled={live} onChange={(e) => set('pillar')(e.target.value)} className={clsx(field, 'cursor-pointer')}>
            {Object.entries(PILLARS).map(([key, p]) => (
              <option key={key} value={key}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <Label htmlFor="post-caption" hint={`${form.caption.length.toLocaleString('en-IN')} / ${MAX_CAPTION.toLocaleString('en-IN')}`}>
          Caption
        </Label>
        <textarea
          id="post-caption"
          rows={6}
          maxLength={MAX_CAPTION}
          value={form.caption}
          disabled={live}
          onChange={(e) => set('caption')(e.target.value)}
          placeholder="What do you want to say? Mention the offer and how to book."
          className={clsx(field, 'resize-y leading-relaxed')}
        />
      </div>
      <div>
        <Label htmlFor="post-hashtags" hint="Press Enter after each">
          Hashtags
        </Label>
        <HashtagInput value={form.hashtags} onChange={set('hashtags')} disabled={live} />
      </div>
      {(isVideo || form.script) && (
        <div>
          <Label htmlFor="post-script">Reel script</Label>
          <textarea
            id="post-script"
            rows={5}
            value={form.script}
            disabled={live}
            onChange={(e) => set('script')(e.target.value)}
            placeholder="Hook in the first 2 seconds, then the middle, then what to do next."
            className={clsx(field, 'resize-y leading-relaxed')}
          />
        </div>
      )}
      <div>
        <Label>Shot list</Label>
        <ShotList value={form.shot_list} onChange={set('shot_list')} disabled={live} />
      </div>
    </div>
  )

  const footer = live ? (
    <div className="flex justify-end">
      <Button onClick={onClose}>Close</Button>
    </div>
  ) : post.status === 'scheduled' ? (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <Button icon={Undo2} loading={unschedule.isPending} onClick={() => run(async () => {
        await unschedule.mutateAsync(post.id)
        toast({ title: 'Unscheduled', body: 'It is a draft again. Nothing was posted.' })
      })}>
        Unschedule
      </Button>
      <div className="flex flex-wrap items-center gap-2">
        {dirty && (
          <Button icon={Save} loading={update.isPending} onClick={() => run(async () => {
            await update.mutateAsync({ id: post.id, changes: form })
            toast({ title: 'Changes saved', tone: 'good' })
          })}>
            Save changes
          </Button>
        )}
        <ConfirmButton icon={Send} question="Post it now?" confirmLabel="Yes, post now" loading={publish.isPending} onConfirm={() => run(async () => {
          await saveIfNeeded()
          await publish.mutateAsync(post.id)
          toast({ title: 'Posted', body: `${post.title} is live on ${platform(form.platform).label}.`, tone: 'good' })
          onClose()
        })}>
          Post now
        </ConfirmButton>
      </div>
    </div>
  ) : (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-0 flex-1">
          <Label htmlFor="post-when">When should it go out? (India time)</Label>
          <input id="post-when" type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} className={clsx(field, 'h-11')} />
        </div>
        <Button
          variant="primary"
          icon={CalendarClock}
          disabled={!at || busy}
          loading={schedule.isPending}
          onClick={() => run(async () => {
            await saveIfNeeded()
            const scheduled = await schedule.mutateAsync({ id: post.id, scheduledAt: fromIstInput(at) })
            toast({ title: 'Scheduled', body: `Goes out ${when(scheduled?.scheduled_at ?? fromIstInput(at))} on ${platform(form.platform).label}.`, tone: 'good' })
            onClose()
          })}
        >
          Schedule
        </Button>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <ConfirmButton variant="danger" icon={Trash2} size="sm" question="Delete this post?" confirmLabel="Delete" loading={remove.isPending} onConfirm={() => run(async () => {
          await remove.mutateAsync(post.id)
          toast({ title: 'Post deleted' })
          onClose()
        })}>
          Delete
        </ConfirmButton>
        <div className="flex flex-wrap gap-2">
          {post.status === 'failed' && (
            <ConfirmButton size="sm" icon={Send} question="Try posting now?" confirmLabel="Yes, try now" loading={publish.isPending} onConfirm={() => run(async () => {
              await saveIfNeeded()
              await publish.mutateAsync(post.id)
              toast({ title: 'Posted', tone: 'good' })
              onClose()
            })}>
              Try again now
            </ConfirmButton>
          )}
          <Button size="sm" icon={Save} disabled={!dirty} loading={update.isPending} onClick={() => run(async () => {
            await update.mutateAsync({ id: post.id, changes: form })
            toast({ title: 'Draft saved', tone: 'good' })
          })}>
            Save draft
          </Button>
        </div>
      </div>
    </div>
  )

  return (
    <Drawer
      eyebrow={
        <span className="flex flex-wrap items-center gap-2">
          <StateBadge map={POST_STATUSES} value={post.status} />
          <span>
            {platform(post.platform).label} · {pillar(post.pillar).label} · {post.scheduled_at || post.published_at ? when(post.published_at ?? post.scheduled_at) : `planned for ${when(post.suggested_at)}`}
          </span>
        </span>
      }
      title={post.title || 'Untitled post'}
      onClose={onClose}
      footer={footer}
    >
      <div className="space-y-5 p-5">
        {post.ai_reason && <WhyNote label="Why the AI suggests this">{post.ai_reason}</WhyNote>}

        {post.status === 'failed' && post.error && (
          <p role="alert" className="rounded-control border border-critical/40 bg-critical-soft p-3 text-sm text-critical-ink">
            {post.error}
          </p>
        )}
        {post.status === 'scheduled' && (
          <p className="rounded-control border border-brand/30 bg-brand-soft p-3 text-sm text-ink">
            Goes out <span className="font-semibold">{when(post.scheduled_at)}</span> on {platform(post.platform).label}. You can still change it.
          </p>
        )}
        {live && <Results post={post} />}

        {unwritten && (
          <div className="ai-draft rounded-control p-4 text-center">
            <p className="text-sm text-ink-2">This is just an idea so far. Let the AI write the caption, hashtags and script, then check it.</p>
            <Button
              className="mt-3"
              variant="primary"
              icon={PenLine}
              loading={write.isPending}
              onClick={() => run(async () => {
                await write.mutateAsync(post.id)
                toast({ title: 'Draft written', body: 'Read it through and change anything before you schedule it.', tone: 'good' })
              })}
            >
              Write with AI
            </Button>
            <p className="mt-2 text-xs text-ink-3">or write it yourself below</p>
          </div>
        )}

        {/* Same wrapper either way, so typing never resets the field you're in. */}
        <div className={clsx(byAi && !dirty && 'ai-draft rounded-control p-3')}>
          {byAi && !dirty ? <AiLabel className="mb-3">Draft by AI · read it before you schedule</AiLabel> : null}
          {fields}
        </div>

        {failed && (
          <p role="alert" className="text-sm text-critical-ink">
            {failed.error.message}
          </p>
        )}
      </div>
    </Drawer>
  )
}
