/*
  Short messages that pop up and fade away: "Copied", "4 posts planned",
  and 🔥 new hot enquiries from the live feed. Shown by <Toaster/>.

  toast({ title: 'Copied', body: 'Paste it in WhatsApp', tone: 'good' })
  toast({ title: 'Hot enquiry', body: '…', tone: 'accent', to: '/leads/12', action: 'Open' })
*/
let toasts = []
let nextId = 1
const listeners = new Set()

function emit() {
  listeners.forEach((notify) => notify())
}

export function dismiss(id) {
  toasts = toasts.filter((t) => t.id !== id)
  emit()
}

export function toast({ title, body, tone = 'neutral', to, action, seconds = 5 }) {
  const id = nextId++
  toasts = [...toasts.slice(-3), { id, title, body, tone, to, action }]
  emit()
  setTimeout(() => dismiss(id), seconds * 1000)
  return id
}

export const toastStore = {
  subscribe(notify) {
    listeners.add(notify)
    return () => listeners.delete(notify)
  },
  snapshot: () => toasts,
}
