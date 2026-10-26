/*
  Renewal reminders (Task 32): the Settings card.

  On / off, and how many days before expiry to remind (3, 5, 7, 10, or 14; default 5).
  Only the owner can change it; staff see the choice.
*/
import clsx from 'clsx'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { Card, CardHeader } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { InlineError } from '@/components/ui/States'
import { toast } from '@/components/ui/toast'
import { keys } from '@/hooks/queryKeys'
import { useBusinessId } from '@/hooks/useBusiness'

const DAYS = [3, 5, 7, 10, 14]
const chip = 'h-10 min-w-12 rounded-full border px-3 text-sm transition-colors disabled:cursor-not-allowed'

export function RenewalSettings() {
  const b = useBusinessId()
  const queryClient = useQueryClient()
  const me = useQuery({ queryKey: ['me'], queryFn: api.me, staleTime: 5 * 60_000 })
  const isOwner = ['owner', 'admin'].includes(me.data?.user?.role)
  const query = useQuery({ queryKey: keys.renewalSettings(b), queryFn: () => api.renewalSettings(b), enabled: Boolean(b) })

  const save = useMutation({
    mutationFn: (changes) => api.updateRenewalSettings(b, changes),
    onSuccess: (data) => {
      queryClient.setQueryData(keys.renewalSettings(b), data)
      queryClient.invalidateQueries({ queryKey: keys.renewals })
      toast({ title: 'Renewal reminders saved', tone: 'good' })
    },
    onError: (error) => toast({ title: "Couldn't save", body: error.message, tone: 'critical' }),
  })

  if (query.isPending) return <Skeleton className="h-44 rounded-card" />
  if (query.isError) return <InlineError error={query.error} onRetry={() => query.refetch()} />
  const s = query.data

  return (
    <Card>
      <CardHeader title="Renewal reminders" subtitle="Get reminded when a customer's membership or service is about to expire, with a ready message to send" />

      <div role="radiogroup" aria-label="Renewal reminders" className="grid grid-cols-2 gap-2">
        {[
          { on: true, label: 'On', hint: 'Show who needs to renew' },
          { on: false, label: 'Off', hint: 'No reminders' },
        ].map((o) => (
          <button
            key={o.label}
            type="button"
            role="radio"
            aria-checked={s.enabled === o.on}
            disabled={!isOwner || save.isPending}
            onClick={() => s.enabled !== o.on && save.mutate({ enabled: o.on })}
            className={clsx(
              'rounded-control border px-3 py-2 text-left transition-colors disabled:cursor-not-allowed',
              s.enabled === o.on ? 'border-brand bg-brand-soft' : 'border-line bg-surface-raised hover:border-ink-3',
            )}
          >
            <span className={clsx('block text-sm font-medium', s.enabled === o.on ? 'text-brand' : 'text-ink')}>{o.label}</span>
            <span className="block text-xs text-ink-3">{o.hint}</span>
          </button>
        ))}
      </div>

      {s.enabled && (
        <fieldset className="mt-4">
          <legend className="text-sm font-medium text-ink">Remind me this many days before expiry</legend>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {DAYS.map((d) => (
              <button
                key={d}
                type="button"
                aria-pressed={s.remind_days_before === d}
                disabled={!isOwner || save.isPending}
                onClick={() => s.remind_days_before !== d && save.mutate({ remind_days_before: d })}
                className={clsx(chip, s.remind_days_before === d ? 'border-brand bg-brand-soft text-brand' : 'border-line text-ink-2 hover:border-ink-3')}
              >
                {d} day{d === 1 ? '' : 's'}
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-ink-3">
            Renewals that expired more than 30 days ago are left alone. You can snooze or stop any
            individual renewal from the Renewals page.
          </p>
        </fieldset>
      )}
      {!isOwner && me.data && <p className="mt-3 text-xs text-ink-3">Only the owner can change this.</p>}
    </Card>
  )
}
