type StatusBannerProps = { documentCount: number; pageCount: number }

export function StatusBanner({ documentCount, pageCount }: StatusBannerProps) {
  return <p className="status-banner" role="status"><span className="status-dot" aria-hidden="true" />{documentCount} documents · {pageCount} pages ready for evidence</p>
}
