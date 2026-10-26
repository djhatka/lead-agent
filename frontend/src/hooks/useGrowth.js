/*
  The weekly growth review.

    useReports(limit)      latest reviews, newest first
    useReport(id)          one review
    useRunReview()         start a review now, and follow it until it's ready
    useCopyWhatsapp()      put a review on the clipboard as a WhatsApp message

  Running a review: some servers answer with the finished review, others
  with a run id to follow (with real AI it can take a minute). In the
  second case we check that run every second; when it's "done" the
  reviews refresh, when "failed" its error is shown.
*/
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { api } from '@/api/client'
import { keys } from '@/hooks/queryKeys'
import { useBusiness, useBusinessId } from '@/hooks/useBusiness'

export function useReports(limit = 10) {
  const b = useBusinessId()
  return useQuery({ queryKey: keys.reports(b, limit), queryFn: () => api.growthReports(b, limit), enabled: b != null })
}

export function useReport(id) {
  const b = useBusinessId()
  return useQuery({ queryKey: keys.report(b, id), queryFn: () => api.growthReport(b, id), enabled: b != null && id != null })
}

export function useRunReview() {
  const client = useQueryClient()
  const b = useBusinessId()
  const [runId, setRunId] = useState(null)

  const refresh = () => {
    client.invalidateQueries({ queryKey: keys.growth })
    client.invalidateQueries({ queryKey: keys.agentRuns })
  }

  const start = useMutation({
    mutationFn: () => api.runGrowthReview(b, 7),
    onSuccess: (answer) => {
      if (answer?.run_id && !answer.headline) setRunId(answer.run_id) // follow the run
      else refresh()
    },
  })

  const run = useQuery({
    queryKey: keys.agentRun(b, runId),
    queryFn: () => api.agentRun(b, runId),
    enabled: runId != null,
    refetchInterval: (q) => (q.state.data?.status === 'running' || !q.state.data ? 1000 : false),
  })

  const status = run.data?.status
  useEffect(() => {
    if (status === 'done') {
      client.invalidateQueries({ queryKey: keys.growth })
      client.invalidateQueries({ queryKey: keys.agentRuns })
    }
  }, [status, client])

  const running = start.isPending || (runId != null && (!status || status === 'running'))
  const error = start.error?.message ?? (status === 'failed' ? run.data?.error : null)
  return { start: () => start.mutate(), running, steps: run.data?.steps ?? [], error }
}

export function useCopyWhatsapp() {
  const b = useBusinessId()
  const { business } = useBusiness()
  return useMutation({
    mutationFn: async (report) => {
      const { text } = await api.reportWhatsapp(b, report, business?.name)
      try {
        await navigator.clipboard.writeText(text)
      } catch {
        throw new Error("Couldn't copy. Your browser blocked the clipboard.")
      }
      return text
    },
  })
}
