/*
  Phone alerts (Task 28): "🔥 New hot lead" on the owner's own WhatsApp.

  The owner types their personal WhatsApp number (not the business number),
  chooses whether hot-lead alerts are on and whether to hold them at night
  (10pm-8am), and can send a test. The latest alerts are listed underneath,
  with the reason if one couldn't be sent.
*/
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { BellRing, Save, Send } from 'lucide-react'
import { useEffect, useState } from 'react'

import { api } from '@/api/client'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { InlineError } from '@/components/ui/States'
import { toast } from '@/components/ui/toast'
import { useBusinessId } from '@/hooks/useBusiness'
import { timeAgo } from '@/styles/tokens'

const SENDER = {
  lead_intel: 'Sent from Lead Intel’s WhatsApp number.',
  business: 'Sent from your business’s connected WhatsApp number.',
  practice: 'Practice mode: alerts are recorded here but not really sent yet.',
}
const STATUS = {
  sent: { label: 'Sent', tone: 'good' },
  pending: { label: 'Waiting', tone: 'warning' },
  failed: { label: 'Not sent', tone: 'critical' },
  skipped: { label: 'Skipped', tone: 'neutral' },
}

function Switch({ label, hint, checked, onChange, disabled }) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4 py-2">
      <span>
        <span className="block text-sm font-medium text-ink">{label}</span>
        <span className="block text-xs text-ink-3">{hint}</span>
      </span>
      <input type="checkbox" className="mt-1 size-5 accent-[var(--brand)]" checked={checked} disabled={disabled}
             onChange={(e) => onChange(e.target.checked)} />
    </label>
  )
}

export function PhoneAlerts() {
  const b = useBusinessId()
  const queryClient = useQueryClient()
  const me = useQuery({ queryKey: ['me'], queryFn: api.me, staleTime: 5 * 60_000 })
  const isOwner = ['owner', 'admin'].includes(me.data?.user?.role)
  const query = useQuery({ queryKey: ['alerts', b], queryFn: () => api.alertSettings(b), enabled: Boolean(b) })
  const [phone, setPhone] = useState('')
  useEffect(() => {
    if (query.data) setPhone(query.data.phone ? query.data.phone.replace(/^\+91/, '') : '')
  }, [query.data])

  const save = useMutation({
    mutationFn: (changes) => api.updateAlertSettings(b, changes),
    onSuccess: (data) => {
      queryClient.setQueryData(['alerts', b], data)
      toast({ title: 'Alert settings saved', tone: 'good' })
    },
    onError: (error) => toast({ title: "Couldn't save", body: error.message, tone: 'critical' }),
  })
  const test = useMutation({
    mutationFn: () => api.testAlert(b),
    onSuccess: (alert) => {
      queryClient.invalidateQueries({ queryKey: ['alerts', b] })
      toast(alert.status === 'sent'
        ? { title: 'Test alert sent', body: 'Check your WhatsApp.', tone: 'good' }
        : { title: 'Test alert not sent', body: alert.error, tone: 'critical' })
    },
    onError: (error) => toast({ title: "Couldn't send the test", body: error.message, tone: 'critical' }),
  })

  if (query.isPending) return <Skeleton className="h-64 rounded-card" />
  if (query.isError) return <InlineError error={query.error} onRetry={() => query.refetch()} />
  const s = query.data
  const changed = (phone.trim() || null) !== (s.phone ? s.phone.replace(/^\+91/, '') : null)

  return (
    <Card>
      <CardHeader title="Phone alerts" subtitle="A WhatsApp on your own phone the moment a hot enquiry comes in" />
      <form
        className="mt-3 space-y-1"
        onSubmit={(e) => {
          e.preventDefault()
          save.mutate({ phone: phone.trim() || null })
        }}
      >
        <label htmlFor="alert-phone" className="block text-sm font-medium text-ink">
          Your WhatsApp number
          <span className="block text-xs font-normal text-ink-3">Your personal number, not the business number.</span>
        </label>
        <div className="flex gap-2">
          <input id="alert-phone" type="tel" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)}
                 disabled={!isOwner} placeholder="98100 00000"
                 className="h-11 w-full rounded-control border border-line bg-surface-raised px-3 text-ink outline-none focus:border-brand" />
          <Button type="submit" icon={Save} loading={save.isPending} disabled={!isOwner || !changed}>Save</Button>
        </div>
      </form>

      <div className="mt-2 divide-y divide-line">
        <Switch label="Hot-lead alerts" hint="When the AI marks an enquiry hot (very likely to buy)."
                checked={s.hot_leads} disabled={!isOwner || save.isPending} onChange={(v) => save.mutate({ hot_leads: v })} />
        <Switch label="Quiet hours" hint="Hold alerts from 10pm and send them at 8am."
                checked={s.quiet_hours} disabled={!isOwner || save.isPending} onChange={(v) => save.mutate({ quiet_hours: v })} />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        {isOwner && (
          <Button size="sm" icon={Send} loading={test.isPending} disabled={!s.phone} onClick={() => test.mutate()}>
            Send a test alert
          </Button>
        )}
        <p className="text-xs text-ink-3">{SENDER[s.sender]}</p>
      </div>
      {!isOwner && <p className="mt-2 text-xs text-ink-3">Only the business owner can change alerts.</p>}

      {s.recent.length > 0 && (
        <div className="mt-4">
          <p className="mb-1 flex items-center gap-1.5 text-sm font-medium text-ink">
            <BellRing aria-hidden className="size-4" /> Latest alerts
          </p>
          <ul className="divide-y divide-line">
            {s.recent.slice(0, 5).map((a) => {
              const st = a.status === 'sent' && a.sent_by === 'practice'
                ? { label: 'Practice', tone: 'warning' }        // recorded, not really sent
                : (STATUS[a.status] ?? { label: a.status, tone: 'neutral' })
              return (
                <li key={a.id} className="flex items-start justify-between gap-3 py-2 text-sm">
                  <span className="min-w-0">
                    <span className="block truncate text-ink">{a.kind === 'test' ? 'Test alert' : a.text.split(': ').slice(1).join(': ').split('. Reply')[0]}</span>
                    <span className="block text-xs text-ink-3">{timeAgo(a.created_at)}{a.error ? ` · ${a.error}` : ''}</span>
                  </span>
                  <Badge tone={st.tone}>{st.label}</Badge>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </Card>
  )
}
