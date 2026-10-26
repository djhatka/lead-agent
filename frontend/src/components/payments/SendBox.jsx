/*
  "Send this message" box, used for payment links and reminders (Task 31).

  Shows the ready message (the owner can change it) and the right button for
  how it can go out:
    app        Send: through the connected WhatsApp / Instagram / Facebook (inside the 24 hours)
    whatsapp   Open WhatsApp: on the owner's phone with the message typed in
    instagram  Copy & open Instagram
    copy       Copy message
  After Open WhatsApp / Copy we ask "Did you send it?", so the dashboard only
  notes it when it really went.

  <SendBox text={ready.request} how={ready.how} link={ready.link} note={ready.note}
           busy={isPending} onSend={(via, text) => …} onCancel={close} />
*/
import { Check, Copy, MessageCircle, Send } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/Button'
import { toast } from '@/components/ui/toast'

const linkButton =
  'inline-flex h-11 cursor-pointer items-center gap-2 rounded-control bg-brand px-4 text-sm font-medium whitespace-nowrap text-on-brand shadow-sm transition-colors hover:bg-brand-strong'

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false // the browser blocked it: the owner can still select the text by hand
  }
}

export function SendBox({ text: ready, how, link, note, busy, onSend, onCancel, label = 'Message' }) {
  const [text, setText] = useState(ready)
  const [confirming, setConfirming] = useState(false)
  const message = text.trim()

  return (
    <div className="space-y-2">
      <label className="block text-sm">
        <span className="text-ink-3">{label} (change anything you like)</span>
        <textarea
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            setConfirming(false)
          }}
          rows={4}
          maxLength={1000}
          className="mt-1 w-full resize-y rounded-control border border-line bg-surface-raised px-3 py-2 text-sm text-ink"
        />
      </label>

      {confirming ? (
        <div className="flex flex-wrap items-center gap-2 rounded-control bg-surface-sunken p-3">
          <p className="mr-auto text-sm font-medium text-ink">Did you send it?</p>
          <Button size="sm" variant="primary" icon={Check} loading={busy} onClick={() => onSend('phone', message)}>
            Yes, I sent it
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
            Not yet
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          {how === 'app' && (
            <Button variant="primary" icon={Send} loading={busy} disabled={!message} onClick={() => onSend('app', message)}>
              Send
            </Button>
          )}
          {how === 'whatsapp' && (
            <a
              href={`${link}?text=${encodeURIComponent(message)}`}
              target="_blank"
              rel="noreferrer"
              className={linkButton}
              onClick={() => setConfirming(true)}
            >
              <MessageCircle aria-hidden className="size-4" /> Open WhatsApp
            </a>
          )}
          {(how === 'instagram' || how === 'copy') && (
            <Button
              variant="primary"
              icon={Copy}
              disabled={!message}
              onClick={async () => {
                if (await copy(message)) toast({ title: 'Message copied', tone: 'good' })
                if (how === 'instagram') window.open(link, '_blank', 'noreferrer')
                setConfirming(true)
              }}
            >
              {how === 'instagram' ? 'Copy & open Instagram' : 'Copy message'}
            </Button>
          )}
          {onCancel && (
            <Button variant="ghost" onClick={onCancel}>
              Close
            </Button>
          )}
        </div>
      )}
      {note && <p className="text-xs text-ink-3">{note}</p>}
    </div>
  )
}
