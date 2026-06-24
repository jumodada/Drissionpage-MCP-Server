"""Command line interface for DrissionPage MCP Server."""

import argparse
import asyncio
import logging
import sys
from typing import List, Optional

from mcp.server.stdio import stdio_server

from . import __version__
from .server import DrissionPageMCPServer

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def main_async(args: Optional[List[str]] = None) -> None:
    """Main async function."""
    parser = argparse.ArgumentParser(
        description="DrissionPage MCP Server - Web automation tools for MCP",
        prog="drissionpage-mcp",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Set the logging level",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command")
    doctor_parser = subparsers.add_parser(
        "doctor",
        aliases=["self-test"],
        help="Print package, MCP, DrissionPage, browser, and config diagnostics",
    )
    doctor_parser.add_argument(
        "--launch-browser",
        action="store_true",
        help="Also attempt to launch and close a browser",
    )

    parsed_args = parser.parse_args(args)

    # Set logging level
    logging.getLogger().setLevel(getattr(logging, parsed_args.log_level))

    if parsed_args.command in {"doctor", "self-test"}:
        from .doctor import format_diagnostics, run_diagnostics

        report = run_diagnostics(launch_browser=parsed_args.launch_browser)
        print(format_diagnostics(report))
        if not report.get("ok"):
            raise SystemExit(1)
        return

    # Create the MCP server
    server = DrissionPageMCPServer()

    # Run with stdio transport
    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info("🚀 Starting DrissionPage MCP Server...")
            logger.info("📊 Server ready for MCP connections")
            await server.run_server(read_stream, write_stream)
    except KeyboardInterrupt:
        logger.info("👋 Server interrupted by user")
    except Exception as e:
        logger.error(f"❌ Server error: {e}")
        raise
    finally:
        logger.info("🧹 Cleaning up...")
        await server.cleanup()


def main(args: Optional[List[str]] = None) -> None:
    """Main entry point."""
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
