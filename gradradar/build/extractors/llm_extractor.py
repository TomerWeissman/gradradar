"""LLM structured extraction from HTML via instructor.

Takes scraped text from faculty/lab pages and extracts structured PI fields.
"""

from __future__ import annotations

import instructor
import litellm
from pydantic import BaseModel, Field

from gradradar.config import get_llm_model

litellm.suppress_debug_info = True


class PIExtraction(BaseModel):
    """Structured data extracted from a PI's web page."""

    research_description: str | None = Field(
        default=None,
        description="2-4 sentence summary of the PI's research interests and focus areas. "
        "Use their own words where possible.",
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

Extract as much structured information as you can. Be conservative:
- Only set is_taking_students to "yes" or "no" if there is clear evidence \
  (e.g. "I am looking for PhD students" or "Not accepting students at this time"). \
  Phrases like "prospective students" in a nav link are NOT sufficient — that's a \
  generic university template.
- For research_description, summarize their actual research interests in 2-4 sentences. \
  Don't just list paper titles.
- For career_stage, infer from their title (e.g. "Assistant Professor" → assistant_professor).
- Leave fields as null if the information isn't clearly present.

Page text:
{page_text}
"""


def extract_pi_from_text(
    page_text: str,
    pi_name: str,
    institution_name: str,
    model: str | None = None,
) -> PIExtraction:
    """Extract structured PI data from scraped page text."""
    model = model or get_llm_model()

    # Truncate very long pages to stay within context limits
    if len(page_text) > 12000:
        page_text = page_text[:12000] + "\n\n[...truncated...]"

    prompt = EXTRACTION_PROMPT.format(
        pi_name=pi_name,
        institution_name=institution_name,
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
