import asyncio
import httpx
import time
import numpy as np

URL = "http://192.168.1.4:5000/route"

async def make_request(i, client):
    try:
        curr_time = time.time()
        new_url = f"{URL}?ts={curr_time}"
        payload = {"values": np.where(np.random.rand(784)>0.49, 1, 0).tolist()}
        resp = await client.post(new_url, json=payload, timeout=100)
        data = resp.json()
        print(f"Client {i} completed by {data['service_port']} in {round(data['timeline']['ts_lb_returned'] - data['timeline']['ts_lb_received'], 2)}s")
        print(curr_time, data['timeline'])
    except Exception as e:
        print(f"Client {i} -> ERROR: {e}")

async def request_loop(rate_per_sec=50):
    """Continuously send requests at a fixed rate per second."""
    interval = 1.0 / rate_per_sec
    i = 0
    async with httpx.AsyncClient() as client:
        while True:
            asyncio.create_task(make_request(i, client))
            i += 1
            await asyncio.sleep(interval)

if __name__ == "__main__":
    asyncio.run(request_loop(rate_per_sec=5))
