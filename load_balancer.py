# load_balancer.py
import subprocess
import itertools
import atexit
import requests
import statistics
import threading
import time
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn

services = []
service_cycle = None
request_count = {}       # Track requests per service port
response_times = []      # Store recent response times
lock = threading.Lock()  # To avoid race conditions

MIN_SERVICES = 1
MAX_SERVICES = 10


def start_service(port: int):
    proc = subprocess.Popen(["python", "service.py", str(port)])
    services.append((port, proc))
    request_count[port] = 0
    print(f"[Scaler] Started service on port {port}")


def stop_service():
    if len(services) <= MIN_SERVICES:
        return
    port, proc = services.pop()
    proc.terminate()
    request_count.pop(port, None)
    print(f"[Scaler] Stopped service on port {port}")


def rebuild_cycle():
    global service_cycle
    if services:
        service_cycle = itertools.cycle([port for port, _ in services])
    else:
        service_cycle = None


def scale_manager():
    """Runs in background: checks metrics & scales services."""
    global response_times
    while True:
        time.sleep(5)  # check every 5s
        with lock:
            if not response_times:
                continue
            avg_latency = statistics.mean(response_times)  # last 50 samples
            print(f"[Scaler] Avg latency = {avg_latency:.3f}s, instances = {len(services)}")

            # addition deletion logic (ASG)
            if avg_latency > 0.4 and len(services) < MAX_SERVICES:
                port = max(p for p, _ in services) + 1
                start_service(port)
                rebuild_cycle()

            elif avg_latency < 0.2 and len(services) > MIN_SERVICES:
                stop_service()
                rebuild_cycle()
            response_times = []


def start_services(n: int):
    base_port = 6000
    for i in range(n):
        start_service(base_port + i)
    rebuild_cycle()


def cleanup():
    for _, proc in services:
        proc.terminate()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import sys
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    start_services(N)
    atexit.register(cleanup)

    # Start autoscaler thread
    t = threading.Thread(target=scale_manager, daemon=True)
    t.start()

    yield
    cleanup()


app = FastAPI(lifespan=lifespan)


@app.get("/route")
def route():
    global service_cycle, request_count, response_times
    if not service_cycle:
        return JSONResponse({"error": "No services available"}, status_code=500)

    service_port = next(service_cycle)
    request_count[service_port] = request_count.get(service_port, 0) + 1

    try:
        # Measure total time from LB perspective
        # start = time.time()
        resp = requests.get(f"http://localhost:{service_port}/process", timeout=30)
        # elapsed = time.time() - start

        # with lock:
        #     response_times.append(elapsed)

        return JSONResponse(resp.json())
    except Exception as e:
        return JSONResponse({"error": str(e), "service": service_port}, status_code=500)

@app.middleware("http")
async def add_timer(request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    with lock:
        response_times.append(elapsed)
    return response

@app.get("/stats")
def stats():
    """Return how many requests each service handled + active instances."""
    return JSONResponse({
        "instances": [p for p, _ in services],
        "counts": request_count,
        "total_requests": sum(request_count.values())
    })


if __name__ == "__main__":
    uvicorn.run("load_balancer:app", host="localhost", port=5000, reload=False)
