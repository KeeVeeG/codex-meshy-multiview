"""Exercise the actual MCP process rather than only Python tool wrappers."""

import os
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_stdio_handshake_and_doctor():
    async def check():
        environment = {
            key: value
            for key, value in os.environ.items()
            if key not in {"MESHY_API_KEY", "MESHY_API_KEY_FILE"}
        }
        # Empty values explicitly override the SDK's inherited environment subset.
        environment.update(MESHY_API_KEY="", MESHY_API_KEY_FILE="")
        server = StdioServerParameters(
            command=sys.executable, args=["-m", "meshy_codex.server"], env=environment
        )
        with anyio.fail_after(30):
            async with stdio_client(server) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    listing = await session.list_tools()
                    assert len(listing.tools) == 8
                    result = await session.call_tool("meshy_doctor", {})
                    assert not result.isError
                    assert result.structuredContent["api_key_configured"] is False

    anyio.run(check)
