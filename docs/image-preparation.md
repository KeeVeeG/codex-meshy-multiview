# Prepare a concept for Meshy Multi-View

The `meshy-multiview` skill generates a concept/reference sheet with ImageGen by default when creating a new initial reference. It also accepts one or more existing images or sheets and four finished views, and honors an explicit request for a single concept image or another format. It works with any subject and adapts the prompt to its shape, proportions, materials, colors, attachments, markings, and asymmetries.

## Choose a starting reference

| Format | Purpose |
| --- | --- |
| Concept/reference sheet (default for new ImageGen references) | Combine useful views, material or construction close-ups, and attachment studies for one design. Include alternative variants only when requested. |
| Single concept image | Establish the overall design in one image when explicitly requested or already supplied. |
| Turnaround/model sheet | Show the same design in a fixed pose from several directions to explain its three-dimensional form. |

These names overlap in practice. A sheet with overview views, detail studies, a scale silhouette, and an alternate effect state is a concept/reference sheet; it may also contain a turnaround. For a new ImageGen reference, start with a sheet unless the user requests another format. Supplied references can proceed directly without creating an additional sheet. Let the sheet's layout follow the subject rather than a fixed panel count.

Supply existing references or describe the subject, style, and desired format for ImageGen. A request to create a concept or sheet alone stops at that artifact; it does not authorize Meshy generation or remesh.

Example concept-sheet prompt:

```text
Create a concept/reference sheet for [subject] in [visual style], using
[existing references or design brief] as the source of truth.

Show one coherent design from useful angles so its silhouette, proportions,
materials, colors, and construction are clear. Add only the close-ups needed
to explain distinctive details and how parts connect. Keep repeated views
consistent; do not redesign the subject between panels.

Use a clear layout and neutral lighting. Include alternative variants or
effect states only if requested, and distinguish them from the main design.
Keep detail studies, detached-part studies, and any requested scale reference
visually separate from the complete subject.

This is a design reference sheet. The four separate orthographic images for
Meshy will be prepared from the selected design in a later step.
```

## Select one design and variant

Inspect all supplied images and panels before preparing the final views. Identify the main subject, full-object views, details, attachments, optional variants, and any conflicting design information. Follow the user's selected version. If multiple plausible designs or variants remain and the choice materially changes the model, clarify that choice instead of blending them.

Treat close-ups as evidence about the corresponding parts, not extra geometry. Detached accessory studies explain construction and attachment; scale figures, panel labels, borders, and background objects are presentation elements. They do not become parts of the model. Keep optional effects, alternate equipment, and alternate colorways confined to the selected variant.

The concept sheet can remain a multi-panel image. Prepare four clean full-object files from it for Meshy; a labeled board or a crop containing a detail study is not a finished view.

Check the sheet itself before delivering it or deriving those files. Within each intended variant, full-object panels and closeups must describe the same proportions, part counts, connections, side-specific details, colors, and configuration, accounting for projection and natural occlusion. Preserve deliberate differences between requested variants. Correct consequential contradictions in the sheet and inspect the result again after each edit. Stop after two unsuccessful sheet repairs rather than carrying an unresolved contradiction into the final views.

Example request for the complete workflow:

> Use $meshy-multiview with these references. Use the main design in its standard, inactive state. Prepare four separate orthographic images: front, the subject's left side, back, and the subject's right side. Preserve the design, fixed pose, and scale. Then generate a textured Meshy model and a separate Adaptive Low remesh, and save the reference images and both models in my chosen output folder.

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

The MCP/CLI generation step accepts exactly four local `.png`, `.jpg`, or `.jpeg` files or HTTPS image URLs. Local files are capped at 20 MiB each by this integration; that cap is not presented as an official Meshy API limit. These final images must contain one subject from distinct views. Codex saves the accepted imagegen outputs in your workspace with their actual format and reports the four paths.

Before spending Meshy credits, Codex inspects the set and corrects visible inconsistencies. If a view still fails after two targeted repair attempts, it reports the specific issue rather than retrying indefinitely or submitting incompatible images.

The API sequence is `meshy_doctor` → `meshy_plan_multiview` → `meshy_start_multiview` → repeated `meshy_advance_workflow` calls → `meshy_download_workflow`. Each advance call polls once and can submit remesh after generation succeeds. Keep the returned `run_dir` to resume instead of starting another paid task.

By default, the four views guide both geometry and textures. An optional `texture_prompt` is for a deliberate text-based texture direction; omit it to keep multi-view texture guidance. The original textured GLB is preserved, and a separate Adaptive Low triangle remesh uses `decimation_mode: 4`. Adaptive Low chooses density based on the model and does not guarantee an exact polygon count.

Configure `MESHY_API_KEY` locally through the plugin setup workflow. Do not paste it into chat. The built-in imagegen tool does not require you to configure an OpenAI API key.

See [concept-sheets.md](../plugins/codex-meshy-multiview/skills/meshy-multiview/references/concept-sheets.md) for source preparation and selection, and [view-generation.md](../plugins/codex-meshy-multiview/skills/meshy-multiview/references/view-generation.md) for the four-view prompt and QA procedure. The discoverable entry point is [SKILL.md](../plugins/codex-meshy-multiview/skills/meshy-multiview/SKILL.md).
