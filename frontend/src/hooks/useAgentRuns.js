/*
  The AI team's diary.

    useAgentRuns(filters)   runs, newest first
    useAgentRun(id)         one run with every agent's step (re-checks while it's running)
    useWorkflow(name)       the steps of a workflow: 'lead' or 'growth'
*/
import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { keepWithinBusiness, keys, LIVE_REFRESH } from '@/hooks/queryKeys'
import { useBusinessId } from '@/hooks/useBusiness'

export function useAgentRuns(filters = {}) {
  const b = useBusinessId()
  return useQuery({
    queryKey: keys.agentRunList(b, filters),
    queryFn: () => api.agentRuns(b, filters),
    enabled: b != null,
    placeholderData: keepWithinBusiness(b),
    refetchInterval: LIVE_REFRESH,
  })
}

export function useAgentRun(id) {
  const b = useBusinessId()
  return useQuery({
    queryKey: keys.agentRun(b, id),
    queryFn: () => api.agentRun(b, id),
    enabled: b != null && id != null,
    refetchInterval: (q) => (q.state.data?.status === 'running' ? 1000 : false),
  })
}

export function useWorkflow(name) {
  const b = useBusinessId()
  return useQuery({
    queryKey: keys.workflow(b, name),
    queryFn: () => (name === 'lead' ? api.leadWorkflow(b) : api.growthWorkflow(b)),
    enabled: b != null,
    staleTime: 60 * 60_000,
  })
}
