# Prepare a concept for Meshy Multi-View

The `meshy-multiview` skill works from an existing concept, a newly generated concept, or four finished views. It is not tied to a particular animal, character, or prop. The prompt is adapted to the actual subject's shape, proportions, materials, colors, attachments, markings, and asymmetries.

Example request to Codex:

> Use $meshy-multiview with this concept. Prepare four separate orthographic images: front, the subject's left side, back, and the subject's right side. Preserve the design, fixed pose, and scale. Then generate a textured Meshy model and a separate Adaptive Low remesh, and save the reference images and both models in my chosen output folder.

To start without a concept, describe the subject and its intended visual style and ask Codex to generate the concept first. To prepare images only, say so explicitly. No Meshy task is necessary for concept work or prompt preparation alone.

## What the four images should contain

- The same subject and selected design variant, including the same number of parts and their connections.
- Front, subject-left, back, and subject-right views as four independent image files, not a collage or contact sheet.
- A fixed pose: camera direction changes; limbs, appendages, openings, and accessories keep their positions.
- Orthographic projection, a square canvas, consistent object scale and vertical alignment, and at least 10% padding on every edge.
- A uniform neutral gray background and soft neutral lighting, without labels, scenery, or a display stand.
- Consistent materials, colors, patterns, and side-specific details. A left view is not a mirrored right view.

The skill asks imagegen for 2048 × 2048 square images and verifies the actual result. Exact dimensions are a prompt request rather than a guarantee of the built-in image tool. The front view is prepared and inspected first; the original concept and accepted front guide each remaining view. User approval is required only when you ask for it or a consequential design decision is missing.

If the original concept does not show a surface, Codex continues established forms and materials conservatively. It should flag an important unknown feature instead of inventing a prominent new design. A generated turnaround approximates the hidden surfaces; it is not a scan of the object.

## Files and handoff

The plugin accepts local `.png`, `.jpg`, or `.jpeg` files and HTTPS image URLs. Local files are capped at 20 MiB each by this integration; that cap is not presented as an official Meshy API limit. Images must contain one subject from distinct views. Codex saves the accepted imagegen outputs in your workspace with their actual format and reports the four paths.

Before spending Meshy credits, Codex inspects the set and corrects visible inconsistencies. If a view still fails after two targeted repair attempts, it reports the specific issue rather than retrying indefinitely or submitting incompatible images.

The API sequence is `meshy_doctor` → `meshy_plan_multiview` → `meshy_start_multiview` → repeated `meshy_advance_workflow` calls → `meshy_download_workflow`. Each advance call polls once and can submit remesh after generation succeeds. Keep the returned `run_dir` to resume instead of starting another paid task.

By default, the four views guide both geometry and textures. An optional `texture_prompt` is for a deliberate text-based texture direction; omit it to keep multi-view texture guidance. The original textured GLB is preserved, and a separate Adaptive Low triangle remesh uses `decimation_mode: 4`. Adaptive Low chooses density based on the model and does not guarantee an exact polygon count.

Configure `MESHY_API_KEY` locally through the plugin setup workflow. Do not paste it into chat. The built-in imagegen tool does not require you to configure an OpenAI API key.

The reusable prompt and QA procedure are in [view-generation.md](../plugins/codex-meshy-multiview/skills/meshy-multiview/references/view-generation.md). The discoverable entry point is [SKILL.md](../plugins/codex-meshy-multiview/skills/meshy-multiview/SKILL.md).
