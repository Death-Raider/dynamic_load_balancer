import asyncio
import httpx
import time

URL = "http://localhost:5000/route"

async def make_request(i, client):
    try:
        start = time.time()
        resp = await client.get(URL, timeout=1000)
        end = time.time()
        print(f"Client {i} completed in {end - start:.2f}s")
        return f"Client {i} -> {resp.json()}"
    except Exception as e:
        return f"Client {i} -> ERROR: {e}"

async def run_clients(num_clients=200):
    async with httpx.AsyncClient() as client:
        tasks = [make_request(i, client) for i in range(num_clients)]
        results = await asyncio.gather(*tasks)
        return results
    
if __name__ == "__main__":
    NUM_CLIENTS = 10
    while True:
        start = time.time()
        results = asyncio.run(run_clients(NUM_CLIENTS))
        print(f"Completed {NUM_CLIENTS} requests in {time.time() - start:.2f}s")