# Changelog

## Unreleased

- Default to concept/reference sheets for new ImageGen references while supporting existing images, sheets, and explicit single-image requests.
- Select one design and variant across references, using detail and attachment studies without importing presentation elements into the model.
- Add subject-independent concept-sheet guidance and examples; concept-only requests stop before paid Meshy generation.
- Check proportions, component counts, connections, handedness, materials, and construction closeups before delivering a sheet or deriving the four final input images.
- Add a live-verified Survey Pod concept-sheet example (352,496 → 6,249 triangles) before the single-image utility robot example; both display the complete reference-to-model image sequence.

## 0.1.0

- Subject-independent concept and four-view preparation skill for Codex ImageGen.
- Meshy Multi-Image generation with PBR textures and separate Adaptive Low remesh.
- MCP and CLI interfaces, resumable local state, and uncertain-submission recovery.
- Downloads and GLB metadata inspection; mocked API tests and cross-platform CI.
