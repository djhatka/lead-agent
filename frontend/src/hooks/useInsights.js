/*
  The weekly review.

    useLatestReview()      the newest report (null if none has run yet)
    useReviewHistory(page) older reports
    useRunReview()         start a review, then follow it until it finishes
    useProfile() / useSaveProfile()   the shop's Google/Instagram numbers

  Running a review: the backend answers at once with a run id (with real
  AI it can take a minute). useRunReview then checks that run every
  second; when it's "done" the reports refresh, when "failed" the error
  is shown.
*/
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { api, ApiError } from '@/api/client'
import { keys } from '@/hooks/queryKeys'

export function useLatestReview() {
  return useQuery({
    queryKey: keys.latestReview,
    queryFn: async () => {
      try {
        return await api.latestReview()
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null // no review yet: not an error
        throw error
      }
    },
  })
}

export function useReviewHistory(page = 1) {
  return useQuery({ queryKey: keys.reviewHistory(page), queryFn: () => api.reviews(page) })
}

export function useRunReview() {
  const client = useQueryClient()
  const [runId, setRunId] = useState(null)

  const start = useMutation({
    mutationFn: (days) => api.runReview(days),
    onSuccess: (started) => setRunId(started.run_id),
  })

  const run = useQuery({
    queryKey: keys.agentRun(runId),
    queryFn: () => api.agentRun(runId),
    enabled: runId != null,
    refetchInterval: (q) => (q.state.data?.status === 'running' || !q.state.data ? 1000 : false),
  })

  const status = run.data?.status
  useEffect(() => {
    if (status === 'done') {
      client.invalidateQueries({ queryKey: keys.reviews })
      client.invalidateQueries({ queryKey: keys.agentRuns })
    }
  }, [status, client])

  const running = start.isPending || (runId != null && (!status || status === 'running'))
  const error = start.error?.message ?? (status === 'failed' ? run.data?.error : null)

  return { start: start.mutate, running, run: run.data, error }
}

export function useProfile() {
  return useQuery({ queryKey: keys.profile, queryFn: api.profile })
}

export function useSaveProfile() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (profile) => api.saveProfile(profile),
    onSuccess: (saved) => client.setQueryData(keys.profile, saved),
  })
}
