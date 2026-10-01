# frontend

Package A only generates TypeScript types from the backend OpenAPI file. Package E scaffolds the Next.js
app (App Router, TypeScript, Tailwind) around this folder, keeps the generator script and owns
`package.json` from then on. Each admin screen of the zalo-agent dashboard maps to a route as listed in
`../docs/PORT-MAP.md` (section "Outside src/").

```
pnpm install
pnpm run gen:types     # ../backend/apps/api/openapi.json -> src/lib/api/schema.d.ts
pnpm run check:types   # tsc --noEmit
```

`src/lib/api/schema.d.ts` is generated and committed; never edit it by hand. Regenerate with
`make types` (from `pema-agent/`) after any backend contract change.
