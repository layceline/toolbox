import json
import logging
import os
import shlex
import subprocess

import pika
import typer
from dotenv import load_dotenv
from pika import URLParameters
from pika.adapters.blocking_connection import BlockingChannel, BlockingConnection
from pika.exceptions import ChannelClosedByBroker

from rmq.publisher import RabbitMQPublisher

load_dotenv()

DEFAULT_EXCHANGE = "events"

app = typer.Typer(
    name="rabbit helper",
    help="Minimal RabbitMQ CLI for local dev",
    no_args_is_help=True,
    add_completion=True,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("rmq")


def _channel(amqp_url: str) -> tuple[BlockingConnection, BlockingChannel]:
    """Open a BlockingConnection + channel for admin operations."""
    conn = pika.BlockingConnection(URLParameters(amqp_url))
    ch = conn.channel()
    return conn, ch


def _safe_close(conn: BlockingConnection | None) -> None:
    """Close connection if present and open."""
    try:
        if conn and conn.is_open:
            conn.close()
    except Exception:
        pass


@app.command("launch")
def launch() -> None:
    """
    Launch a local RabbitMQ (Docker) with management UI.
    - Image: rabbitmq:3.13-management
    - Ports: 5672 (AMQP), 15672 (UI)
    - Auto-removed on stop
    """
    cmd = [
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        "rabbitmq",
        "-p",
        "5672:5672",
        "-p",
        "15672:15672",
        "rabbitmq:3.13-management",
    ]
    typer.echo("$ " + " ".join(shlex.quote(s) for s in cmd))
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        typer.secho("RabbitMQ started", fg=typer.colors.GREEN)
        typer.echo(out.decode().strip())
        typer.echo("UI:   http://localhost:15672  (guest/guest)")
        typer.echo(f"AMQP: {os.getenv('RABBITMQ_AMQP_URL')}")
        typer.echo("Next: create-exchange -> create-queue -> bind -> push")
    except subprocess.CalledProcessError as e:
        typer.secho("Failed to start RabbitMQ:", fg=typer.colors.RED)
        typer.echo(e.output.decode())
        raise typer.Exit(1)


@app.command("init")
def init(
    exchange: str = typer.Option(DEFAULT_EXCHANGE, "--exchange", "-e", envvar="RABBITMQ_EXCHANGE"),
    queue: str = typer.Option("status", "--queue", "-q"),
    routing_key: str = typer.Option("#", "--routing-key", "-r"),
    amqp_url: str = typer.Option(..., "--amqp-url", envvar="RABBITMQ_AMQP_URL", prompt=True),
) -> None:
    """
    Initialize a minimal event bus setup:
    - declare durable exchange
    - declare durable queue
    - bind queue to exchange with routing key
    All actions are idempotent
    """
    conn: BlockingConnection | None = None
    try:
        conn, ch = _channel(amqp_url)

        ch.exchange_declare(exchange=exchange, exchange_type="topic", durable=True)
        typer.echo(f"declared exchange: {exchange} (type=topic, durable=true)")

        ch.queue_declare(queue=queue, durable=True)
        typer.echo(f"declared queue: {queue} (durable=true)")

        ch.queue_bind(queue=queue, exchange=exchange, routing_key=routing_key)
        typer.echo(f"created binding: {queue} <-[{routing_key}]- {exchange}")

        typer.secho("init completed", fg=typer.colors.GREEN)
        typer.echo("Tip: run `status --exchange {exchange} --queue {queue}` to verify.")
    finally:
        _safe_close(conn)


@app.command("create-exchange")
def create_exchange(
    name: str = typer.Option(..., "--name", "-n", prompt=True),
    ex_type: str = typer.Option("topic", "--type", "-t"),
    amqp_url: str = typer.Option(..., "--amqp-url", envvar="RABBITMQ_AMQP_URL"),
) -> None:
    """Declare a durable exchange (default: topic)."""
    conn: BlockingConnection | None = None
    try:
        conn, ch = _channel(amqp_url)
        ch.exchange_declare(exchange=name, exchange_type=ex_type, durable=True)
        typer.secho(f"Exchange '{name}' declared", fg=typer.colors.GREEN)
        default_exchange = os.getenv("RABBITMQ_EXCHANGE", DEFAULT_EXCHANGE)
        if name != default_exchange:
            typer.echo(f"Note: `push` defaults to exchange '{default_exchange}' (set RABBITMQ_EXCHANGE to change).")
    finally:
        _safe_close(conn)


@app.command("create-queue")
def create_queue(
    name: str = typer.Option(..., "--name", "-n", prompt=True),
    amqp_url: str = typer.Option(..., "--amqp-url", envvar="RABBITMQ_AMQP_URL"),
) -> None:
    """Declare a durable queue."""
    conn: BlockingConnection | None = None
    try:
        conn, ch = _channel(amqp_url)
        ch.queue_declare(queue=name, durable=True)
        typer.secho(f"Queue '{name}' declared", fg=typer.colors.GREEN)
    finally:
        _safe_close(conn)


@app.command("bind")
def bind_queue(
    queue: str = typer.Option(..., "--queue", "-q", prompt=True),
    exchange: str = typer.Option(..., "--exchange", "-e", prompt=True),
    routing_key: str = typer.Option("", "--routing-key", "-r"),
    amqp_url: str = typer.Option(..., "--amqp-url", envvar="RABBITMQ_AMQP_URL"),
) -> None:
    """Bind a queue to an exchange with a routing key."""
    conn: BlockingConnection | None = None
    try:
        conn, ch = _channel(amqp_url)
        ch.queue_bind(queue=queue, exchange=exchange, routing_key=routing_key)
        typer.secho(f"Bound '{queue}' <-[{routing_key}]- '{exchange}'", fg=typer.colors.GREEN)
        typer.echo(
            "Tip: publisher uses mandatory=True; ensure a binding matches the routing key.",
        )
    finally:
        _safe_close(conn)


@app.command("push")
def push(
    body: str = typer.Option(..., "--body", "-b", help="String or JSON"),
    routing_key: str = typer.Option(..., "--routing-key", "-r", envvar="RABBITMQ_ROUTING_KEY"),
    exchange: str = typer.Option(DEFAULT_EXCHANGE, "--exchange", "-e", envvar="RABBITMQ_EXCHANGE"),
    amqp_url: str = typer.Option(..., "--amqp-url", envvar="RABBITMQ_AMQP_URL"),
) -> None:
    """Publish with publisher confirms (persistent, application/json)."""
    pub = RabbitMQPublisher(url=amqp_url, exchange=exchange, logger=logger)
    pub.publish(
        routing_key=routing_key,
        message=body,
    )
    typer.secho("Message published", fg=typer.colors.GREEN)
    typer.echo(f"Exchange: {exchange}")
    typer.echo(f"Routing key: {routing_key}")


@app.command("status")
def status(
    amqp_url: str = typer.Option(..., "--amqp-url", envvar="RABBITMQ_AMQP_URL"),
    exchange: str = typer.Option(DEFAULT_EXCHANGE, "--exchange", envvar="RABBITMQ_EXCHANGE"),
    queue: str | None = typer.Option(
        None,
        "--queue",
        help="Optional: check this queue exists (passive)",
    ),
    test_routing_key: str | None = typer.Option(
        None,
        "--test-routing-key",
        help="Optional: quick routability test",
    ),
    dry_run: bool = typer.Option(True, "--dry-run/--send-test"),
) -> None:
    """
    Show basic status:
    - Connect to broker
    - Check exchange exists (passive)
    - Optionally check a queue exists (passive)
    - Optional quick routability test (publishes tiny JSON unless --dry-run)
    """
    conn: BlockingConnection | None = None
    try:
        conn, ch = _channel(amqp_url)
        typer.secho("Connected", fg=typer.colors.GREEN)
        typer.echo(f"AMQP URL: {amqp_url}")

        try:
            ch.exchange_declare(exchange=exchange, passive=True)
            typer.secho(f"Exchange '{exchange}' exists", fg=typer.colors.GREEN)
        except ChannelClosedByBroker:
            typer.secho(f"Exchange '{exchange}' NOT FOUND", fg=typer.colors.RED)
            raise typer.Exit(1)

        if queue:
            try:
                ch.queue_declare(queue=queue, passive=True)
                typer.secho(f"Queue '{queue}' exists", fg=typer.colors.GREEN)
            except ChannelClosedByBroker:
                typer.secho(f"Queue '{queue}' NOT FOUND", fg=typer.colors.RED)
                raise typer.Exit(1)
    finally:
        _safe_close(conn)

    if test_routing_key:
        if dry_run:
            typer.echo(
                f"Routability test (dry-run): would publish to '{exchange}' with rk='{test_routing_key}'.",
            )
            typer.echo("Note: real routability requires an actual publish with mandatory=True.")
        else:
            pub = RabbitMQPublisher(url=amqp_url, exchange=exchange, logger=logger)
            try:
                pub.publish(
                    routing_key=test_routing_key,
                    message=json.dumps({"ping": True}),
                )
                typer.secho("Routability OK (publish confirmed)", fg=typer.colors.GREEN)
            except Exception as e:
                typer.secho(f"Routability FAILED  {e}", fg=typer.colors.RED)
                raise typer.Exit(1)


if __name__ == "__main__":
    app()
