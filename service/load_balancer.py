# load_balancer.py
import matplotlib
matplotlib.use("Agg")
import subprocess
import itertools
import atexit
import statistics
import threading
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
from contextlib import asynccontextmanager
from collections import deque
from datetime import datetime
import httpx
import sys
import psutil
import os


# ---- global for autoscaler ----
response_times = deque(maxlen=1000)
last_scale_time = 0
SCALE_COOLDOWN = 6.0
MIN_SAMPLES = 5
MIN_SERVICES = 1
MAX_SERVICES = 4
SERVICE_PORT_START = 8000
# ---- globals for managing services ----
services = []
service_cycle = None
lock = threading.Lock()  # To avoid race conditions

# ---- global for stats ----
SAMPLE_TIME = 2
stats_history = deque(maxlen=1000)  # store aggregated stats per cycle for visualization
last_sample_time = time.time()
last_sample_count = 0
request_count = {}       # Track requests per service port
plot_cache = {
    "latency": None,
    "rps_scale": None,
    "rt_hist": None,
    "cum_requests": None,
    "resource_usage": None,
}
instance_stats = {}

# ---- URL ENDPOINTS ----
URL = "http://localhost"
ENDPOINT = "/process"
N = 1
application = "app.py"

def start_service(port: int):
    global application, services, request_count
    with lock:
        proc = subprocess.Popen(["python", application, str(port)])
        services.append((port, proc))
        request_count[port] = 0
    print(f"[Scaler] Started service on port {port}")

def stop_service():
    global services, request_count, services
    with lock:
        if len(services) <= MIN_SERVICES:
            return
        port, proc = services.pop()
        proc.terminate()
        request_count.pop(port, None)
    print(f"[Scaler] Stopped service on port {port}")

def rebuild_cycle():
    global service_cycle, services
    if services:
        service_cycle = itertools.cycle([port for port, _ in services])
    else:
        service_cycle = None

def start_services(n: int):
    for i in range(n):
        start_service(SERVICE_PORT_START + i)
    rebuild_cycle()


def cleanup():
    for _, proc in services:
        proc.terminate()

def get_service_stats(interval_time=1):
    global services
    stats = []
    for port, proc in services:
        try:
            p = psutil.Process(proc.pid)
            with p.oneshot():  # optimizes multiple calls
                cpu_percent = p.cpu_percent(interval=interval_time)  # short sample
                memory_info = p.memory_info()
                mem_percent = p.memory_percent()
                threads = p.num_threads()
                create_time = datetime.fromtimestamp(p.create_time()).strftime("%H:%M:%S")
                uptime = round(time.time() - p.create_time(), 2)
                io_counters = p.io_counters() if p.is_running() else None

            stats.append({
                "port": port,
                "pid": proc.pid,
                "status": p.status(),
                "cpu_percent": cpu_percent,
                "memory_percent": mem_percent,
                "memory_rss_mb": round(memory_info.rss / (1024 * 1024), 2),
                "threads": threads,
                "uptime_sec": uptime,
                "create_time": create_time,
                "read_bytes": io_counters.read_bytes if io_counters else 0,
                "write_bytes": io_counters.write_bytes if io_counters else 0
            })
        except psutil.NoSuchProcess:
            stats.append({
                "port": port,
                "pid": None,
                "status": "terminated"
            })
    return stats

def scale_manager():
    global response_times, last_scale_time, stats_history
    while True:
        time.sleep(SAMPLE_TIME)
        with lock:
            samples = list(response_times)

        if len(samples) < MIN_SAMPLES:
            continue

        samples.sort()
        median = statistics.median(samples)
        p95_idx = max(0, int(0.95 * len(samples)) - 1)
        p95 = samples[p95_idx]
        rps = len(samples) / SAMPLE_TIME

        print(f"[Scaler] median={median:.3f}s p95={p95:.3f}s instances={len(services)} rps={rps:.2f}")
        
        now = time.time()

        stats_history.append({
            'timestamp': now,
            'avg_lb_handle_time': statistics.mean(samples) if samples else 0,
            'rps': rps,
            'active_services': len(services),
            'total_responses' : sum(request_count.values()),
        })
        if now - last_scale_time < SCALE_COOLDOWN:
            continue

        # scale-up decisions (use p95 to be robust to spikes)
        if p95 > 1.0 and len(services) < MAX_SERVICES:
            add = min(2, MAX_SERVICES - len(services))
            base = max((p for p, _ in services)) if services else SERVICE_PORT_START
            for k in range(add):
                start_service(base + 1 + k)
            rebuild_cycle()
            last_scale_time = now

        elif p95 > 0.6 and len(services) < MAX_SERVICES:
            base = max((p for p, _ in services))
            start_service(base + 1)
            rebuild_cycle()
            last_scale_time = now

        # scale-down (use median to avoid shrinking on transient spikes)
        elif median < 0.3 and len(services) > MIN_SERVICES:
            stop_service()
            rebuild_cycle()
            last_scale_time = now
        with lock:
            # clear buffer for the next window
            response_times.clear()


def sample_stats_task():
    global stats_history, response_times,  last_sample_time, last_sample_count, instance_stats, plot_cache
    # collect stats snapshot
    while True:
        service_stats = get_service_stats(interval_time=SAMPLE_TIME)
        with lock:
            recent = list(stats_history)[-70:]  # keep last 200 samples
            rtimes = list(response_times)
        
        instance_stats = {
            # current stats below
            'num_services': len(service_stats),
            'ports': [str(s["port"]) for s in service_stats],
            'cpu': [s.get("cpu_percent", 0) for s in service_stats],
            'mem_rss_mb': [s.get("memory_rss_mb", 0) for s in service_stats],
            'mem': [s.get("memory_percent", 0) for s in service_stats],
            'threads': [s.get("threads", 0) for s in service_stats],
            # historical stats below
            'ts': [p["timestamp"] for p in recent],
            'latency': [p["avg_lb_handle_time"] for p in recent],
            'rps': [p["rps"] for p in recent],
            'services': [p["active_services"] for p in recent],
            'total_requests': [p["total_responses"] for p in recent],
            'response_times': rtimes
        }
def pick_backend(endpoint):
    global service_cycle, request_count, URL, ENDPOINT
    service_port = next(service_cycle)
    request_count[service_port] = request_count.get(service_port, 0) + 1
    return f"{URL}:{service_port}/{endpoint.lstrip('/')}", service_port
    

@asynccontextmanager
async def lifespan(app: FastAPI):
    global URL, ENDPOINT, application, N

    N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    application = sys.argv[2] if len(sys.argv) > 2 else "app.py"
    URL = sys.argv[3] if len(sys.argv) > 3 else "http://localhost"
    ENDPOINT = sys.argv[4] if len(sys.argv) > 4 else "/process"
    start_services(N)
    atexit.register(cleanup)

    # Start autoscaler thread
    t1 = threading.Thread(target=scale_manager, daemon=True)
    t2 = threading.Thread(target=sample_stats_task, daemon=True)
    t1.start()
    t2.start()

    yield
    cleanup()

public_dir = os.path.join(os.path.dirname(__file__), "loadbalancer_public")
app = FastAPI(lifespan=lifespan)
app.mount("/public", StaticFiles(directory=public_dir), name="public")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def init_page():
    return FileResponse(os.path.join(public_dir, "dashboard.html"))

@app.get("/stats")
def serve_stats():
    json_values = instance_stats
    return JSONResponse(content=json_values)

@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy(request: Request, full_path: str):
    global service_cycle, request_count, response_times, URL, ENDPOINT

    if not service_cycle:
        return JSONResponse({"error": "No services available"}, status_code=501)
    ts_lb_received = time.time()

    backend_url, service_port = pick_backend(full_path)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Prepare the request to backend
        headers = dict(request.headers)
        method = request.method
        print(f"[LB] Routing request:{method} to {backend_url}")
        body = await request.body()
        backend_response = await client.request(
            method=method,
            url=backend_url,
            headers=headers,
            content=body
        )

    ts_lb_returned = time.time()
    lb_handle_time = ts_lb_returned - ts_lb_received

    with lock:
        response_times.append(lb_handle_time)
    timeline = {
        "ts_lb_received": ts_lb_received,
        "ts_lb_returned": ts_lb_returned
    }

    try:
        backend_json = backend_response.json()
        json_data = {
            **backend_json,
            "service_port": service_port,
            "timeline": timeline,
            "lb_handle_time": lb_handle_time
        }
        return JSONResponse(
            content=json_data,
            status_code=backend_response.status_code,
            headers={"Content-Type": "application/json"}
        )
    except Exception:
        # Not JSON (HTML, text, binary, etc.)
        return Response(
            content=backend_response.content,
            status_code=backend_response.status_code,
            headers=dict(backend_response.headers)
        )
    
if __name__ == "__main__":
    uvicorn.run("load_balancer:app", host="0.0.0.0", port=5000, reload=False)
