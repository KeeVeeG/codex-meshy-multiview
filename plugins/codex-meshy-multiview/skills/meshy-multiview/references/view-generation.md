# Consistent views for Meshy

Use this reference when the user wants to turn a concept image into four views, generate a new concept and its views, or repair an inconsistent view set. It applies to any subject: creatures, characters, props, vehicles, machines, furniture, or other objects. Do not carry species, anatomy, materials, colors, or accessories from an unrelated example into the new subject.

## Choose the starting point

**Existing concept or reference:** inspect each supplied image. A local file must first be opened with `view_image`. Prefer the user's selected design. If a sheet contains multiple variations, identify the intended variation from the request and visible context. Ask only if the choice remains consequential and unresolved; do not combine alternatives into a new design. Multiple photographs should describe the same object.

**New concept:** use the built-in image generation tool to produce the requested subject and style first. A clear three-quarter concept can help establish volume, but preserve an explicitly requested composition. Inspect the generated concept and record its design before deriving views. Creating a concept is a separate image call, in addition to the four view calls. An additional user approval is not required when the user has already authorized this generation and the design is clear.

**Four finished views:** inspect them together. If they already satisfy the invariants below, use them directly. Do not regenerate good source images merely to follow a fixed sequence.

## Record the design before generating views

Write a compact subject-specific inventory in the working prompt:

| Property | What to preserve |
| --- | --- |
| Selected subject/variant | Exact design and reference image or location on a sheet |
| Silhouette and proportions | Relative lengths, widths, heights, masses, curves, and negative spaces |
| Components and counts | Limbs, wheels, horns, handles, panels, tools, fasteners, or other visible parts as applicable |
| Pose/configuration | Every articulated angle, stance, opening, bend, appendage position, and attachment orientation |
| Surface appearance | Palette, material regions, finish, texture style, and existing markings |
| Asymmetry | Subject-left/right features, offsets, wear, patterns, and unequal parts |
| Attachments | Placement, scale, connections, and whether a component belongs to the selected variant |
| Style | The reference's level of realism, stylization, and shape language |
| Unknown surfaces | Hidden areas and the least-assumptive continuation supported by visible geometry |

Do not introduce conspicuous new mechanisms, limbs, ornament, color blocks, or markings on unseen sides. Continue existing forms and materials conservatively. If an unknown side determines a major feature, obtain the missing design decision or reference before finalizing it. Say when a hidden surface is inferred; a generated turnaround is not a measured reconstruction.

## Establish one coordinate convention

- Front is the object's functional/characteristic front or the front explicitly designated by the user. Resolve a genuinely ambiguous front if it would alter the asset.
- Left view means the camera is on the **subject's left**, showing its left side. Right view means the camera is on the **subject's right**, showing its right side. These are not the viewer's left and right in a front image.
- Back is a 180° camera yaw from front. The left and right views are opposite 90° side views. Use a level orthographic camera with no elevation, roll, wide-angle distortion, or three-quarter angle.
- Change only the camera azimuth between views. Keep the object, all articulated parts, and its configuration fixed. Do not turn the head, spread limbs, move a tail, open doors, or reposition accessories to make a view prettier.
- Use one pixel-to-object scale and vertical alignment for the set. The subject's top and bottom should align across views. Choose a scale that allows the widest expected view to fit with at least 10% padding on every edge; do not independently enlarge a narrow view to fill its canvas.

## Reusable English prompt

Fill every bracketed field with observations or user instructions. Remove irrelevant fields. Use this prompt once per view. For the first front image, omit Image 2 and replace references to the accepted front with the selected original concept: establish the fixed pose, scale, alignment and background in this call. For subsequent views, the accepted front fixes these properties.

```text
Use case: stylized-concept
Asset type: one orthographic reference image for multi-view 3D reconstruction.

Primary request:
Create exactly ONE separate [FRONT / SUBJECT-LEFT / BACK / SUBJECT-RIGHT] view
of [SUBJECT AND SELECTED VARIANT], preserving the supplied design. Produce a
single image of this single object. This image will be one member of a set of
four views; do not put the other views in this image.

Input images and roles:
- Image 1: the original concept/reference. It defines identity, geometry,
  design details, palette, materials, and style.
- Image 2, when supplied: the accepted front view. It fixes the final
  proportions, pose, image scale, vertical alignment, and background for the
  view set. Match it without copying its camera angle.
- [Any additional supplied reference: identify its exact role and which
  visible design details it establishes.]

Design inventory to preserve:
- Subject and variant: [SPECIFIC SUBJECT AND VARIANT].
- Silhouette and proportions: [OBSERVED SHAPE AND RELATIVE DIMENSIONS].
- Components and exact counts: [PARTS AND COUNTS RELEVANT TO THIS SUBJECT].
- Fixed pose/configuration: [STANCE, ARTICULATED ANGLES, OPEN/CLOSED STATES,
  APPENDAGE POSITIONS, AND ATTACHMENT ORIENTATIONS].
- Materials and color regions: [OBSERVED MATERIALS, COLORS, AND FINISHES].
- Existing markings and details: [PATTERN PLACEMENT AND DISTINCTIVE FEATURES].
- Subject-left/right asymmetry: [SIDE-SPECIFIC FEATURES, OR NO VISIBLE
  ASYMMETRY IF THAT IS WHAT THE REFERENCE ESTABLISHES].
- Attachments: [WHAT IS ATTACHED, WHERE, AND HOW].
- Style/medium: [REFERENCE STYLE, WITHOUT REDESIGNING THE SUBJECT].
- Unseen surfaces: [CONSERVATIVE CONTINUATION SUPPORTED BY THE REFERENCE;
  NO PROMINENT INVENTED FEATURES].

Camera:
[INSERT THE VIEW-SPECIFIC CAMERA SENTENCE BELOW.]
Use strict orthographic projection, level camera, zero camera roll, and no
perspective or foreshortening. Preserve natural overlap and occlusion of
parts in this view; do not move them to reveal hidden components. Only the
camera azimuth changes. The subject and every articulated part remain in
the exact same pose and configuration as the accepted front view.

Framing and background:
Request a square 2048 by 2048 image. Show the entire subject, including all
protrusions, with at least 10 percent empty padding on each edge. Use the
same object scale, vertical alignment, top/bottom positions, and canvas
composition as the accepted front view. Account for the widest view when
choosing the initial scale; do not enlarge a narrower view independently.
Use a uniform neutral light-gray background, no horizon line, no scenery,
and no display stand or pedestal. Use soft, even, neutral lighting that
keeps the materials legible without harsh cast shadows or color tint.

Constraints:
Preserve the subject's identity, silhouette, part counts, proportions,
materials, color placement, markings, asymmetries, attachments, and pose.
Continue unseen forms and surfaces conservatively. Do not add a prominent
new design feature. Do not mirror one side to fabricate the other side.
Do not beautify, simplify, restyle, or redesign the object.

Avoid:
Multiple views, contact sheets, collages, split panels, extra objects,
duplicates, labels, captions, dimension lines, arrows, watermarks, added
text, stands, cropping, missing parts, new accessories, perspective,
three-quarter angles, changing pose, and inconsistent scale. Preserve any
marking that is an actual established part of the object; add no new text.
```

Choose the most appropriate imagegen use-case slug for the subject if it is not stylized concept art, such as `product-mockup` for a photographic product reference. This is prompt guidance, not a tool parameter.

View-specific camera sentences:

| Output | Sentence |
| --- | --- |
| Front | The camera faces the subject's designated front directly, with its forward-facing surface centered and no visible three-quarter turn. |
| Left | The camera is exactly on the subject's own left side, 90 degrees from the front, showing its true left profile. Preserve subject-left details on their correct side. |
| Back | The camera faces the subject's back directly, 180 degrees from the front. Preserve the same fixed pose and the correct continuation of visible forms and markings. |
| Right | The camera is exactly on the subject's own right side, opposite the left camera and 90 degrees from the front, showing its true right profile. Preserve subject-right details on their correct side. |

## Execute with the image generation tool

1. Generate the front from the original concept and inspect it. If necessary, correct it before using it as the reference for the other views. Here, an "accepted" front means visually checked and consistent with the user's request, unless the user explicitly asked to approve it themselves.
2. Generate the left, back, and right in three separate calls. Include the original concept and accepted front in each call; include another supplied reference only when it adds relevant information. Do not request all four views in one image or assume the tool will emit multiple independent files in one call.
3. Follow the current tool schema. When all reference images have local paths, use `referenced_image_paths` after inspecting them. If any reference exists only in the conversation, use the smallest `num_last_images_to_include` that includes all intended references, up to the tool's limit. Never supply both reference mechanisms. Do not reference missing or unrelated images.
4. Request dimensions in the prompt; the built-in tool has no guaranteed exact-size or output-path parameter. Use its returned output files. Copy selected images to the requested destination after generation, retaining their real format and avoiding unintended overwrites. Suggested names are `front.png`, `left.png`, `back.png`, and `right.png` for actual PNG outputs; use `.jpg` for actual JPEG outputs.
5. Use the built-in tool for visual corrections by default. Do not silently switch to an API/CLI image generator or use programmatic mirroring, repainting, or other image editing to replace the requested generation workflow. Pure file copying and metadata inspection do not change image content.

## Visual QA before Meshy

Inspect each file and compare all four views against the original concept and design inventory. Check full framing, orthographic angle, same height and scale, fixed pose, part counts and connections, correct left/right asymmetry, palette, material boundaries, and markings. Check that different silhouettes are plausible projections of the same geometry rather than separate designs.

When a view fails, make a targeted correction that names the mismatch and repeats the invariants. Use the original concept, accepted front, and failed view as appropriate, with explicit reference roles. Recheck the corrected file. Stop after two unsuccessful repairs of the same view and explain the remaining issue; request a missing design decision or better source only when needed. Do not silently submit a visibly inconsistent set to the paid Meshy workflow.

Check actual file type, dimensions, and byte size. This plugin accepts local PNG/JPEG files or HTTPS image URLs, with a local cap of 20 MiB per file. The square 2048 × 2048 size is a generation request, not an API guarantee or a reason to fabricate file metadata. If a format or framing correction is needed, use the available image generation/editing workflow within the user's request.

Return four distinct final paths, their view assignments, and the prompt set used. Hand them to `meshy_start_multiview` by the named `front`, `back`, `left`, and `right` arguments; the integration makes front the first Meshy reference. Keep the accepted source concept and these reference images alongside the downloaded original and remeshed models.
