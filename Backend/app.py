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
from openai import OpenAI

app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def ai_score(answer, question):
    """Geef score 1-4 voor antwoord"""
    prompt = (
        f"Beoordeel het volgende antwoord op de vraag '{question}': {answer}\n\n"
        "Geef uitsluitend één getal terug, van 1 (slecht) tot 4 (uitstekend)."
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        output = response.choices[0].message.content.strip()
        match = re.search(r"[1-4]", output)
        return int(match.group(0)) if match else 2
    except Exception as e:
        app.logger.error(f"OpenAI fout (score): {e}")
        return 2

def ai_summary(data):
    """Genereer korte samenvatting van antwoorden"""
    try:
        antwoorden = "\n".join([f"{k}: {v}" for k, v in data.items() if "_" in k])
        prompt = (
            f"Maak een korte samenvatting (ongeveer 5 zinnen) van deze Quick Scan antwoorden.\n\n"
            f"{antwoorden}\n\n"
            "Geef een zakelijke samenvatting en sluit af met een conclusie."
        )
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        app.logger.error(f"OpenAI fout (samenvatting): {e}")
        return "Samenvatting kon niet worden gegenereerd."

@app.route("/", methods=["GET"])
def home():
    return "✅ Veerenstael Quick Scan backend is live"

@app.route("/submit", methods=["POST"])
def submit():
    try:
        data = request.json
        app.logger.info(f"Ontvangen data: {data}")

        scores = []
        antwoorden_voor_summary = []

        # PDF opbouwen
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(200, 10, "Veerenstael Quick Scan", ln=True, align="C")
        pdf.set_font("Arial", "", 12)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        pdf.cell(200, 10, f"Datum: {now}", ln=True)
        pdf.cell(200, 10, f"Naam: {data.get('name','')}", ln=True)
        pdf.cell(200, 10, f"Bedrijf: {data.get('company','')}", ln=True)
        pdf.cell(200, 10, f"E-mail: {data.get('email','')}", ln=True)
        pdf.cell(200, 10, f"Telefoon: {data.get('phone','')}", ln=True)

        # Vragen en antwoorden verwerken
        for key, value in data.items():
            if "_" in key:
                score = ai_score(value, key)
                scores.append(score)
                antwoorden_voor_summary.append(f"{key}: {value}")
                pdf.multi_cell(0, 10, f"Vraag: {key}")
                pdf.multi_cell(0, 10, f"Antwoord: {value}")
                pdf.multi_cell(0, 10, f"Score: {score}")
                pdf.ln(5)

        total_score = round(sum(scores) / len(scores), 2) if scores else 0

        # AI-samenvatting
        summary_text = ai_summary(data)
        pdf.multi_cell(0, 10, f"Samenvatting AI:\n{summary_text}")

        filename = "quickscan.pdf"
        pdf.output(filename)

        # E-mail met PDF (naar gebruiker én Veerenstael)
        msg = MIMEMultipart()
        msg["From"] = os.getenv("EMAIL_USER")
        msg["To"] = data.get("email")
        msg["Cc"] = "quickscanveerenstael@gmail.com"
        msg["Subject"] = "Resultaten Veerenstael Quick Scan"
        msg.attach(MIMEText(
            f"Beste {data.get('name')},\n\n"
            f"In de bijlage vind je de resultaten van je Quick Scan.\n\n"
            f"Samenvatting:\n{summary_text}\n\n"
            f"Met vriendelijke groet,\nVeerenstael"
        ))

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
        return jsonify({"total_score": total_score, "summary": summary_text})

    except Exception as e:
        app.logger.error(f"Fout in submit: {e}")
        return jsonify({"error": str(e)}), 500
