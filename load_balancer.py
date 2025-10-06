# load_balancer.py
import matplotlib
matplotlib.use("Agg")
import subprocess
import itertools
import atexit
# import requests
import statistics
import threading
import time
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
from contextlib import asynccontextmanager
import uvicorn
from collections import deque
import io
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from fastapi.responses import StreamingResponse
import httpx
import sys

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
}

# ---- URL ENDPOINTS ----
URL = "http://localhost"
ENDPOINT = "/process"

def start_service(port: int):
    with lock:
        proc = subprocess.Popen(["python", "service/app.py", str(port)])
        services.append((port, proc))
        request_count[port] = 0
    print(f"[Scaler] Started service on port {port}")

def stop_service():
    with lock:
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

def start_services(n: int):
    for i in range(n):
        start_service(SERVICE_PORT_START + i)
    rebuild_cycle()


def cleanup():
    for _, proc in services:
        proc.terminate()

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
    global stats_history, response_times,  last_sample_time, last_sample_count
    # collect stats snapshot
    while True:
        time.sleep(2)
        with lock:
            recent = list(stats_history)[-70:]  # keep last 200 samples
            rtimes = list(response_times)

        # latency plot
        if recent:
            ts = [datetime.fromtimestamp(p["timestamp"]) for p in recent]
            lat = [p["avg_lb_handle_time"] for p in recent]
            buf = io.BytesIO()
            plt.figure(figsize=(8, 4))
            plt.plot(ts, lat, marker="o", markersize=3, linewidth=1)
            plt.title("Average LB Handle Time")
            plt.xlabel("Timestamp")
            plt.ylabel("Latency (s)")
            plt.grid(True)
            ax = plt.gca()
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            plt.gcf().autofmt_xdate()  # rotate labels for readability
            plt.tight_layout()
            plt.savefig(buf, format="png")
            plt.close()
            buf.seek(0)
            plot_cache["latency"] = buf.getvalue()

        if recent:
            ts = [datetime.fromtimestamp(p["timestamp"]) for p in recent]
            rps = [p["rps"] for p in recent]
            services = [p["active_services"] for p in recent]

            buf = io.BytesIO()
            fig, ax1 = plt.subplots(figsize=(8, 4))

            # Left y-axis → RPS
            color_rps = "tab:blue"
            ax1.set_xlabel("Time")
            ax1.set_ylabel("RPS", color=color_rps)
            ax1.plot(ts, rps, color=color_rps, label="RPS")
            ax1.tick_params(axis="y", labelcolor=color_rps)
            ax1.grid(True)
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            fig.autofmt_xdate()  # auto-rotate labels for better readability
            # Right y-axis → Active Services
            ax2 = ax1.twinx()
            color_services = "tab:red"
            ax2.set_ylabel("Active Services", color=color_services)
            ax2.plot(ts, services, color=color_services, label="Services")
            ax2.tick_params(axis="y", labelcolor=color_services)

            # Title and layout
            fig.suptitle("RPS vs Active Services")
            fig.tight_layout()

            plt.savefig(buf, format="png")
            plt.close(fig)
            buf.seek(0)

            plot_cache["rps_scale"] = buf.getvalue()

        # response time histogram
        if rtimes:
            buf = io.BytesIO()
            plt.figure(figsize=(6, 4))
            plt.hist(rtimes, bins=20)
            plt.title("Client Response Time Distribution")
            plt.xlabel("Response Time (s)")
            plt.ylabel("Count")
            plt.tight_layout()
            plt.savefig(buf, format="png")
            plt.close()
            buf.seek(0)
            plot_cache["rt_hist"] = buf.getvalue()

        # cumulative requests
        if recent:
            total = [p["total_responses"] for p in recent]
            buf = io.BytesIO()
            plt.figure(figsize=(8, 4))
            plt.plot(ts, total, label="Total Requests")
            plt.title("Cumulative Requests Over Time")
            plt.grid(True)
            ax = plt.gca()
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            plt.gcf().autofmt_xdate()  # rotate labels for readability
            plt.tight_layout()
            plt.savefig(buf, format="png")
            plt.close()
            buf.seek(0)
            plot_cache["cum_requests"] = buf.getvalue()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global URL, ENDPOINT
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    URL = sys.argv[2] if len(sys.argv) > 2 else "http://localhost"
    ENDPOINT = sys.argv[3] if len(sys.argv) > 3 else "/process"
    start_services(N)
    atexit.register(cleanup)

    # Start autoscaler thread
    t1 = threading.Thread(target=scale_manager, daemon=True)
    t2 = threading.Thread(target=sample_stats_task, daemon=True)
    t1.start()
    t2.start()

    yield
    cleanup()


app = FastAPI(lifespan=lifespan)


@app.post("/route")
async def route(request: Request, ts: float = None):
    global service_cycle, request_count, response_times
    if not service_cycle:
        return JSONResponse({"error": "No services available"}, status_code=501)

    ts_lb_received = time.time()

    service_port = next(service_cycle)
    request_count[service_port] = request_count.get(service_port, 0) + 1
    data_json = await request.json()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{URL}:{service_port}{ENDPOINT}",json=data_json, timeout=30.0)
        service_data = resp.json()
        ts_lb_returned = time.time()
        # LB-local metric for autoscaler: time spent handling the request
        lb_handle_time = ts_lb_returned - ts

        # print(service_data.get("time_taken"))

        # append to rolling window (thread-safe)
        with lock:
            response_times.append(lb_handle_time)

        # return both LB and service timestamps for tracing
        timeline = {
            "ts_client_sent": ts,
            "ts_lb_received": ts_lb_received,
            "ts_service_processed": service_data.get("ts"),  # service timestamp
            "ts_lb_returned": ts_lb_returned
        }

        return JSONResponse({
            "service_port": service_port,
            "hostname": service_data.get("hostname"),
            "message": service_data.get("message"),
            "work_time": service_data.get("time_taken"),
            "timeline": timeline,
            "lb_handle_time": lb_handle_time
        })
    except Exception as e:
        return JSONResponse({"error": str(e), "service": service_port}, status_code=502)

@app.get("/plot/{plot_name}")
def serve_plot(plot_name: str):
    img_data = plot_cache.get(plot_name)
    if not img_data:
        return StreamingResponse(io.BytesIO(), media_type="image/png")
    return StreamingResponse(io.BytesIO(img_data), media_type="image/png")


@app.get("/stats", response_class=HTMLResponse)
def stats_dashboard():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Load Balancer Dashboard</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            h1 { text-align: center; }
            img { border: 1px solid #ccc; display: block; margin: 20px auto; }
            .section { margin-bottom: 50px; }
        </style>
    </head>
    <body>
        <div>
            <h2>Latency Over Time</h2>
            <img id="latency" src="/plot/latency" width="600">
            </div>
            <div>
            <h2>RPS vs Active Services</h2>
            <img id="rps_scale" src="/plot/rps_scale" width="600">
            </div>
            <div>
            <h2>Response Time Histogram</h2>
            <img id="rt_hist" src="/plot/rt_hist" width="600">
            </div>
            <div>
            <h2>Cumulative Requests</h2>
            <img id="cum_requests" src="/plot/cum_requests" width="600">
            </div>
            <script>
            // Refresh plots every 4s
            setInterval(() => {
                ["latency", "rps_scale", "rt_hist", "cum_requests"].forEach(id => {
                const img = document.getElementById(id);
                img.src = `/plot/${id}?t=${Date.now()}`; // cache-bust
                });
            }, 3000);
            </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    uvicorn.run("load_balancer:app", host="0.0.0.0", port=5000, reload=False)
