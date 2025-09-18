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
from openai import OpenAI

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ===== helpers =====
def ai_score(answer, question):
    """Geef score 1-5 voor antwoord"""
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
    except Exception as e:
        app.logger.error(f"OpenAI fout (score): {e}")
        return 3

def ai_summary(data):
    """Genereer korte samenvatting van antwoorden"""
    try:
        # verzamel alle vraag/antwoordregels
        regels = []
        for k, v in data.items():
            if k.endswith("_answer"):
                label_key = k.replace("_answer", "_label")
                vraag = data.get(label_key, k)
                regels.append(f"{vraag}: {v}")
        antwoorden = "\n".join(regels)

        prompt = (
            "Maak een korte zakelijke samenvatting (±5 zinnen) van deze QuickScan-antwoordset.\n\n"
            f"{antwoorden}\n\n"
            "Sluit af met een beknopte conclusie."
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        app.logger.error(f"OpenAI fout (samenvatting): {e}")
        return "Samenvatting kon niet worden gegenereerd."

def fetch_logo(path="veerenstael_logo.png"):
    """Download het Veerenstael-logo indien nog niet aanwezig (voor PDF-header)."""
    if not os.path.exists(path):
        try:
            url = "https://www.veerenstael.nl/wp-content/uploads/2020/06/logo-veerenstael-wit.png"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)
        except Exception as e:
            app.logger.error(f"Kon logo niet ophalen: {e}")
            return None
    return path if os.path.exists(path) else None

class ReportPDF(FPDF):
    def header(self):
        # bovenbalk + logo
        self.set_fill_color(34, 51, 68)   # donkerblauw
        self.rect(0, 0, 210, 22, "F")
        logo_path = fetch_logo()
        if logo_path:
            self.image(logo_path, x=10, y=3, w=50)
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

@app.route("/", methods=["GET"])
def home():
    return "✅ Veerenstael Quick Scan backend is live"

@app.route("/submit", methods=["POST"])
def submit():
    try:
        data = request.json
        app.logger.info(f"Ontvangen data: {data}")

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

        # Intro (exact zoals in het formulier zichtbaar)
        intro = data.get("introText", "")
        if intro:
            pdf.section_title("Introductie QuickScan")
            pdf.set_font("Arial", "", 11)
            pdf.multi_cell(0, 7, intro)
            pdf.ln(2)

        # Tabelkop
        pdf.section_title("Vragen en antwoorden")
        pdf.set_font("Arial", "B", 11)
        pdf.set_fill_color(62, 112, 255)     # blauw voor kolomkop
        pdf.set_text_color(255, 255, 255)
        pdf.cell(95, 8, "Vraag", border=1, ln=0, align="L", fill=True)
        pdf.cell(0, 8, "Antwoord / Cijfers (klant & AI)", border=1, ln=1, align="L", fill=True)
        pdf.set_text_color(0, 0, 0)

        # Inhoud
        scores_ai = []
        scores_klant = []

        for key in sorted([k for k in data.keys() if k.endswith("_answer")]):
            label = data.get(key.replace("_answer", "_label"), key)
            answer = data.get(key, "")
            cust_score = data.get(key.replace("_answer", "_customer_score"), "")
            try:
                cust_score_int = int(cust_score)
            except:
                cust_score_int = 0

            score_ai = ai_score(answer, label)

            # bewaar voor totalen
            if cust_score_int:
                scores_klant.append(cust_score_int)
            scores_ai.append(score_ai)

            # rij renderen
            pdf.set_font("Arial", "B", 11)
            pdf.multi_cell(95, 8, f"{label}", border=1)
            y_after = pdf.get_y()
            x_after = pdf.get_x()
            pdf.set_xy(105, y_after - 8)

            pdf.set_font("Arial", "", 11)
            pdf.multi_cell(0, 8, f"Antwoord: {answer}", border="LTR")
            pdf.set_x(105)
            pdf.set_fill_color(35, 49, 74)     # donkerblauwe balk
            pdf.set_text_color(255, 255, 255)
            pdf.cell(45, 8, f"Cijfer klant: {cust_score_int if cust_score_int else '-'}", border="LBR", align="C", fill=True)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(0, 8, f"Cijfer AI: {score_ai}", border="LBR", ln=1)
            pdf.ln(1)

        # Gemiddelden
        avg_ai = round(sum(scores_ai) / len(scores_ai), 2) if scores_ai else 0
        avg_cust = round(sum(scores_klant) / len(scores_klant), 2) if scores_klant else 0

        pdf.ln(2)
        pdf.section_title("Scores")
        pdf.kv("Gemiddeld cijfer klant:", str(avg_cust))
        pdf.kv("Gemiddeld cijfer AI:", str(avg_ai))

        # AI-samenvatting
        pdf.ln(3)
        pdf.section_title("Samenvatting AI")
        summary_text = ai_summary(data)
        pdf.set_font("Arial", "", 11)
        pdf.multi_cell(0, 7, summary_text)

        filename = "quickscan.pdf"
        pdf.output(filename)

        # ===== E-mail met PDF =====
        msg = MIMEMultipart()
        msg["From"] = os.getenv("EMAIL_USER")
        msg["To"] = data.get("email")
        msg["Cc"] = "quickscanveerenstael@gmail.com"
        msg["Subject"] = "Resultaten Veerenstael Quick Scan"

        body = (
            f"Beste {data.get('name')},\n\n"
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
        s.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"))
        s.send_message(msg)
        s.quit()

        app.logger.info("QuickScan succesvol verstuurd")
        return jsonify({
            "total_score_ai": avg_ai,
            "total_score_customer": avg_cust,
            "summary": summary_text
        })

    except Exception as e:
        app.logger.error(f"Fout in submit: {e}")
        return jsonify({"error": str(e)}), 500
