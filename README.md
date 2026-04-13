# surfline-mcp

Minimal Python MCP server with one tool: `get_surf_forecast`.

It fetches both Surfline forecast endpoints:
- `conditions`
- `rating`

The spot is fixed by environment variable (`SURFLINE_SPOT_ID`) so this server is effectively single-spot.

## Setup

```bash
cd surfline-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run (stdio MCP server)

```bash
cd surfline-mcp
source .venv/bin/activate
export SURFLINE_SPOT_ID=5842041f4e65fad6a7708852
python server.py
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
