import Link from 'next/link'

export default function NotFound() {
  return (
    <main className="route-message" aria-labelledby="not-found-heading">
      <p className="eyebrow">404</p>
      <h1 id="not-found-heading">Page not found</h1>
      <p>The requested page is not part of this evidence workspace.</p>
      <div className="route-message-actions">
        <Link href="/">Return to study desk</Link>
      </div>
    </main>
  )
}
