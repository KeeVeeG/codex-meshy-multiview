# Security and data handling

The client reads `MESHY_API_KEY` or `MESHY_API_KEY_FILE` at runtime. It does not save the key in workflow state, print it, or put it in MCP arguments. Prefer a restricted private key file for desktop use. The project does not provide encrypted credential storage.

Meshy receives the four images and an optional texture prompt when generation starts. Local images are encoded in memory, not uploaded to a separate image host. Network access is required for Meshy calls and returned assets. Credentialed API requests use the fixed `https://api.meshy.ai` origin. Asset downloads use a separate unauthenticated request and generated local filenames.

Run state contains signed download URLs, task identifiers, and API responses. Keep it private and outside Git. An absolute output directory is recommended. The local input size cap of 20 MiB per image is an implementation limit, not a claimed Meshy API limit.

Submissions are billed by Meshy. Intent is saved before sending a POST; uncertain outcomes require attaching the existing task ID. Local locking prevents simultaneous advancement of the same run, but starting a second run creates another paid task.

Report security concerns privately to the repository owner. Do not include secrets or private assets in an issue. Rotate any accidentally disclosed API key through Meshy.
