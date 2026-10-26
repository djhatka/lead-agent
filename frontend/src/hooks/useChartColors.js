/*
  Colour tokens as real values, for chart libraries.

  SVG chart libraries (Recharts) write colours into attributes, where CSS
  variables don't reliably work. This reads the current values of the
  tokens from styles/index.css and re-reads them whenever the theme flips,
  so charts change colour together with the rest of the page.

  const c = useChartColors()   // c.brand, c.grid, c.ink3, c.channel.google …
*/
import { useMemo } from 'react'

import { useTheme } from '@/hooks/useTheme'
import { CHANNELS } from '@/styles/tokens'

const TOKENS = ['brand', 'accent', 'good', 'critical', 'ink', 'ink-2', 'ink-3', 'grid', 'axis', 'surface', 'line', 'surface-raised']

export function useChartColors() {
  const { resolved } = useTheme()

  return useMemo(() => {
    const style = getComputedStyle(document.documentElement)
    const read = (name) => style.getPropertyValue(`--${name}`).trim()
    const colors = Object.fromEntries(TOKENS.map((t) => [t.replace('-', ''), read(t)]))
    colors.channel = Object.fromEntries(CHANNELS.map((c) => [c.key, read(`ch-${c.key}`)]))
    colors.theme = resolved
    return colors
  }, [resolved])
}
