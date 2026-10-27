# Contributing

Contributions should cite the original publisher URL, verify the date or leave it null, and describe methods without fabricating capability scores. Add monitoring endpoints to `sources/registry.json`, not inside a skill. Do not copy report bodies or user conversations. Run `python scripts/validate.py` and `python -m unittest discover -s tests -v` before submitting a PR. Review discovery PRs for source relevance, taxonomy/denominator changes, and license restrictions.
