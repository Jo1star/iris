import asyncio
import os
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MCP_SERVER_PARAMS = StdioServerParameters(
    command="npx",
    args=["-y", "awesome-mineflayer-mcp"],
    env={**os.environ, "MCP_DISABLE_GROUPS": ""}
)

async def main():
    async with stdio_client(MCP_SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            for t in tools.tools:
                if t.name in ["connect_bot", "connect_default", "chat", "get_events", "wait_for_message"]:
                    print(f"\n=== {t.name} ===")
                    print(f"desc: {t.description}")
                    print(f"schema: {json.dumps(t.input_schema, indent=2, ensure_ascii=False)}")

asyncio.run(main())