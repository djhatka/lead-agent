/*
  The current page's settings from routes.jsx: title, subtitle, whether it
  uses the 7/30/90-day period switch, and which API areas it reads
  (for the "Sample data" pill).
*/
import { useMatches } from 'react-router'

export function useRouteHandle() {
  const matches = useMatches()
  return [...matches].reverse().find((m) => m.handle)?.handle ?? {}
}
