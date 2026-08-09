"""Local HTTP application for the interactive memory graph viewer."""

from __future__ import annotations

from pathlib import Path

from datetime import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from thalamus.substrate.schema import SessionGraph
from thalamus.viewer.view_model import GraphView, NodeDetails, session_to_graph_view
from thalamus.viewer.view_query import (
    DEFAULT_OVERVIEW_LIMIT,
    DEFAULT_PER_PROJECT_SESSION_LIMIT,
    MAX_EXPANSION_EDGES,
    MAX_EXPANSION_NODES,
    expand_subgraph,
    persisted_node_details,
    persisted_overview,
)
from gremlin_python.process.graph_traversal import GraphTraversalSource

STATIC_DIR = Path(__file__).with_name("static")


class ExpansionRequest(BaseModel):
    """The bounded neighbor request made by the interactive explorer."""

    root_ids: list[str] = Field(min_length=1, max_length=25)
    direction: Literal["incoming", "outgoing", "both"] = "both"
    depth: Literal[1] = 1
    visible_node_ids: list[str] = Field(default_factory=list)
    visible_edge_ids: list[str] = Field(default_factory=list)
    node_limit: int = Field(default=MAX_EXPANSION_NODES, ge=1, le=MAX_EXPANSION_NODES)
    edge_limit: int = Field(default=MAX_EXPANSION_EDGES, ge=1, le=MAX_EXPANSION_EDGES)


def create_app(
    initial_session: SessionGraph | None = None,
    graph: GraphTraversalSource | None = None,
) -> FastAPI:
    """Create a localhost viewer application with an optional pending session."""
    app = FastAPI(
        title="Thalamus Viewer",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.current_preview = (
        session_to_graph_view(initial_session) if initial_session is not None else None
    )
    app.state.graph = graph

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/previews/current", response_model=GraphView)
    def current_preview() -> GraphView:
        preview: GraphView | None = app.state.current_preview
        if preview is None:
            raise HTTPException(status_code=404, detail="No session preview is loaded")
        return preview

    @app.post("/api/previews", response_model=GraphView)
    def create_preview(session: SessionGraph) -> GraphView:
        preview = session_to_graph_view(session)
        app.state.current_preview = preview
        return preview

    @app.get("/api/overview", response_model=GraphView)
    def overview(
        project: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        per_project_session_limit: int = Query(
            DEFAULT_PER_PROJECT_SESSION_LIMIT, ge=1, le=100
        ),
        total_limit: int = Query(DEFAULT_OVERVIEW_LIMIT, ge=1, le=500),
    ) -> GraphView:
        graph_source = _required_graph(app)
        return persisted_overview(
            graph_source,
            project=project,
            start=start,
            end=end,
            per_project_session_limit=per_project_session_limit,
            total_limit=total_limit,
        )

    @app.post("/api/subgraphs/expand", response_model=GraphView)
    def expand(request: ExpansionRequest) -> GraphView:
        graph_source = _required_graph(app)
        return expand_subgraph(
            graph_source,
            root_ids=request.root_ids,
            direction=request.direction,
            visible_node_ids=set(request.visible_node_ids),
            visible_edge_ids=set(request.visible_edge_ids),
            node_limit=request.node_limit,
            edge_limit=request.edge_limit,
        )

    @app.get("/api/nodes/{node_id:path}", response_model=NodeDetails)
    def node_details(node_id: str) -> NodeDetails:
        details = persisted_node_details(_required_graph(app), node_id)
        if details is None:
            raise HTTPException(status_code=404, detail=f"Persisted node not found: {node_id}")
        return details

    if (STATIC_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", response_class=HTMLResponse)
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        index = STATIC_DIR / "index.html"
        if index.is_file():
            return FileResponse(index)
        return HTMLResponse(
            """
            <!doctype html>
            <html><body>
              <h1>Thalamus viewer frontend is not built</h1>
              <p>Run <code>npm run build</code> in <code>frontend/</code>.</p>
            </body></html>
            """,
            status_code=503,
        )

    return app


def _required_graph(app: FastAPI) -> GraphTraversalSource:
    graph: GraphTraversalSource | None = app.state.graph
    if graph is None:
        raise HTTPException(
            status_code=503,
            detail="The persisted memory graph is unavailable in session-preview mode",
        )
    return graph
