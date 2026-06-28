# Claude repository instructions

Before any work, read [`AGENTS.md`](AGENTS.md), then [`docs/specs/INDEX.md`](docs/specs/INDEX.md) and the subsystem specifications it links.

Critical rules:

- preserve the text-only model policy;
- keep run logs and human score sidecars separate;
- never expose credentials or private server configuration;
- use the canonical `data/competitions/<id>/competition.json` plus direct `data/competitions/<id>/<problem_id>.json` layout;
- update affected Markdown specifications together with code changes;
- run the validation commands in `AGENTS.md` before finishing.

When documentation and implementation disagree, inspect the code, correct the documentation, and mention the discrepancy in the final report.
