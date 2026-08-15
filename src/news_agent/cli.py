"""Buyruqlar qatori interfeysi."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from .collector import collect
from .config import get_settings, load_sources
from .pipeline import run_digest


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)-7s %(name)-28s %(message)s",
        stream=sys.stderr,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def _cmd_sources_check(args) -> int:
    settings = get_settings()
    sources = load_sources()
    _, statuses = await collect(sources, hours=args.hours, timeout=settings.fetch_timeout)

    ok_count = 0
    for status in sorted(statuses, key=lambda s: (s.ok, s.name)):
        if status.ok:
            ok_count += 1
            print(f"  OK    {status.name:<28} {status.entries:>3} element, {status.fresh:>3} yangi")
        else:
            print(f"  XATO  {status.name:<28} {status.error}\n        {status.url}")

    print(f"\n{ok_count}/{len(statuses)} manba ishlayapti.")
    return 0 if ok_count == len(statuses) else 1


async def _cmd_collect(args) -> int:
    settings = get_settings()
    articles, _ = await collect(load_sources(), hours=args.hours, timeout=settings.fetch_timeout)

    if args.json:
        print(json.dumps([a.model_dump(mode="json") for a in articles], ensure_ascii=False, indent=2))
    else:
        for article in articles:
            print(f"{article.published_at:%m-%d %H:%M}  {article.source:<22} {article.title}")
        print(f"\nJami: {len(articles)} ta noyob maqola (so'nggi {args.hours} soat).")
    return 0


async def _cmd_run(args) -> int:
    settings = get_settings()
    result = await run_digest(
        settings,
        dry_run=args.dry_run,
        hours=args.hours,
        telegram_enabled=not args.no_telegram,
        instagram_enabled=args.instagram,
    )

    if not result:
        print("Post qilinmadi (yetarli yangilik topilmadi).", file=sys.stderr)
        return 0

    if args.dry_run:
        from .telegram import MAX_MESSAGE_CHARS, visible_length

        if not args.no_telegram:
            for i, message in enumerate(result.messages, 1):
                # Telegram 4096 chegarasini HTML teglarsiz uzunlikka qo'llaydi.
                shown = visible_length(message)
                print(
                    f"\n{'=' * 60}\n{i}-XABAR — {shown}/{MAX_MESSAGE_CHARS} belgi "
                    f"(HTML bilan {len(message)})\n{'=' * 60}\n"
                )
                print(message)

        if result.card_paths:
            print(f"\n{'=' * 60}\nINSTAGRAM — {len(result.card_paths)} ta rasm\n{'=' * 60}")
            for path in result.card_paths:
                print(f"  {path}")
            print(f"\n--- CAPTION ({len(result.caption)} belgi) ---\n")
            print(result.caption)
    else:
        if not args.no_telegram:
            print(f"{len(result.messages)} ta xabar Telegram kanaliga yuborildi.")
        if result.card_paths:
            print(f"{len(result.card_paths)} ta rasm Instagram'ga joylandi.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="news-agent", description="AI/tech dayjest agenti")
    parser.add_argument("-v", "--verbose", action="store_true", help="batafsil log")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("sources-check", help="RSS manbalarni tekshirish")
    check.add_argument("--hours", type=int, default=24)
    check.set_defaults(func=_cmd_sources_check)

    collect_cmd = subparsers.add_parser("collect", help="maqolalarni yig'ish (LLM'siz)")
    collect_cmd.add_argument("--hours", type=int, default=None)
    collect_cmd.add_argument("--json", action="store_true")
    collect_cmd.set_defaults(func=_cmd_collect)

    run_cmd = subparsers.add_parser("run", help="to'liq dayjest")
    run_cmd.add_argument("--dry-run", action="store_true", help="yubormasdan terminalga chiqarish")
    run_cmd.add_argument("--hours", type=int, default=None)
    run_cmd.add_argument("--instagram", action="store_true", help="Instagram'ga ham joylash")
    run_cmd.add_argument("--no-telegram", action="store_true", help="Telegram'ga yubormaslik")
    run_cmd.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    if getattr(args, "hours", None) is None:
        args.hours = get_settings().window_hours

    try:
        return asyncio.run(args.func(args))
    except RuntimeError as exc:
        print(f"\nXato: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
