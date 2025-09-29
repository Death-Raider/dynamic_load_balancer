# load_balancer.py
import matplotlib
matplotlib.use("Agg")
import subprocess
import itertools
import atexit
import requests
import statistics
import threading
import time
from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
from contextlib import asynccontextmanager
import uvicorn
from collections import deque
import io
import matplotlib.pyplot as plt
from fastapi.responses import StreamingResponse
import asyncio

# ---- global for autoscaler ----
response_times = deque(maxlen=1000)
last_scale_time = 0
SCALE_COOLDOWN = 6.0
MIN_SAMPLES = 5
MIN_SERVICES = 1
MAX_SERVICES = 100

# ---- globals for managing services ----
services = []
service_cycle = None
lock = threading.Lock()  # To avoid race conditions

# ---- global for stats ----
SAMPLE_TIME = 5
stats_history = []  # store aggregated stats per cycle for visualization
last_sample_time = time.time()
last_sample_count = 0
request_count = {}       # Track requests per service port

def start_service(port: int):
    with lock:
        proc = subprocess.Popen(["python", "service.py", str(port)])
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
    base_port = 6000
    for i in range(n):
        start_service(base_port + i)
    rebuild_cycle()


def cleanup():
    for _, proc in services:
        proc.terminate()

def scale_manager():
    global response_times, last_scale_time
    while True:
        time.sleep(SAMPLE_TIME)
        with lock:
            samples = list(response_times)
            # clear buffer for the next window
            response_times.clear()

        if len(samples) < MIN_SAMPLES:
            continue

        samples.sort()
        median = statistics.median(samples)
        p95_idx = max(0, int(0.95 * len(samples)) - 1)
        p95 = samples[p95_idx]
        rps = len(samples) / 4.0

        print(f"[Scaler] median={median:.3f}s p95={p95:.3f}s instances={len(services)} rps={rps:.2f}")

        now = time.time()
        if now - last_scale_time < SCALE_COOLDOWN:
            continue

        # scale-up decisions (use p95 to be robust to spikes)
        if p95 > 1.0 and len(services) < MAX_SERVICES:
            add = min(3, MAX_SERVICES - len(services))
            base = max((p for p, _ in services)) if services else 6000
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


def sample_stats_task():
    """
    Periodically sample stats (RPS, latency, active services) for visualization.
    Runs in background without affecting route() or scaling.
    """
    global last_sample_time, last_sample_count, stats_history

    while True:
        time.sleep(SAMPLE_TIME)

        now = time.time()
        elapsed = now - last_sample_time

        with lock:
            total_responses = len(response_times)
            new_responses = total_responses - last_sample_count
            avg_rt = (sum(response_times) / len(response_times)) if response_times else 0
            active_instances = len(services)

        rps = new_responses / elapsed if elapsed > 0 else 0

        stats_point = {
            "timestamp": now,
            "rps": rps,
            "avg_lb_handle_time": avg_rt,
            "active_services": active_instances,
            "total_responses": total_responses,
        }

        stats_history.append(stats_point)
        last_sample_time = now
        last_sample_count = total_responses


@asynccontextmanager
async def lifespan(app: FastAPI):
    import sys
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
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


@app.get("/route")
def route(ts: float = None):
    global service_cycle, request_count, response_times
    if not service_cycle:
        return JSONResponse({"error": "No services available"}, status_code=501)

    ts_lb_received = time.time()

    service_port = next(service_cycle)
    request_count[service_port] = request_count.get(service_port, 0) + 1

    try:
        resp = requests.get(f"http://localhost:{service_port}/process", timeout=30)
        service_data = resp.json()
        ts_lb_returned = time.time()

        # LB-local metric for autoscaler: time spent handling the request
        lb_handle_time = ts_lb_returned - ts_lb_received

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

@app.get("/plot/latency")
def plot_latency():
    if not stats_history:
        return HTMLResponse("<h3>No data yet</h3>")

    ts = [p["timestamp"] for p in stats_history]
    latencies = [p["avg_lb_handle_time"] for p in stats_history]

    plt.figure(figsize=(8,4))
    plt.plot(ts, latencies, marker='o', markersize=3, linewidth=1)
    plt.title("Average LB Handle Time Over Time")
    plt.xlabel("Timestamp")
    plt.ylabel("Latency (s)")
    plt.grid(True)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

# ----- RPS vs Active Services -----
@app.get("/plot/rps_scale")
def plot_rps_scale():
    if not stats_history:
        return HTMLResponse("<h3>No data yet</h3>")

    ts = [p["timestamp"] for p in stats_history]
    rps = [p["rps"] for p in stats_history]
    services = [p["active_services"] for p in stats_history]

    fig, ax1 = plt.subplots(figsize=(8,4))
    ax1.set_xlabel("Timestamp")
    ax1.set_ylabel("RPS", color="tab:blue")
    ax1.plot(ts, rps, color="tab:blue", marker='o', markersize=3, linewidth=1)
    ax1.tick_params(axis='y', labelcolor="tab:blue")

    ax2 = ax1.twinx()
    ax2.set_ylabel("Active Services", color="tab:orange")
    ax2.plot(ts, services, color="tab:orange", marker='x', markersize=3, linewidth=1)
    ax2.tick_params(axis='y', labelcolor="tab:orange")

    plt.title("RPS vs Active Services Over Time")
    fig.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

# ----- Response Time Histogram -----
@app.get("/plot/rt_hist")
def plot_rt_hist():
    if not response_times:
        return HTMLResponse("<h3>No response times yet</h3>")

    plt.figure(figsize=(8,4))
    plt.hist(list(response_times), bins=30, color='skyblue', edgecolor='black')
    plt.title("Response Time Distribution (Recent Samples)")
    plt.xlabel("LB Handle Time (s)")
    plt.ylabel("Count")
    plt.grid(True)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

# ----- Cumulative Requests -----
@app.get("/plot/cum_requests")
def plot_cum_requests():
    if not stats_history:
        return HTMLResponse("<h3>No data yet</h3>")

    ts = [p["timestamp"] for p in stats_history]
    total = [p["total_responses"] for p in stats_history]

    plt.figure(figsize=(8,4))
    plt.plot(ts, total, marker='o', markersize=3, linewidth=1, color='green')
    plt.title("Cumulative Requests Over Time")
    plt.xlabel("Timestamp")
    plt.ylabel("Total Requests")
    plt.grid(True)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


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
        <h1>Load Balancer Dashboard</h1>

        <div class="section">
            <h2>Average LB Handle Time Over Time</h2>
            <img id="latency_plot" src="/plot/latency" width="800">
        </div>

        <div class="section">
            <h2>RPS vs Active Services</h2>
            <img id="rps_plot" src="/plot/rps_scale" width="800">
        </div>

        <div class="section">
            <h2>Response Time Distribution (Recent Samples)</h2>
            <img id="hist_plot" src="/plot/rt_hist" width="800">
        </div>

        <div class="section">
            <h2>Cumulative Requests Over Time</h2>
            <img id="cum_plot" src="/plot/cum_requests" width="800">
        </div>

        <script>
            // Auto-refresh images every 3 seconds
            setInterval(() => {
                const t = new Date().getTime();
                document.getElementById('latency_plot').src = '/plot/latency?' + t;
                document.getElementById('rps_plot').src = '/plot/rps_scale?' + t;
                document.getElementById('hist_plot').src = '/plot/rt_hist?' + t;
                document.getElementById('cum_plot').src = '/plot/cum_requests?' + t;
            }, 3000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    uvicorn.run("load_balancer:app", host="localhost", port=5000, reload=False)
