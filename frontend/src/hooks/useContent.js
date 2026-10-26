/*
  Social media: the week's posts and how past posts did.

    useCalendar(start)        7 days of posts from `start` ('YYYY-MM-DD', India)
    usePlanWeek()             AI fills empty days with ideas      (owner clicks "Plan my week")
    useWriteWeek()            AI writes every idea in the week    (owner clicks "Write all")
    useWritePost()            AI writes one post
    useUpdatePost()           save the owner's edits
    useSchedulePost() / useUnschedulePost() / usePublishNow() / useDeletePost()
    useTopPosts(by)           best posts by ₹ / enquiries / reach / engagement
    useContentStats(days)     what works per kind of post
    useEvents()               upcoming festivals

  Nothing is posted without the owner pressing a button: the AI only
  creates ideas and drafts.
*/
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { keepWithinBusiness, keys } from '@/hooks/queryKeys'
import { useBusinessId } from '@/hooks/useBusiness'

export function useCalendar(start) {
  const b = useBusinessId()
  return useQuery({
    queryKey: keys.calendar(b, start),
    queryFn: () => api.calendar(b, start, 7),
    enabled: b != null,
    placeholderData: keepWithinBusiness(b),
  })
}

/** A content change: refresh every content view (and the AI diary, which logs AI writing). */
function useContentMutation(run) {
  const client = useQueryClient()
  const b = useBusinessId()
  return useMutation({
    mutationFn: (args) => run(b, args),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.content })
      client.invalidateQueries({ queryKey: keys.agentRuns })
    },
  })
}

export const usePlanWeek = () => useContentMutation((b, start) => api.planWeek(b, start))
export const useWriteWeek = () => useContentMutation((b, start) => api.writeWeek(b, start))
export const useWritePost = () => useContentMutation((b, id) => api.writePost(b, id))
export const useUpdatePost = () => useContentMutation((b, { id, changes }) => api.updatePost(b, id, changes))
export const useSchedulePost = () => useContentMutation((b, { id, scheduledAt }) => api.schedulePost(b, id, scheduledAt))
export const useUnschedulePost = () => useContentMutation((b, id) => api.unschedulePost(b, id))
export const usePublishNow = () => useContentMutation((b, id) => api.publishNow(b, id))
export const useDeletePost = () => useContentMutation((b, id) => api.deletePost(b, id))

export function useTopPosts(by) {
  const b = useBusinessId()
  return useQuery({
    queryKey: keys.topPosts(b, by),
    queryFn: () => api.topPosts(b, by, 8),
    enabled: b != null,
    placeholderData: keepWithinBusiness(b),
  })
}

export function useContentStats(days = 90) {
  const b = useBusinessId()
  return useQuery({ queryKey: keys.contentStats(b, days), queryFn: () => api.contentStats(b, days), enabled: b != null })
}

export function useEvents() {
  const b = useBusinessId()
  return useQuery({ queryKey: keys.events(b), queryFn: () => api.events(b), enabled: b != null, staleTime: 60 * 60_000 })
}
