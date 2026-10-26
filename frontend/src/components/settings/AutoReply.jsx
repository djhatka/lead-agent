/*
  Instant first reply (Task 29): the AI answers a NEW WhatsApp / Instagram /
  Facebook enquiry within seconds, in the business's voice, even at night.

  The owner chooses Off / Always / Only after hours, sets opening times and
  closed days (used to say "we're closed, we'll get back at 9 am"), can add a
  note that ends every reply, and can PREVIEW a reply before turning it on.
  The latest automatic replies are listed underneath.
*/
import clsx from 'clsx'
import { Bot, Eye, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { InlineError } from '@/components/ui/States'
import { toast } from '@/components/ui/toast'
import { useBusinessId } from '@/hooks/useBusiness'
import { timeAgo } from '@/styles/tokens'

const MODES = [
  { key: 'off', label: 'Off', hint: 'Nothing is sent automatically.' },
  { key: 'always', label: 'Always', hint: 'Every new enquiry, day and night.' },
  { key: 'after_hours', label: 'After hours', hint: 'Only when you’re closed.' },
]
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const CHANNEL_NAMES = { whatsapp: 'WhatsApp', instagram: 'Instagram', facebook: 'Facebook' }
const field = 'h-11 w-full rounded-control border border-line bg-surface-raised px-3 text-ink outline-none focus:border-brand'

export function AutoReply() {
  const b = useBusinessId()
  const queryClient = useQueryClient()
  const me = useQuery({ queryKey: ['me'], queryFn: api.me, staleTime: 5 * 60_000 })
  const isOwner = ['owner', 'admin'].includes(me.data?.user?.role)
  const query = useQuery({ queryKey: ['auto-reply', b], queryFn: () => api.autoReplySettings(b), enabled: Boolean(b) })

  const [hours, setHours] = useState({ opens: '09:00', closes: '21:00', closed_days: [], note: '' })
  const [sample, setSample] = useState('Hi, what are your timings? Kitne ki fees hai?')
  useEffect(() => {
    if (query.data) {
      const { opens, closes, closed_days, note } = query.data
      setHours({ opens, closes, closed_days, note })
    }
  }, [query.data])

  const save = useMutation({
    mutationFn: (changes) => api.updateAutoReplySettings(b, changes),
    onSuccess: (data) => {
      queryClient.setQueryData(['auto-reply', b], data)
      toast({ title: 'Instant reply settings saved', tone: 'good' })
    },
    onError: (error) => toast({ title: "Couldn't save", body: error.message, tone: 'critical' }),
  })
  const preview = useMutation({ mutationFn: (message) => api.previewAutoReply(b, message) })

  if (query.isPending) return <Skeleton className="h-80 rounded-card" />
  if (query.isError) return <InlineError error={query.error} onRetry={() => query.refetch()} />
  const s = query.data
  const connected = Object.entries(s.channels).filter(([, on]) => on).map(([p]) => CHANNEL_NAMES[p])
  const changed =
    hours.opens !== s.opens || hours.closes !== s.closes || hours.note.trim() !== s.note ||
    [...hours.closed_days].sort().join() !== [...s.closed_days].sort().join()
  const toggleDay = (d) =>
    setHours((h) => ({ ...h, closed_days: h.closed_days.includes(d) ? h.closed_days.filter((x) => x !== d) : [...h.closed_days, d] }))

  return (
    <Card>
      <CardHeader title="Instant first reply" subtitle="The AI answers new WhatsApp and Instagram enquiries within seconds, in your voice" />

      <div role="radiogroup" aria-label="When to reply" className="grid grid-cols-3 gap-2">
        {MODES.map((m) => (
          <button
            key={m.key}
            type="button"
            role="radio"
            aria-checked={s.mode === m.key}
            disabled={!isOwner || save.isPending}
            onClick={() => save.mutate({ mode: m.key })}
            className={clsx(
              'rounded-control border px-2 py-2 text-left transition-colors disabled:cursor-not-allowed',
              s.mode === m.key ? 'border-brand bg-brand-soft' : 'border-line bg-surface-raised hover:border-ink-3',
            )}
          >
            <span className={clsx('block text-sm font-medium', s.mode === m.key ? 'text-brand' : 'text-ink')}>{m.label}</span>
            <span className="block text-xs text-ink-3">{m.hint}</span>
          </button>
        ))}
      </div>

      {connected.length === 0 ? (
        <p className="mt-3 rounded-control bg-warning-soft px-3 py-2 text-sm text-warning-ink">
          Replies go out through your connected chats, and none is connected yet.{' '}
          <Link to="/settings/connections" className="font-medium underline">Connect WhatsApp or Instagram</Link>
        </p>
      ) : (
        <p className="mt-3 text-xs text-ink-3">Replies go out on: {connected.join(', ')}.</p>
      )}

      <form
        className="mt-4 space-y-3"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate({ ...hours, note: hours.note.trim() })
        }}
      >
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm font-medium text-ink">
            Opens
            <input type="time" required value={hours.opens} disabled={!isOwner}
                   onChange={(e) => setHours({ ...hours, opens: e.target.value })} className={clsx(field, 'mt-1')} />
          </label>
          <label className="text-sm font-medium text-ink">
            Closes
            <input type="time" required value={hours.closes} disabled={!isOwner}
                   onChange={(e) => setHours({ ...hours, closes: e.target.value })} className={clsx(field, 'mt-1')} />
          </label>
        </div>
        <fieldset>
          <legend className="text-sm font-medium text-ink">Closed on</legend>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {DAYS.map((day, d) => (
              <button key={day} type="button" disabled={!isOwner} aria-pressed={hours.closed_days.includes(d)}
                      onClick={() => toggleDay(d)}
                      className={clsx('h-9 min-w-11 rounded-full border px-3 text-sm',
                        hours.closed_days.includes(d) ? 'border-brand bg-brand-soft text-brand' : 'border-line text-ink-2')}>
                {day}
              </button>
            ))}
          </div>
        </fieldset>
        <label className="block text-sm font-medium text-ink">
          Note at the end of every reply <span className="font-normal text-ink-3">(optional)</span>
          <input value={hours.note} maxLength={200} disabled={!isOwner} placeholder="For emergencies call 98100 00000"
                 onChange={(e) => setHours({ ...hours, note: e.target.value })} className={clsx(field, 'mt-1')} />
        </label>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" size="sm" icon={Save} loading={save.isPending} disabled={!isOwner || !changed}>Save hours and note</Button>
          <span className="text-xs text-ink-3">
            {s.open_now ? 'Open now.' : `Closed now: a reply would say you’ll get back ${s.back_at}.`}
          </span>
        </div>
      </form>

      <div className="mt-5 border-t border-line pt-4">
        <p className="mb-1 flex items-center gap-1.5 text-sm font-medium text-ink">
          <Eye aria-hidden className="size-4" /> Preview a reply
        </p>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (sample.trim()) preview.mutate(sample.trim())
          }}
        >
          <input aria-label="A sample customer message" value={sample} maxLength={1000} onChange={(e) => setSample(e.target.value)}
                 className={field} />
          <Button type="submit" size="sm" loading={preview.isPending}>Preview</Button>
        </form>
        {preview.isError && <p role="alert" className="mt-2 text-sm text-critical-ink">{preview.error.message}</p>}
        {preview.data && (
          <div className="mt-3 flex justify-end">
            <div className="max-w-[90%] rounded-2xl rounded-br-md bg-brand px-3.5 py-2 text-sm text-on-brand">
              <p className="whitespace-pre-wrap">{preview.data.reply}</p>
              <p className="mt-1 text-[11px] text-on-brand/75">🤖 Auto-reply · preview, not sent</p>
            </div>
          </div>
        )}
        {preview.data?.check === 'replaced' && (
          <p className="mt-2 text-xs text-ink-3">The AI mentioned a price or a link, so the safe ready-made reply is used instead.</p>
        )}
        <p className="mt-2 text-xs text-ink-3">
          {s.ai_mode === 'mock'
            ? 'Practice mode: replies use ready-made text. With the AI switched on, each one is written fresh in your brand voice.'
            : 'Written fresh for each customer from your services and brand voice (Business profile). It never quotes prices.'}
        </p>
      </div>

      {!isOwner && <p className="mt-2 text-xs text-ink-3">Only the business owner can change instant replies.</p>}

      {s.recent.length > 0 && (
        <div className="mt-4">
          <p className="mb-1 flex items-center gap-1.5 text-sm font-medium text-ink">
            <Bot aria-hidden className="size-4" /> Latest instant replies
          </p>
          <ul className="divide-y divide-line">
            {s.recent.slice(0, 5).map((r) => (
              <li key={`${r.lead_id}-${r.sent_at}`} className="flex items-start justify-between gap-3 py-2 text-sm">
                <Link to={`/leads/${r.lead_id}`} className="min-w-0 hover:underline">
                  <span className="block truncate text-ink">{r.customer}</span>
                  <span className="block truncate text-xs text-ink-3">
                    {timeAgo(r.sent_at)} · {r.delivery_error || r.text}
                  </span>
                </Link>
                <Badge tone={r.delivery === 'sent' ? 'good' : 'critical'}>{r.delivery === 'sent' ? 'Sent' : 'Not sent'}</Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}
