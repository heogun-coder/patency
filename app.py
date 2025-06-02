# app.py

from flask import Flask, request, jsonify, render_template
import time
import hashlib
import numpy as np

app = Flask(__name__)

# --------------------------------------------------
# 전역 상태 (데모용, 한 번에 한 클라이언트만 사용한다고 가정)
# --------------------------------------------------
TK_server = None                # 서버가 보관하는 TK (정수형)
M_A_server = None               # 서버가 받은 클라이언트의 원본 행렬 M_A
M_B_server = None               # 서버가 생성한 자신의 행렬 M_B
Key_server = None               # 서버(=Bob)가 최종 공유 키 행렬
# 행렬 크기 (n×n) — 클라이언트와 사전에 약속한 크기와 동일해야 함
MATRIX_SIZE = 4  # 예시로 4×4 사용 (원래 특허에서는 8의 배수가 요구되나, 데모용으론 작게 설정)


# --------------------------------------------------
# 헬퍼 함수: 무작위 가역 행렬 생성
# --------------------------------------------------
def random_invertible_matrix(n):
    """
    n×n 정수 행렬을 무작위 생성. 행렬식(det)이 0이 아닐 때까지 반복.
    """
    while True:
        M = np.random.randint(1, 10, size=(n, n))
        if round(np.linalg.det(M)) != 0:
            return M


# --------------------------------------------------
# 뷰: 메인 페이지 (클라이언트 HTML)
# --------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


# --------------------------------------------------
# 1) 시간 동기화 엔드포인트
#    - 클라이언트(Alice)가 자신의 t1을 보낸다.
#    - 서버(Bob)는 받은 t1을 사용해 자신의 t2를 생성하고 되돌려준다.
#    => 클라이언트는 응답이 돌아오는 시점 t3를 찍어 RTT 계산.
# --------------------------------------------------
@app.route('/time_sync', methods=['POST'])
def time_sync():
    data = request.get_json()
    # 클라이언트가 보낸 t1 (float, 초 단위)
    t1_client = float(data.get('t1', 0))
    # 서버 현재 시간(t2)
    t2_server = time.time()
    # 서버는 단순히 t1, t2를 그대로 돌려준다.
    return jsonify({'t1': t1_client, 't2': t2_server})


# --------------------------------------------------
# 2) TK 저장 엔드포인트
#    - 클라이언트가 “자신이 계산한 TK_int”를 서버에게 전달한다.
#    - 서버는 전역 변수 TK_server에 저장.
# --------------------------------------------------
@app.route('/set_tk', methods=['POST'])
def set_tk():
    global TK_server
    data = request.get_json()
    # 클라이언트가 계산한 TK_int (정수형)
    TK_server = int(data.get('tk', 0))
    return jsonify({'status': 'TK stored on server.'})


# --------------------------------------------------
# 3) 행렬 교환 엔드포인트
#    - 클라이언트(Alice) 측에서 M_A_masked를 보낸다.
#    - 서버는 자신의 M_A_server = M_A_masked - TK_server 로 복원.
#    - 서버는 새로 M_B_server 행렬을 생성, M_B_masked = M_B_server + TK_server.
#    - 서버는 M_B_masked를 클라이언트에게 반환한다.
#    - 클라이언트는 M_B_masked를 받아서 M_B_client = M_B_masked - TK_int(클라이언트) 복원.
#    - 이 시점에, 서버와 클라이언트 양쪽이 M_A와 M_B를 모두 보유하며,
#      Key = M_A @ M_B를 각자 계산 → 동일한 공유 키 행렬을 갖게 된다.
# --------------------------------------------------
@app.route('/send_matrix', methods=['POST'])
def send_matrix():
    global M_A_server, M_B_server, Key_server

    if TK_server is None:
        return jsonify({'error': 'TK not set on server yet.'}), 400

    data = request.get_json()
    # 클라이언트가 보낸 Masked 행렬 (리스트 형태)
    M_A_masked = np.array(data.get('M_A_masked', []), dtype=np.int64)

    # 1) 서버: M_A 복원
    M_A_server = M_A_masked - TK_server

    # 2) 서버: 자신의 M_B 생성 (가역 행렬)
    n = MATRIX_SIZE
    M_B_server = random_invertible_matrix(n)

    # 3) 서버: M_B_masked 생성
    M_B_masked = M_B_server + TK_server

    # 4) 서버: 공유 키 행렬 계산
    Key_server = M_A_server.dot(M_B_server)

    # 5) 클라이언트에 반환할 M_B_masked (리스트로 직렬화)
    return jsonify({'M_B_masked': M_B_masked.tolist()})


# --------------------------------------------------
# 4) 암호화된 메시지 수신 & 복호화 엔드포인트
#    - 클라이언트가 암호화된 “cipher” (2차원 리스트)와 "shape" (행렬 크기 정보 등) 를 보냄
#    - 서버는 자신의 Key_server를 사용하여 역행렬을 구하고, 평문 복원한 뒤 문자열로 반환
# --------------------------------------------------
@app.route('/decrypt', methods=['POST'])
def decrypt():
    global Key_server

    if Key_server is None:
        return jsonify({'error': 'Key not established on server yet.'}), 400

    data = request.get_json()
    # 클라이언트가 보낸 암호문 배열 (list of lists)
    cipher_blocks = data.get('cipher', [])
    # 행렬 크기 (MATRIX_SIZE)
    n = MATRIX_SIZE

    # NumPy로 변환
    cipher_arr = [np.array(block, dtype=np.float64) for block in cipher_blocks]

    # Key_server (정수 행렬) → float 행렬로 변환 후 역행렬 계산
    Key_mat = np.array(Key_server, dtype=np.float64)
    Key_inv = np.linalg.inv(Key_mat)

    # 복호화: 각 블록마다 Key_inv @ C → 원래 벡터 (float → 반올림 → int)
    plaintext = ""
    for C in cipher_arr:
        P_float = Key_inv.dot(C)
        P_int = np.rint(P_float).astype(np.int64)
        # 각 원소를 유니코드(ASCII) 문자로 변환
        for code in P_int:
            plaintext += chr(int(code))
    # 오른쪽 공백 제거
    plaintext = plaintext.rstrip()
    return jsonify({'plaintext': plaintext})


# --------------------------------------------------
# Flask 앱 실행
# --------------------------------------------------
if __name__ == '__main__':
    # 디버그 모드 켜고, 로컬 5000번 포트에서 실행
    app.run(debug=True)
