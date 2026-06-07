from __future__ import annotations

import argparse
from pathlib import Path

from .asgi import create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aifilm-studio")
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="Run the local FilmGen Studio web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8777)
    serve.add_argument("--data-dir", default=str(Path("var") / "aifilm_studio"))
    serve.add_argument("--db-path", default="")
    serve.add_argument("--reload", action="store_true")

    init = subparsers.add_parser("init", help="Initialize the local SQLite database")
    init.add_argument("--data-dir", default=str(Path("var") / "aifilm_studio"))
    init.add_argument("--db-path", default="")

    args = parser.parse_args(argv)
    if args.command == "init":
        data_dir = Path(args.data_dir)
        db_path = Path(args.db_path) if args.db_path else data_dir / "studio.sqlite3"
        create_app(db_path=db_path, data_dir=data_dir)
        print(f"initialized {db_path}")
        return 0
    if args.command == "serve":
        import uvicorn

        data_dir = Path(args.data_dir)
        db_path = Path(args.db_path) if args.db_path else data_dir / "studio.sqlite3"
        app = create_app(db_path=db_path, data_dir=data_dir)
        uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
