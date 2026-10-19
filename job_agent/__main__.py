import argparse
import uvicorn

from .main import create_app


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local job research dashboard")
    parser.add_argument("--port", type=int, default=8000, help="Local port (default: 8000)")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port,loop='job_agent.server_runtime:new_server_loop')


if __name__ == "__main__":
    main()
