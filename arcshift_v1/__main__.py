"""Run only the local synthetic API; no download or training hooks."""

import uvicorn

from .api import create_app
from .settings import Settings


def main():
    settings = Settings.from_env()
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        proxy_headers=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
