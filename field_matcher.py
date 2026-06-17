"""Rule-based form field matcher for JobAutomata.

Maps form field signals (name, id, label, placeholder, autocomplete, aria_label)
to profile keys using weighted pattern matching.

Public interface
----------------
    match_field(signals: dict) -> Optional[str]

The function returns the best-matching profile key (e.g. ``"firstName"``) or
``None`` if no candidate scores above the confidence threshold.

Extension point for LLM integration
-------------------------------------
``match_field`` delegates to ``_rule_based_match`` internally. A future
``llm_matcher.py`` can import ``match_field`` and fall through to an LLM when
the rule-based score is ``None``:

    from field_matcher import match_field as rule_match

    def match_field(signals: dict) -> Optional[str]:
        result = rule_match(signals)
        if result is not None:
            return result
        return llm_match(signals)          # drop-in extension
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Minimum score a candidate must reach to be returned.  Each exact-string hit
# on the autocomplete attribute scores AUTOCOMPLETE_WEIGHT; pattern hits on
# other signals score 1 (label/placeholder/aria) or ATTR_WEIGHT (name/id).
CONFIDENCE_THRESHOLD = 1
AUTOCOMPLETE_WEIGHT = 10   # autocomplete match is nearly definitive
ATTR_WEIGHT = 3            # name= / id= attribute match outweighs free text

# ---------------------------------------------------------------------------
# Pattern catalogue
# ---------------------------------------------------------------------------
# Structure: profile_key -> {signal_type -> [regex patterns]}
#
# Signal types (checked independently, scores are additive):
#   "autocomplete"  — HTML autocomplete attribute value
#   "attr"          — name= or id= attribute (ATTR_WEIGHT each)
#   "text"          — label, placeholder, aria_label (1 point each)
#
# All patterns are matched case-insensitively against the normalised signal
# string (lowercased, with hyphens/underscores/spaces collapsed).
# ---------------------------------------------------------------------------

_PATTERNS: dict[str, dict[str, list[str]]] = {

    "firstName": {
        "autocomplete": [r"^given[\s-]?name$", r"^first[\s-]?name$"],
        "attr": [
            r"first.?name", r"fname", r"given.?name",
            # German / European
            r"vorname", r"vname",
            # French
            r"pr[eé]nom",
            # Spanish / Portuguese
            r"nombre", r"\bnome\b",
            # Dutch
            r"voornaam",
        ],
        "text": [
            r"first\s*name", r"given\s*name", r"forename",
            r"vorname", r"pr[eé]nom", r"nombre", r"\bnome\b", r"voornaam",
        ],
    },

    "lastName": {
        "autocomplete": [r"^family[\s-]?name$", r"^last[\s-]?name$"],
        "attr": [
            r"last.?name", r"lname", r"family.?name", r"surname",
            r"nachname", r"familienname",
            r"\bnom\b", r"sobrenome", r"apellido",
            r"achternaam",
            r"cognome",
        ],
        "text": [
            r"last\s*name", r"family\s*name", r"surname",
            r"nachname", r"familienname",
            r"\bnom\b", r"sobrenome", r"apellido",
            r"achternaam", r"cognome",
        ],
    },

    "email": {
        "autocomplete": [r"^email$"],
        "attr": [r"e.?mail", r"email.?addr"],
        "text": [r"e-?mail", r"electronic\s*mail"],
    },

    "phone": {
        "autocomplete": [r"^tel$", r"^mobile$", r"^tel[\s-]?national$", r"^tel[\s-]?local$"],
        "attr": [
            r"phone", r"tel(?:ephone)?", r"mobile", r"cell(?:phone)?",
            r"handy", r"telefon", r"t[eé]l[eé]phone",
            r"tel[eé]fono", r"telefone",
        ],
        "text": [
            r"phone", r"telephone", r"mobile", r"cell",
            r"handy", r"telefon", r"t[eé]l[eé]phone",
            r"tel[eé]fono", r"telefone",
        ],
    },

    "address": {
        "autocomplete": [r"^street[\s-]?address$", r"^address[\s-]?line[\s-]?1$"],
        "attr": [
            r"address(?!2|_2|-2|line2)", r"street", r"addr(?!ess2)",
            r"adresse", r"stra(?:ss|ß)e", r"direcci[oó]n", r"endere[çc]o",
        ],
        "text": [
            r"street\s*address", r"address\s*line\s*1", r"address(?!\s*2)",
            r"adresse", r"stra(?:ss|ß)e", r"direcci[oó]n", r"endere[çc]o",
        ],
    },

    "city": {
        "autocomplete": [r"^address[\s-]?level[\s-]?2$"],
        "attr": [
            r"city", r"town", r"municipality", r"locality",
            r"stadt", r"\bort\b", r"\bville\b", r"ciudad", r"cidade",
        ],
        "text": [
            r"city", r"town", r"municipality",
            r"stadt", r"\bort\b", r"\bville\b", r"ciudad", r"cidade",
        ],
    },

    "zip": {
        "autocomplete": [r"^postal[\s-]?code$"],
        "attr": [
            r"zip", r"postal.?code", r"postcode", r"post.?code",
            r"plz", r"postleitzahl", r"code\s*postal", r"c[oó]digo\s*postal", r"c[eé]p",
        ],
        "text": [
            r"zip(?:\s*code)?", r"postal\s*code", r"postcode",
            r"plz", r"postleitzahl", r"code\s*postal", r"c[oó]digo\s*postal", r"cep",
        ],
    },

    "country": {
        "autocomplete": [r"^country$", r"^country[\s-]?name$"],
        "attr": [
            r"country", r"land", r"pays", r"pa[ií]s",
        ],
        "text": [
            r"country", r"land", r"pays", r"pa[ií]s",
        ],
    },

    "nationality": {
        "autocomplete": [],
        "attr": [
            r"national(?:ity)?", r"citizenship", r"staatsb[uü]rger",
            r"nationalit[eé]", r"ciudadan[ií]a",
        ],
        "text": [
            r"nationality", r"citizenship",
            r"staatsb[uü]rgerschaft", r"nationalit[eé]",
        ],
    },

    "linkedin": {
        "autocomplete": [],
        "attr": [r"linkedin", r"linked.in"],
        "text": [r"linkedin", r"linked\s*in"],
    },

    "github": {
        "autocomplete": [],
        "attr": [r"github", r"git.?hub"],
        "text": [r"github", r"git\s*hub"],
    },

    "portfolio": {
        "autocomplete": [r"^url$"],
        "attr": [
            r"portfolio", r"personal.?site", r"website", r"web.?page",
            r"personal.?url", r"homepage",
        ],
        "text": [
            r"portfolio", r"personal\s*(?:website|site|page|url)", r"homepage",
        ],
    },

    "currentTitle": {
        "autocomplete": [r"^organization[\s-]?title$"],
        "attr": [
            r"(?:current|job|current.?job).?title", r"position", r"role",
            r"jobtitle", r"job.?position",
            r"berufsbezeichnung", r"stellenbezeichnung",
            r"intitul[eé]\s*de\s*poste",
        ],
        "text": [
            r"(?:current\s+)?(?:job\s+)?title", r"job\s+position",
            r"current\s+role", r"position",
            r"berufsbezeichnung", r"titre\s*du\s*poste",
        ],
    },

    "currentCompany": {
        "autocomplete": [r"^organization$", r"^organisation$"],
        "attr": [
            r"company", r"employer", r"organization", r"organisation",
            r"current.?company", r"current.?employer",
            r"unternehmen", r"firma", r"entreprise",
        ],
        "text": [
            r"(?:current\s+)?company", r"(?:current\s+)?employer",
            r"organization", r"unternehmen", r"firma", r"entreprise",
        ],
    },

    "university": {
        "autocomplete": [],
        "attr": [
            r"university", r"college", r"school", r"institution",
            r"universit[äae]t", r"hochschule", r"universit[eé]",
            r"universidad", r"universidade",
        ],
        "text": [
            r"university", r"college", r"school(?:\s*name)?",
            r"institution", r"universit[äae]t", r"hochschule",
        ],
    },

    "degree": {
        "autocomplete": [],
        "attr": [
            r"degree", r"qualification", r"diploma", r"major",
            r"studiengang", r"abschluss",
        ],
        "text": [
            r"degree", r"qualification", r"diploma", r"major",
            r"field\s*of\s*study", r"abschluss", r"studiengang",
        ],
    },

    "gradYear": {
        "autocomplete": [],
        "attr": [
            r"grad(?:uation)?[\s._-]?year", r"graduation[\s._-]?date",
            r"completion[\s._-]?year",
        ],
        "text": [
            r"graduation\s*year", r"year\s*of\s*graduation",
            r"graduation\s*date",
        ],
    },

    "yearsExp": {
        "autocomplete": [],
        "attr": [
            r"years?.?exp(?:erience)?", r"experience[._-]?years?",
            r"berufserfahrung", r"exp[._-]?years?",
        ],
        "text": [
            r"years?\s*of\s*experience", r"years?\s*exp(?:erience)?",
            r"berufserfahrung",
        ],
    },

    "workAuth": {
        "autocomplete": [],
        "attr": [
            r"work.?auth(?:orization)?", r"visa.?status", r"work.?permit",
            r"right.?to.?work", r"work.?eligib",
            r"arbeitserlaubnis", r"aufenthaltstitel",
        ],
        "text": [
            r"work\s*auth(?:orization)?", r"visa\s*(?:status|type)",
            r"right\s*to\s*work", r"work\s*permit", r"work\s*eligib",
        ],
    },

    "salaryExpect": {
        "autocomplete": [],
        "attr": [
            r"salary.?expect", r"expected.?salary", r"desired.?salary",
            r"comp(?:ensation)?.?expect", r"pay.?expect",
            r"gehaltsvorstellung", r"gehalt",
            r"r[eé]mun[eé]ration", r"pr[eé]tention\s*salariale",
        ],
        "text": [
            r"salary\s*expect(?:ation)?", r"expected\s*salary",
            r"desired\s*salary", r"compensation\s*expect",
            r"gehaltsvorstellung", r"r[eé]mun[eé]ration",
        ],
    },

    "noticePeriod": {
        "autocomplete": [],
        "attr": [
            r"notice.?period", r"notice", r"k[uü]ndigungsfrist",
            r"pr[eé]avis",
        ],
        "text": [
            r"notice\s*period", r"k[uü]ndigungsfrist", r"pr[eé]avis",
        ],
    },

    "startDate": {
        "autocomplete": [],
        "attr": [
            r"start.?date", r"available.?(?:from|date)", r"earliest.?start",
            r"eintrittsdatum", r"eintritt",
        ],
        "text": [
            r"start\s*date", r"available\s*(?:from|date)",
            r"earliest\s*start", r"eintrittsdatum", r"eintritt",
        ],
    },

    "dateOfBirth": {
        "autocomplete": [r"^bday$", r"^bday[\s-]?day$", r"^bday[\s-]?month$", r"^bday[\s-]?year$"],
        "attr": [
            r"date.?of.?birth", r"dob", r"birth.?date", r"birthdate",
            r"geburtsdatum", r"geburtstag",
            r"fecha.?nacimiento", r"date.?naissance",
        ],
        "text": [
            r"date\s*of\s*birth", r"\bdob\b", r"birth\s*date",
            r"geburtsdatum", r"geburtstag",
            r"fecha\s*de\s*nacimiento", r"date\s*de\s*naissance",
        ],
    },
}

# ---------------------------------------------------------------------------
# Compiled regex cache
# ---------------------------------------------------------------------------

# {profile_key: {signal_type: [compiled_pattern, ...]}}
_COMPILED: dict[str, dict[str, list[re.Pattern]]] = {
    key: {
        sig: [re.compile(p, re.IGNORECASE) for p in patterns]
        for sig, patterns in sigs.items()
    }
    for key, sigs in _PATTERNS.items()
}


# ---------------------------------------------------------------------------
# Internal scoring
# ---------------------------------------------------------------------------

def _normalise(value: str) -> str:
    """Lowercase and collapse separators to a single space for consistent matching."""
    return re.sub(r"[\s_\-]+", " ", value.strip().lower())


def _score_candidate(profile_key: str, signals: dict[str, str]) -> int:
    """Return the total match score for one profile key against the given signals.

    Args:
        profile_key: A key from ``_COMPILED`` (e.g. ``"firstName"``).
        signals:     Normalised signal dict with keys:
                     ``autocomplete``, ``name``, ``id``, ``label``,
                     ``placeholder``, ``aria_label``.

    Returns:
        Cumulative integer score. Higher is more confident.
    """
    patterns = _COMPILED[profile_key]
    score = 0

    # autocomplete — most reliable signal
    ac_value = signals.get("autocomplete", "")
    if ac_value:
        for pat in patterns.get("autocomplete", []):
            if pat.search(ac_value):
                score += AUTOCOMPLETE_WEIGHT
                break

    # name= and id= attributes — strong structural signal
    for attr in ("name", "id"):
        value = signals.get(attr, "")
        if value:
            for pat in patterns.get("attr", []):
                if pat.search(value):
                    score += ATTR_WEIGHT
                    break

    # free-text signals — weaker, but still useful
    for text_key in ("label", "placeholder", "aria_label"):
        value = signals.get(text_key, "")
        if value:
            for pat in patterns.get("text", []):
                if pat.search(value):
                    score += 1
                    break

    return score


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def match_field(signals: dict) -> Optional[str]:
    """Map form field signals to a profile key using rule-based scoring.

    This is the primary extension point: a future LLM matcher can call this
    function first and fall through to an LLM only when ``None`` is returned.

    Args:
        signals: Dict with any subset of the following string keys:

                 - ``autocomplete`` — HTML autocomplete attribute value
                 - ``name``         — field name= attribute
                 - ``id``           — field id= attribute
                 - ``label``        — associated <label> text
                 - ``placeholder``  — placeholder= attribute text
                 - ``aria_label``   — aria-label= attribute value

                 Missing or empty keys are treated as absent.

    Returns:
        The best-matching profile key (e.g. ``"firstName"``) when the top
        candidate's score is at or above ``CONFIDENCE_THRESHOLD``, otherwise
        ``None``.

    Example::

        >>> match_field({"autocomplete": "given-name", "name": "firstName"})
        'firstName'
        >>> match_field({"label": "Vorname"})
        'firstName'
        >>> match_field({"name": "mystery_field"})
        None
    """
    # Normalise all signal values once.
    normalised: dict[str, str] = {
        k: _normalise(str(v)) for k, v in signals.items() if v
    }

    best_key: Optional[str] = None
    best_score = 0

    for profile_key in _COMPILED:
        score = _score_candidate(profile_key, normalised)
        if score > best_score:
            best_score = score
            best_key = profile_key

    if best_score >= CONFIDENCE_THRESHOLD:
        logger.debug(
            "match_field: '%s' -> '%s' (score=%d)",
            {k: v for k, v in normalised.items() if v},
            best_key,
            best_score,
        )
        return best_key

    logger.debug(
        "match_field: no match (best_score=%d, threshold=%d, signals=%s)",
        best_score,
        CONFIDENCE_THRESHOLD,
        normalised,
    )
    return None
