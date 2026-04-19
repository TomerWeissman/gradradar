"""Audit enrichment quality: field fill rates and sample spot-checks."""

import duckdb
from gradradar.config import get_db_path


def run_audit(min_h_index: int = 50):
    con = duckdb.connect(str(get_db_path()), read_only=True)

    total = con.execute("SELECT COUNT(*) FROM pis WHERE h_index >= ?", [min_h_index]).fetchone()[0]
    enriched = con.execute(
        "SELECT COUNT(*) FROM pis WHERE research_description IS NOT NULL AND h_index >= ?",
        [min_h_index],
    ).fetchone()[0]

    print(f"Total PIs (h_index >= {min_h_index}): {total}")
    print(f"Enriched (has research_description): {enriched}")
    print(f"Enrichment progress: {enriched}/{total} ({100 * enriched / total:.1f}%)\n")

    # Field fill rates
    fields = [
        ("research_description", "research_description IS NOT NULL"),
        ("short_bio", "short_bio IS NOT NULL"),
        ("department_name", "department_name IS NOT NULL"),
        ("is_taking_students (yes/no)", "is_taking_students IN ('yes', 'no')"),
        ("email", "email IS NOT NULL"),
        ("lab_name", "lab_name IS NOT NULL"),
        ("career_stage", "career_stage IS NOT NULL"),
        ("personal_url", "personal_url IS NOT NULL"),
        ("lab_url", "lab_url IS NOT NULL"),
        ("current_student_count", "current_student_count IS NOT NULL"),
        ("funding_sources", "funding_sources IS NOT NULL"),
    ]

    print(f"{'Field':<30} {'Count':>6} {'% of enriched':>14}")
    print("-" * 55)
    for name, condition in fields:
        count = con.execute(
            f"SELECT COUNT(*) FROM pis WHERE {condition} AND research_description IS NOT NULL"
        ).fetchone()[0]
        pct = 100 * count / enriched if enriched > 0 else 0
        print(f"{name:<30} {count:>6} {pct:>13.1f}%")

    # Taking students breakdown
    print("\nTaking students breakdown (enriched PIs):")
    for status in ["yes", "no", "unknown"]:
        count = con.execute(
            "SELECT COUNT(*) FROM pis WHERE is_taking_students = ? AND research_description IS NOT NULL",
            [status],
        ).fetchone()[0]
        print(f"  {status}: {count}")

    # Random sample of 10 enriched PIs for manual spot-check
    print("\n" + "=" * 70)
    print("SAMPLE SPOT-CHECK (10 random enriched PIs)")
    print("=" * 70)
    samples = con.execute("""
        SELECT p.name, i.name, p.department_name, p.short_bio, p.research_description,
               p.is_taking_students, p.email, p.lab_name, p.career_stage, p.source_url
        FROM pis p
        LEFT JOIN institutions i ON i.id = p.institution_id
        WHERE p.research_description IS NOT NULL AND p.h_index >= ?
        ORDER BY RANDOM()
        LIMIT 10
    """, [min_h_index]).fetchall()

    for s in samples:
        print(f"\n{'─' * 60}")
        print(f"Name:        {s[0]}")
        print(f"Institution: {s[1]}")
        print(f"Department:  {s[2] or '—'}")
        print(f"Career:      {s[8] or '—'}")
        print(f"Students:    {s[5] or '—'}")
        print(f"Email:       {s[6] or '—'}")
        print(f"Lab:         {s[7] or '—'}")
        bio = s[3] or "—"
        if len(bio) > 150:
            bio = bio[:150] + "..."
        print(f"Bio:         {bio}")
        desc = s[4] or "—"
        if len(desc) > 150:
            desc = desc[:150] + "..."
        print(f"Research:    {desc}")
        print(f"Source URL:  {s[9] or '—'}")

    con.close()


if __name__ == "__main__":
    run_audit()
