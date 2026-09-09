# Prepared paper corpus

Three pinned papers are configured in `manifest.json`:

| ID | Paper | Included sections |
| --- | --- | --- |
| `amem` | [A-Mem: Agentic Memory for LLM Agents](https://arxiv.org/html/2502.12110v11) | Methodology; limitations |
| `mem0` | [Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory](https://arxiv.org/html/2504.19413v1) | Proposed methods; conclusion and future work |
| `longmemeval` | [LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory](https://arxiv.org/html/2410.10813v2) | Related work; LongMemEval benchmark |

From `backend/`, run `uv run python scripts/prepare_papers.py` to populate this
directory. The script extracts selected HTML paragraphs/headings, retains paper
titles and section labels, and records the original HTML's SHA-256. Each section
is cited as `paper:<paper_id>:<section_id>` and has a link to the original section.

These are selected text extracts, not complete papers. Equations, figures, and
tables may be incomplete. Consult the original versions for details. Text rights
remain with the respective authors and publishers. Generated extracts are for
local use and are ignored by Git; the manifest and preparation script are tracked.
The application performs no network fetching during paper search or reading.
