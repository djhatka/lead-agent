/*
  A card that shows one piece of data, with every state handled the same way:

    loading  → a skeleton the size of the content (no jump when it arrives)
    error    → the server's message and a "Try again" button
    empty    → `empty` (if given and isEmpty(data) is true)
    refetch  → the old content stays, slightly dimmed (no skeleton flash)

  <QueryCard query={useSources(days)} title="…" subtitle="…" empty="No enquiries yet" isEmpty={(d) => !d.length}>
    {(data) => <BarList … />}
  </QueryCard>
*/
import clsx from 'clsx'

import { Card, CardHeader } from '@/components/ui/Card'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState, InlineError } from '@/components/ui/States'

export function QueryCard({ query, title, subtitle, action, empty, isEmpty, skeleton = 'h-48', className, children }) {
  let body
  if (query.isPending) body = <Skeleton className={clsx('w-full', skeleton)} />
  else if (query.isError) body = <InlineError error={query.error} onRetry={() => query.refetch()} />
  else if (empty && isEmpty?.(query.data)) body = <EmptyState title={empty} className="py-6" />
  else body = <div className={clsx('transition-opacity duration-200', query.isPlaceholderData && 'opacity-60')}>{children(query.data)}</div>

  return (
    <Card className={clsx('h-full', className)}>
      {title && <CardHeader title={title} subtitle={typeof subtitle === 'function' ? (query.data ? subtitle(query.data) : null) : subtitle} action={action} />}
      {body}
    </Card>
  )
}
