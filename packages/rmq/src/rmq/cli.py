"""Unified `rmq` CLI grouping the RabbitMQ inspection and maintenance commands."""

import typer

from rmq import consume, create_exchange, dump_dlq, helper, publish_dump, purge_dlq

app = typer.Typer(
    name="rmq",
    help="RabbitMQ inspection and maintenance scripts.",
    no_args_is_help=True,
)

app.command("consume", help="Consume messages from a queue to inspect serialization.")(consume.main)
app.command("create-exchange", help="Create a durable exchange.")(create_exchange.main)
app.command("dump-dlq", help="Read a queue (e.g. a DLQ) in batches to JSONL without acking.")(dump_dlq.main)
app.command("purge-dlq", help="Drop DLQ messages that originated from a given source queue.")(purge_dlq.main)
app.command("publish-dump", help="Publish messages from a dump-dlq JSONL file to a broker with a fixed routing key.")(
    publish_dump.main
)
app.add_typer(helper.app, name="helper")


if __name__ == "__main__":
    app()
