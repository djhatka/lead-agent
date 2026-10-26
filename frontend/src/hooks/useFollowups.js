/*
  Follow-up reminders (Task 30): enquiries that have gone quiet.

    useFollowups()           every enquiry that needs a follow-up now (Home card, refreshes every 30 s)
    useLeadFollowup(id)      one enquiry: does it need one? + the ready message (lead drawer)
    useFollowupAction()      send / snooze / stop / resume, then refresh everything it touches
*/
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { keys, LIVE_REFRESH } from '@/hooks/queryKeys'
import { useBusinessId } from '@/hooks/useBusiness'

export function useFollowups() {
  const b = useBusinessId()
  return useQuery({
    queryKey: keys.followupList(b),
    queryFn: () => api.followups(b),
    enabled: b != null,
    refetchInterval: LIVE_REFRESH,
  })
}

export function useLeadFollowup(id) {
  const b = useBusinessId()
  return useQuery({
    queryKey: keys.followup(b, id),
    queryFn: () => api.followup(b, id),
    enabled: b != null && id != null && id !== '',
    staleTime: 60_000, // the ready message is written by the AI: don't rewrite it on every focus
  })
}

/** action = { type: 'send', text, via } | { type: 'snooze', days } | { type: 'stop' } | { type: 'resume' } */
export function useFollowupAction(id) {
  const b = useBusinessId()
  const client = useQueryClient()
  return useMutation({
    mutationFn: (action) => {
      if (action.type === 'send') return api.sendFollowup(b, id, action.text, action.via)
      if (action.type === 'snooze') return api.snoozeFollowup(b, id, action.days)
      if (action.type === 'stop') return api.stopFollowup(b, id)
      return api.resumeFollowup(b, id)
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.followups })
      client.invalidateQueries({ queryKey: keys.lead(b, id) })
      client.invalidateQueries({ queryKey: keys.leads })
      client.invalidateQueries({ queryKey: keys.analytics })
    },
  })
}
