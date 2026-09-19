# MCP tools

| Tool | Purpose | Side effects |
| --- | --- | --- |
| `meshy_doctor` | Check configuration without revealing credentials | None; no network |
| `meshy_plan_multiview` | Validate four inputs and preview settings | Reads inputs; no upload |
| `meshy_start_multiview` | Submit textured Multi-Image generation | Creates a local run and one paid task |
| `meshy_advance_workflow` | Poll once; submit remesh after generation succeeds | Updates state; may create one paid remesh |
| `meshy_workflow_status` | Read saved status | Local read only |
| `meshy_download_workflow` | Download both models and inspect GLBs | Reads API; writes assets and state |
| `meshy_recover_submission` | Attach an existing task ID after an uncertain submission | Reads API; updates state; no POST |
| `meshy_list_tasks` | Find recent generation/remesh tasks | API read only |

`start` and `plan` accept `front`, `back`, `left`, `right`, `output_dir`, and optional `texture_prompt`. Use absolute paths. Four-view texture guidance is the default; a texture prompt replaces it. Defaults: Meshy 7.1, standard geometry, 2K PBR textures, separate triangle remesh with adaptive level 4.

Keep the returned `run_dir` for subsequent calls. Wait about 10 seconds between `advance` calls; use CLI `run`/`resume` for automatic bounded polling.

| `next_step` | Client action |
| --- | --- |
| `advance` | Wait, then call `meshy_advance_workflow` |
| `download` | Call `meshy_download_workflow` |
| `complete` | Report local artifacts and validation warnings |
| `failed` / `submission_failed` | Report failure; no automatic new paid task |
| `submission_uncertain` | Find the accepted task and call recovery |

Downloads report counts for stored mesh primitives, not scene instances. Texture checks verify an embedded image referenced by a base-color material with UV coordinates. They do not replace visual inspection or guarantee that every surface is textured.
