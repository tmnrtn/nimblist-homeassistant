# Nimblist — Home Assistant integration

Exposes your [Nimblist](https://nimblist.app) shopping lists as Home Assistant
**`todo`** entities, so you can view and edit them from dashboards, automations,
and voice assistants (Assist / Alexa / Google via Home Assistant).

> **Status: work in progress.** This is the scaffold (Phase 2 of `TRACKER.md`).
> The API client, config flow, coordinator, and `todo` platform land in the
> following phases.

## What it will do

- Each (non-template) Nimblist shopping list becomes a `todo` entity.
- Add items, rename them, check/uncheck, and delete — synced to Nimblist.
- Polls the Nimblist API (`cloud_polling`); interval configurable.

## Authentication

The integration authenticates with a **Nimblist API token** (sent as an
`X-Api-Key` header), which you create in the Nimblist web app under
**Settings → API tokens**. This works for every account type, including
Google/Facebook/Microsoft sign-ins. No password is stored in Home Assistant.

## Self-hosting

The server URL is configurable, so self-hosted Nimblist instances are supported
(default: `https://nimblist.app`).

## Development

```bash
cd integrations/homeassistant
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements_test.txt
pytest
```

The component lives in `custom_components/nimblist/`. For HACS, this directory is
mirrored to the public `nimblist-homeassistant` repository.
