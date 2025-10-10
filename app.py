from flask import Flask, request, jsonify
from flask_cors import CORS
from fpdf import FPDF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from datetime import datetime
import os
import json
import requests

# Headless plotting
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

VERSION = "QS-2025-10-10-Netlify-Render-NoAI"

# ---------- Kleuren (RGB) ----------
DARKBLUE = (34, 51, 68)
ACCENT   = (19, 209, 124)
CELLBAND = (35, 49, 74)

# ---------- Unicode fonts ----------
FONTS_READY = False
FONT_REGULAR = "DejaVu"
FONT_BOLD = "DejaVuB"
DEJAVU_REG_URL = "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans.ttf"
DEJAVU_BOLD_URL = "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans-Bold.ttf"
DEJAVU_REG_FILE = "DejaVuSans.ttf"
DEJAVU_BOLD_FILE = "DejaVuSans-Bold.ttf"

def ensure_unicode_fonts():
    global FONTS_READY
    if FONTS_READY:
        return True
    def _dl(url, path):
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return True
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)
            return True
        except Exception:
            return False
    ok1 = _dl(DEJAVU_REG_URL, DEJAVU_REG_FILE)
    ok2 = _dl(DEJAVU_BOLD_URL, DEJAVU_BOLD_FILE)
    FONTS_READY = ok1 and ok2
    return FONTS_READY

def sanitize_text_for_latin1(txt: str) -> str:
    if not isinstance(txt, str):
        txt = str(txt)
    repl = {"\u2019":"'", "\u2018":"'", "\u201c":'"', "\u201d":'"',
            "\u2013":"-", "\u2014":"-", "\u2026":"...", "\u20ac":"EUR", "\xa0":" "}
    for k, v in repl.items():
        txt = txt.replace(k, v)
    try:
        return txt.encode("latin-1", "replace").decode("latin-1")
    except Exception:
        return txt

# ---------- Diagram-afbeelding ----------
LOCAL_MODEL_IMAGE = "afbeelding.png"
MODEL_IMAGE_FILE = "model_overlay_base.png"

def ensure_model_image() -> str | None:
    if os.path.exists(MODEL_IMAGE_FILE) and os.path.getsize(MODEL_IMAGE_FILE) > 0:
        return MODEL_IMAGE_FILE
    if os.path.exists(LOCAL_MODEL_IMAGE) and os.path.getsize(LOCAL_MODEL_IMAGE) > 0:
        with open(LOCAL_MODEL_IMAGE, "rb") as src, open(MODEL_IMAGE_FILE, "wb") as dst:
            dst.write(src.read())
            return MODEL_IMAGE_FILE
    return None

# ===== PDF helper =====
class ReportPDF(FPDF):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.unicode_ok = ensure_unicode_fonts()
        if self.unicode_ok:
            try:
                self.add_font(FONT_REGULAR, "", DEJAVU_REG_FILE, uni=True)
                self.add_font(FONT_BOLD, "", DEJAVU_BOLD_FILE, uni=True)
            except Exception:
                pass

    def ufont(self, size=11, bold=False):
        self.set_font(
            FONT_BOLD if (bold and self.unicode_ok) else (FONT_REGULAR if self.unicode_ok else "Arial"),
            "" if self.unicode_ok else ("B" if bold else ""),
            size
        )

    def utext(self, t):
        return t if self.unicode_ok else sanitize_text_for_latin1(t)

    def _nb_lines(self, w, txt, bold=False, size=11, line_h=7.0):
        pf, ps, pz = self.font_family, self.font_style, self.font_size_pt
        self.ufont(size, bold)
        text = self.utext(txt or "")
        lines = 0
        for par in text.split("\n"):
            words = par.split(" ")
            cur = ""
            if not words:
                lines += 1
                continue
            for w2 in words:
                test = (cur + " " + w2).strip()
                if self.get_string_width(test) <= w:
                    cur = test
                else:
                    if cur == "":
                        ch = ""
                        for c in w2:
                            if self.get_string_width(ch + c) <= w:
                                ch += c
                            else:
                                lines += 1
                                ch = c
                        cur = ch
                    else:
                        lines += 1
                        cur = w2
            lines += 1
        self.set_font(pf, ps, pz)
        return max(lines, 1)

    def header(self):
        self.set_fill_color(*DARKBLUE)
        self.rect(0, 0, 210, 24, "F")
        self.set_text_color(255, 255, 255)
        self.ufont(14, True)
        self.set_xy(0, 7)
        self.cell(0, 10, self.utext("Quick Scan"), align="C")
        self.set_text_color(0, 0, 0)
        self.set_y(26)

    def footer(self):
        self.set_y(-12)
        self.ufont(8, False)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Veerenstael Quick Scan · {VERSION}", align="C")

    def section_title(self, txt):
        self.ufont(12, True)
        self.set_text_color(*ACCENT)
        self.cell(0, 8, self.utext(txt), ln=True)
        self.set_text_color(0, 0, 0)

    def kv(self, k, v):
        self.ufont(11, False)
        self.cell(40, 7, self.utext(k), ln=0)
        self.ufont(11, True)
        self.cell(0, 7, self.utext(v), ln=True)

    def _col_widths(self):
        total = getattr(self, "epw", self.w - self.l_margin - self.r_margin)
        w1 = total * 0.48
        return w1, total - w1

    def table_header(self):
        w1, w2 = self._col_widths()
        self.ufont(11, True)
        self.set_fill_color(*DARKBLUE)
        self.set_text_color(255, 255, 255)
        self.cell(w1, 8, self.utext("Vraag"), 1, 0, "L", True)
        self.cell(w2, 8, self.utext("Antwoord / Cijfer (klant)"), 1, 1, "L", True)
        self.set_text_color(0, 0, 0)

    def row_two_cols(self, left, right, cust):
        x0, y0 = self.get_x(), self.get_y()
        w1, w2 = self._col_widths()
        pad = 1.4
        lh = 7.0
        band_h = 8.0
        h_left = self._nb_lines(w1 - 2 * pad, left, True, 11, lh) * lh + 2 * pad
        h_txt = self._nb_lines(w2 - 2 * pad, f"Antwoord: {right}", False, 11, lh) * lh + 2 * pad
        h = max(h_left, h_txt + band_h)

        self.rect(x0, y0, w1, h)
        self.rect(x0 + w1, y0, w2, h)
        self.set_xy(x0 + pad, y0 + pad)
        self.ufont(11, True)
        self.multi_cell(w1 - 2 * pad, lh, self.utext(left), 0)
        self.set_xy(x0 + w1 + pad, y0 + pad)
        self.ufont(11, False)
        self.multi_cell(w2 - 2 * pad, lh, self.utext(f"Antwoord: {right}"), 0)
        yb = y0 + h - band_h
        self.set_fill_color(*CELLBAND)
        self.rect(x0 + w1, yb, w2, band_h, "F")
        self.set_text_color(255, 255, 255)
        self.set_xy(x0 + w1 + pad, yb + (band_h - 6) / 2)
        self.cell(w2 - pad, 6, self.utext(f"Cijfer klant: {cust}"), 0, 1, "L")
        self.set_text_color(0, 0, 0)
        self.set_xy(x0, y0 + h)

# ===== Stoplicht-overlay =====
DEFAULT_STOPLIGHT_TOPPOS = {
    "gegevens analyseren": [0.39, 0.13],
    "werk voorbereiden": [0.77, 0.13],
    "uitvoeren werkzaamheden": [0.96, 0.43],
    "werk afhandelen en controleren": [0.77, 0.72],
    "inregelen onderhoudsplan": [0.39, 0.72],
    "maintenance & reliability engineering": [0.025, 0.43],
    "am-strategie": [0.50, 0.28],
}

def norm_name(s: str) -> str:
    t = (s or "").lower().strip()
    t = t.replace("'", "'").replace("&", " & ").replace("  ", " ")
    t = t.replace("werkvoorbereiding", "werk voorbereiden")
    t = t.replace("uitvoering onderhoud", "uitvoeren werkzaamheden")
    if t in ("analyse gegevens", "analyse van gegevens", "gegevensanalyse", "data analyse", "data-analyse"):
        t = "gegevens analyseren"
    if "am" in t and "strategie" in t:
        t = "am-strategie"
    if "maintenance" in t and "reliability" in t:
        t = "maintenance & reliability engineering"
    return t

def bucket_for_score(v: float) -> str:
    if v < 2.5:
        return "red"
    if v <= 3.5:
        return "yellow"
    return "green"

def lamp_color(name: str) -> tuple:
    return {
        "red": (0.85, 0.20, 0.20),
        "yellow": (1.00, 0.80, 0.00),
        "green": (0.00, 0.70, 0.30)
    }.get(name, (0.6, 0.6, 0.6))

def build_stoplight_overlay(section_labels, section_scores, out_path="stoplicht.png"):
    base_path = ensure_model_image()
    if not base_path:
        return None
    
    img = plt.imread(base_path)
    h, w = img.shape[0], img.shape[1]

    toppos = dict(DEFAULT_STOPLIGHT_TOPPOS)

    fig = plt.figure(figsize=(w / 150, h / 150), dpi=150)
    ax = plt.axes([0, 0, 1, 1])
    ax.imshow(img)
    ax.axis("off")

    housing_w = min(w, h) * 0.060
    housing_h = min(w, h) * 0.115
    radius = housing_w * 0.20
    padding = housing_w * 0.12

    for label, score in zip(section_labels, section_scores):
        key = norm_name(label)
        if key not in toppos:
            continue
        nx, ny = toppos[key]
        cx, top_y = nx * w, ny * h
        cx = max(housing_w / 2, min(w - housing_w / 2, cx))
        top_y = max(0, min(h - housing_h, top_y))

        box_x = cx - housing_w / 2
        box_y = top_y
        shadow = FancyBboxPatch(
            (box_x + 2, box_y + 2), housing_w, housing_h,
            boxstyle="round,pad=0.012,rounding_size=6",
            linewidth=0.0, facecolor=(0, 0, 0, 0.20)
        )
        ax.add_patch(shadow)
        box = FancyBboxPatch(
            (box_x, box_y), housing_w, housing_h,
            boxstyle="round,pad=0.012,rounding_size=6",
            linewidth=1.0, edgecolor=(1, 1, 1, 0.9),
            facecolor=(0.15, 0.17, 0.20, 0.85)
        )
        ax.add_patch(box)

        centers = [
            (cx, box_y + padding + radius),
            (cx, box_y + housing_h / 2),
            (cx, box_y + housing_h - padding - radius)
        ]
        active = bucket_for_score(score)
        for idx, (lx, ly) in enumerate(centers):
            name = ["red", "yellow", "green"][idx]
            col = lamp_color(name)
            if name != active:
                col = (col[0] * 0.45, col[1] * 0.45, col[2] * 0.45)
            ax.add_patch(plt.Circle((lx, ly), radius * 1.25, color=(1, 1, 1, 0.18), ec="none"))
            lw = 2.2 if name == active else 1.0
            ax.add_patch(plt.Circle((lx, ly), radius, color=col, ec="white", lw=lw))

        ax.text(
            cx, box_y - 6, f"{score:.1f}", ha="center", va="top",
            fontsize=11, color="white",
            bbox=dict(boxstyle="round,pad=0.25", fc=(0, 0, 0, 0.55), ec="none")
        )

    fig.savefig(out_path, dpi=150, transparent=False)
    plt.close(fig)
    return out_path

# ===== routes =====
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/version", methods=["GET"])
def version():
    return jsonify({"version": VERSION}), 200

@app.route("/", methods=["GET"])
def home():
    return "✅ Veerenstael Quick Scan backend is live"

@app.route("/submit", methods=["POST", "OPTIONS"])
def submit():
    if request.method == "OPTIONS":
        return ("", 204)
    
    try:
        data = request.json or {}

        # Verzamel items
        items = []
        for k in [k for k in data.keys() if k.endswith("_answer")]:
            prefix = k[:-7]
            vraag = data.get(prefix + "_label", k)
            antwoord = data.get(k, "")
            sect = prefix.rsplit("_", 1)[0]
            cust_raw = data.get(prefix + "_customer_score", "")
            cust = "-"
            try:
                if str(cust_raw).strip() != "":
                    cust = str(int(cust_raw))
            except Exception:
                cust = "-"
            items.append((vraag, antwoord, sect, cust))

        # Genereer PDF
        pdf = ReportPDF()
        pdf.add_page()
        pdf.set_auto_page_break(True, 15)
        pdf.ln(2)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        pdf.kv("Datum:", now)
        pdf.kv("Naam:", data.get("name", ""))
        pdf.kv("Bedrijf:", data.get("company", ""))
        pdf.kv("E-mail:", data.get("email", ""))
        pdf.kv("Telefoon:", data.get("phone", ""))
        pdf.ln(3)

        # Groepeer per onderwerp
        from collections import OrderedDict
        grouped = OrderedDict()
        for v, a, s, c in items:
            grouped.setdefault(s, []).append((v, a, c))

        radar_sections, radar_vals = [], []
        pdf.section_title("Vragen en antwoorden")
        
        for sect, rows in grouped.items():
            pdf.ufont(12, True)
            pdf.set_text_color(*DARKBLUE)
            pdf.cell(0, 7, pdf.utext(sect), ln=True)
            pdf.set_text_color(0, 0, 0)
            pdf.table_header()
            cust_scores = []
            for vraag, antwoord, cust in rows:
                if cust != "-":
                    try:
                        ci = int(cust)
                        cust_scores.append(ci)
                    except Exception:
                        pass
                pdf.row_two_cols(vraag, antwoord, cust)
            subj_avg = round(sum(cust_scores) / len(cust_scores), 2) if cust_scores else 0
            radar_sections.append(sect)
            radar_vals.append(subj_avg)
            pdf.ln(1)

        # Radargrafiek
        if radar_sections:
            pdf.add_page()
            img_path = "radar.png"
            try:
                labels = radar_sections
                values = radar_vals
                N = len(labels)
                values_cycle = values + values[:1]
                angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
                angles += angles[:1]
                fig = plt.figure(figsize=(5, 5))
                ax = plt.subplot(111, polar=True)
                ax.set_theta_offset(np.pi / 2)
                ax.set_theta_direction(-1)
                ax.set_xticks(angles[:-1])
                ax.set_xticklabels(labels, fontsize=8)
                ax.set_rlabel_position(0)
                ax.set_yticks([1, 2, 3, 4, 5])
                ax.set_yticklabels(["1", "2", "3", "4", "5"], fontsize=7)
                ax.set_ylim(0, 5)
                ax.plot(angles, values_cycle)
                ax.fill(angles, values_cycle, alpha=0.25)
                fig.tight_layout()
                fig.savefig(img_path, dpi=180, bbox_inches="tight")
                plt.close(fig)
                pdf.section_title("Gemiddelde score per onderwerp (klant)")
                pdf.image(img_path, w=180)
            except Exception as e:
                app.logger.error(f"Radar error: {e}")

            # Stoplicht
            overlay_path = build_stoplight_overlay(radar_sections, radar_vals)
            if overlay_path:
                pdf.add_page()
                pdf.section_title("Stoplichtoverzicht per onderwerp")
                pdf.image(overlay_path, w=180)

        filename = "quickscan.pdf"
        pdf.output(filename)

        # Email
        email_user = os.getenv("EMAIL_USER")
        email_pass = os.getenv("EMAIL_PASS")
        email_to = data.get("email", "")
        email_sent = False

        if email_user and email_pass and email_to:
            try:
                msg = MIMEMultipart()
                msg["From"] = email_user
                msg["To"] = email_to
                msg["Cc"] = os.getenv("EMAIL_CC", "")
                msg["Subject"] = "Resultaten Veerenstael Quick Scan"
                body = f"Beste {data.get('name', '')},\n\nIn de bijlage staat het rapport van de QuickScan met alle vragen, antwoorden en jouw cijfers.\n\nMet vriendelijke groet,\nVeerenstael"
                msg.attach(MIMEText(body))
                with open(filename, "rb") as f:
                    attach = MIMEApplication(f.read(), _subtype="pdf")
                    attach.add_header("Content-Disposition", "attachment", filename=filename)
                    msg.attach(attach)
                
                smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
                smtp_port = int(os.getenv("SMTP_PORT", "587"))
                s = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
                s.starttls()
                s.login(email_user, email_pass)
                s.send_message(msg)
                s.quit()
                email_sent = True
                print("Email met PDF verzonden!")
            except Exception as e:
                app.logger.error(f"Email error: {e}")

        # Bereken totaal gemiddelde
        all_cust_scores = [float(c) for _, _, _, c in items if c != "-"]
        avg_cust = round(sum(all_cust_scores) / len(all_cust_scores), 2) if all_cust_scores else 0

        return jsonify({
            "total_score_customer": avg_cust if all_cust_scores else "",
            "email_sent": email_sent
        }), 200

    except Exception as e:
        app.logger.error(f"Error in submit: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
