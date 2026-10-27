# aieco

Open, versioned OpenAI and Anthropic research and dataset metadata, designed for reusable AI Agent Skills.

**定位**：持续追踪 AI 对经济与社会的影响，包括使用、就业、生产率、企业、教育和 Agent；不局限于职业分析。

## Repository

- `sources/registry.json`: official sources and dataset endpoints.
- `research/catalog.json`: curated and newly discovered primary-source research URLs.
- `data/manifests/`: dataset revision and file-link metadata (large raw data is not mirrored).
- `scripts/update.py`: scheduled discovery and upstream dataset checks.
- `scripts/query.py`: query the local research catalog.
- `skills/research-explorer/SKILL.md`: platform-neutral research skill.

## Run locally

Python 3.11+, no external packages required.

```bash
python scripts/query.py "labor"
python scripts/query.py "adoption" --json
python scripts/validate.py
python -m unittest discover -s tests -v
python scripts/update.py
```

The updater needs internet access. GitHub Actions checks sources every Monday, and opens a PR only if tracked metadata changes. OpenAI HTML research listings return HTTP 403 from GitHub-hosted runners. To avoid relying on those endpoints, the indexer reads OpenAI's **official news RSS feed** (selecting Research and relevant AI Adoption entries) and tracks OpenAI Signals ZIP/PDF revisions via **official CDN HEAD requests**. Successful fallback checks are required for a complete update; upstream failures remain visible in the workflow summary. Run it manually from **Actions → Update research index → Run workflow**. Enable **Settings → Actions → General → Allow GitHub Actions to create and approve pull requests** if your repository policy requires it.

## Agent skill

Install the directory `skills/research-explorer` as an [Agent Skill](https://agentskills.io/specification) in a compatible client, and give the assistant access to a checkout of this repository. Ask questions such as "Compare Anthropic and OpenAI evidence on AI adoption" or "What can AI currently help with in my job?". The skill indexes research; it does not assert model capability or a job-replacement rate without evidence.

## Scope and quality

Publisher usage data measures **observed adoption**, not model capability, net productivity, or displacement. These require distinct evidence and compatible denominators. Source websites may be incomplete or change their markup; discoveries are reviewed before merging. Automatic ingestion adds links and metadata only, never full report text. The official RSS supplies publication dates for OpenAI entries; other discovered entries can retain unknown dates until verified.

OpenAI Signals public dataset declares CC BY 4.0 and the Anthropic EconomicIndex Hugging Face dataset declares MIT; these **do not automatically license each linked report**. Keep source attribution and review rights before redistributing documents or datasets.

See [methodology](references/methodology.md) and [contributing](CONTRIBUTING.md).
