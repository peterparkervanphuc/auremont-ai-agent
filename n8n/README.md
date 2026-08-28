# Auremont news automation

The workflow in `workflows/official-news-ingestion.json` is intentionally kept
outside the public request path. It polls only these verified publisher pages:

- `https://vinhomes.vn/vi/tin-tuc`
- `https://vingroup.net/vi/tin-tuc-su-kien/bat-dong-san/3`
- `https://market.vinhomes.vn/blog/chuyen-muc/tin-tuc`

It stores title, short description, image, publish date and the canonical source
URL. It never copies the article body and never writes to Documents or Qdrant.

The current business scope is intentionally restricted to **OCP1, OCP2 and
OCP3**. The workflow reads the five newest official Vinhomes Market news pages,
filters candidate URLs before downloading article metadata, and only sends an article
when its normalized title/summary/URL maps to at least one of:

- `Vinhomes Ocean Park` (OCP1)
- `Vinhomes Ocean Park 2` (OCP2)
- `Vinhomes Ocean Park 3` (OCP3)

`Ocean City` articles are tagged with all three projects. Expanding the project
scope requires an explicit update to the mapping in the `Normalise metadata`
node.

## Local setup

1. Set strong, identical `NEWS_INGESTION_KEY` and `N8N_ENCRYPTION_KEY` values in
   `.env`.
2. Start n8n with `docker compose --profile automation up -d n8n`.
3. Open `http://localhost:5678`, create the local owner account, and import
   `n8n/workflows/official-news-ingestion.json`.
4. Run the workflow manually once, inspect the output, then activate it.

The editor is bound to `127.0.0.1` in Compose; do not expose it directly on a
public domain. In production place it behind SSO/VPN and keep the backend
integration key in n8n's secret environment, never in the browser.

The Compose service enables environment access because the reviewed HTTP nodes
read `NEWS_INGESTION_KEY` from `$env`. Do not allow untrusted users to create or
edit workflows on this instance.

The main schedule runs every six hours. The retention branch archives news after
`NEWS_DEFAULT_TTL_DAYS` and permanently removes archived rows after
`NEWS_ARCHIVE_RETENTION_DAYS`.
