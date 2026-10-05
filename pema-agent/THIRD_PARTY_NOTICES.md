# Third-party notices

Pema Agent (`pema-agent/`) is a derivative work of two MIT-licensed projects. Their copyright notices and
permission notices are reproduced below as the MIT license requires. Nothing in this repository adds any
restriction on top of them.

## 1. zalo-agent (derivative work)

* Source: https://github.com/vuhai2002/zalo-agent, version 0.3.1, commit `bf154de68335e73073c2b6913c731be22ca3d0e6`.
* Relationship: the Python backend under `pema-agent/backend/apps/api/pema/` is a module-by-module
  translation of the TypeScript `src/` of zalo-agent (channels, middleware, agent loop, persona, tools,
  conversation and memory, knowledge base, scheduler, MCP client, token accounting, configuration) and the
  Next.js frontend under `pema-agent/frontend/` re-implements the features of its React dashboard (`web/`).
  Constants, thresholds and the reasoning in the comments are kept; every translated file starts with
  `# ported from: src/<path>.ts` and the mapping of every upstream file is in `docs/PORT-MAP.md`.
* Changes: TypeScript to Python, SQLite to PostgreSQL (pgvector added), Vercel AI SDK to the `openai` SDK
  with a hand-written tool loop, Hono/Vite to FastAPI/Next.js, a clinic CRM and policy profiles added.
  The upstream repository is not modified.

```text
MIT License

Copyright (c) 2026 Vu Van Hai

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 2. zca-js

* Source: https://github.com/RFS-ADRENO/zca-js (npm package `zca-js` 2.1.2, the version pinned by zalo-agent).
* Relationship: not translated and not vendored in the Python code. It is used as an unmodified npm
  dependency by the optional Node bridge `pema-agent/backend/bridges/zalo-personal/` that drives a personal
  Zalo account. zca-js is an UNOFFICIAL, reverse-engineered client; using it can get the account locked
  (see the bridge README).

```text
MIT License

Copyright (c) 2024 - 2025 RFS-ADRENO, truong9c2208, JustKemForFun

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## 3. Other dependencies

Python and Node dependencies are installed from their registries under their own licenses (see
`backend/uv.lock` and `frontend/pnpm-lock.yaml`). Fonts, logos and artwork of zalo-agent are NOT copied.
