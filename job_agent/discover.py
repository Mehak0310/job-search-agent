"""Manual/scheduled discovery; works without dashboard, VS Code or Codex."""
import argparse
import json

from .database import Database
from .discovery import Discovery, RunBusy
from .registry import Registry, load_config
from .service import JobService


def main(argv=None):
    parser = argparse.ArgumentParser(description="Discover public Greenhouse/Lever jobs")
    parser.add_argument("--config", default="config/discovery.json")
    parser.add_argument("--db", default="data/jobs.sqlite3")
    parser.add_argument("--sync-sources", action="store_true", help="Explicitly synchronize configured enabled flags")
    parser.add_argument("--setup-only", action="store_true", help="Validate configuration/seed sources without network")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    db = Database(args.db)
    registry = Registry(db)
    if args.sync_sources:
        registry.sync(config)
    else:
        registry.seed(config)
    JobService(db).backfill_v4()
    discovery = Discovery(db, config.settings)
    try:
        if args.setup_only:
            print(json.dumps({"sources": registry.list(), "settings": config.settings.model_dump()}, indent=2))
            return 0
        run_id = discovery.claim()
        result = discovery.execute(run_id)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "COMPLETED" else 1
    except RunBusy:
        print(json.dumps({"status": "SKIPPED", "error": "discovery_in_progress"}))
        return 2
    finally:
        discovery.close()


if __name__ == "__main__":
    raise SystemExit(main())
