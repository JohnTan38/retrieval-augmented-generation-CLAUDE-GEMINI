import type { Metadata } from 'next'
import { IBM_Plex_Mono, Sora, Source_Sans_3 } from 'next/font/google'
import './globals.css'

const sora = Sora({
  subsets: ['latin'],
  variable: '--font-display',
  display: 'swap',
})

const sourceSans = Source_Sans_3({
  subsets: ['latin'],
  variable: '--font-reading',
  display: 'swap',
})

const plexMono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '600', '700'],
  variable: '--font-evidence',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'SgCare Study Desk | SWK501 Evidence Desk',
  description: 'Citation-backed SWK501 study workspace',
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${sora.variable} ${sourceSans.variable} ${plexMono.variable}`}>
      <body>{children}</body>
    </html>
  )
}
