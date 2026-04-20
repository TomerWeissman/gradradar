# gradradar

Discover PhD labs and Masters programs in ML, CS, and Math via natural-language search.

Search runs against a hosted, community-maintained database of **67,571 researchers** across CS-adjacent venues (NeurIPS, ICML, ICLR, AAAI, CVPR, ACL, and more). Anyone with an API key can enrich new PIs with a single command, and the next person to search sees the update. No database to download.

## Quick start

Requires **Python 3.11+**.

```bash
pip install git+https://github.com/TomerWeissman/gradradar.git
gradradar setup    # guided wizard: profile, API key, first search
```

That's it. `setup` takes about 30 seconds.

Prefer to run each step yourself?

```bash
gradradar profile setup                              # opens a Markdown profile in $EDITOR
gradradar search "graph neural networks" --top 5     # hits the hosted DB
```

## What you get

- **67,571 researchers** linked to their institutions, h-indexes, and career info.
- **6,222+ enriched PIs** (and growing — see "Contributing" below) with scraped faculty-page research descriptions, departments, career stage, and inferred "taking students" status.
- **Hosted Postgres full-text search** with stemming and ranking, plus optional LLM re-ranking against your profile.

## Setting up your profile

Your profile is a plain Markdown file. gradradar reads it before ranking results, so matches reflect *your* research interests and background.

```bash
gradradar profile setup     # opens ~/.gradradar/profile.md in $EDITOR
gradradar profile show      # print current profile
gradradar profile path      # print file path
```

The template has sections for research interests, academic background, what you're looking for (degree, geography, funding), and career goals. Edit freely — there's no required schema.

Profile changes invalidate the narration cache automatically (hashed into the cache key), so you always get matches written for the current you.

## Key commands

| Command | What it does |
| --- | --- |
| `gradradar setup` | Interactive first-run wizard (recommended) |
| `gradradar search "<query>"` | Natural-language search with LLM query translation + rerank |
| `gradradar search "<query>" --narrate` | Add 3–5 sentence personalized match narratives for top results |
| `gradradar search "<query>" --no-llm` | Skip all LLM calls (free, plain keyword search) |
| `gradradar search "<query>" --local` | Use a local DuckDB snapshot instead of the hosted DB (see [Offline mode](#offline-mode)) |
| `gradradar contribute <pi_id>` | Enrich a PI from their faculty page and share with the community |
| `gradradar recommend` | Get recommendations based purely on your profile |
| `gradradar profile setup` | Create / edit your profile |

Run any command with `--help` for its flags.

## Contributing data

gradradar maintains itself through community contributions. If you find a PI with no research description, run:

```bash
gradradar contribute <pi_id>
# or pass a specific faculty page:
gradradar contribute <pi_id> --url https://cs.example.edu/~prof-name/
```

The CLI:
1. Fetches the faculty page.
2. Uses **your** Anthropic key (~$0.001 per contribution) to extract structured fields with Haiku.
3. Shows you exactly what will be contributed, and asks for confirmation.
4. POSTs to the hosted Edge Function, which rate-limits (30/hour per IP), logs provenance per field, and updates the shared DB.

Contributions are CC BY 4.0 and publicly visible. Every field keeps a `source_url`, `model`, `contributor_id`, and timestamp so bad data can be surgically reverted.

## LLM features and costs

By default, search uses an LLM for query understanding and relevance re-ranking (~$0.015 per search with Claude Sonnet). Adding `--narrate` generates per-result narratives (~$0.045). Narratives are cached locally in `~/.gradradar/db/` keyed by `(pi_id, query, profile_hash)` — repeat queries are free.

Set `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY` + `GRADRADAR_LLM_MODEL`) in your environment or a `.env` file.

To run with no API costs, use `--no-llm`:

```bash
gradradar search "diffusion models" --no-llm
```

## Offline mode

`--local` uses a local DuckDB snapshot instead of the hosted DB. Useful for air-gapped work, or for running against a custom snapshot. Download the current snapshot from Cloudflare R2 first:

```bash
gradradar init                             # downloads ~1.6 GB to ~/.gradradar/db/
gradradar search "your query" --local
```

The snapshot is a point-in-time copy; community contributions made after the snapshot won't appear until the next published release.

## Configuration

gradradar reads a `.env` file from the current directory or uses system env vars. See [.env.example](.env.example) for the full list. Most users won't need to set anything — search and contribute work out of the box with hardcoded defaults for the hosted backend.

Data lives under `~/.gradradar/`:

```
~/.gradradar/
├── profile.md          # your profile
├── contributor_id      # anonymous UUID used for contributions
├── db/                 # only present if you used --local
│   ├── gradradar.duckdb
│   └── snapshots/
└── cache/              # scraper + LLM response cache
```

## License

Code: CC BY 4.0. Database: aggregated from public web pages and open academic sources; community contributions are CC BY 4.0.

## Contributing code

Issues and PRs welcome at https://github.com/TomerWeissman/gradradar.
