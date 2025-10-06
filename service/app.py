from tensorflow.keras.models import load_model
import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os
import sys
import uvicorn

PORT = None
public_dir = os.path.join(os.path.dirname(__file__), "public")
model_dir = os.path.join(os.path.dirname(__file__), "mnist_cnn.h5")
model = load_model(model_dir)
app = FastAPI()

app.mount("/public", StaticFiles(directory=public_dir), name="public")

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(public_dir, "index.html"))

@app.post("/prediction")
async def prediction(request: Request):
    # 1️⃣ Parse the incoming JSON body
    data = await request.json()
    # print("Received data:", data)
    img = np.array(data['values'])
    # print(img)
    img = img.reshape((1,28,28,1)).astype("float16")

    probs = model.predict(img, verbose=0)
    pred_label = int(np.argmax(probs, axis=1)[0])
    confidence = float(np.max(probs))
    return JSONResponse(content={"output": f"Number {pred_label} with {confidence*100:.2f}% confidence"})

if __name__ == "__main__":
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run("app:app", host="localhost", port=PORT, reload=False)
