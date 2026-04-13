# surfline-mcp

Minimal Python MCP server with one tool: `get_surf_forecast`.

It fetches both Surfline forecast endpoints:
- `conditions`
- `rating`

The spot is fixed by environment variable (`SURFLINE_SPOT_ID`) so this server is effectively single-spot.

## Setup

```bash
cd surfline-mcp
uv sync
```

## Run (stdio MCP server)

```bash
cd surfline-mcp
export SURFLINE_SPOT_ID=5842041f4e65fad6a7708852
uv run surfline-mcp
```

## Run via uvx (from GitHub)

```bash
export SURFLINE_SPOT_ID=5842041f4e65fad6a7708852
uvx --from git+https://github.com/ivoytov/surfline-mcp surfline-mcp
```

## Nanobot MCP config (uvx)

```json
{
  "tools": {
    "mcpServers": {
      "surfline": {
        "command": "uvx",
        "args": ["--from", "git+https://github.com/ivoytov/surfline-mcp", "surfline-mcp"],
        "env": {
          "SURFLINE_SPOT_ID": "5842041f4e65fad6a7708852"
        }
      }
    }
  }
}
```

## Tool

`get_surf_forecast(days=3)`

Returns:
- `spot_id`
- `days`
- `daily_forecast[]` with:
  - `forecastDay`
  - `dayToWatch`
  - `headline`
  - `observation`
  - `rating_summary.dominant_key`
  - `rating_summary.min_value`
  - `rating_summary.max_value`
  - `rating_summary.avg_value`
  - `rating_windows[]` as compact 3-hour snapshots:
    - `local_hour`
    - `key`
    - `value`
