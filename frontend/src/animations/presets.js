/*
  The app's motion vocabulary: how things enter, leave and react.

  Rules (from the design guide):
  - Timing fits the job: tiny feedback is quick, big entrances take longer.
  - Leaving is faster than arriving, so the UI never feels sluggish.
  - Overshoot ("bounce") only on hero cards, never on dense tables or lists.
  - Only opacity and transform are animated (smooth even on cheap phones).
  - "Reduce motion" on the device is respected: <MotionConfig
    reducedMotion="user"> in main.jsx handles Motion; the GSAP helpers
    below check it themselves and jump straight to the end state.

  Motion (motion/react) is used for components appearing/disappearing.
  GSAP is used for numbers counting up and timeline sequences.
*/
import gsap from 'gsap'

// ------------------------------------------------------------- timings
export const duration = {
  fast: 0.15, // hover, press, toggles
  base: 0.25, // menus, tabs, tooltips
  slow: 0.45, // cards and pages entering
}

export const ease = {
  out: [0.16, 1, 0.3, 1], // fast start, soft landing (entering)
  in: [0.7, 0, 0.84, 0], // leaving
  inOut: [0.65, 0, 0.35, 1], // moving from A to B
}

export const spring = {
  snappy: { type: 'spring', stiffness: 520, damping: 38 }, // buttons, toggles
  gentle: { type: 'spring', stiffness: 260, damping: 28 }, // drawers, cards
}

// ------------------------------------------------- Motion variants
// Use as: <motion.div variants={fadeUp} initial="hidden" animate="show" exit="exit" />

export const fadeUp = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: duration.slow, ease: ease.out } },
  exit: { opacity: 0, y: -6, transition: { duration: duration.fast, ease: ease.in } },
}

export const fadeIn = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: duration.base, ease: ease.out } },
  exit: { opacity: 0, transition: { duration: duration.fast } },
}

export const scaleIn = {
  hidden: { opacity: 0, scale: 0.96 },
  show: { opacity: 1, scale: 1, transition: { duration: duration.slow, ease: ease.out } },
  exit: { opacity: 0, scale: 0.98, transition: { duration: duration.fast, ease: ease.in } },
}

/** A parent that reveals its children one after another. */
export function stagger(each = 0.06, delayChildren = 0) {
  return {
    hidden: {},
    show: { transition: { staggerChildren: each, delayChildren } },
    exit: { transition: { staggerChildren: each / 2, staggerDirection: -1 } },
  }
}

/** Rows in lists and tables: short slide, no bounce. */
export const listItem = {
  hidden: { opacity: 0, x: -8 },
  show: { opacity: 1, x: 0, transition: { duration: duration.base, ease: ease.out } },
  exit: { opacity: 0, x: 8, transition: { duration: duration.fast, ease: ease.in } },
}

/** Whole pages when switching in the sidebar. */
export const page = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: duration.slow, ease: ease.out } },
  exit: { opacity: 0, transition: { duration: duration.fast, ease: ease.in } },
}

/** The lead detail drawer sliding in from the right. */
export const drawer = {
  hidden: { x: '100%' },
  show: { x: 0, transition: spring.gentle },
  exit: { x: '100%', transition: { duration: duration.base, ease: ease.in } },
}

/** Press feedback for anything clickable. */
export const press = { whileTap: { scale: 0.97 }, transition: spring.snappy }

// -------------------------------------------------------- GSAP helpers

export function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * Count a number up inside `element` (e.g. 0 → 2,10,000).
 * `format` turns the number into text; returns the tween so callers can kill it.
 */
export function countUp(element, to, { from = 0, seconds = 1.2, format = (n) => Math.round(n).toLocaleString('en-IN') } = {}) {
  if (!element) return null
  if (prefersReducedMotion()) {
    element.textContent = format(to)
    return null
  }
  const counter = { value: from }
  return gsap.to(counter, {
    value: to,
    duration: seconds,
    ease: 'power3.out',
    onUpdate: () => {
      element.textContent = format(counter.value)
    },
    onComplete: () => {
      element.textContent = format(to) // land exactly on the real number
    },
  })
}

/** KPI cards arriving as a wave across a grid (the one place a small bounce is allowed). */
export function revealGrid(targets) {
  if (prefersReducedMotion()) return gsap.set(targets, { opacity: 1, scale: 1, y: 0 })
  return gsap.from(targets, {
    opacity: 0,
    scale: 0.94,
    y: 16,
    duration: 0.45,
    ease: 'back.out(1.4)',
    stagger: { each: 0.06, from: 'start', grid: 'auto' },
    clearProps: 'transform', // hand the cards back to CSS afterwards
  })
}
