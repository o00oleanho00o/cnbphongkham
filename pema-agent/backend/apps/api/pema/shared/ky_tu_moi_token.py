# ported from: src/shared/ky-tu-moi-token.ts
"""Characters per token for Vietnamese.

MEASURED in zalo-agent with ``gpt-tokenizer`` (the original OpenAI BPE tables) on 4 real Vietnamese
samples (conversation, news, technical, the ``<noi_dung_ngoai>`` block):

* o200k family (GPT-4o/5): 3.1 - 3.8 chars/token
* cl100k family (GPT-4):   2.1 - 2.2 chars/token
* English control:         4.5

2.5 over-estimates (24-52% against the real number) for the o200k family but still UNDER-estimates 12-17%
for cl100k. Anthropic's tokenizer is not public so it could not be measured for the default model. The
safety margin ``HE_SO_AN_TOAN`` (30%) absorbs that shortfall, but this is the place to watch through the
``uoc_luong.lech_phan_tram`` log, not a settled constant.

WHY IT IS ITS OWN FILE: three parties need it and two of them must not pull in ``token_estimate``
(agent) : the cross-rule validator in ``config/runtime_tuning_settings`` (config must not import agent)
and the Settings page that shows "~ N tokens" under a character field. This file imports nothing.

THE LESSON ALREADY PAID FOR: before the split, the cross-rule ``DOCUMENT_MAX_CHARS`` hard-coded
4 chars/token, the ENGLISH figure, in a Vietnamese bot. The rule allowed a document ceiling of 45,875
chars while the real estimator only tolerates 28,672 (60% apart); someone setting 40,000 was saved fine
and the bot was cut off mid-file, exactly what the rule exists to prevent. There may be only ONE
chars-to-token constant.
"""

from __future__ import annotations

import math

KY_TU_MOI_TOKEN = 2.5


def uoc_token_tu_ky_tu(so_ky_tu: int) -> int:
    """Estimate the number of tokens of a text ``so_ky_tu`` chars long. Rounds UP."""
    return math.ceil(so_ky_tu / KY_TU_MOI_TOKEN)
