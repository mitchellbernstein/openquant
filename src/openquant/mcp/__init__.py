"""MCP (Model Context Protocol) server for OpenQuant.

Only available when the 'mcp' optional dependency is installed.
"""

try:
    from openquant.mcp.server import create_server
except ImportError:
    pass
