/*
  The little counters on the menu: hot enquiries waiting, unhappy reviews
  without a reply, and customers who say they've paid (confirm them). They
  refresh with the data they count.
*/
import { useDueSummary } from '@/hooks/useDues'
import { useLeads } from '@/hooks/useLeads'
import { useReviewSummary } from '@/hooks/useReviews'

export function useNavCounts() {
  // Hot enquiries are only ever open ones (the AI never flags won/lost enquiries as hot).
  const hot = useLeads({ priority: 'hot', page_size: 1 })
  const reviews = useReviewSummary()
  const dues = useDueSummary({ retry: false }) // an older server without payments: just no counter
  return {
    hot: hot.data?.total ?? 0,
    reviews: reviews.data?.needs_attention ?? 0,
    payments: dues.data?.says_paid ?? 0,
  }
}
