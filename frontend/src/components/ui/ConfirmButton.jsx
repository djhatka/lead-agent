/*
  A button for things that can't be undone (post now, delete). The first
  press asks "Sure?" right there; the second press does it. No pop-up
  dialogs, and it works the same on a phone.

  <ConfirmButton icon={Send} question="Post this now?" confirmLabel="Yes, post" onConfirm={…}>Post now</ConfirmButton>
*/
import { useState } from 'react'

import { Button } from '@/components/ui/Button'

export function ConfirmButton({ onConfirm, question = 'Are you sure?', confirmLabel = 'Yes', variant = 'secondary', loading, icon, size, children }) {
  const [asking, setAsking] = useState(false)

  if (!asking) {
    return (
      <Button variant={variant} icon={icon} size={size} loading={loading} onClick={() => setAsking(true)}>
        {children}
      </Button>
    )
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-2" role="group" aria-label={question}>
      <span className="text-sm font-medium text-ink">{question}</span>
      <Button
        size={size ?? 'sm'}
        variant={variant === 'danger' ? 'danger' : 'primary'}
        autoFocus
        onClick={() => {
          setAsking(false)
          onConfirm()
        }}
      >
        {confirmLabel}
      </Button>
      <Button size={size ?? 'sm'} variant="ghost" onClick={() => setAsking(false)}>
        Cancel
      </Button>
    </span>
  )
}
