/*
  Content calendar: the next 7 days of posts as cards.

  - "Plan my week": the AI puts an idea on every empty day, each with its reason.
  - "Write all": the AI writes caption, hashtags, script and shot list for every idea.
  - Click a post to edit it, then schedule it. Nothing is posted until the
    owner presses Schedule or Post now.

  Big screens: a 7-column board. Phones and tablets: one day under the other.
  The window starts today and moves a week at a time (?from=YYYY-MM-DD,
  so a refresh keeps it).
*/
import clsx from 'clsx'
import { CalendarX, ChevronLeft, ChevronRight, PenLine, Sparkles } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useState } from 'react'
import { useSearchParams } from 'react-router'

import { stagger } from '@/animations/presets'
import { PostCard } from '@/components/content/PostCard'
import { PostEditor } from '@/components/content/PostEditor'
import { PageHeader } from '@/components/layout/PageHeader'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { ErrorState } from '@/components/ui/States'
import { toast } from '@/components/ui/toast'
import { useCalendar, usePlanWeek, useWriteWeek } from '@/hooks/useContent'
import { addDaysKey, dayLabel, istDateKey, plural } from '@/styles/tokens'

const shortDay = (key) => new Date(`${key}T12:00:00Z`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', timeZone: 'UTC' })
const weekday = (key) => new Date(`${key}T12:00:00Z`).toLocaleDateString('en-IN', { weekday: 'short', timeZone: 'UTC' })
const TALLY = {
  scheduled: ['scheduled', 'scheduled'],
  draft: ['draft', 'drafts'],
  idea: ['idea', 'ideas'],
  published: ['published', 'published'],
  failed: ["couldn't post", "couldn't post"],
}
const howMany = (answer, key) => answer?.[key] ?? answer?.posts?.length ?? (Array.isArray(answer) ? answer.length : 0)

function WeekNav({ start, setStart }) {
  const today = istDateKey()
  const button = 'flex size-11 cursor-pointer items-center justify-center rounded-control text-ink-2 hover:bg-surface-sunken'
  return (
    <div className="flex items-center gap-1 rounded-control border border-line bg-surface-raised p-0.5">
      <button type="button" aria-label="Previous 7 days" className={button} onClick={() => setStart(addDaysKey(start, -7))}>
        <ChevronLeft aria-hidden className="size-5" />
      </button>
      <span className="num min-w-32 px-1 text-center text-sm font-medium text-ink">
        {shortDay(start)} – {shortDay(addDaysKey(start, 6))}
      </span>
      <button type="button" aria-label="Next 7 days" className={button} onClick={() => setStart(addDaysKey(start, 7))}>
        <ChevronRight aria-hidden className="size-5" />
      </button>
      {start !== today && (
        <button type="button" className="h-11 cursor-pointer rounded-control px-3 text-sm font-medium text-brand hover:bg-brand-soft" onClick={() => setStart(today)}>
          Today
        </button>
      )}
    </div>
  )
}

function DayHeader({ date, compact }) {
  const isToday = date === istDateKey()
  const label = dayLabel(date)
  return (
    <div className={clsx('flex items-baseline gap-2', compact ? 'mb-2' : 'mb-3')}>
      <span className={clsx('text-sm font-semibold', isToday ? 'text-brand' : 'text-ink')}>{compact ? weekday(date) : label}</span>
      <span className="num text-xs text-ink-3">{compact ? (isToday ? 'Today' : shortDay(date)) : ['Today', 'Tomorrow', 'Yesterday'].includes(label) ? shortDay(date) : ''}</span>
    </div>
  )
}

function EmptyDay({ past }) {
  return (
    <div className="flex min-h-20 items-center justify-center rounded-control border border-dashed border-line px-2 py-4 text-center text-xs text-ink-3">
      {past ? 'No post' : 'Nothing planned yet'}
    </div>
  )
}

function BoardSkeleton() {
  return (
    <div className="grid gap-3 xl:grid-cols-7" aria-busy="true" aria-label="Loading posts">
      {Array.from({ length: 7 }, (_, i) => (
        <div key={i} className="space-y-2">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-28 w-full rounded-control" />
        </div>
      ))}
    </div>
  )
}

export default function ContentCalendar() {
  const [params, setParams] = useSearchParams()
  const today = istDateKey()
  const start = /^\d{4}-\d{2}-\d{2}$/.test(params.get('from') ?? '') ? params.get('from') : today
  const setStart = useCallback(
    (key) => setParams((p) => {
      const next = new URLSearchParams(p)
      if (key === istDateKey()) next.delete('from')
      else next.set('from', key)
      return next
    }, { replace: true }),
    [setParams],
  )

  const calendar = useCalendar(start)
  const plan = usePlanWeek()
  const writeAll = useWriteWeek()
  const [openId, setOpenId] = useState(null)
  const close = useCallback(() => setOpenId(null), [])

  const days = calendar.data?.days ?? []
  const posts = days.flatMap((d) => d.posts)
  const open = posts.find((p) => p.id === openId)
  const ideas = posts.filter((p) => p.status === 'idea' && p.date >= today).length
  const emptyDays = days.filter((d) => d.date >= today && !d.posts.some((p) => p.status !== 'failed')).length
  const tally = ['scheduled', 'draft', 'idea', 'published', 'failed']
    .map((s) => [s, posts.filter((p) => p.status === s).length])
    .filter(([, n]) => n)

  function planWeek() {
    plan.mutate(start, {
      onSuccess: (answer) => {
        const n = howMany(answer, 'created')
        toast(n
          ? { title: `Planned ${plural(n, 'post')}`, body: 'Ideas are on the empty days. Open one to see why, or press Write all.', tone: 'good' }
          : { title: 'Nothing to plan', body: 'Every day in these 7 days already has a post.' })
      },
      onError: (error) => toast({ title: "Couldn't plan the week", body: error.message, tone: 'critical' }),
    })
  }

  function writeWeek() {
    writeAll.mutate(start, {
      onSuccess: (answer) => {
        const n = howMany(answer, 'written')
        toast(n
          ? { title: `Wrote ${plural(n, 'draft')}`, body: 'Read each one before you schedule it.', tone: 'good' }
          : { title: 'No ideas to write', body: 'Press Plan my week first.' })
      },
      onError: (error) => toast({ title: "Couldn't write the posts", body: error.message, tone: 'critical' }),
    })
  }

  return (
    <div>
      <PageHeader
        actions={
          <>
            <WeekNav start={start} setStart={setStart} />
            <Button variant="primary" icon={Sparkles} loading={plan.isPending} disabled={!calendar.data || emptyDays === 0} onClick={planWeek}>
              Plan my week
            </Button>
            <Button icon={PenLine} loading={writeAll.isPending} disabled={!calendar.data || ideas === 0} onClick={writeWeek}>
              Write all{ideas ? ` (${ideas})` : ''}
            </Button>
          </>
        }
      />

      {calendar.isPending ? (
        <BoardSkeleton />
      ) : calendar.isError ? (
        <ErrorState error={calendar.error} onRetry={() => calendar.refetch()} />
      ) : (
        <div className={clsx('transition-opacity duration-200', calendar.isPlaceholderData && 'opacity-60')}>
          <p className="mb-4 text-sm text-ink-3" aria-live="polite">
            {tally.length ? tally.map(([s, n]) => `${n} ${TALLY[s][n === 1 ? 0 : 1]}`).join(' · ') : 'No posts in these 7 days yet.'}
            {emptyDays > 0 && ` · ${plural(emptyDays, 'empty day')}`}
          </p>

          {posts.length === 0 && emptyDays === 0 ? (
            <Card className="flex flex-col items-center gap-2 py-10 text-center">
              <CalendarX aria-hidden className="size-9 text-ink-3" />
              <p className="font-semibold text-ink">Nothing was posted in these 7 days</p>
            </Card>
          ) : (
            <>
              {/* Big screens: a 7-column board */}
              <motion.div variants={stagger(0.03)} initial="hidden" animate="show" className="hidden gap-3 xl:grid xl:grid-cols-7">
                {days.map((day) => (
                  <section key={day.date} aria-label={dayLabel(day.date)} className={clsx('min-w-0 rounded-card p-2', day.date === today && 'bg-brand-soft/50')}>
                    <DayHeader date={day.date} compact />
                    <div className="space-y-2">
                      {day.posts.length ? day.posts.map((post) => <PostCard key={post.id} post={post} onOpen={setOpenId} compact />) : <EmptyDay past={day.date < today} />}
                    </div>
                  </section>
                ))}
              </motion.div>

              {/* Phones and tablets: one day under the other */}
              <motion.div variants={stagger(0.03)} initial="hidden" animate="show" className="space-y-5 xl:hidden">
                {days.map((day) => (
                  <section key={day.date} aria-label={dayLabel(day.date)}>
                    <DayHeader date={day.date} />
                    <div className="grid gap-2 sm:grid-cols-2">
                      {day.posts.length ? day.posts.map((post) => <PostCard key={post.id} post={post} onOpen={setOpenId} />) : <EmptyDay past={day.date < today} />}
                    </div>
                  </section>
                ))}
              </motion.div>
            </>
          )}
        </div>
      )}

      <AnimatePresence>{open && <PostEditor key={open.id} post={open} onClose={close} />}</AnimatePresence>
    </div>
  )
}
