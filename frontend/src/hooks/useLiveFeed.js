/*
  The dashboard's live line to the backend (Server-Sent Events).

  One connection for the whole app, opened by <LiveFeedConnection/> in the
  app shell. When an event arrives it is:
  1. added to the recent-events list (newest first, last 100 kept)
  2. used to refresh exactly the data it makes stale, e.g. a new lead
     refreshes the lead lists and the numbers. Refreshes are bundled
     (once per ~0.8 s) so a burst of 10 leads causes one refresh, not 10.
  3. handed to anyone listening for that type (e.g. the hot-lead toast)

  If the line drops, the browser reconnects on its own and tells the
  backend the last event it saw, so nothing is missed.

    const { status, events } = useLiveFeed()          // status: connecting | live | offline
    useLiveEvent('hot_lead', (event) => toast(event))
*/
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useSyncExternalStore } from 'react'

import { api, auth, liveEventIn, LIVE_TYPES } from '@/api/client'
import { useBusinessId } from '@/hooks/useBusiness'
import { keys } from '@/hooks/queryKeys'

const KEEP = 100

// Which cached data each event makes out of date.
const STALE = {
  lead_created: [keys.leads, keys.analytics, keys.followups],
  message_added: [keys.leads, keys.followups],
  lead_updated: [keys.leads, keys.analytics, keys.followups],
  lead_analyzed: [keys.leads, keys.analytics],
  followup_due: [keys.followups],
  renewal_due: [keys.renewals],
  payment_received: [keys.dues],
  payment_claimed: [keys.dues],
  agent_run_finished: [keys.agentRuns],
  insights_ready: [keys.growth, keys.agentRuns],
}
const EVENT_TYPES = [...Object.keys(STALE), 'hot_lead', 'agent_run_started', 'agent_step']
// The backend's own names ("lead.hot"...), translated by liveEventIn() when they arrive.
const SERVER_TYPES = [...Object.keys(LIVE_TYPES), 'post.published', 'post.failed', 'review.new', 'review.unhappy', 'test']

// ------------------------------------------------------------ the store
let state = { status: 'connecting', events: [] }
const watchers = new Set()
const listeners = new Map() // type -> Set(callback)

function setState(patch) {
  state = { ...state, ...patch }
  watchers.forEach((notify) => notify())
}

function subscribe(notify) {
  watchers.add(notify)
  return () => watchers.delete(notify)
}

function connect(queryClient, business) {
  let source = null
  let closed = false
  let pending = new Set()
  let timer = null

  function refreshSoon(type) {
    for (const key of STALE[type] ?? []) pending.add(JSON.stringify(key))
    if (timer || pending.size === 0) return
    timer = setTimeout(() => {
      pending.forEach((key) => queryClient.invalidateQueries({ queryKey: JSON.parse(key) }))
      pending = new Set()
      timer = null
    }, 800)
  }

  function receive(message) {
    let event
    try {
      event = liveEventIn(JSON.parse(message.data))
    } catch {
      return
    }
    if (state.events.some((e) => e.id === event.id)) return // already have it (after a reconnect)
    setState({ events: [event, ...state.events].slice(0, KEEP) })
    refreshSoon(event.type)
    listeners.get(event.type)?.forEach((callback) => callback(event))
  }

  async function open() {
    // Fill the list with what already happened, then listen from there.
    let lastId = 0
    try {
      const recent = await api.liveRecent(business, KEEP)
      setState({ events: [...recent].reverse() })
      lastId = recent.at(-1)?.id ?? 0
    } catch {
      // Backend not up yet: EventSource below keeps retrying.
    }
    if (closed) return

    source = new EventSource(api.liveStreamUrl(business, lastId))
    source.onopen = () => setState({ status: 'live' })
    source.onerror = () => setState({ status: source.readyState === EventSource.CLOSED ? 'offline' : 'connecting' })
    ;[...EVENT_TYPES, ...SERVER_TYPES].forEach((type) => source.addEventListener(type, receive))
  }

  open()
  return () => {
    closed = true
    source?.close()
    clearTimeout(timer)
  }
}

// --------------------------------------------------------------- hooks

/** Mount once, in the app shell. Opens the line and keeps it open. */
export function LiveFeedConnection() {
  const queryClient = useQueryClient()
  const business = useBusinessId()
  const token = useSyncExternalStore(auth.subscribe, auth.snapshot)
  useEffect(() => {
    if (!business || !token) return undefined
    setState({ status: 'connecting', events: [] }) // a new business: start its own list
    return connect(queryClient, business)
  }, [queryClient, business, token])
  return null
}

export function useLiveFeed() {
  return useSyncExternalStore(subscribe, () => state)
}

/** Run `callback(event)` whenever an event of `type` arrives. */
export function useLiveEvent(type, callback) {
  const latest = useRef(callback)
  useEffect(() => {
    latest.current = callback
  })
  useEffect(() => {
    const run = (event) => latest.current(event)
    if (!listeners.has(type)) listeners.set(type, new Set())
    listeners.get(type).add(run)
    return () => listeners.get(type).delete(run)
  }, [type])
}
