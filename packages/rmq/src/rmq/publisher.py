"""Minimal RabbitMQ publisher: publisher confirms, persistent, application/json."""

import logging
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from pika import BasicProperties, BlockingConnection, URLParameters
from pika.spec import PERSISTENT_DELIVERY_MODE

DEFAULT_HEARTBEAT = "60"
DEFAULT_BLOCKED_CONNECTION_TIMEOUT = "120"


def normalize_amqp_url(url: str) -> str:
    """Return the URL with heartbeat / blocked_connection_timeout defaults filled in."""
    if not url:
        raise ValueError("AMQP url was not provided")

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query.setdefault("heartbeat", [DEFAULT_HEARTBEAT])
    query.setdefault("blocked_connection_timeout", [DEFAULT_BLOCKED_CONNECTION_TIMEOUT])
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


class RabbitMQPublisher:
    """
    One-shot publisher: opens a connection, publishes, closes.

    Publisher confirms are enabled, so an unroutable or rejected message raises
    (pika.exceptions.UnroutableError / NackError) instead of failing silently.
    """

    def __init__(self, url: str, exchange: str, logger: logging.Logger | None = None):
        self.url = normalize_amqp_url(url)
        self.exchange = exchange
        self.logger = logger or logging.getLogger(__name__)

    def publish(self, routing_key: str, message: str | bytes, headers: dict | None = None) -> None:
        connection = BlockingConnection(URLParameters(url=self.url))
        try:
            channel = connection.channel()
            channel.confirm_delivery()
            channel.basic_publish(
                exchange=self.exchange,
                routing_key=routing_key,
                body=message,
                properties=BasicProperties(
                    delivery_mode=PERSISTENT_DELIVERY_MODE,
                    content_type="application/json",
                    headers=headers,
                ),
                mandatory=True,
            )
        finally:
            if connection.is_open:
                connection.close()
