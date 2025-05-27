from flask import Flask, request, jsonify
import time
import hashlib
import random

app = Flask(__name__)
stored_encrypted = []

def generate_matrix(size=8):
    return [[random.randint(0, 255) for _ in range(size)] for _ in range(size)]

def tk_to_A(TK):
    A = []
    for i in range(8):
        row = []
        for j in range(8):
            byte = int(TK[i*8 + j*2 : i*8 + j*2 + 2], 16)
            row.append(byte)
        A.append(row)
    return A

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"time": int(time.time() * 1000)})

@app.route('/key_exchange', methods=['POST'])
def key_exchange():
    data = request.json
    average_RTT = data.get('average_RTT')
    M_prime_A = data.get('M_prime_A')
    TK = hashlib.sha256(str(int(round(average_RTT))).encode()).hexdigest()
    A = tk_to_A(TK)
    M_B = generate_matrix()
    M_prime_B = [[M_B[i][j] + A[i][j] for j in range(8)] for i in range(8)]
    return jsonify({"M_prime_B": M_prime_B})

@app.route('/send', methods=['POST'])
def send():
    global stored_encrypted
    data = request.json
    encrypted = data.get('encrypted')
    stored_encrypted = encrypted
    return jsonify({"status": "success"})

@app.route('/get', methods=['GET'])
def get():
    global stored_encrypted
    if stored_encrypted:
        return jsonify({"encrypted": stored_encrypted})
    else:
        return jsonify({"status": "no messages"})

if __name__ == '__main__':
    app.run(debug=True)