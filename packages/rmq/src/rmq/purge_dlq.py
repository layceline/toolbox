"""
Purge messages from a DLQ that originated from a specific source queue.

Iterates the DLQ with basic_get, inspects each message's `x-death` header to
find the original queue, then:
- acks (drops) messages whose x-death records the given source queue, OR
- nacks with requeue=True for everything else, so the DLQ is left intact for
  other sources.

Defaults to --dry-run (no acks, everything requeued) so you can confirm the
match set before destructive action. Use --apply to actually drop.
"""

import pika
import typer


def _x_death_queues(headers: dict | None) -> list[str]:
    if not headers:
        return []
    x_death = headers.get("x-death") or []
    return [str(entry.get("queue", "")) for entry in x_death if isinstance(entry, dict)]


def main(
    amqp_url: str = typer.Option(
        ..., envvar="RABBITMQ_AMQP_URL", help="AMQP URL, e.g. amqp://guest:guest@localhost:5672/"
    ),
    dlq: str = typer.Option(..., help="Dead-letter queue to purge from."),
    source_queue: str = typer.Option(..., help="Match messages whose x-death records this original queue."),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--apply",
        help="Inspect without dropping. Use --apply to actually purge matching messages.",
    ),
    max_messages: int | None = typer.Option(
        None,
        "--max-messages",
        min=1,
        help="Stop after inspecting this many messages.",
    ),
) -> None:
    print(f"Connecting to {amqp_url}")
    connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
    channel = connection.channel()

    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"[{mode}] Scanning '{dlq}' for messages with x-death source='{source_queue}'")

    matched = 0
    fetched = 0
    requeue_tags: list[int] = []

    try:
        while True:
            method, properties, body = channel.basic_get(queue=dlq, auto_ack=False)
            if method is None:
                break
            fetched += 1

            queues = _x_death_queues(properties.headers)
            is_match = source_queue in queues

            marker = "match " if is_match else "skip  "
            print(f"  {marker} rk={method.routing_key}  x-death-queues={queues}")

            if is_match:
                matched += 1
                if dry_run:
                    requeue_tags.append(method.delivery_tag)
                else:
                    channel.basic_ack(delivery_tag=method.delivery_tag)
            else:
                requeue_tags.append(method.delivery_tag)

            if max_messages and fetched >= max_messages:
                break

        verb = "would drop" if dry_run else "dropped"
        print(f"\nFetched {fetched} messages; {verb} {matched}.")

        if requeue_tags:
            print(f"Requeueing {len(requeue_tags)} messages...")
            for tag in requeue_tags:
                channel.basic_nack(delivery_tag=tag, requeue=True)
    finally:
        connection.close()


if __name__ == "__main__":
    typer.run(main)
