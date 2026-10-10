"""Optional mount into the existing partnerCodeApi FastAPI simulator.

Call install(app, configured_simulator) after creating the existing app. Set the
backend partner BaseUrl to http://127.0.0.1:8000/development/v1. The supplied
Simulator must have passed its Development/Test guard. Existing routes are intact.
"""
def install(app, simulator):
    import asyncio
    import threading
    from contextlib import asynccontextmanager
    from server import callback_worker
    from fastapi import Request
    from fastapi.responses import Response
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with original_lifespan(application) as state:
            stop = threading.Event()
            worker = threading.Thread(target=callback_worker, args=(simulator, stop), daemon=True)
            worker.start()
            try:
                yield state
            finally:
                stop.set()
                await asyncio.to_thread(worker.join, 6)
    app.router.lifespan_context = lifespan

    @app.api_route("/development/v1/{path:path}", methods=["GET", "POST"])
    async def extension(request: Request, path: str):
        # Canonical signatures include the external path. Strip the mount only at
        # business dispatch so mount paths cannot be changed under the signature.
        raw_body = bytearray()
        async for chunk in request.stream():
            raw_body.extend(chunk)
            if len(raw_body) > 65536:
                return Response('{"code":"REQUEST_TOO_LARGE"}', status_code=413, media_type="application/json")
        # Preserve escaped request keys exactly as signed by the HTTP client.
        path = request.scope["raw_path"].decode("ascii")
        query = request.scope.get("query_string", b"").decode("ascii")
        status, headers, raw, drop = simulator.handle(request.method,
            path + ("?" + query if query else ""), dict(request.headers), bytes(raw_body))
        return Response(raw, status_code=503 if drop else status, headers=headers)
