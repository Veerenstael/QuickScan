from flask import Flask, request, jsonify
from flask_cors import CORS
from fpdf import FPDF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from datetime import datetime
import os
import re
import requests

# Headless plotting voor Render
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch

# ====== Optioneel OpenAI client ======
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
client = None
if OPENAI_KEY:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_KEY)
    except Exception:
        client = None

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

VERSION = "QS-2025-09-18-v11-stoplicht-pos-tuned"

# ---------- Kleuren (RGB) ----------
DARKBLUE = (34, 51, 68)        # kop en kolomkop
ACCENT   = (19, 209, 124)      # sectietitels
CELLBAND = (35, 49, 74)        # band onder in cellen

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

    def _download(url, path):
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

    ok_reg = _download(DEJAVU_REG_URL, DEJAVU_REG_FILE)
    ok_b   = _download(DEJAVU_BOLD_URL, DEJAVU_BOLD_FILE)
    FONTS_READY = ok_reg and ok_b
    return FONTS_READY

def sanitize_text_for_latin1(txt: str) -> str:
    if not isinstance(txt, str):
        txt = str(txt)
    replacements = {
        "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u20ac": "EUR", "\xa0": " "
    }
    for k, v in replacements.items():
        txt = txt.replace(k, v)
    try:
        return txt.encode("latin-1", "replace").decode("latin-1")
    except Exception:
        return txt

# ---------- Logo ----------
DEFAULT_LOGO_URL = os.getenv(
    "LOGO_URL",
    "https://www.veerenstael.nl/wp-content/uploads/2020/06/logo-veerenstael-wit.png"
)
LOCAL_LOGO_FILE = "veerenstael_header_logo.png"

def ensure_logo_file() -> str | None:
    if os.path.exists(LOCAL_LOGO_FILE) and os.path.getsize(LOCAL_LOGO_FILE) > 0:
        return LOCAL_LOGO_FILE
    try:
        r = requests.get(DEFAULT_LOGO_URL, timeout=15)
        r.raise_for_status()
        with open(LOCAL_LOGO_FILE, "wb") as f:
            f.write(r.content)
        return LOCAL_LOGO_FILE
    except Exception:
        for p in ["favicon.png", "logo.png", "static/favicon.png"]:
            if os.path.exists(p):
                return p
    return None

# ---------- Diagram-afbeelding (7 cirkels) ----------
DEFAULT_MODEL_IMAGE_URL = os.getenv("MODEL_IMAGE_URL", "")
LOCAL_MODEL_IMAGE = "afbeelding.png"         # Zet dit bestand naast app.py
MODEL_IMAGE_FILE = "model_overlay_base.png"  # interne cache-naam

def ensure_model_image() -> str | None:
    if os.path.exists(MODEL_IMAGE_FILE) and os.path.getsize(MODEL_IMAGE_FILE) > 0:
        return MODEL_IMAGE_FILE
    if os.path.exists(LOCAL_MODEL_IMAGE) and os.path.getsize(LOCAL_MODEL_IMAGE) > 0:
        try:
            with open(LOCAL_MODEL_IMAGE, "rb") as src, open(MODEL_IMAGE_FILE, "wb") as dst:
                dst.write(src.read())
            return MODEL_IMAGE_FILE
        except Exception:
            pass
    if DEFAULT_MODEL_IMAGE_URL:
        try:
            r = requests.get(DEFAULT_MODEL_IMAGE_URL, timeout=15)
            r.raise_for_status()
            with open(MODEL_IMAGE_FILE, "wb") as f:
                f.write(r.content)
            return MODEL_IMAGE_FILE
        except Exception:
            return None
    return None

# ===== AI helpers =====
def ai_score(answer, question):
    if not client:
        return 3
    prompt = (
        f"Beoordeel kort het volgende antwoord op de vraag '{question}': {answer}\n\n"
        "Geef uitsluitend één getal terug, van 1 (slecht) tot 5 (uitstekend)."
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        output = response.choices[0].message.content.strip()
        match = re.search(r"[1-5]", output)
        return int(match.group(0)) if match else 3
    except Exception:
        return 3

def ai_summary(pairs):
    if not client:
        return "Korte samenvatting: de ingevulde antwoorden zijn verzameld en geven aanknopingspunten voor verbetering binnen asset management. De uitwerking volgt in een vervolggesprek."
    regels = [f"{v}: {a}" for v, a, _sect in pairs]
    tekst = "\n".join(regels)
    prompt = (
        "Maak een korte zakelijke samenvatting (±5 zinnen) van deze QuickScan-antwoordset.\n\n"
        f"{tekst}\n\n"
        "Sluit af met een beknopte conclusie."
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return "Samenvatting kon niet worden gegenereerd."

# ===== PDF helper-klasse =====
class ReportPDF(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        unicode_ok = ensure_unicode_fonts()
        self.unicode_ok = unicode_ok
        if unicode_ok:
            try:
                self.add_font(FONT_REGULAR, "", DEJAVU_REG_FILE, uni=True)
                self.add_font(FONT_BOLD,    "", DEJAVU_BOLD_FILE, uni=True)
            except Exception:
                pass

    def ufont(self, size=11, bold=False):
        if self.unicode_ok:
            self.set_font(FONT_BOLD if bold else FONT_REGULAR, "", size)
        else:
            self.set_font("Arial", "B" if bold else "", size)

    def utext(self, text: str) -> str:
        return text if self.unicode_ok else sanitize_text_for_latin1(text)

    # ---- HULP: aantal regels berekenen zonder te printen ----
    def _nb_lines(self, w_mm: float, txt: str, bold: bool = False, size: int = 11, line_h: float = 7.0) -> int:
        prev_family, prev_style, prev_size_pt = self.font_family, self.font_style, self.font_size_pt
        self.ufont(size, bold)
        text = self.utext(txt or "")
        lines = 0
        for paragraph in text.split("\n"):
            words = paragraph.split(" ")
            if not words:
                lines += 1
                continue
            cur = ""
            for w in words:
                test = (cur + " " + w).strip()
                if self.get_string_width(test) <= w_mm:
                    cur = test
                else:
                    if cur == "":
                        chunk = ""
                        for ch in w:
                            if self.get_string_width(chunk + ch) <= w_mm:
                                chunk += ch
                            else:
                                lines += 1
                                chunk = ch
                        cur = chunk
                    else:
                        lines += 1
                        cur = w
            lines += 1
        self.set_font(prev_family, prev_style, prev_size_pt)
        return max(lines, 1)

    def header(self):
        # Donkerblauwe balk
        self.set_fill_color(*DARKBLUE)
        self.rect(0, 0, 210, 24, "F")

        # Logo links
        logo_path = ensure_logo_file()
        if logo_path:
            try:
                self.image(logo_path, x=10, y=5, h=10)
            except Exception:
                pass

        # Titel in de balk (midden, wit): "Quick Scan"
        self.set_text_color(255, 255, 255)
        self.ufont(14, bold=True)
        self.set_xy(0, 7)
        self.cell(0, 10, self.utext("Quick Scan"), align="C")
        self.set_text_color(0, 0, 0)
        self.set_y(26)

    def footer(self):
        self.set_y(-12)
        try:
            self.ufont(8, bold=False)
        except Exception:
            self.set_font("Arial", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Veerenstael Quick Scan · {VERSION}", align="C")

    def section_title(self, txt):
        self.ufont(12, bold=True)
        self.set_text_color(*ACCENT)
        self.cell(0, 8, self.utext(txt), ln=True)
        self.set_text_color(0, 0, 0)

    def kv(self, k, v):
        self.ufont(11, bold=False)
        self.cell(40, 7, self.utext(k), ln=0)
        self.ufont(11, bold=True)
        self.cell(0, 7, self.utext(v), ln=True)

    def _col_widths(self):
        try:
            total = self.epw
        except AttributeError:
            total = self.w - self.l_margin - self.r_margin
        w1 = total * 0.48
        w2 = total - w1
        return w1, w2

    def table_header(self):
        w1, w2 = self._col_widths()
        self.ufont(11, bold=True)
        self.set_fill_color(*DARKBLUE)
        self.set_text_color(255, 255, 255)
        self.cell(w1, 8, self.utext("Vraag"), border=1, ln=0, align="L", fill=True)
        self.cell(w2, 8, self.utext("Antwoord / Cijfers (klant & AI)"), border=1, ln=1, align="L", fill=True)
        self.set_text_color(0, 0, 0)

    def row_two_cols(self, left_text: str, right_answer: str, cust: str, ai: int):
        x0 = self.get_x()
        y0 = self.get_y()
        w1, w2 = self._col_widths()
        pad = 1.4
        line_h = 7.0
        band_h = 8.0

        h_left  = self._nb_lines(w1 - 2*pad, left_text, bold=True,  size=11, line_h=line_h) * line_h + 2*pad
        h_right_txt = self._nb_lines(w2 - 2*pad, f"Antwoord: {right_answer}", bold=False, size=11, line_h=line_h) * line_h + 2*pad
        h_right = h_right_txt + band_h
        h = max(h_left, h_right)

        self.rect(x0, y0, w1, h)
        self.rect(x0 + w1, y0, w2, h)

        self.set_xy(x0 + pad, y0 + pad); self.ufont(11, bold=True)
        self.multi_cell(w1 - 2*pad, line_h, self.utext(left_text), border=0)

        self.set_xy(x0 + w1 + pad, y0 + pad); self.ufont(11, bold=False)
        self.multi_cell(w2 - 2*pad, line_h, self.utext(f"Antwoord: {right_answer}"), border=0)

        y_band = y0 + h - band_h
        self.set_fill_color(*CELLBAND)
        self.rect(x0 + w1, y_band, w2, band_h, "F")
        self.set_text_color(255, 255, 255)
        self.set_xy(x0 + w1 + pad, y_band + (band_h - 6) / 2)
        kl_w = max(40, w2 * 0.42)
        self.cell(kl_w - pad, 6, self.utext(f"Cijfer klant: {cust}"), ln=0, align="C")
        self.cell(w2 - kl_w, 6, self.utext(f"Cijfer AI: {ai}"), ln=1, align="L")
        self.set_text_color(0, 0, 0)

        self.set_xy(x0, y0 + h)

# ===== Stoplicht-overlay =====
# NIEUWE posities in genormaliseerde coordinaten (x,y in 0..1) — uitgelijnd op jouw rode stippen
STOPLIGHT_POS = {
    "gegevens analyseren":                 (0.445, 0.215),  # rechts van de boven-linker cirkel
    "werk voorbereiden":                   (0.790, 0.215),  # rechts van de boven-rechter cirkel
    "uitvoeren werkzaamheden":             (0.940, 0.355),  # rechts van de rechter cirkel
    "werk afhandelen en controleren":      (0.755, 0.770),  # links van de onder-rechter cirkel
    "inregelen onderhoudsplan":            (0.410, 0.740),  # rechts van de onder-linker cirkel
    "maintenance & reliability engineering":(0.060, 0.530),  # links van de linker cirkel
    "am-strategie":                        (0.505, 0.390),  # boven de midden-cirkel
    "asset management strategie":          (0.505, 0.390),
    "am strategie":                        (0.505, 0.390),
}

def norm_name(s: str) -> str:
    t = (s or "").lower().strip()
    t = t.replace("’", "'").replace("&", " & ").replace("  ", " ")
    t = t.replace("werkvoorbereiding", "werk voorbereiden")
    t = t.replace("uitvoering onderhoud", "uitvoeren werkzaamheden")
    t = t.replace("maintenance-en reliability-engineering", "maintenance & reliability engineering")
    t = t.replace("maintenance- en reliability-engineering", "maintenance & reliability engineering")
    t = t.replace("maintenance en reliability engineering", "maintenance & reliability engineering")
    if "am" in t and "strategie" in t:
        t = "am-strategie"
    return t

def bucket_for_score(v: float) -> str:
    if v < 2.5:  return "red"
    if v <= 3.5: return "yellow"
    return "green"

def lamp_color(name: str) -> tuple:
    if name == "red":    return (0.85, 0.20, 0.20)
    if name == "yellow": return (1.00, 0.80, 0.00)
    if name == "green":  return (0.00, 0.70, 0.30)
    return (0.6, 0.6, 0.6)

def build_stoplight_overlay(section_labels, section_scores, out_path="stoplicht.png"):
    base_path = ensure_model_image()
    if not base_path:
        return None

    img = plt.imread(base_path)
    h, w = img.shape[0], img.shape[1]

    fig = plt.figure(figsize=(w/150, h/150), dpi=150)
    ax = plt.axes([0, 0, 1, 1])
    ax.imshow(img)
    ax.axis("off")

    # optioneel debug-raster met percentages
    if os.getenv("STOPLIGHT_DEBUG", "0") == "1":
        for i in range(11):
            ax.plot([w*i/10, w*i/10], [0, h], color=(1,1,1,0.15), lw=0.8)
            ax.plot([0, w], [h*i/10, h*i/10], color=(1,1,1,0.15), lw=0.8)
            ax.text(w*i/10, 12, f"{i/10:.1f}", color=(1,1,1,0.7), ha="center", va="top", fontsize=8)
            ax.text(20, h*i/10, f"{i/10:.1f}", color=(1,1,1,0.7), ha="left", va="center", fontsize=8)

    # stoplicht-maten
    housing_w = min(w, h) * 0.060
    housing_h = min(w, h) * 0.115
    radius    = housing_w * 0.20
    padding   = housing_w * 0.12

    for label, score in zip(section_labels, section_scores):
        key = norm_name(label)
        if key not in STOPLIGHT_POS:
            continue
        nx, ny = STOPLIGHT_POS[key]
        cx = nx * w
        cy = ny * h

        # behuizing
        box_x = cx - housing_w/2
        box_y = cy - housing_h/2
        shadow = FancyBboxPatch(
            (box_x+2, box_y+2), housing_w, housing_h,
            boxstyle="round,pad=0.012,rounding_size=6",
            linewidth=0.0, facecolor=(0,0,0,0.20)
        )
        ax.add_patch(shadow)
        box = FancyBboxPatch(
            (box_x, box_y), housing_w, housing_h,
            boxstyle="round,pad=0.012,rounding_size=6",
            linewidth=1.0, edgecolor=(1,1,1,0.9), facecolor=(0.15,0.17,0.20,0.85)
        )
        ax.add_patch(box)

        # lampjes
        centers = [
            (cx, box_y + padding + radius),                           # boven (rood)
            (cx, box_y + housing_h/2),                                # midden (geel)
            (cx, box_y + housing_h - padding - radius),               # onder (groen)
        ]
        active = bucket_for_score(score)

        for idx, (lx, ly) in enumerate(centers):
            name = ["red", "yellow", "green"][idx]
            col = lamp_color(name)
            if name != active:
                col = (col[0]*0.45, col[1]*0.45, col[2]*0.45)  # dim
            ax.add_patch(plt.Circle((lx, ly), radius*1.25, color=(1,1,1,0.18), ec="none"))
            lw = 2.2 if name == active else 1.0
            ax.add_patch(plt.Circle((lx, ly), radius, color=col, ec="white", lw=lw))

        # score-label boven de behuizing
        ax.text(cx, box_y - 8, f"{score:.1f}", ha="center", va="bottom", fontsize=11, color="white",
                bbox=dict(boxstyle="round,pad=0.25", fc=(0,0,0,0.55), ec="none"))

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

        # items: (vraag, antwoord, sectie, klantcijfer-string)
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

        # PDF
        pdf = ReportPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Meta
        pdf.ln(2)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        pdf.kv("Datum:", now)
        pdf.kv("Naam:", data.get("name", ""))
        pdf.kv("Bedrijf:", data.get("company", ""))
        pdf.kv("E-mail:", data.get("email", ""))
        pdf.kv("Telefoon:", data.get("phone", ""))
        pdf.ln(3)

        # Intro
        intro = data.get("introText", "")
        if intro:
            pdf.section_title("Introductie QuickScan")
            pdf.ufont(11, bold=False)
            pdf.multi_cell(0, 7, pdf.utext(intro))
            pdf.ln(2)

        # Groeperen per onderwerp (in volgorde)
        from collections import OrderedDict
        grouped = OrderedDict()
        for vraag, antwoord, sect, cust in items:
            grouped.setdefault(sect, []).append((vraag, antwoord, cust))

        MIN_SPACE_FOR_SECTION = 70  # mm

        radar_sections, radar_vals = [], []
        all_ai, all_cust = [], []

        pdf.section_title("Vragen en antwoorden")
        for sect, rows in grouped.items():
            remaining = pdf.h - pdf.b_margin - pdf.get_y()
            if remaining < MIN_SPACE_FOR_SECTION:
                pdf.add_page()

            pdf.ufont(12, bold=True)
            pdf.set_text_color(*DARKBLUE)
            pdf.cell(0, 7, pdf.utext(sect), ln=True)
            pdf.set_text_color(0, 0, 0)

            pdf.table_header()

            ai_scores_for_avg = []
            cust_scores_for_avg = []

            for (vraag, antwoord, cust) in rows:
                ai_val = ai_score(antwoord, vraag)
                ai_scores_for_avg.append(ai_val)
                all_ai.append(ai_val)
                if cust != "-":
                    try:
                        cust_int = int(cust)
                        cust_scores_for_avg.append(cust_int)
                        all_cust.append(cust_int)
                    except Exception:
                        pass

                pdf.row_two_cols(vraag, antwoord, cust, ai_val)

            all_vals = ai_scores_for_avg + cust_scores_for_avg
            subj_avg = round(sum(all_vals)/len(all_vals), 2) if all_vals else 0
            radar_sections.append(sect)
            radar_vals.append(subj_avg)
            pdf.ln(1)

        # Scores
        avg_ai = round(sum(all_ai)/len(all_ai), 2) if all_ai else 0
        avg_cust = round(sum(all_cust)/len(all_cust), 2) if all_cust else 0

        pdf.ln(2)
        pdf.section_title("Scores")
        pdf.kv("Gemiddeld cijfer klant:", str(avg_cust if all_cust else "-"))
        pdf.kv("Gemiddeld cijfer AI:", str(avg_ai))

        # Samenvatting
        pairs_for_summary = [(v, a, s) for (v, a, s, _c) in items]
        summary_text = ai_summary(pairs_for_summary)
        pdf.ln(3)
        pdf.section_title("Samenvatting AI")
        pdf.ufont(11, bold=False)
        pdf.multi_cell(0, 7, pdf.utext(summary_text))

        # Visuals (radar) + altijd afsluiten met stoplichtpagina
        if radar_sections:
            # RADAR
            pdf.add_page()
            def wrap_label(lbl: str) -> str:
                l = lbl.strip()
                if l.lower() == "uitvoering onderhoud":
                    return "Uitvoering\nonderhoud"
                if l == "Maintenance & Reliability Engineering":
                    return "Maintenance &\nReliability\nEngineering"
                return l

            img_path = "radar.png"
            try:
                labels = [wrap_label(s) for s in radar_sections]
                values = radar_vals
                N = len(labels)
                values_cycle = values + values[:1]
                angles = np.linspace(0, 2*np.pi, N, endpoint=False).tolist()
                angles += angles[:1]

                fig = plt.figure(figsize=(5, 5))
                ax = plt.subplot(111, polar=True)
                ax.set_theta_offset(np.pi / 2)
                ax.set_theta_direction(-1)

                ax.set_xticks(angles[:-1])
                ax.set_xticklabels(labels, fontsize=8)

                ax.set_rlabel_position(0)
                ax.set_yticks([1, 2, 3, 4, 5])
                ax.set_yticklabels(["1","2","3","4","5"], fontsize=7)
                ax.set_ylim(0, 5)

                ax.plot(angles, values_cycle)
                ax.fill(angles, values_cycle, alpha=0.25)

                fig.tight_layout()
                fig.savefig(img_path, dpi=180, bbox_inches="tight")
                plt.close(fig)

                pdf.section_title("Gemiddelde score per onderwerp")
                pdf.image(img_path, w=180)
            except Exception as e:
                app.logger.error(f"Kon radargrafiek niet maken: {e}")

            # STOPLICHT (laatste pagina)
            overlay_path = build_stoplight_overlay(radar_sections, radar_vals, out_path="stoplicht.png")
            if overlay_path:
                pdf.add_page()
                pdf.section_title("Stoplichtoverzicht per onderwerp")
                pdf.image(overlay_path, w=180)

        # PDF opslaan
        filename = "quickscan.pdf"
        pdf.output(filename)

        # E-mail (optioneel)
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

                body = (
                    f"Beste {data.get('name','')},\n\n"
                    "In de bijlage staat het rapport van de QuickScan met per vraag het antwoord en de cijfers (klant & AI).\n\n"
                    f"Samenvatting:\n{summary_text}\n\n"
                    "Met vriendelijke groet,\nVeerenstael"
                )
                msg.attach(MIMEText(body))

                with open(filename, "rb") as f:
                    attach = MIMEApplication(f.read(), _subtype="pdf")
                    attach.add_header("Content-Disposition", "attachment", filename=filename)
                    msg.attach(attach)

                smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
                smtp_port = int(os.getenv("SMTP_PORT", "587"))
                s = smtplib.SMTP(smtp_server, smtp_port)
                s.starttls()
                s.login(email_user, email_pass)
                s.send_message(msg)
                s.quit()
                email_sent = True
            except Exception as e:
                app.logger.error(f"E-mail verzenden mislukt: {e}")

        return jsonify({
            "total_score_ai": avg_ai,
            "total_score_customer": avg_cust if all_cust else "",
            "summary": summary_text,
            "email_sent": email_sent
        }), 200

    except Exception as e:
        app.logger.error(f"Fout in submit: {e}")
        return jsonify({"error": str(e)}), 500
