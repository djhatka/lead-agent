/*
  Follow-up reminder inside the lead drawer (Task 30).

  When an enquiry has gone quiet ("Asked about Zumba 2 days ago. No reply
  yet."), this shows a ready message written by the AI. The owner can change
  it, then send it in one tap:
    - Send             through the connected WhatsApp / Instagram / Facebook
                       (only possible within 24 hours of the customer's last message)
    - Open WhatsApp    opens WhatsApp on their phone with the message typed in;
                       afterwards they confirm "Yes, I sent it" so it's noted here
    - Copy             for Instagram usernames, or when we have no number
  Or: remind me tomorrow / in 3 days / stop reminding me about this one.

  Shows nothing when the enquiry doesn't need a follow-up.
*/
import { BellOff, BellRing, Check, Clock, Copy, MessageCircle, Send } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Skeleton'
import { toast } from '@/components/ui/toast'
import { useFollowupAction, useLeadFollowup } from '@/hooks/useFollowups'
import { when } from '@/styles/tokens'

const linkButton =
  'inline-flex h-11 cursor-pointer items-center gap-2 rounded-control bg-brand px-4 text-sm font-medium whitespace-nowrap text-on-brand shadow-sm transition-colors hover:bg-brand-strong'

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false // e.g. the browser blocked it: the owner can still select the text by hand
  }
}

export function FollowUpPanel({ leadId }) {
  const query = useLeadFollowup(leadId)
  const action = useFollowupAction(leadId)
  const [text, setText] = useState('')
  const [confirming, setConfirming] = useState(false) // opened WhatsApp / copied: did they send it?
  const draft = query.data?.draft
  // Fill the box once per reminder; a background refresh must never wipe what the owner typed.
  const seed = draft ? `${leadId}-${draft.kind}-${draft.nth}` : null
  const [seeded, setSeeded] = useState(null)

  if (seed && seed !== seeded) {
    // React's "adjust state when the data changes" pattern: set it during render, no effect needed
    setSeeded(seed)
    setText(draft.text)
    setConfirming(false)
  }

  if (query.isPending) return <div className="border-t border-line px-5 py-5"><Skeleton className="h-40 w-full rounded-control" /></div>
  if (query.isError) return null // an older server without follow-ups: the drawer works as before

  const f = query.data
  const run = (what, done) =>
    action.mutate(what, {
      onSuccess: (result) => {
        if (what.type === 'send' && result?.delivery === 'failed') {
          toast({ title: 'Not sent', body: result.delivery_error, tone: 'critical', seconds: 10 })
          return
        }
        if (done) toast({ title: done, tone: 'good' })
      },
      onError: (error) => toast({ title: "Couldn't do that", body: error.message, tone: 'critical' }),
    })

  const snoozed = Boolean(f.snoozed_until) // the server only sends it while the snooze is still on
  if (!f.due) {
    if (!f.stopped && !snoozed) return null
    return (
      <section className="flex items-center justify-between gap-3 border-t border-line px-5 py-3">
        <p className="flex items-center gap-2 text-sm text-ink-3">
          <BellOff aria-hidden className="size-4" />
          {f.stopped ? 'Follow-up reminders are off for this enquiry.' : `Follow-up reminder snoozed until ${when(f.snoozed_until)}.`}
        </p>
        <Button size="sm" variant="ghost" loading={action.isPending} onClick={() => run({ type: 'resume' })}>
          Turn back on
        </Button>
      </section>
    )
  }

  const message = text.trim()
  const sendVia = (via) => run({ type: 'send', text: message, via }, 'Follow-up done ✅')

  return (
    <section className="border-t border-line px-5 py-5">
      <div className="rounded-control border border-accent/40 bg-accent-soft/60 p-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-accent-ink">
          <BellRing aria-hidden className="size-4" />
          {f.draft.nth > 1 ? 'Time for one last follow-up' : 'Time to follow up'}
        </h3>
        <p className="mt-1 text-sm text-ink-2">{f.reminder.reason}</p>

        <label className="mt-3 block text-sm">
          <span className="text-ink-3">Ready message (change anything you like)</span>
          <textarea
            value={text}
            onChange={(e) => {
              setText(e.target.value)
              setConfirming(false)
            }}
            rows={4}
            maxLength={1000}
            className="mt-1 w-full resize-y rounded-control border border-line bg-surface-raised px-3 py-2 text-ink"
          />
        </label>
        {f.draft.check === 'replaced' && (
          <p className="text-xs text-ink-3">The AI mentioned a price, so we used the safe message. Add your price yourself if you like.</p>
        )}

        {confirming ? (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-control bg-surface-raised p-3">
            <p className="mr-auto text-sm font-medium text-ink">Did you send it?</p>
            <Button size="sm" variant="primary" icon={Check} loading={action.isPending} onClick={() => sendVia('phone')}>
              Yes, I sent it
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
              Not yet
            </Button>
          </div>
        ) : (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {f.draft.how === 'app' && (
              <Button variant="primary" icon={Send} loading={action.isPending} disabled={!message} onClick={() => sendVia('app')}>
                Send follow-up
              </Button>
            )}
            {f.draft.how === 'whatsapp' && (
              <a
                href={`${f.draft.link}?text=${encodeURIComponent(message)}`}
                target="_blank"
                rel="noreferrer"
                className={linkButton}
                onClick={() => setConfirming(true)}
              >
                <MessageCircle aria-hidden className="size-4" /> Open WhatsApp
              </a>
            )}
            {f.draft.how === 'instagram' && (
              <Button
                variant="primary"
                icon={Copy}
                disabled={!message}
                onClick={async () => {
                  if (await copy(message)) toast({ title: 'Message copied', body: 'Paste it in their Instagram chat', tone: 'good' })
                  window.open(f.draft.link, '_blank', 'noreferrer')
                  setConfirming(true)
                }}
              >
                Copy &amp; open Instagram
              </Button>
            )}
            {f.draft.how === 'copy' && (
              <Button
                variant="primary"
                icon={Copy}
                disabled={!message}
                onClick={async () => {
                  if (await copy(message)) toast({ title: 'Message copied', tone: 'good' })
                  setConfirming(true)
                }}
              >
                Copy message
              </Button>
            )}
          </div>
        )}
        <p className="mt-2 text-xs text-ink-3">{f.draft.note}</p>

        <div className="mt-3 flex flex-wrap items-center gap-1 border-t border-accent/30 pt-3">
          <span className="mr-1 text-xs text-ink-3">Not now:</span>
          <Button size="sm" variant="ghost" icon={Clock} disabled={action.isPending}
                  onClick={() => run({ type: 'snooze', days: 1 }, "OK, we'll remind you tomorrow")}>
            Tomorrow
          </Button>
          <Button size="sm" variant="ghost" disabled={action.isPending}
                  onClick={() => run({ type: 'snooze', days: 3 }, "OK, we'll remind you in 3 days")}>
            In 3 days
          </Button>
          <Button size="sm" variant="ghost" icon={BellOff} disabled={action.isPending}
                  onClick={() => run({ type: 'stop' }, 'Reminders stopped for this enquiry')}>
            Stop reminders
          </Button>
        </div>
      </div>
    </section>
  )
}
