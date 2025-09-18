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
# Gebruik LOGO_URL als die gezet is, anders de boxed website-variant; als dat faalt, fallback op favicon.png lokaal.
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
        # Fallback: lokale bestandsnamen proberen
        for p in ["favicon.png", "logo.png", "static/favicon.png"]:
            if os.path.exists(p):
                return p
    return None

# ===== helpers =====
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

    def header(self):
        # Donkerblauwe balk + website-logo links
        self.set_fill_color(*DARKBLUE)
        self.rect(0, 0, 210, 24, "F")
        logo_path = ensure_logo_file()
        if logo_path:
            try:
                # Hoogte 10mm, behoud aspect
                self.image(logo_path, x=10, y=5, h=10)
            except Exception:
                pass
        # Titel rechts gecentreerd
        self.set_y(26)

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

    def table_header(self):
        # Kolomkop in hetzelfde donkerblauw als de header
        self.ufont(11, bold=True)
        self.set_fill_color(*DARKBLUE)
        self.set_text_color(255, 255, 255)
        self.cell(95, 8, self.utext("Vraag"), border=1, ln=0, align="L", fill=True)
        self.cell(0, 8, self.utext("Antwoord / Cijfers (klant & AI)"), border=1, ln=1, align="L", fill=True)
        self.set_text_color(0, 0, 0)

    def row_two_cols(self, left_text: str, right_answer: str, cust: str, ai: int):
        """
        Nette uitlijning: vraag en antwoord op gelijke hoogte.
        Bepaal hoogte per kolom en neem de max als rijhoogte.
        """
        x0 = self.get_x()
        y0 = self.get_y()
        w1 = 95
        w2 = 105  # resterend

        # Linker kolom (vraag) – meet hoogte
        self.ufont(11, bold=True)
        self.multi_cell(w1, 7, self.utext(left_text), border=1)
        y1 = self.get_y()
        h1 = y1 - y0

        # Rechter kolom – meet hoogte
        self.set_xy(x0 + w1, y0)
        self.ufont(11, bold=False)
        # Antwoord
        self.multi_cell(w2, 7, self.utext(f"Antwoord: {right_answer}"), border="LTR")
        y2_mid = self.get_y()
        # Band met cijfers
        self.set_x(x0 + w1)
        self.set_fill_color(*CELLBAND)
        self.set_text_color(255, 255, 255)
        self.cell(45, 8, self.utext(f"Cijfer klant: {cust}"), border="LBR", align="C", fill=True)
        self.set_text_color(0, 0, 0)
        self.cell(w2 - 45, 8, self.utext(f"Cijfer AI: {ai}"), border="LBR", ln=1)
        y2 = self.get_y()
        h2 = y2 - y0

        # Breng beide kolommen op gelijke hoogte
        hmax = max(h1, h2)
        if h1 < hmax:
            # Trek extra kaderlijn om linker kolom optisch te vullen
            self.set_xy(x0, y0 + h1)
            self.cell(w1, hmax - h1, "", border=1, ln=1)
        else:
            # Cursor op einde rij
            self.set_xy(x0, y0 + hmax)

# ===== routes =====
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

        # a) verzamel alle items en leid 'onderwerp' af uit de key prefix: SECTION_i_answer
        #    keys bevatten de sectienaam (zoals in de frontend: `${section}_${i}_answer`)
        items = []  # tuples: (vraag, antwoord, onderwerp, cust_score, ai_score)
        # We willen de originele volgorde aanhouden; sorteert op key werkt omdat prefix dat bewaart
        answer_keys = sorted(k for k in data.keys() if k.endswith("_answer"))
        for k in answer_keys:
            prefix = k[:-7]  # strip "_answer"
            vraag = data.get(prefix + "_label", k)
            antwoord = data.get(k, "")
            # onderwerp uit prefix (alles tot laatste "_")
            sect = prefix.rsplit("_", 1)[0]
            # klantcijfer
            cust_raw = data.get(prefix + "_customer_score", "")
            cust = "-"
            try:
                if str(cust_raw).strip() != "":
                    cust = str(int(cust_raw))
            except Exception:
                cust = "-"
            items.append((vraag, antwoord, sect, cust))

        # b) bouw PDF
        pdf = ReportPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Titel (onder balk)
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

        # c) Vragen per onderwerp, steeds twee vragen per onderwerp
        pdf.section_title("Vragen en antwoorden")

        # groepeer per onderwerp
        from collections import OrderedDict, defaultdict
        grouped = OrderedDict()
        for vraag, antwoord, sect, cust in items:
            grouped.setdefault(sect, []).append((vraag, antwoord, cust))

        # scoreregistratie voor radargrafiek
        radar_sections = []
        radar_vals = []

        # renderen
        for sect, rows in grouped.items():
            # onderwerp-kop
            pdf.ufont(12, bold=True)
            pdf.set_text_color(*DARKBLUE)
            pdf.cell(0, 7, pdf.utext(sect), ln=True)
            pdf.set_text_color(0, 0, 0)

            # kolomkop
            pdf.table_header()

            # twee vragen per onderwerp (zoals jouw formulier)
            ai_scores_for_avg = []
            cust_scores_for_avg = []

            for (vraag, antwoord, cust) in rows:
                ai_val = ai_score(antwoord, vraag)
                if cust != "-":
                    try:
                        cust_scores_for_avg.append(int(cust))
                    except Exception:
                        pass
                ai_scores_for_avg.append(ai_val)

                pdf.row_two_cols(vraag, antwoord, cust, ai_val)

            # gemiddelde per onderwerp (vier cijfers: 2x klant + 2x AI)
            # als er minder waarden zijn, neem het gemiddelde van wat er is
            all_vals = ai_scores_for_avg + cust_scores_for_avg
            subj_avg = round(sum(all_vals)/len(all_vals), 2) if all_vals else 0
            radar_sections.append(sect)
            radar_vals.append(subj_avg)
            pdf.ln(1)

        # d) Scores-overzicht
        all_ai = []
        all_cust = []
        for sect, rows in grouped.items():
            for (vraag, antwoord, cust) in rows:
                if cust != "-":
                    try:
                        all_cust.append(int(cust))
                    except Exception:
                        pass
                all_ai.append(ai_score(antwoord, vraag))
        avg_ai = round(sum(all_ai)/len(all_ai), 2) if all_ai else 0
        avg_cust = round(sum(all_cust)/len(all_cust), 2) if all_cust else 0

        pdf.ln(2)
        pdf.section_title("Scores")
        pdf.kv("Gemiddeld cijfer klant:", str(avg_cust if all_cust else "-"))
        pdf.kv("Gemiddeld cijfer AI:", str(avg_ai))

        # e) Samenvatting
        pairs_for_summary = [(v, a, s) for (v, a, s, _c) in [(it[0], it[1], it[2], it[3]) for it in items]]
        summary_text = ai_summary(pairs_for_summary)
        pdf.ln(3)
        pdf.section_title("Samenvatting AI")
        pdf.ufont(11, bold=False)
        pdf.multi_cell(0, 7, pdf.utext(summary_text))

        # f) Radargrafiek onderaan – gemiddeld per onderwerp
        if radar_sections:
            img_path = "radar.png"
            try:
                # Data voorbereiden
                labels = radar_sections
                values = radar_vals
                N = len(labels)
                # sluit de polygon
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

                pdf.ln(4)
                pdf.section_title("Radar – gemiddelde score per onderwerp")
                # plaats afbeelding, maximale breedte 180mm
                pdf.image(img_path, w=180)
            except Exception as e:
                app.logger.error(f"Kon radargrafiek niet maken: {e}")

        # g) PDF opslaan
        filename = "quickscan.pdf"
        pdf.output(filename)

        # h) E-mail (optioneel)
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
