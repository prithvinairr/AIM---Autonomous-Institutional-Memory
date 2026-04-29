#!/usr/bin/env bash
# A.1 key-rotation drill.
#
# The config supports key rotation via ``encryption_keys`` (list, newest
# first). The claim in the code: encryption uses [0]; decryption tries
# each in order. This drill verifies that claim under actual rotation.
#
# Procedure:
#   1. Start with key K1 only. Write a row with an encrypted field.
#   2. Rotate to [K2, K1] — K2 is new, K1 is retiring.
#   3. Write a second row. Verify BOTH rows still read (K1 row via K1,
#      K2 row via K2).
#   4. Rotate to [K2] only — K1 is fully retired.
#   5. Verify K2 row still reads; K1 row fails to decrypt (this is
#      expected — retiring a key is a promise that its ciphertext no
#      longer needs to be readable).
#
# Exit 0: rotation works as claimed.
# Exit 1: step 3 fails (old ciphertext unreadable during overlap window).
# Exit 2: step 5 ambiguous (old key somehow still reading).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

fernet_key() {
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
}

echo "[drill] generating test keys..."
K1=$(fernet_key)
K2=$(fernet_key)

# ── Step 1: single-key encrypt under K1 ──────────────────────────────
echo "[drill] step 1: writing sample ciphertext under K1"
python - <<PYEOF
import os
os.environ["ENCRYPTION_KEYS"] = "$K1"
os.environ["ENCRYPTED_FIELDS"] = "email"
from aim.utils.crypto import encrypt_field
import json
ct_k1 = encrypt_field("secret-under-k1@example.com")
json.dump({"ct_k1": ct_k1}, open("/tmp/aim_rotate.json", "w"))
print("  wrote ct_k1:", ct_k1[:24], "...")
PYEOF

# ── Step 2 & 3: rotate to [K2, K1] and verify BOTH decrypt ───────────
echo "[drill] step 2-3: rotating to [K2, K1] (overlap window)"
python - <<PYEOF
import os, json
os.environ["ENCRYPTION_KEYS"] = "$K2,$K1"
os.environ["ENCRYPTED_FIELDS"] = "email"
# Force re-import so new env is picked up.
import importlib, aim.utils.crypto
importlib.reload(aim.utils.crypto)
from aim.utils.crypto import encrypt_field, decrypt_field
data = json.load(open("/tmp/aim_rotate.json"))
# NEW write under K2
ct_k2 = encrypt_field("secret-under-k2@example.com")
# READ old K1 ciphertext — must succeed during overlap
try:
    pt_k1 = decrypt_field(data["ct_k1"])
    assert "k1" in pt_k1, f"unexpected plaintext: {pt_k1}"
    print("  K1 ciphertext still reads:", pt_k1)
except Exception as e:
    print("  FAIL step 3: K1 ciphertext unreadable during overlap —", e)
    raise SystemExit(1)
# READ new K2 ciphertext
pt_k2 = decrypt_field(ct_k2)
assert "k2" in pt_k2
print("  K2 ciphertext reads:", pt_k2)
data["ct_k2"] = ct_k2
json.dump(data, open("/tmp/aim_rotate.json", "w"))
PYEOF

# ── Step 4 & 5: fully retire K1; verify K2 still reads, K1 does not ──
echo "[drill] step 4-5: retiring K1, keeping only K2"
python - <<PYEOF
import os, json
os.environ["ENCRYPTION_KEYS"] = "$K2"
os.environ["ENCRYPTED_FIELDS"] = "email"
import importlib, aim.utils.crypto
importlib.reload(aim.utils.crypto)
from aim.utils.crypto import decrypt_field
data = json.load(open("/tmp/aim_rotate.json"))
# K2 ciphertext must still read
pt_k2 = decrypt_field(data["ct_k2"])
assert "k2" in pt_k2
print("  K2 ciphertext still reads:", pt_k2)
# K1 ciphertext should now fail — K1 is not in the key set.
try:
    pt_k1 = decrypt_field(data["ct_k1"])
    print("  AMBIGUOUS step 5: K1 ciphertext still decrypted after retirement?", pt_k1)
    raise SystemExit(2)
except Exception as e:
    print("  K1 correctly unreadable after retirement:", type(e).__name__)
PYEOF

echo "[drill] PASS — key rotation works as claimed"
