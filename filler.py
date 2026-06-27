"""Playwright-based form filler for JobAutomata.

Launches a visible Chromium window, navigates to a job application URL,
scans all form fields, matches them to the user's profile, and fills them
in place. The browser is left open so the user can review and submit.

Public interface
----------------
    await fill_form(url, profile, resume_path=None) -> dict
"""

import logging
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

    All three checks are performed in a single JS round-trip.
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


async def _fill_combobox(page: Page, element: ElementHandle, value: str) -> bool:
    """Fill a typeahead / combobox input and select the best suggestion.

    Strategy:
    1. Click the element and type the value to trigger the suggestion list.
    2. Wait briefly for a ``[role=listbox]`` or ``[role=option]`` to appear.
    3. Click the first option whose text contains the typed value
       (case-insensitive), falling back to the very first option if none match.
    4. If no dropdown appears, the typed value is left as-is (plain text fill).

    Returns True if a suggestion was selected or the value was typed, False on
    hard errors.
    """
    _LISTBOX_TIMEOUT_MS = 1_500

    try:
        await element.click(timeout=_FILL_TIMEOUT_MS)
        await element.fill(value, timeout=_FILL_TIMEOUT_MS)
    except PlaywrightError as exc:
        logger.debug("combobox click/fill failed: %s", exc)
        return False

    # Wait for any listbox/option container to appear.
    try:
        await page.wait_for_selector(
            "[role='listbox'], [role='option'], [role='menu'], ul[class*='dropdown'], ul[class*='suggest']",
            timeout=_LISTBOX_TIMEOUT_MS,
            state="visible",
        )
    except PlaywrightError:
        # No dropdown appeared — the typed value stands (e.g. plain text input).
        logger.debug("combobox: no suggestion list appeared, leaving typed value")
        return True

    lower = value.lower()
    try:
        options = await page.query_selector_all(
            "[role='option'], [role='listbox'] li, [role='menu'] li, ul[class*='dropdown'] li, ul[class*='suggest'] li"
        )
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
            logger.debug("combobox: selected option %r for value %r", await best.text_content(), value)
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


async def _attach_resume(element: ElementHandle, resume_path: str) -> bool:
    """Set the file input's value to the resume PDF path."""
    try:
        await element.set_input_files(resume_path, timeout=_FILL_TIMEOUT_MS)
        logger.info("Resume attached: %s", resume_path)
        return True
    except PlaywrightError as exc:
        logger.warning("Failed to attach resume: %s", exc)
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

async def fill_form(
    url: str,
    profile: dict,
    resume_path: Optional[str] = None,
    cover_letter_path: Optional[str] = None,
    reference_letter_path: Optional[str] = None,
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
        resume_path:           Absolute path to the resume PDF.
        cover_letter_path:     Absolute path to the cover letter PDF.
        reference_letter_path: Absolute path to the reference letter PDF.

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
                key_map = {
                    "resume": "resumePath",
                    "cover_letter": "coverLetterPath",
                    "reference_letter": "referenceLetterPath",
                }
                file_path = path_map.get(doc_type) if doc_type else None
                if file_path:
                    ok = await _attach_resume(element, file_path)
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

            if tag == "select":
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
                    ok = await _fill_combobox(page, element, str_value)
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
