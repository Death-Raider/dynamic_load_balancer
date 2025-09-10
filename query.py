import requests
import tensorflow as tf
import numpy as np
import random

# Load test data locally just for queries
(_, _), (x_test, y_test) = tf.keras.datasets.mnist.load_data()

def main():
    n = int(input("How many queries? "))
    server_url = "http://<LOAD_BALANCER_IP>/predict"

    for i in range(n):
        idx = random.randint(0, len(x_test)-1)
        img, true_label = x_test[idx], y_test[idx]

        # Send POST request
        response = requests.post(server_url, json={"image": img.tolist()})
        result = response.json()

        print(f"Query {i+1}: True={true_label}, Predicted={result['prediction']}, Confidence={result['confidence']:.2f}")

if __name__ == "__main__":
    main()
