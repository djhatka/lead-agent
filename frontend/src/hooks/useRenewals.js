/*
  Renewal reminders (Task 32): memberships and services about to expire.

    useRenewals()             every renewal that needs attention (Renewals page + Home card, refreshes every 30 s)
    useRenewal(id)            one renewal + the ready message (detail view)
    useRenewalAction()        send / snooze / stop / resume / renewed / create, then refresh what it touches
*/
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { keys, LIVE_REFRESH } from '@/hooks/queryKeys'
import { useBusinessId } from '@/hooks/useBusiness'

export function useRenewals() {
  const b = useBusinessId()
  return useQuery({
    queryKey: keys.renewalList(b),
    queryFn: () => api.renewals(b),
    enabled: b != null,
    refetchInterval: LIVE_REFRESH,
  })
}

export function useRenewal(id) {
  const b = useBusinessId()
  return useQuery({
    queryKey: keys.renewal(b, id),
    queryFn: () => api.renewal(b, id),
    enabled: b != null && id != null,
    staleTime: 60_000, // the ready message is written by the AI: don't rewrite it on every focus
  })
}

/**
 * action = { type: 'create', body } | { type: 'send', id } | { type: 'snooze', id, days }
 *        | { type: 'stop', id } | { type: 'resume', id } | { type: 'renewed', id }
 */
export function useRenewalAction() {
  const b = useBusinessId()
  const client = useQueryClient()
  return useMutation({
    mutationFn: (a) => {
      if (a.type === 'create') return api.createRenewal(b, a.body)
      if (a.type === 'send') return api.sendRenewal(b, a.id)
      if (a.type === 'snooze') return api.snoozeRenewal(b, a.id, a.days)
      if (a.type === 'stop') return api.stopRenewal(b, a.id)
      if (a.type === 'resume') return api.resumeRenewal(b, a.id)
      return api.markRenewed(b, a.id)
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.renewals })
    },
  })
}
