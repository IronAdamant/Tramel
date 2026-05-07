# Grok Connectors / BYO MCP Support

This project is ready for Grok Connectors (Bring Your Own MCP) and Grok Build.

The MCP server is designed to work with any MCP-compatible client, including future Grok Build local agents and remote MCP connections in Grok.

## For Grok Connectors (BYO MCP)

When Grok supports adding custom MCP servers:

1. Start the server locally (example for this project):
   ```bash
   python -m trammel.mcp_server --port 8737
   ```
   Or use stdio mode for local agents if available.

2. For remote access from Grok, expose the HTTP endpoint over HTTPS using a secure tunnel (e.g., Cloudflare Tunnel, ngrok).

3. Add to Grok Connectors / remote MCP config:
   - **server_url**: `https://your-https-tunnel/mcp` (or the specific MCP endpoint)
   - **server_label**: `trammel`
   - **server_description**: "Planning and execution harness for LLM-assisted coding: dependency-aware decomposition, beam strategy, verification, and recipe memory"

The server implements MCP tools for planning, task management, and verification. Grok will discover the tools automatically.

## For Grok Build (Local)

Once Grok Build is available:
- Use the MCP server alongside Grok Build agents for systematic planning, verification, and safe execution of complex refactors and rebuilds.
- The project provides dependency-aware task graphs and incremental verification that integrate naturally with autonomous agent workflows.

No changes to your existing workflows are required. This project was built to be backend-agnostic and work with any LLM/IDE/CLI via MCP.

See README.md for full setup.

For questions or to contribute Grok-specific adapters, open an issue.