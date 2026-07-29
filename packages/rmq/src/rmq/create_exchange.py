"""Create a RabbitMQ exchange."""

import pika
import typer

DEFAULT_EXCHANGE = "events"
DEFAULT_EXCHANGE_TYPE = "topic"


def main(
    amqp_url: str = typer.Option(
        ..., envvar="RABBITMQ_AMQP_URL", help="AMQP URL, e.g. amqp://guest:guest@localhost:5672/"
    ),
    exchange: str = typer.Option(DEFAULT_EXCHANGE, envvar="RABBITMQ_EXCHANGE", help="Exchange name."),
    exchange_type: str = typer.Option(DEFAULT_EXCHANGE_TYPE, help="Exchange type (topic, fanout, direct, headers)."),
) -> None:
    print(f"Connecting to {amqp_url}")
    connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
    channel = connection.channel()

    channel.exchange_declare(
        exchange=exchange,
        exchange_type=exchange_type,
        durable=True,
    )

    print(f"Exchange '{exchange}' (type={exchange_type}, durable=True) created successfully.")

    connection.close()


if __name__ == "__main__":
    typer.run(main)
