"""Deterministic department inference from URL and page title.

Runs before LLM extraction — if we can infer the department from URL/title
patterns, we skip asking the LLM for it.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse


# Longer patterns matched against both URL and title text
DEPT_PATTERNS = [
    (r"\bcomputer science and engineering\b", "Computer Science & Engineering"),
    (r"\bcomputer science & engineering\b", "Computer Science & Engineering"),
    (r"\bcomputer science\b", "Computer Science"),
    (r"\bartificial intelligence\b", "Artificial Intelligence"),
    (r"\bmachine learning\b", "Machine Learning"),
    (r"\belectrical engineering and computer science\b", "Electrical Engineering & Computer Science"),
    (r"\belectrical and computer engineering\b", "Electrical & Computer Engineering"),
    (r"\belectrical engineering\b", "Electrical Engineering"),
    (r"\bmechanical engineering\b", "Mechanical Engineering"),
    (r"\bchemical engineering\b", "Chemical Engineering"),
    (r"\bbiomedical engineering\b", "Biomedical Engineering"),
    (r"\bcivil engineering\b", "Civil Engineering"),
    (r"\bmaterials science\b", "Materials Science"),
    (r"\bmathematics\b", "Mathematics"),
    (r"\bstatistics\b", "Statistics"),
    (r"\bbiostatistics\b", "Biostatistics"),
    (r"\bphysics\b", "Physics"),
    (r"\bchemistry\b", "Chemistry"),
    (r"\bpsychology\b", "Psychology"),
    (r"\beconomics\b", "Economics"),
    (r"\bbiology\b", "Biology"),
    (r"\bneuroscience\b", "Neuroscience"),
    (r"\bneurology\b", "Neurology"),
    (r"\bradiology\b", "Radiology"),
    (r"\bpharmacy\b", "Pharmacy"),
    (r"\bpharmacology\b", "Pharmacology"),
    (r"\bpublic health\b", "Public Health"),
    (r"\bepidemiolog\w+\b", "Epidemiology"),
    (r"\binformatics\b", "Informatics"),
    (r"\binformation science\b", "Information Science"),
    (r"\blinguistics\b", "Linguistics"),
    (r"\beducation\b", "Education"),
    (r"\bmedicine\b", "Medicine"),
    (r"\bpathology\b", "Pathology"),
    (r"\boperations research\b", "Operations Research"),
    (r"\bmanagement science\b", "Management Science"),
    (r"\bsociology\b", "Sociology"),
    (r"\bpolitical science\b", "Political Science"),
    (r"\bphilosophy\b", "Philosophy"),
    (r"\bgenetics\b", "Genetics"),
    (r"\bmicrobiology\b", "Microbiology"),
    (r"\bimmunology\b", "Immunology"),
    (r"\boncology\b", "Oncology"),
    (r"\bcardiology\b", "Cardiology"),
    (r"\baeronautics\b", "Aeronautics"),
    (r"\baerospace\b", "Aerospace Engineering"),
    (r"\benvironmental science\b", "Environmental Science"),
    (r"\boceanography\b", "Oceanography"),
    (r"\bgeophysics\b", "Geophysics"),
    (r"\bgeology\b", "Geology"),
    (r"\bastronomy\b", "Astronomy"),
    (r"\bastrophysics\b", "Astrophysics"),
]

# Short patterns matched against URL only (subdomains + path segments)
URL_PATTERNS = [
    (r"(?:^|[/.])cs(?:[./]|$)", "Computer Science"),
    (r"(?:^|[/.])cse(?:[./]|$)", "Computer Science & Engineering"),
    (r"(?:^|[/.])eecs(?:[./]|$)", "Electrical Engineering & Computer Science"),
    (r"(?:^|[/.])ece(?:[./]|$)", "Electrical & Computer Engineering"),
    (r"(?:^|[/.])ee(?:[./]|$)", "Electrical Engineering"),
    (r"(?:^|[/.])me(?:[./]|$)", "Mechanical Engineering"),
    (r"(?:^|[/.])bme(?:[./]|$)", "Biomedical Engineering"),
    (r"/math/", "Mathematics"),
    (r"/stat/", "Statistics"),
    (r"/biostat/", "Biostatistics"),
    (r"/physics/", "Physics"),
    (r"/chem/", "Chemistry"),
    (r"/psych/", "Psychology"),
    (r"/econ/", "Economics"),
    (r"/sph/", "Public Health"),
    (r"/pharmacy/", "Pharmacy"),
    (r"/radiology/", "Radiology"),
    (r"(?:^|[/.])med(?:[./]|$)", "Medicine"),
    (r"/neurosci/", "Neuroscience"),
    (r"/biology/", "Biology"),
]


def infer_department(url: str, page_title: str = "") -> str | None:
    """Infer department from URL and page title using pattern matching.

    Returns the department name if a match is found, None otherwise.
    """
    url_lower = (url or "").lower()
    title_lower = (page_title or "").lower()

    # Check URL-specific short patterns first (most reliable)
    parsed = urlparse(url_lower)
    # Combine hostname and path for matching
    url_text = f"{parsed.hostname or ''}{parsed.path}"
    for pattern, dept in URL_PATTERNS:
        if re.search(pattern, url_text):
            return dept

    # Check longer patterns against title and URL combined
    combined = f"{url_lower} {title_lower}"
    for pattern, dept in DEPT_PATTERNS:
        if re.search(pattern, combined):
            return dept

    return None
