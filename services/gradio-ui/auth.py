import bcrypt
from database import get_connection

# ================= REGISTER =================
def register_user(username: str, password: str) -> str:
    if not username or not password:
        return "Username dan password wajib diisi ❌"

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hashed)
        )

        conn.commit()
        conn.close()

        return "Registrasi berhasil ✅"

    except Exception as e:
        return "Username sudah terdaftar ❌"


# ================= LOGIN =================
def login_user(username: str, password: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT password FROM users WHERE username = ?",
        (username,)
    )

    row = cur.fetchone()
    conn.close()

    if row:
        stored_password = row["password"]

        if isinstance(stored_password, str):
            stored_password = stored_password.encode()

        if bcrypt.checkpw(password.encode(), stored_password):
            return True

    return False