/*
  While a drawer or menu is open, the page behind it must not scroll
  (otherwise scrolling the drawer drags the list underneath).
*/
import { useEffect } from 'react'

export function useLockScroll(locked = true) {
  useEffect(() => {
    if (!locked) return
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [locked])
}
