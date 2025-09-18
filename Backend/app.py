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
import math
import matplotlib
matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt

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

# ---------- Kleuren, paden ----------
DARK_BLUE = (34, 51, 68)     # header + tabelkop
SCORE_BLUE = (35, 49, 74)    # scorebalkje bij antwoord
HEADER_LOGO_URL = "https://www.veerenstael.nl/wp-content/uploads/2020/06/logo-veerenstael-wit.png"
HEADER_LOGO_FILE = "veerenstael_header_logo.png"

# ---------- Unicode fonts ----------
FONTS_READY = False
FONT_REGULAR = "DejaVu"
FONT_BOLD = "DejaVuB"
DEJAVU_REG_URL = "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans.ttf"
DEJAVU_BOLD_URL = "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans-Bold.ttf"
DEJAVU_REG_FILE = "DejaVuSans.ttf"
DEJAVU_BOLD_FILE = "DejaVuSans-Bold.ttf"


def ensure_file(url: str, path: str) -> bool:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return True
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        with open(path, "wb") as f:
            f.write(r.content)
        return True
    except Exception:
        return False


def ensure_unicode_fonts():
    global FONTS_READY
    if FONTS_READY:
        return True
    ok_reg = ensure_file(DEJAVU_REG_URL, DEJAVU_REG_FILE)
    ok_bold = ensure_file(DEJAVU_BOLD_URL, DEJAVU_BOLD_FILE)
    FONTS_READY = ok_reg and ok_bold
    return FONTS_READY


def sanitize_text_for_latin1(txt: str) -> str:
    if not isinstance(txt, str):
        txt = str(txt)
    replacements = {
        "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u20ac": "EUR", "\xa0": " ",
    }
    for k, v in replacements.items():
        txt = txt.replace(k, v)
    try:
        return txt.encode("latin-1", "replace").decode("latin-1")
    except Exception:
        return txt


def ai_score(answer, question):
    """Score 1–5; valt terug op 3 zonder OpenAI of bij fout."""
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
    regels = [f"{vraag}: {antwoord}" for vraag, antwoord in pairs]
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


def find_logo():
    """Gebruik lokaal logo indien aanwezig, anders download de witte header-variant van de site."""
    if os.path.exists(HEADER_LOGO_FILE) and os.path.getsize(HEADER_LOGO_FILE) > 0:
        return HEADER_LOGO_FILE
    ok = ensure_file(HEADER_LOGO_URL, HEADER_LOGO_FILE)
    return HEADER_LOGO_FILE if ok else None


class ReportPDF(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        unicode_ok = ensure_unicode_fonts()
        self.unicode_ok = unicode_ok
        if unicode_ok:
            try:
                self.add_font(FONT_REGULAR, "", DEJAVU_REG_FILE, uni=True)
                self.add_font(FONT_BOLD, "", DEJAVU_BOLD_FILE, uni=True)
            except Exception:
                pass

    # shorthand voor font + sanitizer
    def ufont(self, size=11, bold=False):
        if self.unicode_ok:
            self.set_font(FONT_BOLD if bold else FONT_REGULAR, "", size)
        else:
            self.set_font("Arial", "B" if bold else "", size)

    def utext(self, text: str) -> str:
        return text if self.unicode_ok else sanitize_text_for_latin1(text)

    def header(self):
        # Donkerblauwe kopbalk
        self.set_fill_color(*DARK_BLUE)
        self.rect(0, 0, 210, 22, "F")
        logo_path = find_logo()
        if logo_path:
            try:
                # wit logo op donkere achtergrond
                self.image(logo_path, x=10, y=3, w=40)
            except Exception:
                pass
        self.set_y(26)

    def section_title(self, txt):
        self.ufont(12, bold=True)
        self.set_text_color(19, 209, 124)
        self.cell(0, 8, self.utext(txt), ln=True)
        self.set_text_color(0, 0, 0)

    def kv(self, k, v):
        self.ufont(11, bold=False)
        self.cell(40, 7, self.utext(k), ln=0)
        self.ufont(11, bold=True)
        self.cell(0, 7, self.utext(v), ln=True)

    # helpers om rijen met gelijke hoogte te tekenen
    def text_height(self, w, h, txt):
        lines = self.multi_cell(w, h, self.utext(txt), split_only=True)
        return h * max(1, len(lines))

    def row_qna(self, vraag, antwoord, cust, ai, w_left=95, w_right=95, lh=8):
        # meet hoogte in beide kolommen, zodat ze gelijk zijn
        h_left = self.text_height(w_left, lh, vraag)
        # Antwoord-blok bestaat uit 2 multi-cells: tekst en scores; reken totale hoogte uit
        h_ans = self.text_height(w_right, lh, f"Antwoord: {antwoord}")
        h_scores = lh  # 1 rij
        h_right = h_ans + h_scores
        row_h = max(h_left, h_right)

        # startpositie
        x0, y0 = self.get_x(), self.get_y()

        # linkerkolom (Vraag)
        self.ufont(11, bold=True)
        self.multi_cell(w_left, lh, self.utext(vraag), border=1)
        # reset naar start van rechterkolom
        self.set_xy(x0 + w_left, y0)

        # rechterkolom (Antwoord + scores)
        self.ufont(11, bold=False)
        # Antwoord (top)
        self.multi_cell(w_right, lh, self.utext(f"Antwoord: {antwoord}"), border="LTR")
        # Scores (onder)
        self.set_x(x0 + w_left)
        self.set_fill_color(*SCORE_BLUE)
        self.set_text_color(255, 255, 255)
        self.cell(45, lh, self.utext(f"Cijfer klant: {cust}"), border="LBR", align="C", fill=True)
        self.set_text_color(0, 0, 0)
        self.cell(w_right - 45, lh, self.utext(f"Cijfer AI: {ai}"), border="LBR", ln=1)

        # corrigeer Y indien rechts lager uitkwam dan links
        y_end = max(y0 + row_h, self.get_y())
        self.set_xy(x0, y_end)


def generate_radar(scores_by_topic, out_file="radar.png"):
    """
    scores_by_topic: dict {topic: float_score}
    Maakt een radar/spider chart en slaat op als PNG.
    """
    labels = list(scores_by_topic.keys())
    values = [scores_by_topic[k] for k in labels]

    # radar sluit de cirkel, dus laatste punt = eerste punt
    angles = [n / float(len(labels)) * 2 * math.pi for n in range(len(labels))]
    angles += angles[:1]
