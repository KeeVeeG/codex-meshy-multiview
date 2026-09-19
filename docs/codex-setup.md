# Codex setup

## Plugin: tools and image-preparation skill

From a clone of this repository:

```sh
uv tool install .
codex plugin marketplace add .
codex plugin add codex-meshy-multiview@meshy-tools
```

The repository's `.agents/plugins/marketplace.json` exposes the plugin under `plugins/codex-meshy-multiview`. The plugin launches the locally installed Python runtime with `uv tool run --offline --from codex-meshy-multiview codex-meshy-multiview-mcp`. Install the runtime before enabling the plugin. Ensure `uv` is on the PATH used by Codex.

Configure `MESHY_API_KEY` or `MESHY_API_KEY_FILE` before launching Codex, then start a new task. A key file must contain only your key, be readable only by your user, and remain outside the repository. `meshy_doctor` reports configuration presence without showing the key or using network access.

For Windows desktop launches, set a user-level variable pointing to the private file:

```powershell
[Environment]::SetEnvironmentVariable('MESHY_API_KEY_FILE', 'C:\private\meshy-api.key', 'User')
```

Replace the example path with the actual file location and fully restart Codex. The command does not create the file. On macOS/Linux, launch Codex from an environment with `MESHY_API_KEY_FILE` exported, or configure the corresponding environment setting in your MCP client. Never put the actual key in a prompt or committed MCP configuration.

## MCP only

To register the server without the skill/plugin:

```sh
codex mcp add meshy -- uv tool run --offline --from codex-meshy-multiview codex-meshy-multiview-mcp
```

Use either the plugin or direct registration to avoid duplicate tool sets. Any client supporting stdio MCP can launch the same command.

## Updates

Pull the new revision, then run `uv tool install --reinstall .`. Reinstall the plugin from `meshy-tools` when its version or skills change, and start a new task. Runtime and plugin versions should match.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Runtime unavailable | Run `uv tool install .` and check `uv` is on PATH. |
| Doctor reports no key | Check the environment seen by Codex and restart the app. |
| HTTP 401 / 402 | Check the API key / API credit balance in Meshy. |
| `submission_uncertain` | Recover the existing task ID; do not repeat the paid submission. |
| Download URL expired | Run `download` to refresh URLs while Meshy still retains the task. |
| ImageGen unavailable | Supply four prepared PNG/JPEG images or enable image generation. |

Official references: [Codex MCP](https://developers.openai.com/codex/mcp), [Codex plugins](https://developers.openai.com/plugins/build/plugins).
