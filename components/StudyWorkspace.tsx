'use client'

import { CorpusStrip } from '@/components/CorpusStrip'
import { QueryComposer } from '@/components/QueryComposer'
import { StatusBanner } from '@/components/StatusBanner'
import type { CorpusDocument } from '@/lib/api/types'
import { sampleQueries } from '@/lib/sample-queries'

type StudyWorkspaceProps = { documents?: CorpusDocument[] }

export function StudyWorkspace({ documents = [] }: StudyWorkspaceProps) {
  const pageCount = documents.reduce((total, document) => total + document.pages, 0)

  return (
    <main className="study-workspace">
      <header className="desk-nav">
        <div className="desk-identity">
          <p className="eyebrow">SWK501 evidence workspace · Singapore social work</p>
          <h1>SgCare Study Desk</h1>
        </div>
        <StatusBanner documentCount={documents.length} pageCount={pageCount} />
      </header>

      <div className="workspace-intro">
        <p className="eyebrow">Evidence desk</p>
        <h2>Trace your exam reasoning to the page that supports it.</h2>
        <p>A focused reading workspace for working through cases, concepts, and interventions in the SWK501 model answers.</p>
      </div>

      <CorpusStrip documents={documents} />

      <section className="question-section" aria-labelledby="question-heading">
        <div className="question-copy">
          <p className="eyebrow">Start a study thread</p>
          <h2 id="question-heading">Ask once. Follow the evidence.</h2>
        </div>
        <QueryComposer disabled={false} onSubmit={() => undefined} />
        <div className="sample-queries" aria-label="Suggested study questions">
          <p>Try a guided question</p>
          <div>
            {sampleQueries.map((query) => <button key={query} type="button" onClick={() => undefined}>{query}</button>)}
          </div>
        </div>
      </section>

      <p className="educational-note">For study and exam preparation. Read the cited material before drawing conclusions.</p>
    </main>
  )
}
