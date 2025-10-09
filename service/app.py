from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import os
import sys
import uvicorn

public_dir = os.path.join(os.path.dirname(__file__), "public")

app = FastAPI()

app.mount("/public", StaticFiles(directory=public_dir), name="public")

BACKEND_PATH = 'http://localhost:5000/prediction'

@app.get("/")
async def serve_index():
    html_content = f"""
<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8">
    <title>Image Recogonition</title>
    <link href="https://fonts.googleapis.com/css2?family=Courgette&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/public/graphics.css">
  </head>
  <body>

    <center id="canvasStuff" style="touch-action:none;">
      <canvas height="600" width="600" id="myCanvas" background="Black"></canvas><br>

      <br>
      <button id="predictor" onclick="parseImg('{BACKEND_PATH}')">PREDICT!!!</button>
      <button id="clear" onclick="clearScreen()">CLEAR</button>
      <p id="prediction">Prediction appears here!</p><br>
    </center>

    <script src="/public/graphics.js" charset="utf-8"></script>
    <script src="/public/sending.js" charset="utf-8"></script>
  </body>
</html>"""
    return HTMLResponse(content=html_content, status_code=200)
# FileResponse(os.path.join(public_dir, "index.html"))

if __name__ == "__main__":
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, reload=False)
