"""
Publish messages from a JSONL dump (as produced by `dump-dlq`) to a RabbitMQ
broker, using a single fixed routing key instead of each message's original
one.

Useful for replaying a captured dump (e.g. from prod) into staging to check
that a consumer handles it correctly, without touching the source queue or
routing to a production-like consumer.

Defaults to --dry-run (prints what would be sent, publishes nothing). Use
--send to actually publish.
"""

import json
import logging

import typer

from rmq.publisher import RabbitMQPublisher

logger = logging.getLogger("rmq")


def _load_body(payload: dict) -> bytes:
    if "json" in payload:
        return json.dumps(payload["json"]).encode("utf-8")
    if "text" in payload:
        return payload["text"].encode("utf-8")
    raise ValueError(f"Unsupported payload shape: {list(payload)}")


def main(
    amqp_url: str = typer.Option(
        ..., envvar="RABBITMQ_AMQP_URL", help="Destination AMQP URL, e.g. staging broker."
    ),
    exchange: str = typer.Option(..., help="Destination exchange to publish to."),
    routing_key: str = typer.Option(
        ..., help="Routing key to publish every message with (overrides each message's original)."
    ),
    input_file: str = typer.Option(..., help="JSONL dump produced by dump-dlq."),
    dry_run: bool = typer.Option(
        True, "--dry-run/--send", help="Preview without publishing. Use --send to actually publish."
    ),
    limit: int | None = typer.Option(None, min=1, help="Only publish the first N messages."),
) -> None:
    publisher = RabbitMQPublisher(url=amqp_url, exchange=exchange, logger=logger)

    mode = "DRY-RUN" if dry_run else "SEND"
    print(f"[{mode}] Publishing from '{input_file}' to exchange='{exchange}' routing_key='{routing_key}'")

    sent = 0
    with open(input_file, encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            if limit and i > limit:
                break
            record = json.loads(line)
            body = _load_body(record["payload"])
            print(f"  [{i}] original_routing_key={record.get('routing_key')!r} bytes={len(body)}")
            if not dry_run:
                publisher.publish(routing_key=routing_key, message=body)
            sent += 1

    verb = "would publish" if dry_run else "published"
    print(f"\n{verb} {sent} message(s) to exchange='{exchange}' with routing_key='{routing_key}'.")


if __name__ == "__main__":
    typer.run(main)
