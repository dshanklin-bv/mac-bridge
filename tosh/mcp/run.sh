#!/bin/bash
# Wrapper to run tosh MCP server from correct directory
cd /Users/dshanklinbv/repos-personal/mac-bridge
exec python3 -m tosh.mcp.server
