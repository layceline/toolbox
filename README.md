# toolbox

Ad-hoc operational tooling: a RabbitMQ inspection CLI, an OAuth2 token helper, and a
Postgres dump/restore script. Nothing here is tied to a particular company or
environment — every broker URL, exchange, endpoint, and config path is supplied by you
via flags or environment variables.

## Install

Requires [uv](https://docs.astral.sh/uv/) and Python >= 3.14. From the repo root:

```sh
uv sync
```

That installs the workspace packages (`packages/rmq`, `packages/authpy`) into `.venv`
and puts the `rmq` and `authpy` entry points on the path. Prefix commands with
`uv run`, or activate the venv (`source .venv/bin/activate`) and call them directly.

To get the `rmq`/`authpy` commands on your `PATH` globally (no `uv run`, no venv
activation), install each package as a `uv` tool with `-e`. That links the tool
environment straight to this checkout, so `git pull` is enough to pick up changes —
no reinstall needed:

```sh
uv tool install -e ./packages/rmq
uv tool install -e ./packages/authpy
```

## CLIs

### `rmq` — RabbitMQ inspection and maintenance

```sh
uv run rmq --help
```

| Command | Description |
|---|---|
| `rmq consume` | Bind a temporary exclusive queue to an exchange and print each message (routing key, headers, JSON body). |
| `rmq create-exchange` | Declare a durable exchange. |
| `rmq dump-dlq` | Read a queue (e.g. a DLQ) in batches to JSONL. Leaves the queue untouched by default; `--replay` republishes each message to the queue it was dead-lettered from and removes it from the DLQ. |
| `rmq purge-dlq` | Drop DLQ messages whose `x-death` header names a given source queue. Defaults to `--dry-run`; pass `--apply` to actually delete. |
| `rmq publish-dump` | Publish messages from a `dump-dlq` JSONL file to a broker/exchange, all under one fixed routing key. Defaults to `--dry-run`; pass `--send` to actually publish. |
| `rmq helper` | Local-dev helpers (subcommands below). |

`rmq helper` subcommands:

| Command | Description |
|---|---|
| `rmq helper launch` | Start a local RabbitMQ in Docker (`rabbitmq:3.13-management`, ports 5672/15672, auto-removed on stop). |
| `rmq helper init` | Declare a durable exchange + queue and bind them. Idempotent. |
| `rmq helper create-exchange` | Declare a durable exchange (default type: topic). |
| `rmq helper create-queue` | Declare a durable queue. |
| `rmq helper bind` | Bind a queue to an exchange with a routing key. |
| `rmq helper push` | Publish a message with publisher confirms (persistent, `application/json`). |
| `rmq helper status` | Connect and passively check an exchange (and optionally a queue) exists; optional routability test. |

Pass `--help` to any command for its full options:

```sh
uv run rmq dump-dlq --help
uv run rmq helper push --help
```

A local round-trip:

```sh
export RABBITMQ_AMQP_URL=amqp://guest:guest@localhost:5672/
uv run rmq helper launch
uv run rmq helper init --exchange events --queue status --routing-key '#'
uv run rmq helper push --routing-key v1.thing.happened --body '{"hello":"world"}'
uv run rmq consume --exchange events
```

### `authpy` — OAuth2 client-credentials tokens

Fetches an access token via the `client_credentials` grant and prints it to stdout, so
it composes into other commands. Tokens are cached on disk and reused until they
expire.

This CLI has a single command, so there is **no subcommand** — options go directly on
`authpy`:

```sh
uv run authpy --help
uv run authpy --profile prod --scopes read:company,write:admin
curl -H "Authorization: Bearer $(uv run authpy -s read:company)" https://api.example.com/companies
```

| Option | Default | Description |
|---|---|---|
| `--profile`, `-p` | `default` | Which profile to read from the credentials file. |
| `--scopes`, `-s` | *(none)* | Comma-separated scopes, without the resource prefix (e.g. `read:company,write:admin`). |
| `--resource`, `-r` | *(none)* | Resource server identifier prefixed to each scope as `<resource>/<scope>`. Omit to send scopes bare. |

Credentials live in `$AUTHPY_HOME/credentials.toml` (default `~/.authpy/credentials.toml`),
one table per profile. The file is created empty on first run:

```toml
[default]
client_id = "..."
client_secret = "..."
endpoint = "https://auth.example.com"   # token is POSTed to <endpoint>/oauth2/token

[prod]
client_id = "..."
client_secret = "..."
endpoint = "https://auth.prod.example.com"
```

Cached tokens are written to `$AUTHPY_HOME/cache.json`, keyed by profile and scope set.
Both files contain secrets — keep them out of version control.

### `db-export-import.sh` — Postgres dump / restore

Interactive `pg_dump` / `pg_restore` wrapper that remembers named connection strings.

```sh
./db-export-import.sh
```

Requires `gum`, `jq`, `pg_dump`/`pg_restore`, and `dbmate` (used to drop, recreate, and
migrate the target database on import). It offers to install `jq` for you; the others
must already be present.

- **export** writes `~/Downloads/dump-<name>-<timestamp>.dump` (custom format, no owner/ACL).
- **import** drops and recreates the target database, restores the dump, then runs
  `dbmate migrate`. It is **refused unless the connection string points at `localhost`
  or `0.0.0.0`**, so you cannot overwrite a remote database with it.

Connections are stored as JSON at `$DB_DUMP_CONFIG` (default
`~/.config/toolbox/db-dump.json`), created on first run. Pick `+ new connection` in the
prompt to add one, or write the file yourself:

```json
{
  "dbConnections": {
    "local": "postgresql://postgres:postgres@localhost:5432/app?sslmode=disable",
    "staging": "postgresql://user:pass@staging.example.com:5432/app"
  }
}
```

This file contains database passwords — it lives outside the repo by default, and
should stay that way.

## Environment variables

Every variable is optional in the sense that the corresponding flag can always be
passed instead; the table notes which ones have no default and must come from one
source or the other.

| Variable | Used by | Default | Description |
|---|---|---|---|
| `RABBITMQ_AMQP_URL` | every `rmq` command that connects to a broker, i.e. all but `helper launch` (equivalent to `--amqp-url`) | *none — required* | Broker URL, e.g. `amqp://guest:guest@localhost:5672/`. `rmq helper push`/`status` append `heartbeat=60` and `blocked_connection_timeout=120` if absent; the other commands pass the URL to pika as-is. `helper launch` takes no `--amqp-url` — it only echoes this value as a hint after starting the container. |
| `RABBITMQ_EXCHANGE` | `rmq consume`, `create-exchange`, `helper init`, `helper push`, `helper status` (equivalent to `--exchange`) | `events` | Exchange to publish to, bind to, or declare. `rmq helper bind` has no default and always needs `--exchange`. |
| `RABBITMQ_ROUTING_KEY` | `rmq helper push` (equivalent to `--routing-key`) | *none — required* | Routing key to publish under. |
| `AUTHPY_HOME` | `authpy` | `~/.authpy` | Directory holding `credentials.toml` and `cache.json`. |
| `AUTHPY_RESOURCE` | `authpy` (equivalent to `--resource`) | *(none)* | Resource server identifier prefixed to each requested scope. |
| `DB_DUMP_CONFIG` | `db-export-import.sh` | `~/.config/toolbox/db-dump.json` | Path to the saved-connections JSON file. |

Precedence is the usual one: an explicit flag beats the environment variable, which
beats the built-in default.

### `.env` files

`rmq` and `authpy` load a `.env` file through `python-dotenv`. Note that discovery
walks up from the **package source directory**, not your current working directory — in
this workspace that resolves to a `.env` at the repo root. A `.env` sitting in some
other directory you happen to `cd` into is *not* picked up, so prefer exported
variables when working outside the repo. `.env` is gitignored.

```sh
# <repo root>/.env
RABBITMQ_AMQP_URL=amqp://guest:guest@localhost:5672/
RABBITMQ_EXCHANGE=events
AUTHPY_RESOURCE=api.example.com
```

## Layout

```
packages/rmq/        # `rmq` CLI — pika only, no private dependencies
packages/authpy/     # `authpy` CLI — OAuth2 client-credentials via requests
db-export-import.sh  # Postgres dump/restore wrapper
```
