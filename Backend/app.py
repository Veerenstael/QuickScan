from flask import Flask, request, jsonify
from flask_cors import CORS
from fpdf import FPDF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from datetime import datetime
import openai
import os

app = Flask(__name__)
CORS(app)  # Zorgt dat frontend (Netlify) toegang krijgt tot backend

# OpenAI API key uit environment
openai.api_key = os.getenv("OPENAI_API_KEY")

def ai_score(answer, question):
    """Vraag de AI om een score tussen 1 en 4"""
    prompt = f"Geef een score van 1 (slecht) tot 4 (uitstekend) voor dit antwoord op de vraag '{question}': {answer}\nAlleen het cijfer teruggeven."
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        score = int(response["choices"][0]["message"]["content"].strip())
        return score
    except Exception as e:
        app.logger.error(f"OpenAI fout: {e}")
        return 2  # fallback score

@app.route("/", methods=["GET"])
def home():
    return "✅ Veerenstael Quick Scan backend is live"

@app.route("/submit", methods=["POST"])
def submit():
    try:
        data = request.json
        app.logger.info(f"Ontvangen data: {data}")

        scores = []

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
            if "_" in key:  # vraagvelden
                score = ai_score(value, key)
                scores.append(score)
                pdf.multi_cell(0, 10, f"Vraag: {key}")
                pdf.multi_cell(0, 10, f"Antwoord: {value}")
                pdf.multi_cell(0, 10, f"Sc_
