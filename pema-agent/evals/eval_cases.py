# ported from: evals/eval-cases.ts
"""The set of cases that run against a REAL model: where the groups are gathered.

Originally one file (each case ~15 lines, splitting is fiddly) with a promise to "split above 200 lines". The
memory group touched 255 lines so it was split for real, by WHAT IS MEASURED and not by line count: tool use,
manner of speaking, memory.

EXPENSIVE TOOLS ARE TURNED OFF per case (``create_image``, ``create_word_document``, ``create_excel_file``)
in the cases that do not need them. Two reasons, the second is the main one:

* Money: one image call is real money and 60-135 seconds of waiting.
* ACCURACY of the measurement: the "formatting" case asks for a comparison table, and with
  ``create_excel_file`` on the model quite likely creates an Excel file and answers with a short "file sent";
  then "the final text has no markdown left" is green and measures nothing.

Package P adds the dermatology CSKH cases next to these (all fictional).
"""

from __future__ import annotations

from evals.eval_case_type import EvalCase
from evals.eval_cases_cach_noi import CASE_CACH_NOI
from evals.eval_cases_memory import CASE_MEMORY
from evals.eval_cases_tool import CASE_TOOL

EVAL_CASES: list[EvalCase] = [*CASE_TOOL, *CASE_CACH_NOI, *CASE_MEMORY]
