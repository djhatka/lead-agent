/*
  The business profile the AI writes from, and the connected social accounts.

    useBusinessProfile() / useUpdateBusiness()
    useSocialAccounts() / useAddSocialAccount() / useUpdateSocialAccount()
*/
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { keys } from '@/hooks/queryKeys'
import { useBusinessId } from '@/hooks/useBusiness'

export function useBusinessProfile() {
  const b = useBusinessId()
  return useQuery({ queryKey: keys.business(b), queryFn: () => api.business(b), enabled: b != null })
}

export function useUpdateBusiness() {
  const client = useQueryClient()
  const b = useBusinessId()
  return useMutation({
    mutationFn: (changes) => api.updateBusiness(b, changes),
    onSuccess: (saved) => {
      client.setQueryData(keys.business(b), saved)
      client.invalidateQueries({ queryKey: keys.businesses }) // the name in the switcher
    },
  })
}

export function useSocialAccounts() {
  const b = useBusinessId()
  return useQuery({ queryKey: keys.social(b), queryFn: () => api.socialAccounts(b), enabled: b != null })
}

function useSocialMutation(run) {
  const client = useQueryClient()
  const b = useBusinessId()
  return useMutation({
    mutationFn: (args) => run(b, args),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.social(b) }),
  })
}

export const useAddSocialAccount = () => useSocialMutation((b, account) => api.addSocialAccount(b, account))
export const useUpdateSocialAccount = () =>
  useSocialMutation((b, { id, changes }) => api.updateSocialAccount(b, id, changes))
