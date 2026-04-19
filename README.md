# gradradar

Discover PhD labs and Masters programs in ML, CS, and Math via natural-language search.

gradradar ships with a curated DuckDB database of **67,571 researchers** (6,222 deeply enriched with research descriptions, departments, career stage, and "taking students" status) and runs hybrid retrieval — full-text search → structured SQL filters → LLM re-ranking → personalized narrative matches — all on your laptop.

## Quick start

```bash
pip install git+https://github.com/TomerWeissman/gradradar.git
gradradar init                                       # downloads the DB (~1.6 GB) from R2
gradradar search "graph neural networks" --top 5
```

The `init` step downloads the latest database snapshot from a public Cloudflare R2 bucket. No credentials required.

## What you get

- **67,571 researchers** across CS-adjacent venues (NeurIPS, ICML, ICLR, AAAI, CVPR, ACL, and more), linked to their institutions, papers, citations, and h-indexes.
- **6,222 enriched PIs** with scraped faculty-page research descriptions, department, career stage, and inferred "taking students" status.
- **870K+ author-paper links** and **613K papers** for recency / citation-based ranking.

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
| `gradradar init` | Download the DB from R2 (run once) |
| `gradradar search "<query>"` | Natural-language search with LLM query translation + rerank |
| `gradradar search "<query>" --narrate` | Add 3–5 sentence personalized match narratives for top results |
| `gradradar search "<query>" --no-llm` | Skip all LLM calls (free, FTS + SQL only) |
| `gradradar recommend` | Get recommendations based purely on your profile |
| `gradradar profile setup` | Create / edit your profile |
| `gradradar db stats` | Table row counts and enrichment coverage |
| `gradradar db validate` | Schema and integrity checks |

Run any command with `--help` for its flags.

## LLM features and costs

By default, search uses an LLM for query understanding and relevance re-ranking (~$0.015 per search with Claude Sonnet). Adding `--narrate` generates per-result narratives (~$0.045). Narratives are cached in the local DB keyed by `(pi_id, query, profile_hash)` — repeat queries are free.

Set `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY` + `GRADRADAR_LLM_MODEL`) in your environment or a `.env` file.

To run fully offline with no API costs, use `--no-llm`:

```bash
gradradar search "diffusion models" --no-llm
```

## Configuration

gradradar reads a `.env` file from the current directory or uses system env vars. See [.env.example](.env.example) for the full list. The only variable most users need is `ANTHROPIC_API_KEY`.

Data lives under `~/.gradradar/`:

```
~/.gradradar/
├── db/
│   ├── gradradar.duckdb        # the database
│   ├── manifest.json            # downloaded version info
│   └── snapshots/               # your local backups
├── profile.md                   # your profile
└── cache/                       # scraper + LLM response cache
```

## License

Code: CC BY 4.0. Database: aggregated from public web pages and open academic sources.

## Contributing

Issues and PRs welcome at https://github.com/TomerWeissman/gradradar.
