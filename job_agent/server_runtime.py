"""Keep the Windows HTTP server off Proactor socket cleanup after peer resets.

Only Uvicorn's loop is selected. The process-wide event-loop policy is untouched,
so Playwright and other subprocess work in their own threads retain their loops.
"""
import asyncio
import sys


def new_server_loop():
    if sys.platform=='win32':return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()
