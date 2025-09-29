import asyncio
import httpx
import time

URL = "http://localhost:5000/route"

async def make_request(i, client):
    try:
        curr_time = time.time()
        new_url = f"{URL}?ts={curr_time}"
        resp = await client.get(new_url, timeout=1000)
        print(f"Client {i} completed in {round(resp.json()['ts']-curr_time,2)}s")
        print(resp.json())
        return f"Client {i} -> {resp.json()}"
    except Exception as e:
        return f"Client {i} -> ERROR: {e}"

async def run_clients(num_clients=200):
    async with httpx.AsyncClient() as client:
        tasks = [make_request(i, client) for i in range(num_clients)]
        results = await asyncio.gather(*tasks)
        return results
    
if __name__ == "__main__":
    NUM_CLIENTS = 1
    while True:
        time.sleep(1)
        start = time.time()
        results = asyncio.run(run_clients(NUM_CLIENTS))