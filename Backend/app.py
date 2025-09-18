from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from fpdf import FPDF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from datetime import datetime
import os
import re

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
    regels = []
    for vraag, antwoord in pairs:
        regels.append(f"{vraag}: {antwoord}")
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
    """Zoek lokaal logo voor PDF-header."""
    for p in ["favicon.png", "logo.png", "static/favicon.png"]:
        if os.path.exists(p):
            return p
    return None

class ReportPDF(FPDF):
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
        self.set_font("Arial", "B", 12)
        self.set_text_color(19, 209, 124)
        self.cell(0, 8, txt, ln=True)
        self.set_text_color(0, 0, 0)

    def kv(self, k, v):
        self.set_font("Arial", "", 11)
        self.cell(40, 7, k, ln=0)
        self.set_font("Arial", "B", 11)
        self.cell(0, 7, v, ln=True)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/", methods=["GET"])
def home():
    return "✅ Veerenstael Quick Scan backend is live"

@app.route("/submit", methods=["POST", "OPTIONS"])
def submit():
    if request.method == "OPTIONS":
        # CORS preflight
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
        pdf.set_font("Arial", "B", 16)
        pdf.set_text_color(184, 199, 224)
        pdf.cell(0, 10, "Veerenstael Quick Scan", ln=True, align="C")
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
            pdf.set_font("Arial", "", 11)
            pdf.multi_cell(0, 7, intro)
            pdf.ln(2)

        # Tabelkop
        pdf.section_title("Vragen en antwoorden")
        pdf.set_font("Arial", "B", 11)
        pdf.set_fill_color(62, 112, 255)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(95, 8, "Vraag", border=1, ln=0, align="L", fill=True)
        pdf.cell(0, 8, "Antwoord / Cijfers (klant & AI)", border=1, ln=1, align="L", fill=True)
        pdf.set_text_color(0, 0, 0)

        scores_ai = []
        scores_klant = []

        for vraag, antwoord in vraag_antw_pairs:
            # klantcijfer ophalen (kan leeg zijn)
            base_key = None
            # reconstruct base_key door label te zoeken
            for cand in ["_label"]:
                pass
            # Zoek bijbehorende prefix in data op basis van label
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
            pdf.set_font("Arial", "B", 11)
            pdf.multi_cell(95, 8, f"{vraag}", border=1)
            y_after = pdf.get_y()
            pdf.set_xy(105, y_after - 8)

            pdf.set_font("Arial", "", 11)
            pdf.multi_cell(0, 8, f"Antwoord: {antwoord}", border="LTR")
            pdf.set_x(105)
            pdf.set_fill_color(35, 49, 74)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(45, 8, f"Cijfer klant: {cust}", border="LBR", align="C", fill=True)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 8, f"Cijfer AI: {score_ai}", border="LBR", ln=1)
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
        pdf.set_font("Arial", "", 11)
        pdf.multi_cell(0, 7, summary_text)

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
