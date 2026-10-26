/*
  Reputation: Google reviews, AI-drafted replies, and review requests.

    useReviewSummary()     rating, stars, what people praise and complain about
    useReviews()           every review, unhappy ones first
    useDraftAll()          AI drafts a reply for every unanswered review (nothing is posted)
    usePostReply()         post the owner's reply (only on their click)
    useReviewRequests()    "please review us" messages: waiting / sent / reviewed
    useSkipRequest()       don't send one
*/
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { keys } from '@/hooks/queryKeys'
import { useBusinessId } from '@/hooks/useBusiness'

export function useReviewSummary() {
  const b = useBusinessId()
  return useQuery({ queryKey: keys.reviewSummary(b), queryFn: () => api.reviewSummary(b), enabled: b != null })
}

export function useReviews(filters = {}) {
  const b = useBusinessId()
  return useQuery({ queryKey: keys.reviewList(b, filters), queryFn: () => api.reviews(b, filters), enabled: b != null })
}

export function useReviewRequests() {
  const b = useBusinessId()
  return useQuery({ queryKey: keys.reviewRequests(b), queryFn: () => api.reviewRequests(b), enabled: b != null })
}

function useReviewMutation(run, { diary = false } = {}) {
  const client = useQueryClient()
  const b = useBusinessId()
  return useMutation({
    mutationFn: (args) => run(b, args),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.reviews })
      if (diary) client.invalidateQueries({ queryKey: keys.agentRuns })
    },
  })
}

export const useDraftAll = () => useReviewMutation((b) => api.draftAllReplies(b), { diary: true })
export const usePostReply = () => useReviewMutation((b, { id, text }) => api.postReply(b, id, text))
export const useSkipRequest = () => useReviewMutation((b, id) => api.skipReviewRequest(b, id))
