"""
Read messages from a RabbitMQ queue (e.g. a DLQ) in batches without acking.

Pulls messages with basic_get, holding them unacked so the same messages are
not redelivered while the script runs. Writes batches of BATCH_SIZE messages
to a JSONL file and logs queue / routing-key / payload for each one.

By default, every fetched message is nack'd with requeue=True so the queue is
left untouched. With --replay, each message is instead republished to the
original queue it was dead-lettered from (read from its `x-death` header) and
then ack'd (removed) from the DLQ. Messages without a resolvable x-death queue
are left in the DLQ (nack'd with requeue=True) regardless of --replay.
"""

import json
from datetime import UTC, datetime

import pika
import typer
from pika.exceptions import NackError, UnroutableError

DEFAULT_BATCH_SIZE = 10


def original_queue(headers: dict | None) -> str | None:
    """Return the queue a message was most recently dead-lettered from, per x-death."""
    if not headers:
        return None
    x_death = headers.get("x-death") or []
    for entry in x_death:
        if isinstance(entry, dict) and entry.get("queue"):
            return str(entry["queue"])
    return None


def serialize_body(body: bytes):
    try:
        return {"json": json.loads(body)}
    except (json.JSONDecodeError, UnicodeDecodeError):
        try:
            return {"text": body.decode("utf-8")}
        except UnicodeDecodeError:
            return {"raw": repr(body)}


def log_message(queue, method, properties, payload):
    print(f"\n{'=' * 60}")
    print(f"[{datetime.now(tz=UTC).isoformat()}]")
    print(f"  Queue       : {queue}")
    print(f"  Routing Key : {method.routing_key}")
    print(f"  Exchange    : {method.exchange}")
    print(f"  Redelivered : {method.redelivered}")
    print(f"  Content-Type: {properties.content_type}")
    print(f"  Headers     : {properties.headers}")
    print(f"  Payload     : {json.dumps(payload, indent=2, default=str)}")
    print(f"{'=' * 60}")


def write_batch(output, batch):
    for record in batch:
        output.write(json.dumps(record, default=str) + "\n")
    output.flush()


def main(
    amqp_url: str = typer.Option(
        ..., envvar="RABBITMQ_AMQP_URL", help="AMQP URL, e.g. amqp://guest:guest@localhost:5672/"
    ),
    queue: str = typer.Option(..., help="Queue to dump (e.g. my.queue.dlq)."),
    output_file: str | None = typer.Option(None, help="Output JSONL path. Defaults to <queue>-dump.jsonl."),
    one_batch: bool = typer.Option(False, "--one-batch", help="Stop after a single batch."),
    batch_size: int = typer.Option(
        DEFAULT_BATCH_SIZE, "--batch-size", min=1, help="Messages per flushed batch."
    ),
    replay: bool = typer.Option(
        False,
        "--replay",
        help=(
            "Republish each message to the queue it was dead-lettered from (per its "
            "x-death header) and remove it from the DLQ, instead of leaving it in the DLQ."
        ),
    ),
) -> None:
    output_path = output_file or f"{queue}-dump.jsonl"

    print(f"Connecting to {amqp_url}")
    connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
    channel = connection.channel()
    if replay:
        channel.confirm_delivery()

    mode = "one batch" if one_batch else "all messages"
    print(f"Reading from queue '{queue}' ({mode}, batch size {batch_size}), writing to '{output_path}'")
    if replay:
        print("Replay enabled: messages will be republished to their original queue and removed from the DLQ.")

    requeue_tags = []
    replayed = 0
    total = 0
    batch = []

    try:
        with open(output_path, "a", encoding="utf-8") as output:
            while True:
                method, properties, body = channel.basic_get(queue=queue, auto_ack=False)
                if method is None:
                    break

                payload = serialize_body(body)
                record = {
                    "fetched_at": datetime.now(tz=UTC).isoformat(),
                    "queue": queue,
                    "routing_key": method.routing_key,
                    "exchange": method.exchange,
                    "redelivered": method.redelivered,
                    "content_type": properties.content_type,
                    "headers": properties.headers,
                    "payload": payload,
                }

                log_message(queue, method, properties, payload)

                target_queue = original_queue(properties.headers) if replay else None
                if target_queue:
                    try:
                        channel.basic_publish(
                            exchange="",
                            routing_key=target_queue,
                            body=body,
                            properties=properties,
                            mandatory=True,
                        )
                    except (NackError, UnroutableError) as exc:
                        requeue_tags.append(method.delivery_tag)
                        print(f"  replay FAILED ({exc}) -> left in DLQ")
                    else:
                        channel.basic_ack(delivery_tag=method.delivery_tag)
                        replayed += 1
                        record["replayed_to"] = target_queue
                        print(f"  replayed -> '{target_queue}'")
                elif replay:
                    requeue_tags.append(method.delivery_tag)
                    print("  no x-death queue found -> left in DLQ")
                else:
                    requeue_tags.append(method.delivery_tag)

                batch.append(record)

                if len(batch) >= batch_size:
                    write_batch(output, batch)
                    total += len(batch)
                    print(f"\n--- Batch flushed: {len(batch)} messages (total: {total}) ---")
                    batch = []
                    if one_batch:
                        break

            if batch:
                write_batch(output, batch)
                total += len(batch)
                print(f"\n--- Final batch flushed: {len(batch)} messages (total: {total}) ---")

        print(f"\nFetched {total} messages.")
        if replay:
            print(f"Replayed {replayed} messages to their original queue.")
        if requeue_tags:
            print(f"Requeueing {len(requeue_tags)} messages back into '{queue}'...")
            for tag in requeue_tags:
                channel.basic_nack(delivery_tag=tag, requeue=True)
        print(f"Output: {output_path}")
    finally:
        connection.close()


if __name__ == "__main__":
    typer.run(main)
