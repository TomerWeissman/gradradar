"""Build seeds/institutions.json by looking up OpenAlex IDs for target institutions.

Run: python scripts/build_institution_seeds.py
"""

import json
import time
from pathlib import Path

import httpx

HEADERS = {"User-Agent": "mailto:gradradar@example.com"}
BASE = "https://api.openalex.org"

# Target institutions: (search_name, country, region, type)
TARGETS = [
    # --- US Top 50 CS/Math ---
    ("Massachusetts Institute of Technology", "US", "US", "university"),
    ("Stanford University", "US", "US", "university"),
    ("Carnegie Mellon University", "US", "US", "university"),
    ("University of California, Berkeley", "US", "US", "university"),
    ("California Institute of Technology", "US", "US", "university"),
    ("Princeton University", "US", "US", "university"),
    ("Harvard University", "US", "US", "university"),
    ("University of Washington", "US", "US", "university"),
    ("Cornell University", "US", "US", "university"),
    ("University of Illinois Urbana-Champaign", "US", "US", "university"),
    ("Georgia Institute of Technology", "US", "US", "university"),
    ("University of Michigan", "US", "US", "university"),
    ("University of Texas at Austin", "US", "US", "university"),
    ("Columbia University", "US", "US", "university"),
    ("University of California, Los Angeles", "US", "US", "university"),
    ("University of California, San Diego", "US", "US", "university"),
    ("University of Wisconsin–Madison", "US", "US", "university"),
    ("University of Maryland, College Park", "US", "US", "university"),
    ("University of Pennsylvania", "US", "US", "university"),
    ("New York University", "US", "US", "university"),
    ("Duke University", "US", "US", "university"),
    ("University of Chicago", "US", "US", "university"),
    ("Yale University", "US", "US", "university"),
    ("University of Massachusetts Amherst", "US", "US", "university"),
    ("Johns Hopkins University", "US", "US", "university"),
    ("Northwestern University", "US", "US", "university"),
    ("Rice University", "US", "US", "university"),
    ("University of Southern California", "US", "US", "university"),
    ("Ohio State University", "US", "US", "university"),
    ("University of Minnesota", "US", "US", "university"),
    ("Purdue University", "US", "US", "university"),
    ("Brown University", "US", "US", "university"),
    ("University of Virginia", "US", "US", "university"),
    ("University of California, Irvine", "US", "US", "university"),
    ("University of California, Santa Barbara", "US", "US", "university"),
    ("Boston University", "US", "US", "university"),
    ("Northeastern University", "US", "US", "university"),
    ("University of Colorado Boulder", "US", "US", "university"),
    ("Pennsylvania State University", "US", "US", "university"),
    ("Rutgers University", "US", "US", "university"),
    ("University of North Carolina at Chapel Hill", "US", "US", "university"),
    ("Stony Brook University", "US", "US", "university"),
    ("University of Utah", "US", "US", "university"),
    ("Arizona State University", "US", "US", "university"),
    ("University of Florida", "US", "US", "university"),
    ("Virginia Tech", "US", "US", "university"),
    ("University of California, Davis", "US", "US", "university"),
    ("Washington University in St. Louis", "US", "US", "university"),
    ("Emory University", "US", "US", "university"),
    ("Texas A&M University", "US", "US", "university"),
    # --- UK Top 20 ---
    ("University of Oxford", "GB", "UK", "university"),
    ("University of Cambridge", "GB", "UK", "university"),
    ("Imperial College London", "GB", "UK", "university"),
    ("University College London", "GB", "UK", "university"),
    ("University of Edinburgh", "GB", "UK", "university"),
    ("University of Manchester", "GB", "UK", "university"),
    ("King's College London", "GB", "UK", "university"),
    ("University of Bristol", "GB", "UK", "university"),
    ("University of Warwick", "GB", "UK", "university"),
    ("University of Glasgow", "GB", "UK", "university"),
    ("University of Birmingham", "GB", "UK", "university"),
    ("University of Leeds", "GB", "UK", "university"),
    ("University of Southampton", "GB", "UK", "university"),
    ("University of Sheffield", "GB", "UK", "university"),
    ("University of Nottingham", "GB", "UK", "university"),
    ("University of Bath", "GB", "UK", "university"),
    ("University of St Andrews", "GB", "UK", "university"),
    ("University of York", "GB", "UK", "university"),
    ("University of Exeter", "GB", "UK", "university"),
    ("University of Surrey", "GB", "UK", "university"),
    # --- Europe Top 30 ---
    ("ETH Zurich", "CH", "Europe", "university"),
    ("EPFL", "CH", "Europe", "university"),
    ("Technical University of Munich", "DE", "Europe", "university"),
    ("Max Planck Society", "DE", "Europe", "research_institute"),
    ("RWTH Aachen University", "DE", "Europe", "university"),
    ("Heidelberg University", "DE", "Europe", "university"),
    ("Technical University of Berlin", "DE", "Europe", "university"),
    ("University of Bonn", "DE", "Europe", "university"),
    ("INRIA", "FR", "Europe", "research_institute"),
    ("Sorbonne University", "FR", "Europe", "university"),
    ("École Normale Supérieure", "FR", "Europe", "university"),
    ("École Polytechnique", "FR", "Europe", "university"),
    ("Université Paris-Saclay", "FR", "Europe", "university"),
    ("KU Leuven", "BE", "Europe", "university"),
    ("Delft University of Technology", "NL", "Europe", "university"),
    ("University of Amsterdam", "NL", "Europe", "university"),
    ("Eindhoven University of Technology", "NL", "Europe", "university"),
    ("KTH Royal Institute of Technology", "SE", "Europe", "university"),
    ("Uppsala University", "SE", "Europe", "university"),
    ("University of Copenhagen", "DK", "Europe", "university"),
    ("Aalto University", "FI", "Europe", "university"),
    ("University of Helsinki", "FI", "Europe", "university"),
    ("Sapienza University of Rome", "IT", "Europe", "university"),
    ("Politecnico di Milano", "IT", "Europe", "university"),
    ("Technical University of Denmark", "DK", "Europe", "university"),
    ("University of Vienna", "AT", "Europe", "university"),
    ("Technical University of Vienna", "AT", "Europe", "university"),
    ("Charles University", "CZ", "Europe", "university"),
    ("University of Warsaw", "PL", "Europe", "university"),
    ("Universitat Politècnica de Catalunya", "ES", "Europe", "university"),
    # --- Industry Labs ---
    ("Google DeepMind", "GB", "UK", "industry_lab"),
    ("Microsoft Research", "US", "US", "industry_lab"),
    ("Meta AI", "US", "US", "industry_lab"),
    ("OpenAI", "US", "US", "industry_lab"),
    ("Allen Institute for Artificial Intelligence", "US", "US", "research_institute"),
]


def lookup_institution(name: str, country: str) -> dict | None:
    """Look up an institution by name in OpenAlex."""
    try:
        resp = httpx.get(
            f"{BASE}/institutions",
            params={
                "filter": f"display_name.search:{name}",
                "per_page": 5,
            },
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

        # Try to find exact or close match
        for r in results:
            if r["country_code"] == country or country in ("", None):
                return {
                    "name": r["display_name"],
                    "openalex_id": r["id"].replace("https://openalex.org/", ""),
                    "country": r["country_code"],
                    "city": r.get("geo", {}).get("city"),
                    "works_count": r.get("works_count", 0),
                }

        # Fallback: first result
        if results:
            r = results[0]
            return {
                "name": r["display_name"],
                "openalex_id": r["id"].replace("https://openalex.org/", ""),
                "country": r["country_code"],
                "city": r.get("geo", {}).get("city"),
                "works_count": r.get("works_count", 0),
            }
    except Exception as e:
        print(f"  ERROR looking up {name}: {e}")
    return None


def main():
    institutions = []
    failed = []

    for i, (name, country, region, inst_type) in enumerate(TARGETS):
        print(f"[{i+1}/{len(TARGETS)}] Looking up: {name}...")
        result = lookup_institution(name, country)

        if result:
            institutions.append({
                "name": result["name"],
                "openalex_id": result["openalex_id"],
                "country": result["country"],
                "region": region,
                "city": result.get("city"),
                "type": inst_type,
            })
            print(f"  Found: {result['name']} ({result['openalex_id']}) — {result['works_count']} works")
        else:
            failed.append(name)
            print(f"  NOT FOUND")

        # Polite rate limiting
        time.sleep(0.2)

    # Write output
    output_path = Path(__file__).parent.parent / "seeds" / "institutions.json"
    with open(output_path, "w") as f:
        json.dump(institutions, f, indent=2, ensure_ascii=False)

    print(f"\nDone! Wrote {len(institutions)} institutions to {output_path}")
    if failed:
        print(f"Failed lookups ({len(failed)}): {failed}")


if __name__ == "__main__":
    main()
