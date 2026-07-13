# Nimblist — Home Assistant integration

[![Validate](https://github.com/tmnrtn/nimblist-homeassistant/actions/workflows/validate.yml/badge.svg)](https://github.com/tmnrtn/nimblist-homeassistant/actions/workflows/validate.yml)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)

Expose your [Nimblist](https://nimblist.app) shopping lists as Home Assistant
**`todo`** entities — view and edit them from dashboards, automations, scripts,
and voice assistants (Assist / Alexa / Google via Home Assistant).

## Features

- Each (non-template) Nimblist shopping list becomes its own `todo` entity.
- **Add, rename, check/uncheck, and delete** items — synced straight to Nimblist.
- Item quantity maps to the to-do item's description.
- Your household **pantry** appears as a stock `todo` entity (`todo.pantry`) plus a
  **"Pantry expiring soon"** `sensor` (see below).
- Polls the Nimblist API (`cloud_polling`); the update interval is configurable.
- Works against the hosted app **or a self-hosted instance** (the server URL is configurable).

## Pantry

Alongside your shopping lists, the integration exposes your household pantry:

- **`todo.pantry`** — a stock-style entity for managing pantry items from Home Assistant.
  Add, rename, update the quantity (free text, e.g. `1kg` / `2 packs` → the item
  description), and remove items. Pantry items are *stock*, not a checklist, so they
  don't get checked off. Each item's estimated use-by shows as the to-do item's `due` date.
- **`sensor.pantry_expiring_soon`** — the count of pantry items whose estimated use-by
  falls within a configurable window (default **7 days**; change it under *Configure*).
  The individual items are exposed as the sensor's `items` attribute, which powers the
  headline automation: *notify me when something nears its use-by.*

> **Use-by dates are estimates, not food-safety advice.** `EstimatedUseBy` is derived
> from when an item was added plus a typical storage time (from the embedded USDA
> FoodKeeper dataset). Treat it as a rough planning aid — always use your own judgement
> about whether food is safe to eat.

## Installation

### HACS (recommended)

1. In Home Assistant, go to **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/tmnrtn/nimblist-homeassistant` with category **Integration**.
3. Install **Nimblist**, then **restart Home Assistant**.

### Manual

Copy `custom_components/nimblist/` into your Home Assistant `config/custom_components/`
directory and restart Home Assistant.

## Configuration

1. First, create an API token: in the Nimblist web app go to **Settings → API tokens**,
   create one, and copy it (it's shown only once). This works for **every** account type,
   including Google/Facebook/Microsoft sign-ins — no password is stored in Home Assistant.
2. In Home Assistant: **Settings → Devices & Services → Add Integration → Nimblist**.
3. Enter your **server URL** (default `https://nimblist.app`; use your own URL if self-hosting)
   and the **API token**.

That's it — you'll get one `todo` entity per active shopping list. Options (cog → *Configure*)
let you change the update interval. If a token is ever revoked, Home Assistant prompts you to
re-authenticate with a new one.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

The component lives in `custom_components/nimblist/`.

> This repository is **published automatically** from the Nimblist monorepo; open issues
> here, but code changes are made upstream.

## License

[MIT](LICENSE)
