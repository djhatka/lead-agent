/*
  Follow-up reminders (Task 30): the Settings card.

  On / off, and after how many quiet days an enquiry shows up under
  "Follow up today" on Home (1, 2, 3, 5 or 7; default 2). Only the owner can
  change it; staff see the choice.
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

const DAYS = [1, 2, 3, 5, 7]
const chip = 'h-10 min-w-12 rounded-full border px-3 text-sm transition-colors disabled:cursor-not-allowed'

export function FollowUpSettings() {
  const b = useBusinessId()
  const queryClient = useQueryClient()
  const me = useQuery({ queryKey: ['me'], queryFn: api.me, staleTime: 5 * 60_000 })
  const isOwner = ['owner', 'admin'].includes(me.data?.user?.role)
  const query = useQuery({ queryKey: ['followup-settings', b], queryFn: () => api.followupSettings(b), enabled: Boolean(b) })

  const save = useMutation({
    mutationFn: (changes) => api.updateFollowupSettings(b, changes),
    onSuccess: (data) => {
      queryClient.setQueryData(['followup-settings', b], data)
      queryClient.invalidateQueries({ queryKey: keys.followups })
      toast({ title: 'Follow-up reminders saved', tone: 'good' })
    },
    onError: (error) => toast({ title: "Couldn't save", body: error.message, tone: 'critical' }),
  })

  if (query.isPending) return <Skeleton className="h-44 rounded-card" />
  if (query.isError) return <InlineError error={query.error} onRetry={() => query.refetch()} />
  const s = query.data

  return (
    <Card>
      <CardHeader title="Follow-up reminders" subtitle="Get reminded when an enquiry goes quiet, with a ready message to send in one tap" />

      <div role="radiogroup" aria-label="Follow-up reminders" className="grid grid-cols-2 gap-2">
        {[
          { on: true, label: 'On', hint: 'Show who needs a follow-up' },
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
          <legend className="text-sm font-medium text-ink">Remind me when an enquiry has been quiet for</legend>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {DAYS.map((d) => (
              <button
                key={d}
                type="button"
                aria-pressed={s.after_days === d}
                disabled={!isOwner || save.isPending}
                onClick={() => s.after_days !== d && save.mutate({ after_days: d })}
                className={clsx(chip, s.after_days === d ? 'border-brand bg-brand-soft text-brand' : 'border-line text-ink-2 hover:border-ink-3')}
              >
                {d} day{d === 1 ? '' : 's'}
              </button>
            ))}
          </div>
          <p className="mt-3 text-xs text-ink-3">
            At most 2 follow-ups per enquiry, then we stop, so nobody gets nagged. Enquiries quiet for more than 2 weeks
            are left alone. When the customer writes again, everything starts fresh.
          </p>
        </fieldset>
      )}
      {!isOwner && me.data && <p className="mt-3 text-xs text-ink-3">Only the owner can change this.</p>}
    </Card>
  )
}
