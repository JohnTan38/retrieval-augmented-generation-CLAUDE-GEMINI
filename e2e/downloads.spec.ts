import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'


type Manifest = {
  documents: Array<{ download_url: string; filename: string; sha256: string }>
}

const manifest = JSON.parse(
  await readFile(new URL('../data/corpus-manifest.json', import.meta.url), 'utf-8'),
) as Manifest


test('serves every checked corpus download as the exact PDF', async ({ request }) => {
  expect(manifest.documents).toHaveLength(3)

  for (const document of manifest.documents) {
    const response = await request.get(document.download_url)
    expect(response.status(), document.filename).toBe(200)
    expect(response.headers()['content-type'], document.filename).toMatch(/^application\/pdf(?:;|$)/i)
    const body = await response.body()
    expect(body.subarray(0, 5).toString('ascii'), document.filename).toBe('%PDF-')
    expect(createHash('sha256').update(body).digest('hex'), document.filename).toBe(document.sha256)
  }
})
