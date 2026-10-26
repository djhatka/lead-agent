/*
  Shown for an address that doesn't exist, or if a page crashes while
  loading. Always offers a way back to the Overview.
*/
import { Compass } from 'lucide-react'
import { isRouteErrorResponse, Link, useRouteError } from 'react-router'

import { Card } from '@/components/ui/Card'

export default function NotFound() {
  const error = useRouteError()
  const crashed = error && !(isRouteErrorResponse(error) && error.status === 404)

  return (
    <div className="flex min-h-[60dvh] items-center justify-center p-4">
      <Card className="max-w-md text-center">
        <Compass aria-hidden className="mx-auto size-10 text-ink-3" />
        <h2 className="mt-3 text-xl font-semibold">{crashed ? 'Something went wrong' : 'Page not found'}</h2>
        <p className="mt-1 text-ink-2">
          {crashed
            ? 'This page hit an error. Going back to the overview usually fixes it.'
            : "There's no page at this address."}
        </p>
        <Link
          to="/"
          className="mt-5 inline-flex h-11 items-center rounded-control bg-brand px-4 text-sm font-medium text-on-brand hover:bg-brand-strong"
        >
          Back to Overview
        </Link>
      </Card>
    </div>
  )
}
