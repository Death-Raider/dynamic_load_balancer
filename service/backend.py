from tensorflow.keras.models import load_model
import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os
import sys
import uvicorn
import time
import socket
from fastapi.middleware.cors import CORSMiddleware

PORT = None
model_dir = os.path.join(os.path.dirname(__file__), "mnist_cnn.h5")
model = load_model(model_dir)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # "http://localhost:7000", # frontend url
        # "http://localhost:5000", # load balancer url
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/prediction")
async def prediction(request: Request):
    # 1️⃣ Parse the incoming JSON body
    data = await request.json()
    start_time = time.time()
    # print("Received data:", data)
    img = np.array(data['values'])
    # print(img)
    img = img.reshape((1,28,28,1)).astype("float16")

    probs = model.predict(img, verbose=0)
    pred_label = int(np.argmax(probs, axis=1)[0])
    confidence = float(np.max(probs))
    end_time = time.time()
    return JSONResponse(content={
        "output": f"Number {pred_label} with {confidence*100:.2f}% confidence", 
        'ts':time.time(),
        'service_port': PORT,
        'time_taken': end_time - start_time,
        'messaged': 'data processed successfully',
        'hostname': socket.gethostname()
    })

@app.get("/health")
def health_check():
    return {"status": "ok", "port": PORT}

if __name__ == "__main__":
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
    uvicorn.run("backend:app", host="0.0.0.0", port=PORT, reload=False)