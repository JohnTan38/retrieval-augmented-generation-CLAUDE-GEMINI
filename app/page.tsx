import { StudyWorkspace } from '@/components/StudyWorkspace'
import { loadPublicCorpus } from '@/lib/corpus'

export default function Home() {
  return <StudyWorkspace documents={loadPublicCorpus()} />
}
