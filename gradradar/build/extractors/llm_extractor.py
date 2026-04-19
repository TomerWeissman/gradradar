"""LLM structured extraction from HTML via instructor.

Takes scraped text from faculty/lab pages and extracts structured PI fields.
"""

from __future__ import annotations

import instructor
import litellm
from pydantic import BaseModel, Field

from gradradar.config import get_llm_model

litellm.suppress_debug_info = True

# Use Haiku for extraction — structured field extraction doesn't need a large model
ENRICHMENT_MODEL = "anthropic/claude-haiku-4-5-20251001"


class PIExtraction(BaseModel):
    """Structured data extracted from a PI's web page."""

    research_description: str | None = Field(
        default=None,
        description="2-4 sentence summary of the PI's research interests and focus areas. "
        "Use their own words where possible.",
    )
    short_bio: str | None = Field(
        default=None,
        description="The PI's 'About me' or bio blurb as written on their page. "
        "Keep it verbatim if short (under 300 words), otherwise summarize to ~150 words.",
    )
    department: str | None = Field(
        default=None,
        description="The department the PI belongs to (e.g. 'Computer Science', "
        "'Electrical Engineering and Computer Science'). Use the official name from the page.",
    )
    is_taking_students: str | None = Field(
        default=None,
        description="'yes' if the page indicates they're recruiting students, "
        "'no' if it says they're not, None if unclear.",
    )
    taking_students_confidence: float | None = Field(
        default=None,
        description="Confidence in the is_taking_students assessment (0.0-1.0). "
        "1.0 = explicit statement, 0.5 = inferred from context.",
    )
    email: str | None = Field(
        default=None, description="Email address found on the page."
    )
    personal_url: str | None = Field(
        default=None, description="The PI's personal homepage URL (not the institution page)."
    )
    lab_url: str | None = Field(
        default=None, description="URL of their research lab or group page."
    )
    lab_name: str | None = Field(
        default=None, description="Name of their research lab or group."
    )
    career_stage: str | None = Field(
        default=None,
        description="One of: assistant_professor, associate_professor, full_professor, "
        "postdoc, industry_researcher, research_scientist. Infer from title on page.",
    )
    current_student_count: int | None = Field(
        default=None, description="Number of current PhD students, if listed."
    )
    funding_sources: str | None = Field(
        default=None,
        description="Comma-separated list of funding sources mentioned (e.g. 'NSF, NIH, DARPA').",
    )


EXTRACTION_PROMPT = """\
You are extracting structured information about a professor/researcher from their \
web page. The text below was scraped from a faculty or lab page.

PI name: {pi_name}
Institution: {institution_name}
Page URL: {page_url}
Page title: {page_title}

Extract as much structured information as you can. Be conservative:
- Only set is_taking_students to "yes" or "no" if there is clear evidence \
  (e.g. "I am looking for PhD students" or "Not accepting students at this time"). \
  Phrases like "prospective students" in a nav link are NOT sufficient — that's a \
  generic university template.
- For research_description, summarize their actual research interests in 2-4 sentences. \
  Don't just list paper titles.
- For short_bio, capture the "About me" or biographical blurb if present. Keep it \
  verbatim if short, otherwise summarize. This is distinct from research_description — \
  it's their personal background/story.
- For department, YOU MUST infer this from ALL available signals. Check in this order: \
  1. URL path segments: /cs/ = Computer Science, /eecs/ = EECS, /math/ = Mathematics, \
     /physics/ = Physics, /statistics/ or /stat/ or /biostat/ = Statistics, \
     /economics/ = Economics, /psychology/ = Psychology, /cse/ = Computer Science & Engineering, \
     /ece/ or /ee/ = Electrical Engineering, /me/ = Mechanical Engineering, etc. \
  2. Page title and headings \
  3. Text mentions like "Department of..." or "School of..." \
  4. The institution subdomain (e.g. cs.utexas.edu → Computer Science) \
  If ANY of these signals are present, set the department. Only leave null if truly no signal exists.
- For career_stage, infer from their title (e.g. "Assistant Professor" → assistant_professor).
- Leave fields as null if the information isn't clearly present.

Page text:
{page_text}
"""


def extract_pi_from_text(
    page_text: str,
    pi_name: str,
    institution_name: str,
    page_url: str = "",
    page_title: str = "",
    model: str | None = None,
) -> PIExtraction:
    """Extract structured PI data from scraped page text."""
    model = model or ENRICHMENT_MODEL

    # Truncate to 6K — useful info is typically in the first few KB
    if len(page_text) > 6000:
        page_text = page_text[:6000] + "\n\n[...truncated...]"

    prompt = EXTRACTION_PROMPT.format(
        pi_name=pi_name,
        institution_name=institution_name,
        page_url=page_url,
        page_title=page_title,
        page_text=page_text,
    )

    client = instructor.from_litellm(litellm.completion)
    result = client.chat.completions.create(
        model=model,
        response_model=PIExtraction,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=1024,
    )
    return result
