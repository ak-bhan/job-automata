"""Playwright-based form filler for JobAutomata.

Launches a visible Chromium window, navigates to a job application URL,
scans all form fields, matches them to the user's profile, and fills them
in place. The browser is left open so the user can review and submit.

Public interface
----------------
    await fill_form(url, profile, resume_path=None) -> dict
"""

import logging
import re
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    Page,
    ElementHandle,
    Error as PlaywrightError,
)

from field_matcher import match_field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Input types we never attempt to fill.
_SKIP_INPUT_TYPES = frozenset({
    "hidden", "submit", "button", "reset", "image",
})

# Input types treated as plain text (fill with a string value).
_TEXT_INPUT_TYPES = frozenset({
    "text", "email", "tel", "url", "number", "search",
    "date", "month", "week", "time", "datetime-local", "color", "",
})

# CEFR level equivalence groups — ordered from highest to lowest.
# Each group contains the canonical CEFR label plus synonyms that appear
# in ATS dropdowns. Matching is case-insensitive and partial.
_CEFR_GROUPS: list[tuple[str, list[str]]] = [
    ("native", ["native", "muttersprache", "mother tongue", "first language",
                "native speaker", "muttersprachler", "langue maternelle"]),
    ("c2",     ["c2", "mastery", "proficient", "verhandlungssicher",
                "fließend", "fliessend", "fluent", "bilingual", "advanced proficiency"]),
    ("c1",     ["c1", "advanced", "c1-c2", "c1/c2", "effective operational proficiency"]),
    ("b2",     ["b2", "upper intermediate", "upper-intermediate", "b1-b2",
                "b1/b2", "vantage", "sehr gut", "good"]),
    ("b1",     ["b1", "intermediate", "threshold", "a2-b1", "a2/b1",
                "gut", "grundkenntnisse fortgeschritten"]),
    ("a2",     ["a2", "elementary", "pre-intermediate", "waystage",
                "grundkenntnisse", "basic", "basics", "a1-a2", "a1/a2"]),
    ("a1",     ["a1", "beginner", "breakthrough", "anfänger", "debutant",
                "notions", "rudimentary"]),
]

def _cefr_group_index(value: str) -> int:
    """Return the index of the CEFR group that best matches *value*.

    Lower index = higher proficiency. Returns -1 if no group matches.
    """
    v = value.lower().strip()
    for i, (_, synonyms) in enumerate(_CEFR_GROUPS):
        if any(s in v or v in s for s in synonyms):
            return i
    return -1


# Keywords in file-input signals that identify a resume / CV upload field.
_RESUME_KEYWORDS = frozenset({
    "resume", "cv", "curriculum", "vitae", "lebenslauf",
    "bewerbung", "upload",
})

# Keywords for cover letter file inputs.
_COVER_LETTER_KEYWORDS = frozenset({
    "cover", "covering", "anschreiben", "motivation", "motivationsschreiben",
    "lettre", "begeleidende",
})

# Keywords for reference letter file inputs.
_REFERENCE_KEYWORDS = frozenset({
    "reference", "referenz", "empfehlung", "recommendation",
    "zeugnis", "arbeitszeugnis", "testimonial",
})

# How long to wait for the page to settle after navigation (ms).
_PAGE_LOAD_TIMEOUT_MS = 30_000

# How long to wait for a single fill action before giving up (ms).
_FILL_TIMEOUT_MS = 5_000


# ---------------------------------------------------------------------------
# Internal helpers — signal collection
# ---------------------------------------------------------------------------

async def _get_label_text(element: ElementHandle) -> str:
    """Return the human-readable label associated with a form element.

    Checks, in order:
    1. ``aria-labelledby`` — resolves referenced element text content.
    2. ``<label for="id">`` — standard HTML association.
    3. Nearest ``<label>`` ancestor — implicit wrapping pattern.
    4. Previous sibling text — catches ``<p>`` / ``<div>`` question labels
       common in ATS platforms (e.g. Personio) that don't use ``<label>``.
    5. Parent container heading text — walks up to find text-bearing siblings
       within the same form group.

    All checks are performed in a single JS round-trip.
    """
    text: str = await element.evaluate("""el => {
        // 1. aria-labelledby
        const labelledby = el.getAttribute('aria-labelledby');
        if (labelledby) {
            const parts = labelledby.trim().split(/\\s+/)
                .map(id => { const n = document.getElementById(id); return n ? n.textContent.trim() : ''; })
                .filter(Boolean);
            if (parts.length) return parts.join(' ');
        }

        // 2. <label for="id">
        if (el.id) {
            const lbl = document.querySelector('label[for="' + el.id + '"]');
            if (lbl) return lbl.textContent.trim();
        }

        // 3. Ancestor <label>
        const ancestor = el.closest('label');
        if (ancestor) return ancestor.textContent.trim();

        // 4. Previous sibling elements — look for a nearby text node in p/div/span/h*
        const textTags = new Set(['P', 'DIV', 'SPAN', 'H1', 'H2', 'H3', 'H4', 'LEGEND', 'DT']);
        let sib = el.previousElementSibling;
        for (let i = 0; i < 3 && sib; i++) {
            if (textTags.has(sib.tagName)) {
                const t = sib.textContent.trim();
                if (t.length > 2) return t;
            }
            sib = sib.previousElementSibling;
        }

        // 5. Walk up one level and look at preceding siblings of the parent.
        if (el.parentElement) {
            let psib = el.parentElement.previousElementSibling;
            for (let i = 0; i < 3 && psib; i++) {
                if (textTags.has(psib.tagName)) {
                    const t = psib.textContent.trim();
                    if (t.length > 2) return t;
                }
                psib = psib.previousElementSibling;
            }
        }

        return '';
    }""")
    return (text or "").strip()


async def _collect_signals(element: ElementHandle) -> dict[str, str]:
    """Return a signals dict for ``match_field`` from a DOM element.

    Gathers ``name``, ``id``, ``placeholder``, ``autocomplete``,
    ``aria_label``, and ``label`` (resolved human-readable text).
    """
    signals: dict[str, str] = {}

    for attr in ("name", "id", "placeholder", "autocomplete"):
        val = await element.get_attribute(attr)
        if val and val.strip():
            signals[attr] = val.strip()

    aria_label = await element.get_attribute("aria-label")
    if aria_label and aria_label.strip():
        signals["aria_label"] = aria_label.strip()

    label = await _get_label_text(element)
    if label:
        signals["label"] = label

    return signals


# ---------------------------------------------------------------------------
# Internal helpers — element introspection
# ---------------------------------------------------------------------------

async def _is_fillable(element: ElementHandle) -> bool:
    """Return True if the element is usable for filling.

    File inputs are exempt from the visibility check because ATS platforms
    (e.g. Personio) commonly hide the native <input type="file"> inside a
    custom drag-and-drop widget. Playwright's set_input_files() works on
    hidden file inputs directly without requiring them to be visible.
    """
    try:
        itype = await _input_type(element)
        if itype != "file" and not await element.is_visible():
            return False
        if await element.is_disabled():
            return False
        readonly = await element.get_attribute("readonly")
        if readonly is not None:
            return False
        return True
    except PlaywrightError:
        return False


async def _input_type(element: ElementHandle) -> str:
    """Return the lowercase ``type`` attribute, defaulting to ``'text'``."""
    t = await element.get_attribute("type")
    return (t or "text").lower()


def _classify_file_input(signals: dict[str, str]) -> str | None:
    """Return the document type a file input is likely expecting.

    Checks signal text against keyword sets in priority order:
    cover letter > reference letter > resume.  Returns ``None`` when no
    keyword set matches (e.g. an unrelated attachment field).

    Returns one of: ``"cover_letter"``, ``"reference_letter"``,
    ``"resume"``, or ``None``.
    """
    combined = " ".join(signals.values()).lower()
    if any(kw in combined for kw in _COVER_LETTER_KEYWORDS):
        return "cover_letter"
    if any(kw in combined for kw in _REFERENCE_KEYWORDS):
        return "reference_letter"
    if any(kw in combined for kw in _RESUME_KEYWORDS):
        return "resume"
    return None


# ---------------------------------------------------------------------------
# Internal helpers — filling
# ---------------------------------------------------------------------------

async def _fill_text(element: ElementHandle, value: str) -> bool:
    """Clear and type *value* into a text-like input or textarea.

    Uses ``fill`` (atomic clear + set) rather than ``type`` (keystroke
    simulation) — faster and more reliable for programmatic filling.
    """
    try:
        await element.fill(value, timeout=_FILL_TIMEOUT_MS)
        return True
    except PlaywrightError as exc:
        logger.debug("fill_text failed: %s", exc)
        return False


_LANGUAGE_LEVEL_KEYS = frozenset({
    "englishLevel", "germanLevel", "frenchLevel",
    "spanishLevel", "italianLevel",
})

_LISTBOX_SELECTOR = (
    "[role='option'], [role='listbox'] li, [role='menu'] li, "
    "ul[class*='dropdown'] li, ul[class*='suggest'] li"
)
_LISTBOX_WAIT_SELECTOR = (
    "[role='listbox'], [role='option'], [role='menu'], "
    "ul[class*='dropdown'], ul[class*='suggest']"
)
_LISTBOX_TIMEOUT_MS = 1_500


async def _open_combobox_options(page: Page, element: ElementHandle) -> list:
    """Click the element to open its dropdown and return all visible option elements."""
    try:
        await element.click(timeout=_FILL_TIMEOUT_MS)
        await page.wait_for_selector(_LISTBOX_WAIT_SELECTOR, timeout=_LISTBOX_TIMEOUT_MS, state="visible")
        return await page.query_selector_all(_LISTBOX_SELECTOR)
    except PlaywrightError:
        return []


async def _fill_combobox(
    page: Page,
    element: ElementHandle,
    value: str,
    cefr_fallback: bool = False,
) -> bool:
    """Fill a typeahead / combobox input and select the best suggestion.

    Strategy:
    1. Click the element and type the value to trigger the suggestion list.
    2. Wait briefly for a listbox / option list to appear.
    3a. If *cefr_fallback* is True: collect all options by opening the dropdown
        with an empty query, then pick the best by CEFR proximity rather than
        text-contains (handles "Advanced" vs "C1", "C1-C2" vs "C1", etc).
    3b. Otherwise: click the first option whose text contains the typed value,
        falling back to the very first option.
    4. If no dropdown appears, the typed value is left as-is (plain text fill).
    """
    try:
        await element.click(timeout=_FILL_TIMEOUT_MS)
        await element.fill(value, timeout=_FILL_TIMEOUT_MS)
    except PlaywrightError as exc:
        logger.debug("combobox click/fill failed: %s", exc)
        return False

    # Wait for dropdown.
    try:
        await page.wait_for_selector(_LISTBOX_WAIT_SELECTOR, timeout=_LISTBOX_TIMEOUT_MS, state="visible")
    except PlaywrightError:
        logger.debug("combobox: no suggestion list appeared, leaving typed value")
        return True

    try:
        if cefr_fallback:
            # Clear the input so the dropdown shows all options, not just
            # those matching the typed CEFR code.
            await element.fill("", timeout=_FILL_TIMEOUT_MS)
            try:
                await page.wait_for_selector(_LISTBOX_WAIT_SELECTOR, timeout=_LISTBOX_TIMEOUT_MS, state="visible")
            except PlaywrightError:
                pass
            options = await page.query_selector_all(_LISTBOX_SELECTOR)
            target_idx = _cefr_group_index(value)
            best = None
            best_distance = 999
            for opt in options:
                text = (await opt.text_content() or "").strip()
                if not text:
                    continue
                opt_idx = _cefr_group_index(text)
                if opt_idx == -1:
                    continue
                distance = abs(opt_idx - target_idx)
                if distance < best_distance:
                    best_distance = distance
                    best = opt
            # If CEFR matching found nothing, fall back to first option.
            if best is None and options:
                best = options[0]
        else:
            options = await page.query_selector_all(_LISTBOX_SELECTOR)
            lower = value.lower()
            best = None
            for opt in options:
                text = (await opt.text_content() or "").strip()
                if lower in text.lower():
                    best = opt
                    break
            if best is None and options:
                best = options[0]

        if best:
            await best.click(timeout=_FILL_TIMEOUT_MS)
            logger.debug("combobox: selected %r for value %r (cefr=%s)", await best.text_content(), value, cefr_fallback)
            return True
    except PlaywrightError as exc:
        logger.debug("combobox option click failed: %s", exc)

    return False


async def _fill_select(element: ElementHandle, value: str) -> bool:
    """Select the best-matching option in a ``<select>`` element.

    Attempts, in order:
    1. Exact value match.
    2. Case-insensitive value match.
    3. Case-insensitive label (visible text) match.
    4. Partial label match — option label starts with the profile value
       (or vice versa). Useful when a select shows "Deutschland" and the
       profile has "Deutschland" with trailing punctuation, or abbreviated
       country names.
    """
    # Retrieve all options once to avoid repeated round-trips.
    options: list[dict] = await element.evaluate("""sel => {
        return Array.from(sel.options).map(o => ({
            value: o.value,
            label: o.text.trim(),
        }));
    }""")

    lower_value = value.lower().strip()

    # Tier 1 — exact value
    for opt in options:
        if opt["value"] == value:
            try:
                await element.select_option(value=value, timeout=_FILL_TIMEOUT_MS)
                return True
            except PlaywrightError:
                pass

    # Tier 2 — case-insensitive value
    for opt in options:
        if opt["value"].lower() == lower_value:
            try:
                await element.select_option(value=opt["value"], timeout=_FILL_TIMEOUT_MS)
                return True
            except PlaywrightError:
                pass

    # Tier 3 — case-insensitive label
    for opt in options:
        if opt["label"].lower() == lower_value:
            try:
                await element.select_option(label=opt["label"], timeout=_FILL_TIMEOUT_MS)
                return True
            except PlaywrightError:
                pass

    # Tier 4 — partial label: option label starts with profile value or vice versa.
    # Only applied when the profile value is at least 3 characters to avoid
    # accidental single-letter matches.
    if len(lower_value) >= 3:
        for opt in options:
            opt_lower = opt["label"].lower()
            if opt_lower.startswith(lower_value) or lower_value.startswith(opt_lower):
                try:
                    await element.select_option(label=opt["label"], timeout=_FILL_TIMEOUT_MS)
                    logger.debug("select tier-4 partial match: %r ~ %r", value, opt["label"])
                    return True
                except PlaywrightError:
                    pass

    logger.debug("select: no matching option for value=%r", value)
    return False


async def _fill_language_select(element: ElementHandle, value: str) -> bool:
    """Select the closest CEFR-equivalent option in a language-level ``<select>``.

    First tries the standard tiers from :func:`_fill_select`. If those all
    fail, maps both the stored value and each option label to a CEFR group
    index and picks the option whose group index is closest to the stored
    value's group index.

    Example: stored "C1" matches "C1-C2" (same group) or falls back to the
    option nearest in proficiency (e.g. "advanced").
    """
    # Try standard matching first.
    if await _fill_select(element, value):
        return True

    # CEFR proximity fallback.
    target_idx = _cefr_group_index(value)
    if target_idx == -1:
        logger.debug("language select: stored value %r not in any CEFR group", value)
        return False

    options: list[dict] = await element.evaluate("""sel => {
        return Array.from(sel.options).map(o => ({
            value: o.value,
            label: o.text.trim(),
        }));
    }""")

    best_opt = None
    best_distance = 999

    for opt in options:
        if not opt["label"] or not opt["value"]:
            continue
        opt_idx = _cefr_group_index(opt["label"])
        if opt_idx == -1:
            continue
        distance = abs(opt_idx - target_idx)
        if distance < best_distance:
            best_distance = distance
            best_opt = opt

    if best_opt:
        try:
            await element.select_option(label=best_opt["label"], timeout=_FILL_TIMEOUT_MS)
            logger.debug(
                "language select CEFR match: %r -> %r (distance=%d)",
                value, best_opt["label"], best_distance,
            )
            return True
        except PlaywrightError as exc:
            logger.debug("language select option click failed: %s", exc)

    return False


async def _attach_resume(element: ElementHandle, resume_path: str, original_name: str = "") -> bool:
    """Set the file input's value to the document at *resume_path*.

    If *original_name* is provided the file is presented to the form under
    that name (e.g. ``"John_CV.pdf"`) rather than the UUID filename stored
    on disk.  Playwright supports this via the buffer-based file descriptor.
    """
    try:
        if original_name:
            file_bytes = Path(resume_path).read_bytes()
            await element.set_input_files(
                {"name": original_name, "mimeType": "application/pdf", "buffer": file_bytes},
                timeout=_FILL_TIMEOUT_MS,
            )
        else:
            await element.set_input_files(resume_path, timeout=_FILL_TIMEOUT_MS)
        logger.info("Document attached: %s (as %r)", resume_path, original_name or resume_path)
        return True
    except PlaywrightError as exc:
        logger.warning("Failed to attach document: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Internal helpers — page scanning
# ---------------------------------------------------------------------------

async def _scan_elements(page: Page) -> list[ElementHandle]:
    """Return all potentially fillable form elements from the page.

    Collects ``<input>`` (excluding hidden/button/submit/reset/image),
    ``<select>``, and ``<textarea>`` elements.
    """
    selector = (
        "input:not([type='hidden'])"
        ":not([type='submit'])"
        ":not([type='button'])"
        ":not([type='reset'])"
        ":not([type='image'])"
        ", select"
        ", textarea"
    )
    return await page.query_selector_all(selector)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def _match_question(label: str, qa_pairs: list) -> Optional[str]:
    """Return the answer whose question best matches *label* using Jaccard similarity.

    Tokenises both strings to lowercase word sets and computes the Jaccard
    index (|intersection| / |union|).  Returns the answer only when the best
    score exceeds 0.25 to avoid spurious matches.

    Args:
        label:    The form field label / aria-label / placeholder text.
        qa_pairs: List of dicts with at least ``question`` and ``answer`` keys.

    Returns:
        The matching answer string, or ``None`` if no pair scores high enough.
    """
    if not label or not qa_pairs:
        return None

    # Strip punctuation, lowercase, split into words.
    def _tokens(text: str) -> set[str]:
        return set(re.sub(r"[^\w\s]", " ", text.lower()).split())

    label_tokens = _tokens(label)
    if not label_tokens:
        return None

    best_score = 0.0
    best_answer: Optional[str] = None

    for pair in qa_pairs:
        question = pair.get("question", "")
        answer = pair.get("answer", "")
        if not question or not answer:
            continue
        q_tokens = _tokens(question)
        if not q_tokens:
            continue
        intersection = label_tokens & q_tokens
        union = label_tokens | q_tokens
        score = len(intersection) / len(union)
        if score > best_score:
            best_score = score
            best_answer = answer

    _MATCH_THRESHOLD = 0.20
    if best_score >= _MATCH_THRESHOLD:
        logger.info("Q&A match: score=%.2f label=%r", best_score, label)
        return best_answer
    logger.info("Q&A no match: best_score=%.2f label=%r", best_score, label)
    return None


async def fill_form(
    url: str,
    profile: dict,
    resume_path: Optional[str] = None,
    resume_name: Optional[str] = None,
    cover_letter_path: Optional[str] = None,
    cover_letter_name: Optional[str] = None,
    reference_letter_path: Optional[str] = None,
    reference_letter_name: Optional[str] = None,
    qa_pairs: list = [],
) -> dict:
    """Open a visible browser, navigate to *url*, and fill the form.

    Launches Chromium in headed mode, waits for the page to fully load,
    then iterates over all form elements. Each element's signals are
    collected and passed to :func:`field_matcher.match_field`. Matched
    fields are filled with the corresponding profile value.

    The browser is intentionally left open after the function returns so
    the user can inspect the filled fields, make corrections, and submit.

    Args:
        url:         Job application URL to navigate to.
        profile:     Profile dict as returned by :func:`profile.get_profile`.
        resume_path:            Absolute path to the resume PDF.
        resume_name:            Original filename to present to the form.
        cover_letter_path:      Absolute path to the cover letter PDF.
        cover_letter_name:      Original filename to present to the form.
        reference_letter_path:  Absolute path to the reference letter PDF.
        reference_letter_name:  Original filename to present to the form.
        qa_pairs:               List of Q&A dicts (question/answer) used to
                                fill screening question textareas that have no
                                profile-key match.

    Returns:
        A summary dict with the following keys:

        - ``fields_detected`` (int): total form elements found.
        - ``fields_filled``   (int): elements successfully filled.
        - ``fields_skipped``  (int): elements not filled (no match /
          no value / unsupported type).
        - ``detail``          (list[dict]): one entry per detected
          element with ``signals``, ``matched_key``, and ``status``.

    Raises:
        PlaywrightError: if the browser cannot launch or the page fails
                         to load within ``_PAGE_LOAD_TIMEOUT_MS``.
    """
    logger.info("Starting fill_form for URL: %s", url)

    # Use .start() instead of a context manager so the browser is NOT
    # closed when this coroutine returns — the user must see the window.
    pw = await async_playwright().start()

    try:
        browser: Browser = await pw.chromium.launch(headless=False)
        page: Page = await browser.new_page()

        logger.info("Navigating to %s", url)
        await page.goto(url, wait_until="domcontentloaded", timeout=_PAGE_LOAD_TIMEOUT_MS)

        # Wait for network to settle so lazy-rendered fields appear.
        try:
            await page.wait_for_load_state("networkidle", timeout=_PAGE_LOAD_TIMEOUT_MS)
        except PlaywrightError:
            # networkidle can time out on pages with long-polling — that is OK.
            logger.debug("networkidle timeout — continuing with current DOM")

        elements = await _scan_elements(page)
        logger.info("Detected %d form element(s)", len(elements))

        # Pre-scan: determine whether a dedicated phone country code field
        # exists on this page.  If it does, fill the phone number as stored
        # (without prefix).  If it does not, prepend the country code.
        has_country_code_field = False
        for el in elements:
            if await _is_fillable(el):
                sig = await _collect_signals(el)
                if match_field(sig) == "phoneCountryCode":
                    has_country_code_field = True
                    break
        logger.debug("has_country_code_field=%s", has_country_code_field)

        fields_filled = 0
        fields_skipped = 0
        detail: list[dict] = []

        for element in elements:
            if not await _is_fillable(element):
                continue

            tag: str = (await element.evaluate("el => el.tagName.toLowerCase()"))
            itype = await _input_type(element) if tag == "input" else tag

            signals = await _collect_signals(element)
            entry: dict = {
                "signals": signals,
                "type": itype,
                "matched_key": None,
                "status": "skipped",
            }

            # ----------------------------------------------------------------
            # File inputs: attach the right document based on field signals.
            # ----------------------------------------------------------------
            if itype == "file":
                doc_type = _classify_file_input(signals)
                path_map = {
                    "resume": resume_path,
                    "cover_letter": cover_letter_path,
                    "reference_letter": reference_letter_path,
                }
                name_map = {
                    "resume": resume_name,
                    "cover_letter": cover_letter_name,
                    "reference_letter": reference_letter_name,
                }
                key_map = {
                    "resume": "resumePath",
                    "cover_letter": "coverLetterPath",
                    "reference_letter": "referenceLetterPath",
                }
                file_path = path_map.get(doc_type) if doc_type else None
                orig_name = name_map.get(doc_type, "") or ""
                if file_path:
                    ok = await _attach_resume(element, file_path, original_name=orig_name)
                    entry["matched_key"] = key_map[doc_type]
                    entry["status"] = "filled" if ok else "error"
                    if ok:
                        fields_filled += 1
                    else:
                        fields_skipped += 1
                else:
                    entry["status"] = "skipped"
                    fields_skipped += 1
                detail.append(entry)
                continue

            # ----------------------------------------------------------------
            # Checkbox / radio: skip in v0.1 (job-form specific values).
            # ----------------------------------------------------------------
            if itype in ("checkbox", "radio"):
                entry["status"] = "skipped"
                fields_skipped += 1
                detail.append(entry)
                continue

            # ----------------------------------------------------------------
            # All other inputs + select + textarea: rule-based matching.
            # ----------------------------------------------------------------
            matched_key = match_field(signals)
            entry["matched_key"] = matched_key

            if matched_key is None:
                # For textarea and plain text inputs, try Q&A matching before giving up.
                # Personio screening questions often use <textarea> but some ATSes use
                # <input type="text"> for open-ended questions.
                is_open_text = tag == "textarea" or itype in ("text", "")
                if is_open_text and qa_pairs:
                    # Build a combined label string from all available signals.
                    candidate_label = " ".join(filter(None, [
                        signals.get("label", ""),
                        signals.get("aria_label", ""),
                        signals.get("placeholder", ""),
                    ]))
                    logger.info("Q&A candidate label for unmatched %s: %r", tag, candidate_label)
                    qa_answer = _match_question(candidate_label, qa_pairs)
                    if qa_answer:
                        ok = await _fill_text(element, qa_answer)
                        entry["matched_key"] = "qa_answer"
                        entry["status"] = "filled" if ok else "error"
                        if ok:
                            fields_filled += 1
                        else:
                            fields_skipped += 1
                        detail.append(entry)
                        continue
                entry["status"] = "no_match"
                fields_skipped += 1
                detail.append(entry)
                continue

            profile_value = profile.get(matched_key)
            if not profile_value:
                entry["status"] = "no_value"
                fields_skipped += 1
                detail.append(entry)
                continue

            str_value = str(profile_value)

            # If this is the phone field and no dedicated country code field
            # exists on the page, prepend the stored country code so the full
            # international number is entered in the single phone field.
            if matched_key == "phone" and not has_country_code_field:
                country_code = str(profile.get("phoneCountryCode", "")).strip()
                if country_code and not str_value.startswith(country_code):
                    str_value = country_code + str_value
                    logger.debug("Prepended country code %r to phone: %r", country_code, str_value)

            if tag == "select" and matched_key in _LANGUAGE_LEVEL_KEYS:
                ok = await _fill_language_select(element, str_value)
            elif tag == "select":
                ok = await _fill_select(element, str_value)
            elif itype in _TEXT_INPUT_TYPES or tag == "textarea":
                # Check if this text input is actually a combobox/typeahead.
                role = await element.get_attribute("role") or ""
                has_list = await element.get_attribute("list")  # datalist
                autocomplete_attr = await element.get_attribute("autocomplete") or ""
                is_combobox = (
                    role.lower() == "combobox"
                    or has_list is not None
                    or "combobox" in (await element.get_attribute("aria-haspopup") or "").lower()
                )
                if is_combobox:
                    ok = await _fill_combobox(
                        page, element, str_value,
                        cefr_fallback=matched_key in _LANGUAGE_LEVEL_KEYS,
                    )
                else:
                    ok = await _fill_text(element, str_value)
            else:
                logger.debug("Unsupported input type '%s', skipping", itype)
                entry["status"] = "unsupported_type"
                fields_skipped += 1
                detail.append(entry)
                continue

            entry["status"] = "filled" if ok else "error"
            if ok:
                fields_filled += 1
                logger.debug("Filled %s = %r", matched_key, str_value)
            else:
                fields_skipped += 1
                logger.warning("Failed to fill %s (key=%s)", signals.get("name") or signals.get("id", "?"), matched_key)

            detail.append(entry)

        page_title = await page.title()

        summary = {
            "fields_detected": len(elements),
            "fields_filled": fields_filled,
            "fields_skipped": fields_skipped,
            "page_title": page_title,
            "detail": detail,
        }
        logger.info(
            "fill_form complete — detected=%d filled=%d skipped=%d",
            len(elements), fields_filled, fields_skipped,
        )
        return summary

    except PlaywrightError:
        # Clean up only on hard failure; on success we leave everything open.
        await pw.stop()
        raise
