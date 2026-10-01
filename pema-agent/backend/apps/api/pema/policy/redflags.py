"""Red-flag detector for the ``patient_channel`` profile (PLAN-AI01 section 5).

New module (no zalo-agent original). Rule of the profile: when a patient message carries a sign that a
dermatology patient must not wait on (bleeding, fever, pus, difficulty breathing), the turn goes to a
DOCTOR before any model is called. This module is the detector only; ``hooks.ClinicPolicyHooks.before_llm``
turns a hit into a triage ``review_item`` and ``BeforeLlmAction.HAND_OFF``.

Design choices, all on the safe side:

* Matching runs on text folded by ``text_normalize.normalize_for_flags``: lower case, no diacritics,
  stretched letters and separators inside a word removed. So "chảy máu", "chay mau", "chayyy mau",
  "chảy mầu" (wrong tone), "ch.ảy máu" and "chay maù" all hit the same rule.
* A false positive costs a doctor a glance; a false negative can cost a patient. Therefore ambiguity
  resolves to "flag" EXCEPT for a few everyday words that mean something else in Vietnamese and would
  otherwise flood the doctor ("sốt ruột" = impatient, "mũ" = hat, "sót" = left over, "màu cam" =
  orange). Those are excluded by an explicit guard that looks at the diacritics the patient really typed.
* Negation ("không sốt", "hết sốt", "không bị chảy máu") suppresses a hit ONLY when the negator stands
  directly in front of the keyword, and never for "chưa hết sốt" / "không hết sốt" (still ongoing).
  Suppressed hits are returned in ``RedFlagResult.suppressed`` so a log or an eval can show them.
  "Không thở được" and the like are rules of their own and are never negated.
* The four required categories are ``bleeding``, ``fever``, ``pus``, ``dyspnea``. Two more
  (``severe_allergy``, ``vascular_vision``) are PROVISIONAL and marked so: a doctor must confirm or remove
  them (open item of package P). The whole list is data (``RED_FLAG_RULES``) so the clinic's doctor can
  edit it without touching the logic.

The module never logs message text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from pema.policy.text_normalize import NormalizedText, normalize_for_flags

BLEEDING = "bleeding"
FEVER = "fever"
PUS = "pus"
DYSPNEA = "dyspnea"
SEVERE_ALLERGY = "severe_allergy"
VASCULAR_VISION = "vascular_vision"

REQUIRED_CATEGORIES: tuple[str, ...] = (BLEEDING, FEVER, PUS, DYSPNEA)
"""The four categories named by PLAN-AI01 section 5."""

PROVISIONAL_CATEGORIES: tuple[str, ...] = (SEVERE_ALLERGY, VASCULAR_VISION)
"""Added by package P as clearly dangerous in dermatology; need doctor sign-off."""

CATEGORY_PRIORITY: tuple[str, ...] = (DYSPNEA, SEVERE_ALLERGY, BLEEDING, VASCULAR_VISION, FEVER, PUS)
"""Order in which categories are reported (most urgent first)."""

_CONTEXT_WINDOW = 30
_NEGATION_LOOKBEHIND = 24


@dataclass(frozen=True)
class RedFlagRule:
    category: str
    pattern: re.Pattern[str]
    label: str
    """Short id of the rule for logs and evals. Never message text."""
    negatable: bool = True
    reject_original: tuple[str, ...] = ()
    """If the diacritics the patient typed inside the match contain one of these, the rule does not apply
    (a different word: ``mũ`` hat, ``sót`` left over, ``màu`` colour)."""
    needs_context: re.Pattern[str] | None = None
    """Folded text around the match must match this (for words too short to be unambiguous alone)."""
    bypass_context_if_typed: tuple[str, ...] = ()
    """The context check is skipped when the patient typed one of these accented forms ("máu", "mủ")."""
    reject_context: re.Pattern[str] | None = None
    """Folded text just BEFORE the match must not match this (warm water is not a fever)."""


@dataclass(frozen=True)
class RedFlagHit:
    category: str
    label: str
    negated: bool = False


@dataclass(frozen=True)
class RedFlagResult:
    hits: tuple[RedFlagHit, ...] = ()
    suppressed: tuple[RedFlagHit, ...] = ()
    """Matches that were negated ("không sốt"); informational only."""

    @property
    def triggered(self) -> bool:
        return bool(self.hits)

    @property
    def flags(self) -> tuple[str, ...]:
        """Distinct category codes, most urgent first."""
        found = {hit.category for hit in self.hits}
        return tuple(c for c in CATEGORY_PRIORITY if c in found)


def _p(body: str) -> re.Pattern[str]:
    return re.compile(body)


def _r(
    category: str,
    label: str,
    body: str,
    *,
    negatable: bool = True,
    reject_original: Sequence[str] = (),
    needs_context: str | None = None,
    bypass_context_if_typed: Sequence[str] = (),
    reject_context: str | None = None,
) -> RedFlagRule:
    return RedFlagRule(
        category=category,
        label=label,
        pattern=_p(body),
        negatable=negatable,
        reject_original=tuple(reject_original),
        needs_context=_p(needs_context) if needs_context else None,
        bypass_context_if_typed=tuple(bypass_context_if_typed),
        reject_context=_p(reject_context) if reject_context else None,
    )


# Wrong-tone forms that make a "mau" mean colour or sample instead of blood.
_NOT_BLOOD = ("màu", "mầu", "mẫu", "mãu")
_NOT_PUS = ("mũ", "mù", "mụ")
_NOT_FEVER = ("sót", "sọt", "sòt")

_PUS_CONTEXT = r"(?:vet|thuong|chay|dong|sung|vang|xanh|duc|mun|tiem|dich|nhiem|ap\s*xe)"
_WARM_WATER = r"(?:nuoc|ngam|tam|rua|chuom|duong|may|thoi|troi|ngoai\s*troi|phong|sua|ruou)\s*$"
_DEG = r"(?:do(?![a-z])|\*|°|oc(?![a-z])|c(?![a-z]))"

RED_FLAG_RULES: tuple[RedFlagRule, ...] = (
    # ------------------------------------------------------------------ bleeding
    _r(
        BLEEDING,
        "chay_mau",
        r"(?<![a-z])(?:chay|ri|ro|tuon|phun|trao)\s*(?:ra\s*)?(?:nhieu\s*|lien\s*tuc\s*)?mau(?![a-z])",
    ),
    _r(
        BLEEDING,
        "ra_mau",
        r"(?<![a-z])(?:ra|ho\s*ra|non\s*ra|oi\s*ra|dai\s*ra|tieu\s*ra|nho\s*ra)\s*mau(?![a-z])",
        reject_original=_NOT_BLOOD,
    ),
    _r(
        BLEEDING,
        "mau_chay",
        r"(?<![a-z])mau\s*(?:chay|tuon|ri(?![a-z])|khong\s*(?:ngung|dung|cam|het)|dong\s*cuc|tuoi|cam(?![a-z]))",
        reject_original=_NOT_BLOOD,
    ),
    _r(BLEEDING, "xuat_huyet", r"(?<![a-z])xuat\s*huyet(?![a-z])"),
    _r(BLEEDING, "mat_mau", r"(?<![a-z])mat\s*mau(?![a-z])", reject_original=_NOT_BLOOD),
    _r(
        BLEEDING,
        "cam_mau",
        r"(?<![a-z])(?:khong\s*)?cam\s*(?:duoc\s*)?mau(?![a-z])",
        reject_original=_NOT_BLOOD,
    ),
    _r(
        BLEEDING,
        "tham_dinh_mau",
        r"(?<![a-z])(?:tham|dinh|nhuom)\s*mau(?![a-z])",
        reject_original=_NOT_BLOOD,
    ),
    _r(
        BLEEDING,
        "co_mau",
        r"(?<![a-z])(?:co|bi|thay|nhin\s*thay)\s*mau(?![a-z])",
        reject_original=_NOT_BLOOD,
        needs_context=r"(?:vet|thuong|da(?![a-z])|mun|tiem|nuoc|ho(?![a-z])|non|dai|phan|dam|chay|nhieu|bong)",
        bypass_context_if_typed=("máu",),
    ),
    # ----------------------------------------------------------------------- pus
    _r(PUS, "mung_mu", r"(?<![a-z])mung\s*mu(?![a-z])"),
    _r(
        PUS,
        "chay_mu",
        r"(?<![a-z])(?:chay|ri|ro|ra|tiet|dong|co|bi|nhieu|dinh)\s*mu(?![a-z])",
        reject_original=_NOT_PUS,
    ),
    _r(
        PUS,
        "mu_mau_sac",
        r"(?<![a-z])mu\s*(?:vang|xanh|duc|trang|nhieu)(?![a-z])",
        reject_original=_NOT_PUS,
    ),
    _r(
        PUS,
        "mu_tu_do",
        r"(?<![a-z])mu(?![a-z])",
        reject_original=_NOT_PUS,
        needs_context=_PUS_CONTEXT,
        bypass_context_if_typed=("mủ",),
    ),
    _r(PUS, "nhiem_trung", r"(?<![a-z])nhiem\s*(?:trung|khuan)(?![a-z])"),
    _r(PUS, "ap_xe", r"(?<![a-z])ap\s*xe(?![a-z])"),
    _r(PUS, "dich_co_mau", r"(?<![a-z])dich\s*(?:vang|duc|xanh|mau)(?![a-z])"),
    _r(
        PUS,
        "chay_dich_bat_thuong",
        r"(?<![a-z])(?:chay|ri|ro|tiet)\s*dich\s*(?:vang|duc|xanh|mau|nhieu|hoi|thoi)(?![a-z])",
    ),
    _r(PUS, "sung_nong_do_dau", r"(?<![a-z])sung\s*(?:nong\s*)?do\s*dau(?![a-z])"),
    _r(PUS, "sung_tay", r"(?<![a-z])sung\s*tay(?![a-z])"),
    _r(
        PUS,
        "mui_hoi_vet_thuong",
        r"(?<![a-z])mui\s*(?:hoi|thoi)(?![a-z])",
        needs_context=r"(?:vet|thuong|mun|da(?![a-z])|tiem|laser|cat|khau)",
    ),
    # --------------------------------------------------------------------- fever
    _r(
        FEVER,
        "sot",
        r"(?<![a-z])sot(?![a-z])(?!\s*(?:ruot|sang|deo|lai|ca\s*chua))",
        reject_original=_NOT_FEVER,
    ),
    _r(
        FEVER,
        "nong_nguoi",
        r"(?<![a-z])(?:nong\s*nguoi|nguoi\s*nong|(?:ca|toan)\s*nguoi\s*nong)(?![a-z])",
    ),
    _r(FEVER, "on_lanh", r"(?<![a-z])(?:on\s*lanh|run\s*lanh|ret\s*run|lanh\s*run)(?![a-z])"),
    _r(
        FEVER,
        "nhiet_do_38_tro_len",
        r"(?<![\d.,])(?:3[89]|4[0-2])(?:[.,]\d{1,2})?\s*" + _DEG,
        negatable=False,
        reject_context=_WARM_WATER,
    ),
    _r(
        FEVER,
        "nhiet_do_37_5",
        r"(?<![\d.,])37[.,][5-9]\d?\s*" + _DEG,
        negatable=False,
        reject_context=_WARM_WATER,
    ),
    _r(
        FEVER,
        "nhiet_do_la",
        r"(?<![a-z])nhiet\s*do\s*(?:la\s*|len\s*|khoang\s*|dang\s*)?(?:3[89]|4[0-2]|37[.,][5-9])",
        negatable=False,
    ),
    # ------------------------------------------------------------------ dyspnea
    _r(DYSPNEA, "kho_tho", r"(?<![a-z])(?:kho\s*(?:ma\s*)?tho|tho\s*kho)(?![a-z])"),
    _r(
        DYSPNEA,
        "khong_tho_duoc",
        r"(?<![a-z])(?:k|ko|kh|khg|kg|khong|hok|hong)\s*(?:the\s*|con\s*|co\s*)?tho\s*(?:duoc|dc|noi|nua|tiep|ra|vao)(?![a-z])",
        negatable=False,
    ),
    _r(
        DYSPNEA,
        "tho_khong_duoc",
        r"(?<![a-z])tho\s*(?:khong|k|ko|hok|kg)\s*(?:duoc|dc|noi|ra|vao)(?![a-z])",
        negatable=False,
    ),
    _r(
        DYSPNEA,
        "tho_gap",
        r"(?<![a-z])tho\s*(?:doc|gap|hon\s*hen|ham\s*ham|rit|khe\s*khe|ngan|met)(?![a-z])",
    ),
    _r(
        DYSPNEA,
        "hut_hoi",
        r"(?<![a-z])(?:hut\s*hoi|nghet\s*tho|ngat\s*tho|ngop\s*tho|tac\s*tho|nghen\s*(?:tho|hong|co))(?![a-z])",
    ),
    _r(DYSPNEA, "kho_nuot", r"(?<![a-z])kho\s*nuot(?![a-z])"),
    _r(DYSPNEA, "tuc_nguc", r"(?<![a-z])(?:tuc|nang)\s*nguc(?![a-z])"),
    _r(DYSPNEA, "dau_nguc", r"(?<![a-z])dau\s*(?:that\s*)?nguc(?![a-z])"),
    # ------------------------------------------------- provisional: severe allergy
    _r(SEVERE_ALLERGY, "phu_mat_moi_luoi", r"(?<![a-z])phu\s*(?:mat|moi|luoi|hong|mach)(?![a-z])"),
    _r(SEVERE_ALLERGY, "sung_moi_luoi_hong", r"(?<![a-z])sung\s*(?:moi|luoi|hong|ca\s*mat)(?![a-z])"),
    _r(SEVERE_ALLERGY, "soc_phan_ve", r"(?<![a-z])(?:soc\s*)?phan\s*ve(?![a-z])"),
    _r(SEVERE_ALLERGY, "di_ung_nang", r"(?<![a-z])di\s*ung\s*nang(?![a-z])"),
    _r(
        SEVERE_ALLERGY,
        "noi_me_day_khap_nguoi",
        r"(?<![a-z])noi\s*me\s*day\s*(?:khap|toan|ca|lan)(?![a-z])",
    ),
    _r(
        SEVERE_ALLERGY,
        "ngat_xiu",
        r"(?<![a-z])(?:bi\s*ngat(?![a-z])|ngat\s*(?:xiu|di)|bat\s*tinh|xiu\s*di|lim\s*di)",
    ),
    # --------------------------------------------- provisional: vascular / vision
    _r(VASCULAR_VISION, "hoai_tu", r"(?<![a-z])hoai\s*tu(?![a-z])"),
    _r(
        VASCULAR_VISION,
        "da_tim_den",
        r"(?<![a-z])da\s*(?:chuyen\s*|bi\s*|dang\s*)?(?:tim|den|xam|trang\s*bech)\s*(?:tai|lai|dan|di)(?![a-z])",
    ),
    _r(VASCULAR_VISION, "tim_tai", r"(?<![a-z])tim\s*tai(?![a-z])"),
    _r(
        VASCULAR_VISION,
        "mat_thi_luc",
        r"(?<![a-z])(?:mat\s*thi\s*luc|nhin\s*(?:mo|doi|khong\s*(?:ro|thay))|mo\s*mat\s*(?:dot\s*ngot|di))(?![a-z])",
    ),
    _r(
        VASCULAR_VISION,
        "dau_du_doi",
        r"(?<![a-z])dau\s*(?:du\s*doi|dien\s*cuong|khung\s*khiep|khong\s*chiu\s*noi|nhieu\s*(?:sau|khi)\s*tiem)(?![a-z])",
    ),
)

_NEGATOR = re.compile(
    r"(?<![a-z])(?:khong|ko|k|kg|khg|chua|het|chang|hok|hong|dau\s*co|khoi|bot)\s*"
    r"(?:bi\s*|thay\s*|co\s*|con\s*|hien\s*tuong\s*|dau\s*hieu\s*|nua\s*|them\s*)*$"
)
_STILL_ONGOING = re.compile(r"(?<![a-z])(?:chua|khong|ko|k|kg|hok|hong|van\s*chua|van\s*khong)\s*het\s*$")


def _is_negated(folded: str, start: int) -> bool:
    prefix = folded[max(0, start - _NEGATION_LOOKBEHIND) : start]
    if _STILL_ONGOING.search(prefix):
        return False
    return _NEGATOR.search(prefix) is not None


def _rule_applies(rule: RedFlagRule, text: NormalizedText, start: int, end: int) -> bool:
    folded = text.folded
    if rule.reject_original:
        typed = text.original_span(start, end).lower()
        if any(bad in typed for bad in rule.reject_original):
            return False
    if rule.reject_context is not None:
        before = folded[max(0, start - _CONTEXT_WINDOW) : start]
        if rule.reject_context.search(before):
            return False
    if rule.needs_context is not None:
        if rule.bypass_context_if_typed:
            typed = text.original_span(start, end).lower()
            if any(form in typed for form in rule.bypass_context_if_typed):
                return True
        around = folded[max(0, start - _CONTEXT_WINDOW) : start] + " " + folded[end : end + _CONTEXT_WINDOW]
        if not rule.needs_context.search(around):
            return False
    return True


def detect_red_flags(text: str, rules: Iterable[RedFlagRule] = RED_FLAG_RULES) -> RedFlagResult:
    """Scan one message. Pure and synchronous; the text is never stored or logged."""
    if not text or not text.strip():
        return RedFlagResult()
    normalized = normalize_for_flags(text)
    folded = normalized.folded
    candidates: list[tuple[int, int, RedFlagRule]] = []
    for rule in rules:
        for match in rule.pattern.finditer(folded):
            start, end = match.span()
            if _rule_applies(rule, normalized, start, end):
                candidates.append((start, end, rule))
    # A short rule that matches INSIDE a longer one is the same words ("mủ" inside "mưng mủ"): keep the
    # longer rule, so negation is judged where the phrase starts ("không thấy mưng mủ" is negated).
    candidates.sort(key=lambda c: (c[0], -(c[1] - c[0])))
    kept: list[tuple[int, int, RedFlagRule]] = []
    for start, end, rule in candidates:
        if any(k_start <= start and end <= k_end for k_start, k_end, _ in kept):
            continue
        kept.append((start, end, rule))
    hits: list[RedFlagHit] = []
    suppressed: list[RedFlagHit] = []
    seen: set[tuple[str, bool]] = set()
    for start, _, rule in kept:
        negated = rule.negatable and _is_negated(folded, start)
        key = (rule.label, negated)
        if key in seen:
            continue
        seen.add(key)
        hit = RedFlagHit(category=rule.category, label=rule.label, negated=negated)
        (suppressed if negated else hits).append(hit)
    return RedFlagResult(hits=tuple(hits), suppressed=tuple(suppressed))


def detect_red_flags_in_batch(texts: Iterable[str]) -> RedFlagResult:
    """Union over every message of a turn: ONE red-flag message anywhere in the batch triggers."""
    hits: list[RedFlagHit] = []
    suppressed: list[RedFlagHit] = []
    for text in texts:
        result = detect_red_flags(text)
        hits.extend(result.hits)
        suppressed.extend(result.suppressed)
    return RedFlagResult(hits=tuple(hits), suppressed=tuple(suppressed))


@dataclass(frozen=True)
class RedFlagCatalogEntry:
    category: str
    provisional: bool
    labels: tuple[str, ...] = field(default_factory=tuple[str, ...])


def catalog() -> tuple[RedFlagCatalogEntry, ...]:
    """The categories and rule labels, for the doctor who reviews the list (docs, admin UI)."""
    out: list[RedFlagCatalogEntry] = []
    for category in CATEGORY_PRIORITY:
        labels = tuple(rule.label for rule in RED_FLAG_RULES if rule.category == category)
        out.append(RedFlagCatalogEntry(category, category in PROVISIONAL_CATEGORIES, labels))
    return tuple(out)
