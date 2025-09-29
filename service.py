# service.py
import random
import asyncio
import socket
import sys
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
import time

PORT = None
app = FastAPI()

@app.get("/process")
async def process():
    # Simulate async work
    work_time = random.uniform(0.1, 0.5)
    await asyncio.sleep(work_time)
    return JSONResponse({
        "message": "Request processed",
        "hostname": socket.gethostname(),
        "time_taken": work_time,
        "ts": time.time(),
    })

if __name__ == "__main__":
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
    uvicorn.run("service:app", host="localhost", port=PORT, reload=False)
