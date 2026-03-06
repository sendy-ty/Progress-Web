import gradio as gr
import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from auth import register_user, login_user
from yolo_infer import detect_tree

UPLOAD_DIR = "uploads"
REPORT_DIR = "reports"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# ================= PDF =================
def generate_pdf(username, count, image_path, lokasi, luas):
    pdf_path = os.path.join(REPORT_DIR, "laporan_deteksi_pohon.pdf")
    c = canvas.Canvas(pdf_path, pagesize=A4)
    w, h = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w / 2, h - 40, "LAPORAN DETEKSI POHON DURIAN")

    c.setFont("Helvetica", 11)
    c.drawString(50, h - 80, f"User       : {username}")
    c.drawString(50, h - 100, f"Waktu      : {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}")
    c.drawString(50, h - 120, f"Lokasi     : {lokasi}")
    c.drawString(50, h - 140, f"Luas Lahan : {luas} ha")
    c.drawString(50, h - 160, f"Jumlah     : {count} pohon")

    img = ImageReader(image_path)
    iw, ih = img.getSize()
    scale = min((w - 100) / iw, (h - 240) / ih)

    c.drawImage(
        img,
        50,
        h - 200 - ih * scale,
        width=iw * scale,
        height=ih * scale,
        preserveAspectRatio=True
    )

    c.showPage()
    c.save()

    return pdf_path


# ================= LOGIC =================
def handle_login(username, password):
    if login_user(username, password):
        return (
            "Login berhasil ✅",
            True,
            username,
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(visible=False),
        )

    return (
        "Login gagal ❌",
        False,
        "",
        gr.update(visible=True),
        gr.update(visible=False),
        gr.update(visible=False),
    )


def handle_detect(img, logged):
    if not logged or img is None:
        return None, "", 0, ""

    img_path = os.path.join(UPLOAD_DIR, "input.jpg")
    img.save(img_path)

    out_path, count = detect_tree(img_path)

    result_md = f"""
    ### 🌳 Jumlah Pohon Yang Terdeteksi  
    ## {count}
    """

    return out_path, result_md, count, out_path


def goto_report():
    return gr.update(visible=False), gr.update(visible=False), gr.update(visible=True)


def back_to_detect():
    return gr.update(visible=False), gr.update(visible=True), gr.update(visible=False)


def back_to_login():
    return gr.update(visible=True), gr.update(visible=False), gr.update(visible=False)


def logout():
    return "", False, gr.update(visible=True), gr.update(visible=False), gr.update(visible=False)


# ================= UI =================
with gr.Blocks(theme=gr.themes.Soft()) as demo:

    login_state = gr.State(False)
    user_state = gr.State("")
    count_state = gr.State(0)
    image_state = gr.State("")

    # ===== PAGE 1 =====
    with gr.Column(visible=True) as page_auth:
        gr.Markdown("## 🔐 Login Sistem Deteksi Pohon Durian")

        with gr.Tabs():

            with gr.Tab("Login"):
                l_user = gr.Textbox(label="Username")
                l_pass = gr.Textbox(label="Password", type="password")
                btn_login = gr.Button("Login")
                login_msg = gr.Textbox(interactive=False)

            with gr.Tab("Register"):
                r_user = gr.Textbox(label="Username")
                r_pass = gr.Textbox(label="Password", type="password")
                btn_reg = gr.Button("Register")
                reg_msg = gr.Textbox(interactive=False)

    # ===== PAGE 2 =====
    with gr.Column(visible=False) as page_detect:
        gr.Markdown("## 📤 Unggah Citra & Visualisasi Deteksi")

        img_input = gr.Image(type="pil", label="Citra Mentah")
        img_result = gr.Image(label="Hasil Deteksi")

        btn_detect = gr.Button("🔍 Proses Deteksi")
        result_display = gr.Markdown()

        btn_report = gr.Button("📄 Lihat Laporan")
        btn_back_login = gr.Button("⬅ Kembali")

    # ===== PAGE 3 =====
    with gr.Column(visible=False) as page_report:
        gr.Markdown("## 📑 Laporan Deteksi Pohon Durian")

        img_final = gr.Image(label="Citra Hasil Deteksi")
        txt_count = gr.Markdown()

        lokasi = gr.Textbox(label="Lokasi Lahan")
        luas = gr.Textbox(label="Luas Lahan (ha)")

        btn_pdf = gr.Button("⬇ Download Laporan PDF")
        pdf_file = gr.File()

        btn_back = gr.Button("⬅ Kembali")
        btn_logout = gr.Button("Logout")

    # ===== EVENTS =====
    btn_login.click(
        handle_login,
        [l_user, l_pass],
        [login_msg, login_state, user_state, page_auth, page_detect, page_report]
    )

    btn_reg.click(register_user, [r_user, r_pass], reg_msg)

    btn_detect.click(
        handle_detect,
        [img_input, login_state],
        [img_result, result_display, count_state, image_state],
        show_progress=True
    )

    btn_report.click(
        lambda img, c: (img, f"### 🌳 Jumlah Pohon Yang Terdeteksi\n## {c}"),
        [img_result, count_state],
        [img_final, txt_count]
    )

    btn_report.click(goto_report, outputs=[page_auth, page_detect, page_report])
    btn_back.click(back_to_detect, outputs=[page_auth, page_detect, page_report])
    btn_back_login.click(back_to_login, outputs=[page_auth, page_detect, page_report])
    btn_logout.click(logout, outputs=[user_state, login_state, page_auth, page_detect, page_report])

    btn_pdf.click(
        generate_pdf,
        [user_state, count_state, image_state, lokasi, luas],
        pdf_file
    )

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        show_error=True
    )