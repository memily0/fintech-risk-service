"""Explicit filesystem-local token inspection for .test accounts; never sends mail."""

import argparse
import json

from .auth import read_local_outbox
from .settings import Settings


def main():
    parser = argparse.ArgumentParser(description="Inspect local synthetic account messages; sensitive test tokens are printed")
    parser.add_argument("--email", required=True, help="Synthetic address ending in .test")
    args = parser.parse_args()
    settings = Settings.from_env()
    if settings.storage_backend != "sqlite":
        parser.error("Local outbox requires sqlite storage")
    print(json.dumps({"synthetic": True, "delivery_mode": "local_outbox_only", "messages": read_local_outbox(settings.database_path, args.email)}, indent=2))


if __name__ == "__main__":
    main()
