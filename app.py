from flask import Flask, request, jsonify
from tensorflow.keras.models import load_model
import numpy as np

app = Flask(__name__)
model = load_model("mnist_cnn.h5")

@app.route("/predict", methods=["POST"])
def predict():
    data = request.json["image"]  # Expect a 28x28 list
    img = np.array(data).astype("float32") / 255.0
    img = np.expand_dims(img, axis=(0, -1))  # (1,28,28,1)

    probs = model.predict(img, verbose=0)
    pred_label = int(np.argmax(probs, axis=1)[0])
    confidence = float(np.max(probs))

    return jsonify({"prediction": pred_label, "confidence": confidence})
