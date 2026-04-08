"""Build seeds/anchor_pis.json with well-known ML/CS/Math researchers.

Run: python scripts/build_anchor_pis.py
"""

import json
import time
from pathlib import Path

import httpx

HEADERS = {"User-Agent": "mailto:gradradar@example.com"}
BASE = "https://api.openalex.org"

# Anchor PIs: (name, institution hint for disambiguation)
ANCHORS = [
    ("Yoshua Bengio", "Mila"),
    ("Geoffrey Hinton", "Toronto"),
    ("Yann LeCun", "New York University"),
    ("Ilya Sutskever", "OpenAI"),
    ("Andrej Karpathy", "Stanford"),
    ("Pieter Abbeel", "Berkeley"),
    ("Sergey Levine", "Berkeley"),
    ("Percy Liang", "Stanford"),
    ("Christopher Manning", "Stanford"),
    ("Daphne Koller", "Stanford"),
    ("Michael Jordan", "Berkeley"),
    ("Sanjeev Arora", "Princeton"),
    ("Leskovec Jure", "Stanford"),
    ("Stefanie Jegelka", "MIT"),
    ("Tommi Jaakkola", "MIT"),
    ("Suvrit Sra", "MIT"),
    ("Chelsea Finn", "Stanford"),
    ("Sara Beery", "MIT"),
    ("Aleksander Madry", "MIT"),
    ("Been Kim", "Google"),
]


def lookup_author(name: str, hint: str) -> dict | None:
    try:
        resp = httpx.get(
            f"{BASE}/authors",
            params={"search": name, "per_page": 5},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None

        # Try to match by institution hint
        for r in results:
            inst_name = (r.get("last_known_institutions") or [{}])[0].get("display_name", "") if r.get("last_known_institutions") else ""
            if hint.lower() in inst_name.lower() or inst_name.lower() in hint.lower():
                return _format(r)

        # Fallback: highest cited
        return _format(results[0])
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def _format(r):
    inst = (r.get("last_known_institutions") or [{}])[0] if r.get("last_known_institutions") else {}
    return {
        "name": r["display_name"],
        "openalex_id": r["id"].replace("https://openalex.org/", ""),
        "institution": inst.get("display_name"),
        "h_index": r.get("summary_stats", {}).get("h_index"),
        "works_count": r.get("works_count", 0),
        "cited_by_count": r.get("cited_by_count", 0),
    }


def main():
    pis = []
    for i, (name, hint) in enumerate(ANCHORS):
        print(f"[{i+1}/{len(ANCHORS)}] {name}...")
        result = lookup_author(name, hint)
        if result:
            pis.append(result)
            print(f"  {result['name']} @ {result['institution']} — h={result['h_index']}, {result['works_count']} works")
        else:
            print(f"  NOT FOUND")
        time.sleep(0.2)

    output = Path(__file__).parent.parent / "seeds" / "anchor_pis.json"
    with open(output, "w") as f:
        json.dump(pis, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {len(pis)} anchor PIs to {output}")


if __name__ == "__main__":
    main()
