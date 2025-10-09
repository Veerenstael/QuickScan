import json
import os
import base64
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from datetime import datetime
from fpdf import FPDF
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch
import requests
import gc

# Kleuren
DARKBLUE = (34, 51, 68)
ACCENT = (19, 209, 124)
CELLBAND = (35, 49, 74)

# Unicode fonts
FONTS_READY = False
FONT_REGULAR = "DejaVu"
FONT_BOLD = "DejaVuB"
DEJAVU_REG_URL = "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans.ttf"
DEJAVU_BOLD_URL = "https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans-Bold.ttf"
DEJAVU_REG_FILE = "/tmp/DejaVuSans.ttf"
DEJAVU_BOLD_FILE = "/tmp/DejaVuSans-Bold.ttf"

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
        except:
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
    except:
        return txt

class ReportPDF(FPDF):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.unicode_ok = ensure_unicode_fonts()
        if self.unicode_ok:
            try:
                self.add_font(FONT_REGULAR, "", DEJAVU_REG_FILE, uni=True)
                self.add_font(FONT_BOLD, "", DEJAVU_BOLD_FILE, uni=True)
            except:
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
        self.cell(0, 8, "Veerenstael Quick Scan", align="C")

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

def handler(event, context):
    if event['httpMethod'] == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': ''
        }
    
    try:
        data = json.loads(event['body'])
        
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
            except:
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
                    except:
                        pass
                pdf.row_two_cols(vraag, antwoord, cust)
            subj_avg = round(sum(cust_scores) / len(cust_scores), 2) if cust_scores else 0
            radar_sections.append(sect)
            radar_vals.append(subj_avg)
            pdf.ln(1)

        # Radar
        if radar_sections:
            pdf.add_page()
            img_path = "/tmp/radar.png"
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
                fig.savefig(img_path, dpi=75, bbox_inches="tight")
                plt.close(fig)
                plt.clf()
                gc.collect()
                pdf.section_title("Gemiddelde score per onderwerp (klant)")
                pdf.image(img_path, w=140)
            except:
                pass

        filename = "/tmp/quickscan.pdf"
        pdf.output(filename)

        # Email via Gmail SMTP (werkt op Netlify!)
        email_user = os.environ.get("EMAIL_USER")
        email_pass = os.environ.get("EMAIL_PASS")
        email_to = data.get("email", "")
        email_sent = False

        if email_user and email_pass and email_to:
            try:
                msg = MIMEMultipart()
                msg["From"] = email_user
                msg["To"] = email_to
                msg["Subject"] = "Resultaten Veerenstael Quick Scan"
                body = f"Beste {data.get('name', '')},\n\nIn de bijlage staat het rapport.\n\nMet vriendelijke groet,\nVeerenstael"
                msg.attach(MIMEText(body))
                with open(filename, "rb") as f:
                    attach = MIMEApplication(f.read(), _subtype="pdf")
                    attach.add_header("Content-Disposition", "attachment", filename="quickscan.pdf")
                    msg.attach(attach)
                
                s = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
                s.starttls()
                s.login(email_user, email_pass)
                s.send_message(msg)
                s.quit()
                email_sent = True
            except Exception as e:
                print(f"Email error: {e}")

        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({"email_sent": email_sent})
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({"error": str(e)})
        }
