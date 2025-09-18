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

# ---------- Unicode helpers ----------
FONTS_READY = False
FONT_REGULAR = "DejaVu"
FONT_BOLD = "DejaVuB"

DEJAVU_REG_URL = "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans.ttf"
DEJAVU_BOLD_URL = "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans-Bold.ttf"
DEJAVU_REG_FILE = "DejaVuSans.ttf"
DEJAVU_BOLD_FILE = "DejaVuSans-Bold.ttf"


def ensure_unicode_fonts():
    """
    Download en registreer DejaVu Sans (regular & bold) zodat FPDF unicode tekens (zoals ‘ ’ “ ” – €) kan renderen.
    """
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
    ok_bold = _download(DEJAVU_BOLD_URL, DEJAVU_BOLD_FILE)

    # Font-registratie gebeurt pas in de PDF-instantie (zie ReportPDF.__init__)
    FONTS_READY = ok_reg and ok_bold
    return FONTS_READY


def sanitize_text_for_latin1(txt: str) -> str:
    """
    Nood-fallback: als het unicode font niet beschikbaar is, vervang enkele vaak voorkomende
    unicode-tekens door ASCII-equivalenten en forceer latin-1 (met '?').
    """
    if not isinstance(txt, str):
        txt = str(txt)

    replacements = {
        "\u2019": "'",  # right single quote
        "\u2018": "'",  # left single quote
        "\u201c": '"',  # left double quote
        "\u201d": '"',  # right double quote
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\u2026": "...",  # ellipsis
        "\u20ac": "EUR",  # euro
        "\xa0": " ",      # no-break space
    }
    for k, v in replacements.items():
        txt = txt.replace(k, v)

    try:
        # Forceer latin-1 compatibel
        return txt.encode("latin-1", "replace").decode("latin-1")
    except Exception:
        return txt  # laatste redmiddel


# ===== helpers =====
def ai_score(answer, question):
    """Geef score 1–5; valt terug op 3 zonder OpenAI of bij fout."""
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
    """Korte samenvatting; valt terug op generieke tekst zonder OpenAI."""
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
    """Zoek lokaal logo voor PDF-header (gebruik favicon.png indien aanwezig)."""
    for p in ["favicon.png", "logo.png", "static/favicon.png"]:
        if os.path.exists(p):
            return p
    return None


class ReportPDF(FPDF):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Probeer unicode fonts klaar te zetten
        unicode_ok = ensure_unicode_fonts()
        self.unicode_ok = unicode_ok

        if unicode_ok:
            # Registreer TTF fonts (uni=True vereist voor unicode)
            try:
                self.add_font(FONT_REGULAR, "", DEJAVU_REG_FILE, uni=True)
                self.add_font(FONT_BOLD, "", DEJAVU_BOLD_FILE, uni=True)
            except Exception:
                # In zeldzame gevallen kan add_font herhaald worden; negeer fouten
                pass

    def ufont(self, size=11, bold=False):
        """
        Stel een unicode-capabel font in als beschikbaar, anders fallback core-font (Arial).
        """
        if self.unicode_ok:
            if bold:
                self.set_font(FONT_BOLD, "", size)
            else:
                self.set_font(FONT_REGULAR, "", size)
        else:
            # Fallback: Latin-1 (kan sommige tekens niet aan)
            self.set_font("Arial", "B" if bold else "", size)

    def utext(self, text: str) -> str:
        """
        Tekst door de fallback-sanitizer als unicode-fonts ontbreken.
        """
        if self.unicode_ok:
            return text if isinstance(text, str) else str(text)
        return sanitize_text_for_latin1(text)

    def header(self):
        # Headerbalk
        self.set_fill_color(34, 51, 68)   # donkerblauw
        self.rect(0, 0, 210, 22, "F")
        logo_path = find_logo()
        if logo_path:
            try:
                self.image(logo_path, x=10, y=3, w=14)
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


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def home():
    return "✅ Veerenstael Quick Scan backend is live"


@app.route("/submit", methods=["POST", "OPTIONS"])
def submit():
    if request.method == "OPTIONS":
        return ("", 204)

    try:
        data = request.json or {}
        # Verzamel vragen/antwoorden uit payload
        vraag_antw_pairs = []
        keys = [k for k in data.keys() if k.endswith("_answer")]
        keys.sort()
        for k in keys:
            vraag = data.get(k.replace("_answer", "_label"), k)
            antwoord = data.get(k, "")
            vraag_antw_pairs.append((vraag, antwoord))

        # ===== PDF opbouwen =====
        pdf = ReportPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Titel
        pdf.ufont(16, bold=True)
        pdf.set_text_color(184, 199, 224)
        pdf.cell(0, 10, pdf.utext("Veerenstael Quick Scan"), ln=True, align="C")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(2)

        # Metadata
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

        # Tabelkop
        pdf.section_title("Vragen en antwoorden")
        pdf.ufont(11, bold=True)
        pdf.set_fill_color(62, 112, 255)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(95, 8, pdf.utext("Vraag"), border=1, ln=0, align="L", fill=True)
        pdf.cell(0, 8, pdf.utext("Antwoord / Cijfers (klant & AI)"), border=1, ln=1, align="L", fill=True)
        pdf.set_text_color(0, 0, 0)

        scores_ai = []
        scores_klant = []

        for vraag, antwoord in vraag_antw_pairs:
            # klantcijfer ophalen
            cust = "-"
            for key in data.keys():
                if key.endswith("_label") and data[key] == vraag:
                    prefix = key[:-6]
                    cust_val = data.get(prefix + "_customer_score", "")
                    if str(cust_val).strip() != "":
                        cust = str(cust_val)
                        try:
                            scores_klant.append(int(cust))
                        except Exception:
                            pass
                    break

            score_ai = ai_score(antwoord, vraag)
            scores_ai.append(score_ai)

            # render rij
            pdf.ufont(11, bold=True)
            pdf.multi_cell(95, 8, pdf.utext(f"{vraag}"), border=1)
            y_after = pdf.get_y()
            pdf.set_xy(105, y_after - 8)

            pdf.ufont(11, bold=False)
            pdf.multi_cell(0, 8, pdf.utext(f"Antwoord: {antwoord}"), border="LTR")
            pdf.set_x(105)
            pdf.set_fill_color(35, 49, 74)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(45, 8, pdf.utext(f"Cijfer klant: {cust}"), border="LBR", align="C", fill=True)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 8, pdf.utext(f"Cijfer AI: {score_ai}"), border="LBR", ln=1)
            pdf.ln(1)

        avg_ai = round(sum(scores_ai) / len(scores_ai), 2) if scores_ai else 0
        avg_cust = round(sum(scores_klant) / len(scores_klant), 2) if scores_klant else 0

        pdf.ln(2)
        pdf.section_title("Scores")
        pdf.kv("Gemiddeld cijfer klant:", str(avg_cust if scores_klant else "-"))
        pdf.kv("Gemiddeld cijfer AI:", str(avg_ai))

        pdf.ln(3)
        pdf.section_title("Samenvatting AI")
        summary_text = ai_summary(vraag_antw_pairs)
        pdf.ufont(11, bold=False)
        pdf.multi_cell(0, 7, pdf.utext(summary_text))

        filename = "quickscan.pdf"
        pdf.output(filename)

        # ===== E-mail (optioneel) =====
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
            "total_score_customer": avg_cust if scores_klant else "",
            "summary": summary_text,
            "email_sent": email_sent
        }), 200

    except Exception as e:
        app.logger.error(f"Fout in submit: {e}")
        return jsonify({"error": str(e)}), 500
