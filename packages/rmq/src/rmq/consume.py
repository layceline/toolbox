"""Quick RabbitMQ consumer to inspect message serialization."""

import json
from datetime import UTC, datetime

import pika
import typer

DEFAULT_EXCHANGE = "events"
DEFAULT_ROUTING_KEY = "#"


def on_message(channel, method, properties, body):
    print(f"\n{'=' * 60}")
    print(f"[{datetime.now(tz=UTC).isoformat()}]")
    print(f"  Routing Key : {method.routing_key}")
    print(f"  Content-Type: {properties.content_type}")
    print(f"  Headers     : {properties.headers}")

    try:
        parsed = json.loads(body)
        print(f"  Body (JSON) :\n{json.dumps(parsed, indent=2, default=str)}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        print(f"  Body (raw)  : {body!r}")

    print(f"{'=' * 60}")
    channel.basic_ack(delivery_tag=method.delivery_tag)


def main(
    amqp_url: str = typer.Option(
        ..., envvar="RABBITMQ_AMQP_URL", help="AMQP URL, e.g. amqp://guest:guest@localhost:5672/"
    ),
    exchange: str = typer.Option(DEFAULT_EXCHANGE, envvar="RABBITMQ_EXCHANGE", help="Exchange to bind to."),
    routing_key: str = typer.Option(DEFAULT_ROUTING_KEY, help="Routing key to bind to."),
) -> None:
    print(f"Connecting to {amqp_url}")
    connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
    channel = connection.channel()

    result = channel.queue_declare(queue="", exclusive=True)
    queue_name = result.method.queue

    channel.queue_bind(exchange=exchange, queue=queue_name, routing_key=routing_key)

    print(f"Bound queue '{queue_name}' to exchange '{exchange}' with routing key '{routing_key}'")
    print("Waiting for messages... (Ctrl+C to quit)\n")

    channel.basic_consume(queue=queue_name, on_message_callback=on_message)

    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        print("\nStopping.")
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    typer.run(main)
