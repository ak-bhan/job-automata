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
    "bewerbung", "attachment", "upload",
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
    """Return True if the element is visible, enabled, and not read-only."""
    try:
        if not await element.is_visible():
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


async def _is_resume_file_input(signals: dict[str, str]) -> bool:
    """Return True if a file input's signals suggest it accepts a resume/CV."""
    combined = " ".join(signals.values()).lower()
    return any(kw in combined for kw in _RESUME_KEYWORDS)


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


async def _fill_select(element: ElementHandle, value: str) -> bool:
    """Select the best-matching option in a ``<select>`` element.

    Attempts, in order:
    1. Exact value match.
    2. Case-insensitive value match.
    3. Case-insensitive label (visible text) match.
    """
    # Retrieve all options once to avoid repeated round-trips.
    options: list[dict] = await element.evaluate("""sel => {
        return Array.from(sel.options).map(o => ({
            value: o.value,
            label: o.text.trim(),
        }));
    }""")

    lower_value = value.lower()

    # Exact value
    for opt in options:
        if opt["value"] == value:
            try:
                await element.select_option(value=value, timeout=_FILL_TIMEOUT_MS)
                return True
            except PlaywrightError:
                pass

    # Case-insensitive value
    for opt in options:
        if opt["value"].lower() == lower_value:
            try:
                await element.select_option(value=opt["value"], timeout=_FILL_TIMEOUT_MS)
                return True
            except PlaywrightError:
                pass

    # Case-insensitive label
    for opt in options:
        if opt["label"].lower() == lower_value:
            try:
                await element.select_option(label=opt["label"], timeout=_FILL_TIMEOUT_MS)
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
        resume_path: Absolute path to the resume PDF to attach to file
                     inputs that look like resume / CV fields. Pass
                     ``None`` to skip file attachments.

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
            # File inputs: attach resume if signals suggest resume/CV field.
            # ----------------------------------------------------------------
            if itype == "file":
                if resume_path and await _is_resume_file_input(signals):
                    ok = await _attach_resume(element, resume_path)
                    entry["matched_key"] = "resumePath"
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

            if tag == "select":
                ok = await _fill_select(element, str_value)
            elif itype in _TEXT_INPUT_TYPES or tag == "textarea":
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

        summary = {
            "fields_detected": len(elements),
            "fields_filled": fields_filled,
            "fields_skipped": fields_skipped,
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
