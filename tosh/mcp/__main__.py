"""Allow running as python -m tosh.mcp.server"""
from .server import mcp

if __name__ == "__main__":
    mcp.run()
