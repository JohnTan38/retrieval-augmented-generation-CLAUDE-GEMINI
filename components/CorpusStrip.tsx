import type { CorpusDocument } from '@/lib/api/types'

type CorpusStripProps = { documents: CorpusDocument[] }

const semesterClassNames = ['semester-teal', 'semester-blue', 'semester-amber']

export function CorpusStrip({ documents }: CorpusStripProps) {
  const semesters = Array.from(new Set(documents.map((document) => document.semester)))

  return (
    <section className="corpus-strip" aria-labelledby="corpus-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Citation corpus</p>
          <h2 id="corpus-heading">Three semesters, two study modes each</h2>
        </div>
        <p className="section-note">Research answers lead factual retrieval. CLAUDE recall packs support revision and exam structure.</p>
      </div>
      <div className="corpus-grid">
        {semesters.map((semester, index) => {
          const pairedDocuments = documents.filter((document) => document.semester === semester)
          return (
            <article className={`semester-panel ${semesterClassNames[index % semesterClassNames.length]}`} key={semester}>
              <div className="semester-marker" aria-hidden="true" />
              <p className="semester-label">{semester}</p>
              <h3>Paired exam study set</h3>
              <div className="document-pair">
                {pairedDocuments.map((document) => (
                  <section className="document-row" key={document.document_id} aria-label={`${document.variant === 'research' ? 'Research answer' : 'CLAUDE recall pack'} for ${semester}`}>
                    <div className="document-row-heading">
                      <span className="variant-badge" data-variant={document.variant}>{document.variant === 'research' ? 'Research answer' : 'CLAUDE recall pack'}</span>
                      <span className="document-meta">{document.pages} pages</span>
                    </div>
                    <h4>{document.title}</h4>
                    <ul className="topic-list" aria-label={`Topics in ${document.title}`}>
                      {document.topics.slice(0, 2).map((topic) => <li key={topic}>{topic}</li>)}
                    </ul>
                    <a
                      href={document.download_url}
                      download={document.filename}
                      className="download-link"
                      aria-label={`Download ${document.variant === 'research' ? 'research PDF' : 'CLAUDE recall PDF'} for ${semester}`}
                    >
                      Download PDF <span aria-hidden="true">↓</span>
                    </a>
                  </section>
                ))}
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}
