'use client'

import { KeyboardEvent, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { SourceCard } from '@/components/SourceCard'
import type { SourceEvidence } from '@/lib/api/types'

export type EvidenceRibbonProps = {
  sources: SourceEvidence[]
  activeSourceId: string | null
  onSelect: (sourceId: string) => void
  activationKey?: string | number
  restoreFocusCitationKey?: string | null
}

function useMobileEvidence() {
  const [mobile, setMobile] = useState(false)
  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 760px)')
    if (!media) return
    const update = () => setMobile(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  return mobile
}

export function EvidenceRibbon({ sources, activeSourceId, onSelect, activationKey, restoreFocusCitationKey }: EvidenceRibbonProps) {
  const mobile = useMobileEvidence()
  const [manuallyOpen, setManuallyOpen] = useState(false)
  const [dismissedActivation, setDismissedActivation] = useState<string | number | null>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const returnFocusRef = useRef<HTMLElement | null>(null)
  const sourceRefs = useRef(new Map<string, HTMLElement>())
  const wasOpen = useRef(false)
  const currentActivation = activationKey ?? activeSourceId
  const sheetOpen = mobile && (manuallyOpen || (activeSourceId !== null && currentActivation !== dismissedActivation))

  useLayoutEffect(() => {
    if (!sheetOpen) return
    if (!wasOpen.current) {
      returnFocusRef.current = restoreFocusCitationKey
        ? document.querySelector<HTMLElement>(`[data-citation-key="${restoreFocusCitationKey}"]`)
        : document.activeElement as HTMLElement
    }
    closeRef.current?.focus()
    wasOpen.current = true
  }, [restoreFocusCitationKey, sheetOpen])

  useEffect(() => {
    if (sheetOpen || !wasOpen.current) return
    wasOpen.current = false
    returnFocusRef.current?.focus()
  }, [sheetOpen])

  useEffect(() => {
    if (!activeSourceId) return
    if (mobile && !sheetOpen) return
    const source = sourceRefs.current.get(activeSourceId)
    source?.focus()
    source?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' })
  }, [activationKey, activeSourceId, mobile, sheetOpen])

  if (sources.length === 0) return null

  function closeSheet() {
    setManuallyOpen(false)
    setDismissedActivation(currentActivation)
  }

  const cards = sources.map((source, index) => (
    <SourceCard
      key={source.source_id}
      ref={(node) => {
        if (node) sourceRefs.current.set(source.source_id, node)
        else sourceRefs.current.delete(source.source_id)
      }}
      source={source}
      rank={index + 1}
      active={source.source_id === activeSourceId}
      onSelect={onSelect}
    />
  ))

  function handleDialogKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      closeSheet()
      return
    }
    if (event.key !== 'Tab') return
    const focusable = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])'))
    const first = focusable[0]!
    const last = focusable[focusable.length - 1]!
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  if (mobile) {
    return (
      <section className="evidence-mobile">
        <button ref={triggerRef} type="button" className="evidence-trigger" aria-haspopup="dialog" onClick={() => setManuallyOpen(true)}>
          Review {sources.length} {sources.length === 1 ? 'source' : 'sources'}
        </button>
        {sheetOpen ? (
          <div className="sheet-backdrop">
            <div className="evidence-sheet" role="dialog" aria-modal="true" aria-labelledby="evidence-sheet-title" onKeyDown={handleDialogKeyDown}>
              <div className="sheet-heading">
                <div>
                  <p className="eyebrow">Citation thread</p>
                  <h2 id="evidence-sheet-title">Evidence from your results</h2>
                </div>
                <button ref={closeRef} type="button" className="sheet-close" onClick={closeSheet} aria-label="Close evidence">×</button>
              </div>
              <div className="evidence-card-list">{cards}</div>
            </div>
          </div>
        ) : null}
      </section>
    )
  }

  return (
    <section className="evidence-ribbon" aria-labelledby="evidence-heading">
      <div className="evidence-heading-row">
        <div><p className="eyebrow">Citation thread</p><h2 id="evidence-heading">Evidence behind this answer</h2></div>
        <p>{sources.length} ranked {sources.length === 1 ? 'passage' : 'passages'}</p>
      </div>
      <div className="evidence-card-list">{cards}</div>
    </section>
  )
}
