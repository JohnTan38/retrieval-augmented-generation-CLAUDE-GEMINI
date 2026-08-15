import type { CorpusDocument } from '@/lib/api/types'

type CorpusStripProps = { documents: CorpusDocument[] }

const semesterClassNames = ['semester-teal', 'semester-blue', 'semester-amber']

export function CorpusStrip({ documents }: CorpusStripProps) {
  return (
    <section className="corpus-strip" aria-labelledby="corpus-heading">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Citation corpus</p>
          <h2 id="corpus-heading">Three exam semesters, ready for evidence</h2>
        </div>
        <p className="section-note">Each result will point back to its original page.</p>
      </div>
      <div className="corpus-grid">
        {documents.map((document, index) => (
          <article className={`corpus-card ${semesterClassNames[index % semesterClassNames.length]}`} key={document.document_id}>
            <div className="semester-marker" aria-hidden="true" />
            <p className="semester-label">{document.semester}</p>
            <h3>{document.title}</h3>
            <p className="document-meta">{document.pages} pages · verified study material</p>
            <ul className="topic-list" aria-label={`Topics in ${document.semester}`}>
              {document.topics.slice(0, 3).map((topic) => <li key={topic}>{topic}</li>)}
            </ul>
            <a href={document.download_url} download={document.filename} className="download-link">
              Download PDF <span aria-hidden="true">↓</span><span className="sr-only"> for {document.semester}</span>
            </a>
          </article>
        ))}
      </div>
    </section>
  )
}
