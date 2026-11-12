from gradradar.build.extractors.department_parser import infer_department


def test_finance_title_beats_generic_operations_research():
    title = "Department of Operations Research and Financial Engineering"
    assert infer_department("https://example.edu/people/x", title) == "Operations Research & Financial Engineering"


def test_ieor_url_segment():
    assert infer_department("https://ieor.columbia.edu/faculty/x") == "Industrial Engineering & Operations Research"


def test_orfe_url_segment():
    assert infer_department("https://orfe.princeton.edu/people/x") == "Operations Research & Financial Engineering"


def test_plain_finance_department():
    assert infer_department("https://example.edu/x", "Professor of Finance | Business School") == "Finance"


def test_generic_operations_research_still_matches():
    assert infer_department("https://example.edu/x", "Operations Research Center") == "Operations Research"


def test_cs_unchanged():
    assert infer_department("https://cs.stanford.edu/~x") == "Computer Science"


def test_extraction_normalizes_enum_fields():
    from gradradar.build.extractors.llm_extractor import PIExtraction
    e = PIExtraction(career_stage="Associate Professor", is_taking_students="Yes", taking_students_confidence=1.5)
    assert (e.career_stage, e.is_taking_students, e.taking_students_confidence) == ("associate_professor", "yes", None)
    e = PIExtraction(career_stage="Lecturer", is_taking_students="maybe")
    assert (e.career_stage, e.is_taking_students) == (None, None)
    assert PIExtraction(career_stage="Professor").career_stage == "full_professor"


def test_name_on_page_matches_surname_with_accents():
    from gradradar.build.sources.url_discovery import name_on_page
    assert name_on_page("Andrzej Święch", "Professor Andrzej Swiech, School of Math")
    assert name_on_page("I.E. Grossmann", "Ignacio Grossmann directs the CAPD")
    assert not name_on_page("Marcus A. Pereira", "Anjuli Datta, Biosciences")
    assert not name_on_page("Wei-Choun Yu", "Young faculty in yuma county")


def test_url_filter_rejects_roots_logins_and_ratings():
    from gradradar.build.sources.url_discovery import _is_usable_url
    assert not _is_usable_url("https://www.mit.edu/")
    assert not _is_usable_url("https://shibidp.cit.cornell.edu/idp/profile/SAML2/Redirect/SSO")
    assert not _is_usable_url("https://www.ratemyprofessors.com/professor/123")
    assert _is_usable_url("https://people.orie.cornell.edu/dag369/")
