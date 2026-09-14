# rmq

RabbitMQ inspection and maintenance scripts, exposed as a single `rmq` command.

## Install

From the workspace root:

```sh
uv sync
```

## Usage

```sh
uv run rmq --help
```

### Commands

| Command | Description |
|---|---|
| `rmq consume` | Consume messages from a queue to inspect serialization. |
| `rmq create-exchange` | Create a durable exchange. |
| `rmq dump-dlq` | Read a queue (e.g. a DLQ) in batches to JSONL without acking. |
| `rmq purge-dlq` | Drop DLQ messages that originated from a given source queue. |
| `rmq publish-dump` | Publish messages from a dump-dlq JSONL file to a broker with a fixed routing key. |
| `rmq helper` | Minimal RabbitMQ CLI for local dev (subcommands below). |

### `rmq helper` subcommands

| Command | Description |
|---|---|
| `rmq helper launch` | Launch a local RabbitMQ (Docker) with management UI. |
| `rmq helper init` | Declare a durable exchange + queue and bind them (idempotent). |
| `rmq helper create-exchange` | Declare a durable exchange (default: topic). |
| `rmq helper create-queue` | Declare a durable queue. |
| `rmq helper bind` | Bind a queue to an exchange with a routing key. |
| `rmq helper push` | Publish a message with publisher confirms. |
| `rmq helper status` | Connect and check exchange/queue exist; optional routability test. |

Pass `--help` to any command for its options, e.g.:

```sh
uv run rmq dump-dlq --help
uv run rmq helper push --help
```

### Configuration

Connection details come from flags or from `RABBITMQ_AMQP_URL`, `RABBITMQ_EXCHANGE`,
and `RABBITMQ_ROUTING_KEY`. See the [environment variable reference](../../README.md#environment-variables)
in the root README for defaults and which commands read which.
