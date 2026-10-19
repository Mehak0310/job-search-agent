import asyncio
import socket
import struct
import sys
from types import SimpleNamespace
from job_agent import server_runtime


def test_server_factory_preserves_subprocess_capable_global_policy():
    import uvicorn
    policy=asyncio.get_event_loop_policy()
    factory=uvicorn.Config('unused:app',loop='job_agent.server_runtime:new_server_loop').get_loop_factory()
    loop=factory()
    try:
        if sys.platform=='win32':assert isinstance(loop,asyncio.SelectorEventLoop)
        assert asyncio.get_event_loop_policy() is policy
    finally:loop.close()
    default=asyncio.new_event_loop()
    async def subprocess_check():
        child=await asyncio.create_subprocess_exec(sys.executable,'-c','print(42)',stdout=asyncio.subprocess.PIPE)
        output,_=await child.communicate();assert child.returncode==0 and output.strip()==b'42'
    try:default.run_until_complete(subprocess_check())
    finally:default.close()


def test_other_platform_uses_its_existing_policy(monkeypatch):
    monkeypatch.setattr(server_runtime,'sys',SimpleNamespace(platform='other'))
    loop=server_runtime.new_server_loop()
    try:assert not loop.is_closed()
    finally:loop.close()


def test_connection_reset_allows_bounded_server_close_without_callback_errors():
    loop=server_runtime.new_server_loop();errors=[]
    loop.set_exception_handler(lambda loop,context:errors.append(type(context.get('exception')).__name__))
    async def exercise():
        disconnected=asyncio.Event();connected=asyncio.Event()
        class Protocol(asyncio.Protocol):
            def connection_made(self,transport):self.transport=transport;connected.set()
            def connection_lost(self,error):disconnected.set()
        server=await loop.create_server(Protocol,'127.0.0.1',0)
        try:
            for _ in range(3):
                disconnected.clear();connected.clear()
                with socket.socket() as client:
                    client.connect(server.sockets[0].getsockname())
                    await asyncio.wait_for(connected.wait(),3)
                    client.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('hh' if sys.platform=='win32' else 'ii',1,0))
                await asyncio.wait_for(disconnected.wait(),3)
        finally:
            server.close();await asyncio.wait_for(server.wait_closed(),3)
    try:loop.run_until_complete(exercise())
    finally:loop.close()
    assert errors==[]
