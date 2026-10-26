/*
  A number that counts up when it appears or changes (GSAP).

  <CountUp value={2101500} format={(n) => inr(n, { short: true })} />

  Screen readers get the final value straight away (aria-label), not
  every in-between number.
*/
import { useGSAP } from '@gsap/react'
import { useRef } from 'react'

import { countUp } from '@/animations/presets'

const defaultFormat = (n) => Math.round(n).toLocaleString('en-IN')

export function CountUp({ value, format = defaultFormat, seconds = 1.2, className }) {
  const ref = useRef(null)
  const previous = useRef(0)

  useGSAP(
    () => {
      countUp(ref.current, value, { from: previous.current, seconds, format })
      previous.current = value // next change counts from here, not from 0
    },
    { dependencies: [value], scope: ref },
  )

  return (
    <span ref={ref} className={className} aria-label={format(value)}>
      {format(0)}
    </span>
  )
}
