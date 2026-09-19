---
name: meshy-multiview
description: Prepare four consistent object views from a new or existing concept, then generate a textured Meshy model and an Adaptive Low remesh through the Meshy API. Use for Meshy multi-view or four-view 3D asset workflows.
---

# Meshy Multi-View

Turn a concept or four reference views into a textured 3D asset, preserving the source model and a separate Adaptive Low remesh. Respect the user's requested starting point: creating this integration or preparing prompts alone does not request live image or Meshy generation.

## Prepare the views

When views need generation or correction, read [view-generation.md](references/view-generation.md). Use the available `imagegen` skill and built-in image generation tool by default; do not substitute a hand-drawn placeholder, mirrored image, collage, or unauthorized CLI fallback.

- Start with the user's existing concept/reference, or generate a concept when that is requested. Inspect local images with `view_image` before using them as references. Identify the selected variant, silhouette, proportions, component counts, materials, colors, markings, asymmetries, attachments, and pose. Clarify a mixed design sheet only when selecting the wrong variant would materially change the result.
- Produce four **separate** assets with four image generation calls: front first, then left, back, and right. Use the original concept plus the visually accepted front as references for the remaining views. The front may be accepted through your own visual QA; user confirmation is not automatically required.
- All views show the same object at a fixed pose and scale, with an orthographic camera, neutral gray background, full silhouette, and at least 10% edge padding. Left and right mean the subject's own left and right. Request square 2048 × 2048 output in the prompt, but verify and report actual dimensions rather than promising exact tool output.
- Inspect every output and compare the set. Correct a consequential inconsistency before Meshy submission. Limit repairs to two targeted attempts per problematic view; if it remains inconsistent, report the issue and request the missing design decision or better reference. Do not spend Meshy credits on a visibly inconsistent set.
- Copy accepted tool outputs into the user's workspace and retain their actual file formats. Report saved paths. Four suitable supplied views can proceed directly after inspection without regeneration.

## Run the API workflow

1. Call `meshy_doctor` to check configuration. Read only whether the key is available; never print it or ask for a key in chat. If missing, direct the user to configure `MESHY_API_KEY` locally using the plugin's setup instructions.
2. Call `meshy_plan_multiview` to validate `front`, `back`, `left`, `right`, and an absolute `output_dir`, then call `meshy_start_multiview` with those inputs. Inputs accept local PNG/JPEG files or HTTPS URLs. Each local file is capped at 20 MiB by this tool, not a documented Meshy API limit. Leave `texture_prompt` unset to guide textures with all four views; set it only for an intentional user-requested texturing direction.
3. Save the returned `run_dir` (the directory, not `workflow.json`). When `next_step` is `advance`, wait about 10 seconds, then call `meshy_advance_workflow(run_dir)`. Each call polls once and may submit remesh after generation succeeds. Stop on `failed` or `submission_failed`; recover an existing task ID on `submission_uncertain`. Preserve `run_dir` across interruptions.
4. When `next_step` is `download`, call `meshy_download_workflow(run_dir)`. At `complete`, report the original textured model, remeshed output, inspection counts and any warnings. Adaptive Low does not promise a particular face count.

The intended API settings are Meshy 7.1, textures enabled, original generation without remesh, then a separate triangle remesh with `decimation_mode: 4`. The tool passes the generated GLB URL to remesh because the public remesh `input_task_id` contract does not explicitly list multi-image tasks. Do not add a fixed `target_polycount` to adaptive mode.

Continue within the user's existing authorization; do not invent a blanket confirmation step for the requested workflow. Stop on missing inputs, unresolved design conflicts, or uncertain paid submission results. Recover existing tasks before considering a new submission. Download results promptly because Meshy API assets have limited retention.
