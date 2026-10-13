import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import openapiTS, { astToString } from 'openapi-typescript'

const schemaUrl = new URL('../../contracts/openapi.json', import.meta.url)
const target = fileURLToPath(new URL('../src/api/schema.d.ts', import.meta.url))
const generated = astToString(await openapiTS(schemaUrl))
// The CLI adds a generated-file header; compare its body to the library result.
const committed = readFileSync(target, 'utf8').replace(/^\/\*\*[\s\S]*?\*\/\s*/, '')
if (committed.replace(/\r\n/g, '\n').trim() !== generated.trim()) {
  console.error('API types differ from OpenAPI. Run npm run generate:api.')
  process.exitCode = 1
} else {
  console.log('API types match OpenAPI.')
}
