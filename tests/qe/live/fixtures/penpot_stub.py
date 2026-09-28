"""A stdio MCP server that answers to the name `penpot`, for the live tier.

It is named after the real design server so the roster's real capability matcher —
`mcp__penpot__*` in the default boundary and in role-guard's hook matcher — applies to
it without a fixture-only code path. Two tools, one of each kind a boundary tells
apart: a read (`read_board`) and an authoring call (`create_board`). Each answers with
a fixed sentence the oracle looks for in the transcript, so "the call ran" is
observable apart from "the model said it ran".
"""

from fastmcp import FastMCP

mcp = FastMCP("penpot")


@mcp.tool
def read_board(name: str) -> str:
    """Read a design board by name."""
    return f"board {name}: 3 frames"


@mcp.tool
def create_board(name: str) -> str:
    """Create a new design board."""
    return f"board {name} created"


if __name__ == "__main__":
    mcp.run(show_banner=False)
