/*
  The AI score (1-100) as a ring that fills up, with the number inside.

  One colour for every score (it's a quantity, not a category): a fuller
  ring = more likely to buy. Whether a lead is "hot" is shown separately
  with the 🔥 badge, so the ring never has to carry two meanings.
*/
import { motion } from 'motion/react'

import { duration, ease } from '@/animations/presets'

export function ScoreRing({ score, size = 40, stroke = 4, className }) {
  if (score == null) {
    return (
      <span className="inline-flex items-center justify-center text-xs text-ink-3" style={{ width: size, height: size }}>
        —
      </span>
    )
  }
  const r = (size - stroke) / 2
  return (
    <span
      className={`relative inline-flex shrink-0 items-center justify-center ${className ?? ''}`}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`Score ${score} out of 100`}
    >
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-sunken)" strokeWidth={stroke} />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--brand)"
          strokeWidth={stroke}
          strokeLinecap="round"
          initial={{ pathLength: 0 }}
          animate={{ pathLength: score / 100 }}
          transition={{ duration: duration.slow * 1.5, ease: ease.out }}
        />
      </svg>
      <span className="absolute num font-semibold text-ink" style={{ fontSize: size * 0.32 }}>
        {score}
      </span>
    </span>
  )
}
