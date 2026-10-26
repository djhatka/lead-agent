/*
  Shows the current page, with a soft fade when switching pages.

  The trick: when the address changes, the OLD page must stay on screen
  for its short exit animation. `useOutlet()` gives us the page element,
  and we freeze it per address so AnimatePresence can fade it out while
  the new one fades in.
*/
import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import { useLocation, useOutlet } from 'react-router'

import { page } from '@/animations/presets'

function Frozen({ children }) {
  const [kept] = useState(children) // remembered from this page's first render
  return kept
}

export function AnimatedOutlet() {
  const location = useLocation()
  const outlet = useOutlet()
  // Lead detail (/leads/12) opens over the list, so it counts as the same page.
  const pageKey = location.pathname.startsWith('/leads') ? '/leads' : location.pathname

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div key={pageKey} variants={page} initial="hidden" animate="show" exit="exit">
        {pageKey === '/leads' ? outlet : <Frozen>{outlet}</Frozen>}
      </motion.div>
    </AnimatePresence>
  )
}
