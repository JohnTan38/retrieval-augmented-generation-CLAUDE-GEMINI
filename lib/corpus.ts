import 'server-only'

import corpusManifest from '@/data/corpus-manifest.json'
import type { CorpusDocument } from '@/lib/api/types'

type CorpusManifest = { documents: CorpusDocument[] }

const manifest = corpusManifest as CorpusManifest

export function loadPublicCorpus(): CorpusDocument[] {
  return manifest.documents
}
