from flask import Flask, request, jsonify
from fpdf import FPDF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from datetime import datetime
import openai
import os

app = Flask(__name__)

# Zet je OpenAI API key als environment variable in Render
openai.api_key = os.getenv("OPENAI_API_KEY")

def ai_score(answer, question):
    """Vraag de AI om een score tussen 1 en 4"""
    prompt = f"Geef een score van 1 (slecht) tot 4 (uitstekend) voor dit antwoord op de vraag '{question}': {answer}\nAlleen het cijfer teruggeven."
    response = openai.ChatCompletion.create(
        model="gpt-5",
        messages=[{"role": "user", "content": prompt}]
    )
    score = int(response["choices"][0]["message"]["content"].strip())
    return score

@app.route("/submit", methods=["POST"])
def submit():
    data = request.json
    scores = []
    
    # PDF setup
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(200, 10, "Veerenstael Quick Scan", ln=True, align="C")
    pdf.set_font("Arial", "", 12)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    pdf.cell(200, 10, f"Datum: {now}", ln=True)
    pdf.cell(200, 10, f"Naam: {data['name']}", ln=True)
    pdf.cell(200, 10, f"Bedrijf: {data['company']}", ln=True)
    pdf.cell(200, 10, f"E-mail: {data['email']}", ln=True)
    pdf.cell(200, 10, f"Telefoon: {data['phone']}", ln=True)

    # Vragen en antwoorden scoren
    for key, value in data.items():
        if "_" in key:  # vraagvelden
            score = ai_score(value, key)
            scores.append(score)
            pdf.multi_cell(0, 10, f"Vraag: {key}")
            pdf.multi_cell(0, 10, f"Antwoord: {value}")
            pdf.multi_cell(0, 10, f"Score: {score}")
            pdf.ln(5)

    total_score = round(sum(scores) / len(scores), 2)
    pdf.cell(200, 10, f"Totaalscore: {total_score}", ln=True)
    filename = "quickscan.pdf"
    pdf.output(filename)

    # Verstuur e-mail
    msg = MIMEMultipart()
    msg["From"] = os.getenv("EMAIL_USER")
    msg["To"] = data["email"]
    msg["Subject"] = "Resultaten Veerenstael Quick Scan"
    msg.attach(MIMEText("Beste,\n\nIn de bijlage vind je de resultaten van je Quick Scan.\n\nMet vriendelijke groet,\nVeerenstael"))

    with open(filename, "rb") as f:
        attach = MIMEApplication(f.read(), _subtype="pdf")
        attach.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(attach)

    s = smtplib.SMTP("smtp.gmail.com", 587)
    s.starttls()
    s.login(os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"))
    s.send_message(msg)
    s.quit()

    return jsonify({"total_score": total_score})
