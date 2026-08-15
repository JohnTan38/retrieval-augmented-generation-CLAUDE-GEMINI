'use client'

import Link from 'next/link'

type ErrorPageProps = {
  error: Error & { digest?: string }
  retry: () => void
}

export default function ErrorPage({ retry }: ErrorPageProps) {
  return (
    <main className="route-message" aria-labelledby="route-error-heading">
      <p className="eyebrow">Study desk interruption</p>
      <h1 id="route-error-heading">We could not load the study desk.</h1>
      <p>Your study material is still safe. Try loading this page again, or return to the workspace.</p>
      <div className="route-message-actions">
        <button type="button" onClick={retry}>Try again</button>
        <Link href="/">Return to study desk</Link>
      </div>
    </main>
  )
}
