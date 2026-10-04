# Evals: run against a REAL model

Port of `evals/` of zalo-agent (package D1). Run from `pema-agent/backend`:

```bash
uv run python -m evals.run_eval                                   # whole set
EVAL_ONLY=gio-chinh-xac,tra-cuu uv run python -m evals.run_eval   # a subset (every turn is real tokens)
```

Exit code 0 when every case passes, 1 when a case fails or the run stops on a missing precondition.

## Status of the real run

**No real-model run was made by package D1.** What was run is the fake-model suite below (`pytest`). The
instructions for the real run on the GPU PC are in the next section and are untested end to end.

## Real run with a third-party API (current default)

Since 2026-10-02 the agent uses a third-party LLM API, as zalo-agent does; the local Ollama is paused. Any
provider kind works. Use synthetic data only: the eval text leaves the machine.

```bash
export LLM_PROVIDER=openai-compatible          # or anthropic / google (then leave LLM_BASE_URL empty)
export LLM_BASE_URL=https://openrouter.ai/api/v1
export LLM_MODEL=<a model id of that provider that supports tool calling>
export LLM_API_KEY=<your key>                  # never commit it
cd pema-agent/backend
uv run python -m evals.run_eval
```

## Real run with Ollama (GPU PC) - paused (TẠM TẮT LLM LOCAL, 2026-10-02)

Ollama speaks the OpenAI chat-completions API, so it goes through the `openai-compatible` provider of
`pema.agent.providers.openai_compatible`. Ollama does not check the key but the runner insists on a non-empty one.

```bash
ollama pull qwen3:8b                      # any model that supports tool calling
export LLM_PROVIDER=openai-compatible
export LLM_BASE_URL=http://localhost:11434/v1
export LLM_MODEL=qwen3:8b
export LLM_API_KEY=ollama                 # any non-empty string
cd pema-agent/backend
uv run python -m evals.run_eval
```

The first line printed is `Model: <name> (<provider>) - source <...>`: check it before reading the table.
Notes for the run:

* Pick a model with reliable tool calling. A model that never calls tools turns the tool cases red for the
  right reason ("must call X but did not"); a model that cannot call tools at all is not a valid target.
* `LLM_TURN_TIMEOUT_MS` is forced to 180 s by the runner (`eval_env.EVAL_TUNING_OVERRIDES`). A small local model
  on a busy GPU may need more: change the override, never run with a hidden different value.
* Cases that assert FORMATTING (`danh-sach-de-luot-mat`, `tro-chuyen-thi-dung-trang-tri`, `thu-moi-khi-duoc-nho`)
  report FAILED with "the runner did not provide it" unless a `format_reply` is wired; `python -m evals.run_eval` wires C2's (`eval_wiring.real_format_reply`).
  That is deliberate: a skipped case would be a false green.
* Local models vary a lot between runs. Re-run a red case 3 times before changing a persona rule, and read
  `Bot trả lời` in the failure block.

To measure the settings of a real clinic instead of the environment, set `PEMA_EVAL_DATABASE_URL` (an
`postgresql+asyncpg://` URL of a READ-ONLY role), `PEMA_EVAL_CLINIC_ID` and `PEMA_SECRET_ENCRYPTION_KEY`: the DB
then OVERRIDES the environment exactly as in production (`read_real_llm_settings`). Only a `SELECT` is issued.

## Why this exists next to `pytest`

They differ in PURPOSE, not in degree.

`pytest` runs a fake model, so it measures what is deterministic: wiring, error branches, order. A fake model
returns what it was programmed to, so it says nothing about whether a REAL model looks things up instead of
guessing, tells the truth when a tool is missing, or gets worse after the persona is edited.

The evals measure that part. In exchange they need a model, may cost tokens, and run by hand before a release,
not in CI.

## Three vital constraints

1. **Never touch a real channel.** The engine hands the `action` tools a channel to send through. The runner
   builds its own `FakeZaloApi` and a `FakeChannel` and takes none from outside; the last line printed is the
   number of calls it caught.
2. **Temporary state.** Settings are in memory and every case gets a fresh fake conversation store (the original's
   `DELETE FROM memories` is "a new store per case"). The real DB is only READ, for the LLM and search settings.
3. **Assert BEHAVIOUR, not wording.** "Must call `web_search`" is stable; "must contain word X" is randomly red,
   and a randomly red eval is one people stop reading, which loses the real reds too.

## What is faked (and what the original did)

| Original (`run-eval.ts`) | This port |
|---|---|
| goes through `processBatch` (production message processor) | goes through `run_agent_turn` (the engine, D1): the processor is the channel packages' (C1/C2) |
| production tool set, real web search/fetch | `python -m evals.run_eval` wires D4's registry over fake stores (`eval_wiring.real_registry`: real tool bodies, no database); an `EvalWiring()` built by hand keeps `FakeToolRegistry` with canned synthetic web data (`eval_canned_tools.py`); `search_probe` re-enables the web-search precondition |
| reply text and styles recorded by the fake zca-js API | the reply goes through `EvalWiring.format_reply` (C2's clean-up and markdown-to-styles, `eval_wiring.real_format_reply`) into `FakeZaloApi`; without it formatting cases FAIL, never skip |
| temp SQLite dir | in-memory settings + fake stores; env overrides restored at the end |

## The set: 17 original scenarios

| Group (file) | Cases |
|---|---|
| Tool use (`eval_cases_tool.py`) | `gio-chinh-xac`, `ngay-co-san`, `tin-tuc-phai-mo-bai`, `tra-cuu`, `khong-tra-thua`, `cong-cu-hep` |
| Manner of speaking (`eval_cases_cach_noi.py`) | `hoi-lai-khi-thieu`, `khong-hoi-van`, `hoi-gop-mot-lan`, `dinh-dang`, `dan-vao-thi-hoi-lai`, `danh-sach-de-luot-mat`, `luat-thang-lich-su-cu`, `tro-chuyen-thi-dung-trang-tri`, `thu-moi-khi-duoc-nho` |
| Memory (`eval_cases_memory.py`) | `nho-chu-dong`, `dinh-chinh-thi-sua` |

Package P adds the dermatology CSKH set next to these (red flags with and without diacritics, identity not
verified, marketing opt-out, birthday never auto-sent); all cases are fictional.

## Adding a case

Add it to the right `eval_cases_*.py`. `ly_do` is mandatory: a case that cannot say why it exists is one the next
person deletes by mistake when it goes red, or worse, edits until it is green without knowing a barrier was lost.

```python
EvalCase(
    ten="ten-ngan",
    ly_do="Why this case exists, including the incident that caused it",
    tin_nhan="what the user writes",
    disabled_tools=["create_image"],  # turn expensive tools off when the case does not need them
    mong_doi=MongDoi(
        goi_tool=["web_search"],  # MUST be called (calling others too is fine)
        khong_goi_tool=["create_image"],  # must NEVER be called
        goi_tool_it_nhat={"web_fetch": 2},  # a floor on the number of calls
        kiem_tra_text=KiemTraText(mo_ta="...", dat=lambda t: "**" not in t),
    ),
)
```

`kiem_tra_text` is ONLY for structural properties (ends with a question mark, has no `**`, shorter than N).
Asserting semantic content is forbidden. **Turn expensive tools off** in cases that do not need them, for money and,
more importantly, for ACCURACY: a "formatting" case that leaves `create_excel_file` on may produce a file and a
short "file sent", and "no markdown left" is then green while measuring nothing.

## Traps already fallen into (do not fall again)

**A failed turn scored PASS.** The first real run went through the processor, which CATCHES errors and sends a
"technical problem" sentence. The router answered 404 and 3 of 5 cases passed: `khong-tra-thua` ("no tool called":
the turn died), `cong-cu-hep` ("reply longer than 10 characters": the error sentence is longer), `dinh-dang` ("no
markdown": the error sentence has none). `phat_hien_luot_hong` stops this: 0 tokens, or a reply equal to a system
error sentence.

**Reading configuration from a different source than production.** The model is configured through the dashboard
(table `runtime_settings`) and the environment is only a fallback that often keeps an old value. Reading the
environment alone called a wrong model name and led to "the bot is broken" while it was fine. `read_real_*` read
the right source, by the production rule, and the run prints which source won.

**An expectation that contradicts the design.** The first case asked "what day is it" and demanded `get_datetime`,
but the system prompt deliberately already holds the date, so calling the tool is waste, exactly what
`khong-tra-thua` punishes. Now the question about the TIME (not in the prompt) must call the tool and the one about
the DAY must not. Read what the prompt already tells the model before writing an expectation.

**A search service that is dead.** DuckDuckGo returned 0 results and the research case went red with "did not call
web_fetch", a wrong diagnosis. `preflight_web_search` stops the whole run when two ordinary queries both return
nothing.

## Test of the eval suite itself

An eval that does not catch a fault you introduce on purpose is useless. Add a line to `BASE_PERSONA` telling the
model not to use tools, then run `EVAL_ONLY=gio-chinh-xac,tra-cuu uv run python -m evals.run_eval`: both must go
RED with "must call X but did not", and the token count must be NON-ZERO (non-zero means the turn really ran and the
model merely skipped the tool: the difference from a dead turn). Restore the persona afterwards.

## The fake-model tests (no network, no key)

```bash
cd pema-agent/backend
uv run pytest -c pyproject.toml --rootdir=. ../evals
uv run ruff check ../evals && uv run ruff format --check ../evals
uv run pyright -p ../evals/pyrightconfig.json
```

`test_eval_assert.py`, `test_eval_formatting_view.py` and `test_preflight_web_search.py` are the translated
originals; `test_run_eval.py` runs the real engine against a scripted model; `test_eval_env.py` and
`test_eval_report.py` cover the configuration and the table. They ARE part of `make test`: the workspace
`testpaths` of `backend/pyproject.toml` lists `../evals` next to `packages` and `apps`, so a bare `uv run pytest`
runs them (78 tests, fake model); `make lint` checks them with ruff too. Only the run against a REAL model
(`run_eval.py`) is separate.
