from __future__ import annotations

import argparse
import logging
import threading
from pathlib import Path

from shrimpicus.config import Settings
from shrimpicus.web.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the Shrimpicus Discord bot and web app together"
    )
    parser.add_argument("--host", default=None, help="Web bind host (default: settings.web_host)")
    parser.add_argument("--port", type=int, default=None, help="Web bind port (default: settings.web_port)")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    settings = Settings()
    host = args.host if args.host is not None else settings.web_host
    port = args.port if args.port is not None else settings.web_port

    app = create_app()

    def _serve_web() -> None:
        # use_reloader=False: reloader spawns a child process which would double-run the bot
        app.run(host=host, port=port, debug=args.debug, use_reloader=False)

    web_thread = threading.Thread(target=_serve_web, name="shrimpicus-web", daemon=True)
    web_thread.start()

    logging.getLogger("shrimpicus").info(
        "Web app running on http://%s:%s (thread: %s)", host, port, web_thread.name
    )

    # Run the bot in the main thread's event loop. Imported here so the web thread
    # is already serving before bot startup logging/initialization begins.
    from shrimpicus.main import run as run_bot

    import asyncio

    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logging.getLogger("shrimpicus").info("Received Ctrl-C, shutting down.")


if __name__ == "__main__":
    main()
