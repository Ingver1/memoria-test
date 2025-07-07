"""memory_system.cli

Command‑line interface for **AI‑memory‑**.

This optional CLI interacts with the running API service via HTTP.  It
lives in the `cli` extra so production deployments can avoid pulling
interactive libraries.  When *rich* is missing we degrade to plain‑text
output.
"""
from __future__ import annotations

# ─────────────────────────────── stdlib imports ───────────────────────────────
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# ────────────────────────────── third-party imports ────────────────────────────
import httpx
import typer

# ---------------------------------------------------------------------------

# Optional rich import (colourful tables & pretty JSON)

# ---------------------------------------------------------------------------

try:
    from rich import print as rprint
    from rich.panel import Panel
    from rich.table import Table
except ModuleNotFoundError:  # rich not installed -> degrade gracefully
    def rprint(*args: Any, **kwargs: Any) -> None:  # fallback printer
        if not os.environ.get("AI_MEM_RICH_WARNING_SHOWN"):
            print(
                "[hint] Install extras for colours:  pip install ai-memory[cli]",
                file=sys.stderr,
            )
            os.environ["AI_MEM_RICH_WARNING_SHOWN"] = "1"
        print(*args, **kwargs)

    class Panel:  # type: ignore[too-few-public-methods]
        """Minimal shim so code stays import-safe without *rich*."""

        def __init__(self, renderable: str, **_: Any) -> None:  # noqa: D401
            self.renderable = renderable

        def __str__(self) -> str:  # noqa: D401
            return self.renderable

    class Table:  # type: ignore[too-few-public-methods]
        """Plain ASCII table shim used when *rich* is missing."""

        def __init__(self, title: str | None = None, **_: Any) -> None:  # noqa: D401
            self.title = title or ""
            self.rows: list[list[str]] = []

        def add_column(self, *_: Any, **__: Any) -> None:  # noqa: D401
            return None

        def add_row(self, *values: str) -> None:  # noqa: D401
            self.rows.append(list(values))

        def __str__(self) -> str:  # noqa: D401
            head = [self.title] if self.title else []
            lines = [" | ".join(r) for r in self.rows]
            return "\n".join(head + lines)

# ---------------------------------------------------------------------------

# Typer application

# ---------------------------------------------------------------------------

app = typer.Typer(
name="ai-mem",
help="Interact with an AI-memory- server via REST API.",
)

API_URL_ENV = "AI_MEM_API_URL"
DEFAULT_API = "[http://localhost:8000](http://localhost:8000)"

# ---------------------------------------------------------------------------

# Helper utilities

# ---------------------------------------------------------------------------

async def _client(base_url: str) -> httpx.AsyncClient:  # noqa: D401
    """Return shared httpx client with reasonable timeout."""
    return httpx.AsyncClient(base_url=base_url, timeout=30.0)
    
def _metadata_option(
    _ctx: typer.Context,
    _param: typer.CallbackParam,
    value: str | None,
) -> Optional[dict[str, Any]]:
    """Parse `--metadata` JSON string into dict."""
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise typer.BadParameter(f"Invalid JSON: {exc}") from exc

# ---------------------------------------------------------------------------

# Commands

# ---------------------------------------------------------------------------

@app.command()
def add(
text: str = typer.Argument(..., help="Text to remember."),
importance: float = typer.Option(0.5, help="0-1 importance weighting."),
metadata: str | None = typer.Option(
None,
"--metadata",
callback=_metadata_option,
help="Arbitrary JSON metadata.",
),
url: str = typer.Option(
os.getenv(API_URL_ENV, DEFAULT_API),
"--url",
show_default="env/localhost",
),
) -> None:  # noqa: D401
    """Add a new memory row to the store."""


async def _run() -> None:  # helper to allow ``asyncio.run()``
    async with _client(url) as client:
        payload = {"text": text, "importance": importance, "metadata": metadata or {}}
        rprint(f"[grey]POST {url}/memory/add …")
        resp = await client.post("/memory/add", json=payload)
        resp.raise_for_status()
        rprint(Panel("Memory ID → [bold green]" + resp.json()["id"]))

asyncio.run(_run())


@app.command()
def search(
query: str = typer.Argument(..., help="Search query."),
k: int = typer.Option(5, help="Number of results."),
url: str = typer.Option(
os.getenv(API_URL_ENV, DEFAULT_API),
"--url",
show_default="env/localhost",
),
) -> None:  # noqa: D401
    """Semantic search in the memory vector store."""


async def _run() -> None:
    async with _client(url) as client:
        params = {"q": query, "k": k}
        rprint(f"[grey]GET {url}/memory/search?q={query}&k={k} …")
        resp = await client.get("/memory/search", params=params)
        resp.raise_for_status()
        results = resp.json()

        table = Table(title=f"Top-{k} results for '{query}'")
        table.add_column("Score", justify="right")
        table.add_column("Text", justify="left")

        for row in results:
            text_snip = row["text"][:80] + ("…" if len(row["text"]) > 80 else "")
            table.add_row(f"{row['score']:.2f}", text_snip)

        rprint(table)

asyncio.run(_run())


@app.command()
def delete(
mem_id: str = typer.Argument(..., help="Memory ID to delete."),
url: str = typer.Option(
os.getenv(API_URL_ENV, DEFAULT_API),
"--url",
show_default="env/localhost",
),
) -> None:  # noqa: D401
    """Delete a memory by ID."""


async def _run() -> None:
    async with _client(url) as client:
        rprint(f"[grey]DELETE {url}/memory/{mem_id} …")
        resp = await client.delete(f"/memory/{mem_id}")
        resp.raise_for_status()
        rprint(Panel("Deleted ✔", style="bold red"))

asyncio.run(_run())


@app.command()
def import_json(
file: Path = typer.Argument(
..., exists=True, readable=True, help="JSONL file (one memory per line)."
),
url: str = typer.Option(
os.getenv(API_URL_ENV, DEFAULT_API),
"--url",
show_default="env/localhost",
),
) -> None:  # noqa: D401
    """Bulk‑import memories from a .jsonl file."""


async def _run() -> None:
    async with _client(url) as client:
        added = 0
        async with asyncio.Semaphore(8):
            for line in file.read_text().splitlines():
                if not line.strip():
                    continue
                payload = json.loads(line)
                resp = await client.post("/memory/add", json=payload)
                resp.raise_for_status()
                added += 1
        rprint(Panel(f"Imported [bold green]{added}[/] memories"))

asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover
    app()  # Typer dispatch
