import json
import os
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import typer
from dotenv import load_dotenv

from authpy.token_manager import TokenManager

load_dotenv()

AUTH_DIR = Path(os.getenv("AUTHPY_HOME") or Path.home() / ".authpy")
CREDS_FILE = AUTH_DIR / "credentials.toml"
CACHE_FILE = AUTH_DIR / "cache.json"

app = typer.Typer(
    name="authpy",
    help="Auth helper to retrieve Cognito tokens",
    no_args_is_help=True,
    add_completion=True,
)


@app.command()
def get_token(
    profile: str = typer.Option(
        "default",
        "--profile",
        "-p",
        help="The profile to use from the credentials file",
    ),
    scopes: str = typer.Option(
        "",
        "--scopes",
        "-s",
        help="The scopes to request without resource, comma separated (read:company,write:admin)",
    ),
    resource: str = typer.Option(
        "",
        "--resource",
        "-r",
        envvar="AUTHPY_RESOURCE",
        help="Resource server identifier prefixed to each scope (e.g. api.example.com).",
    ),
):
    _ensure_auth_dir()

    with open(CACHE_FILE) as f:
        cached_tokens = json.load(f)

    scopes_list = [_qualify_scope(s.strip(), resource) for s in scopes.split(",")] if scopes.strip() else []
    scopes_str = " ".join(scopes_list)
    token_data = cached_tokens.get(f"{profile}/{scopes_str}")

    now = datetime.now(UTC)

    if token_data is None:
        token, expires_at = _retrieve_new_token(profile, scopes_list)
    else:
        expires_at = datetime.fromisoformat(token_data.get("expireAt").replace("Z", "+00:00"))
        token = token_data.get("access")
        if now >= expires_at:
            token, expires_at = _retrieve_new_token(profile, scopes_list)

    if not token:
        raise ValueError("Failed to retrieve token")

    cached_tokens[f"{profile}/{scopes_str}"] = {
        "access": token,
        "expireAt": expires_at.isoformat().replace("+00:00", "Z"),
    }

    with open(CACHE_FILE, "w") as f:
        json.dump(cached_tokens, f)

    typer.echo(token)


def _qualify_scope(scope: str, resource: str) -> str:
    return f"{resource}/{scope}" if resource else scope


def _retrieve_new_token(profile: str, scopes: list[str]) -> tuple[str, datetime]:
    with open(CREDS_FILE, "rb") as f:
        credentials = tomllib.load(f)

    creds_data = credentials.get(profile, {})

    if not creds_data:
        raise ValueError(f"No credentials found for profile '{profile}'")

    token_manager = TokenManager(
        client_id=creds_data["client_id"],
        client_secret=creds_data["client_secret"],
        endpoint=creds_data["endpoint"],
    )

    token = token_manager.get_token(scopes)
    scopes_str = " ".join(scopes)
    expires_at = token_manager.tokens.get(scopes_str, {}).get("expires_at")
    return token, expires_at


def _ensure_auth_dir():
    AUTH_DIR.mkdir(parents=True, exist_ok=True)

    if not CREDS_FILE.exists():
        CREDS_FILE.write_text("", encoding="utf-8")

    if not CACHE_FILE.exists():
        CACHE_FILE.write_text("{}", encoding="utf-8")


if __name__ == "__main__":
    app()
