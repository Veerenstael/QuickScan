from flask import Flask, request, jsonify
from flask_cors import CORS
from fpdf import FPDF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText
from datetime import datetime
import os
import requests

# Headless plotting voor Render
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

VERSION = "QS-2025-10-24-v1-no-ai"

# ---------- Kleuren (RGB) ----------
DARKBLUE = (34, 51, 68)
ACCENT   = (19, 209, 124)
CELLBAND = (35, 49, 74)

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
    def _dl(url, path):
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return True
        try:
            r = requests.get(url, timeout=15); r.raise_for_status()
            with open(path, "wb") as f: f.write(r.content)
            return True
        except Exception:
            return False
    ok1 = _dl(DEJAVU_REG_URL, DEJAVU_REG_FILE)
    ok2 = _dl(DEJAVU_BOLD_URL, DEJAVU_BOLD_FILE)
    FONTS_READY = ok1 and ok2
    return FONTS_READY

def sanitize_text_for_latin1(txt: str) -> str:
    if not isinstance(txt, str): txt = str(txt)
    repl = {"\u2019":"'", "\u2018":"'", "\u201c":'"', "\u201d":'"',
            "\u2013":"-", "\u2014":"-", "\u2026":"...", "\u20ac":"EUR", "\xa0":" "}
    for k,v in repl.items(): txt = txt.replace(k,v)
    try: return txt.encode("latin-1","replace").decode("latin-1")
    except Exception: return txt

# ---------- Logo ----------
DEFAULT_LOGO_URL = os.getenv("LOGO_URL",
    "https://www.veerenstael.nl/wp-content/uploads/2020/06/logo-veerenstael-wit.png")
LOCAL_LOGO_FILE = "veerenstael_header_logo.png"

def ensure_logo_file() -> str | None:
    if os.path.exists(LOCAL_LOGO_FILE) and os.path.getsize(LOCAL_LOGO_FILE)>0:
        return LOCAL_LOGO_FILE
    try:
        r=requests.get(DEFAULT_LOGO_URL,timeout=15); r.raise_for_status()
        with open(LOCAL_LOGO_FILE,"wb") as f: f.write(r.content)
        return LOCAL_LOGO_FILE
    except Exception:
        for p in ["favicon.png","logo.png","static/favicon.png"]:
            if os.path.exists(p): return p
    return None

# ---------- Diagram-afbeelding ----------
DEFAULT_MODEL_IMAGE_URL = os.getenv("MODEL_IMAGE_URL","")
LOCAL_MODEL_IMAGE = "afbeelding.png"          # naast app.py
MODEL_IMAGE_FILE = "model_overlay_base.png"   # cache

def ensure_model_image() -> str | None:
    if os.path.exists(MODEL_IMAGE_FILE) and os.path.getsize(MODEL_IMAGE_FILE)>0:
        return MODEL_IMAGE_FILE
    if os.path.exists(LOCAL_MODEL_IMAGE) and os.path.getsize(LOCAL_MODEL_IMAGE)>0:
        with open(LOCAL_MODEL_IMAGE,"rb") as src, open(MODEL_IMAGE_FILE,"wb") as dst:
            dst.write(src.read()); return MODEL_IMAGE_FILE
    if DEFAULT_MODEL_IMAGE_URL:
        try:
            r=requests.get(DEFAULT_MODEL_IMAGE_URL,timeout=15); r.raise_for_status()
            with open(MODEL_IMAGE_FILE,"wb") as f: f.write(r.content)
            return MODEL_IMAGE_FILE
        except Exception:
            return None
    return None

# ===== PDF helper =====
class ReportPDF(FPDF):
    def __init__(self,*a,**k):
        super().__init__(*a,**k)
        self.unicode_ok=ensure_unicode_fonts()
        if self.unicode_ok:
            try:
                self.add_font(FONT_REGULAR,"",DEJAVU_REG_FILE,uni=True)
                self.add_font(FONT_BOLD,"",DEJAVU_BOLD_FILE,uni=True)
            except Exception: pass
    def ufont(self,size=11,bold=False):
        self.set_font(FONT_BOLD if (bold and self.unicode_ok) else
                      (FONT_REGULAR if self.unicode_ok else "Arial"),
                      "" if self.unicode_ok else ("B" if bold else ""), size)
    def utext(self,t): return t if self.unicode_ok else sanitize_text_for_latin1(t)
    def _nb_lines(self,w,txt,bold=False,size=11,line_h=7.0):
        pf,ps,pz=self.font_family,self.font_style,self.font_size_pt
        self.ufont(size,bold); text=self.utext(txt or ""); lines=0
        for par in text.split("\n"):
            words=par.split(" "); cur=""
            if not words: lines+=1; continue
            for w2 in words:
                test=(cur+" "+w2).strip()
                if self.get_string_width(test)<=w: cur=test
                else:
                    if cur=="":  # forcebreak
                        ch=""; 
                        for c in w2:
                            if self.get_string_width(ch+c)<=w: ch+=c
                            else: lines+=1; ch=c
                        cur=ch
                    else: lines+=1; cur=w2
            lines+=1
        self.set_font(pf,ps,pz); return max(lines,1)
    def header(self):
        self.set_fill_color(*DARKBLUE); self.rect(0,0,210,24,"F")
        lp=ensure_logo_file()
        if lp:
            try: self.image(lp,x=10,y=5,h=10)
            except Exception: pass
        self.set_text_color(255,255,255); self.ufont(14,True)
        self.set_xy(10,16); self.cell(0,6,self.utext("Quick Scan Rapport"),align="L")
        self.ln(12)
    def footer(self):
        self.set_y(-15); self.set_text_color(120,120,120); self.ufont(8)
        self.cell(0,10,f"Pagina {self.page_no()}/{{nb}}",align="C")
    def section_title(self,txt):
        self.ufont(13,True); self.set_text_color(*DARKBLUE)
        self.cell(0,8,self.utext(txt),ln=True); self.set_text_color(0,0,0)
    def kv(self,key,val):
        self.ufont(11,True); k_w=self.get_string_width(self.utext(key))+2
        self.cell(k_w,6,self.utext(key)); self.ufont(11,False)
        self.cell(0,6,self.utext(str(val)),ln=True)
    def table_header(self):
        self.set_fill_color(*CELLBAND); self.ufont(10,True); self.set_text_color(255,255,255)
        self.cell(90,7,"Vraag",border=0,fill=True)
        self.cell(70,7,"Antwoord",border=0,fill=True)
        self.cell(25,7,"Uw cijfer",border=0,fill=True,align="C"); self.ln()
        self.set_text_color(0,0,0)
    def row_two_cols(self, vraag, antwoord, cust_score):
        self.ufont(10,False)
        vraag_lines=self._nb_lines(88, vraag, size=10)
        antw_lines=self._nb_lines(68, antwoord, size=10)
        
        row_h=max(vraag_lines, antw_lines)*7 + 2
        if self.get_y()+row_h > self.h-self.b_margin:
            self.add_page(); self.table_header()
        y0=self.get_y()
        self.multi_cell(90,7,self.utext(vraag),border=0)
        y1=self.get_y(); self.set_xy(100,y0)
        self.multi_cell(70,7,self.utext(antwoord or "-"),border=0)
        y2=self.get_y(); self.set_xy(170,y0)
        
        # Alleen klantcijfer tonen
        self.cell(25,row_h,str(cust_score),border=0,align="C")
        
        self.set_xy(10, max(y1,y2))
        self.set_draw_color(220,220,220); self.line(10,self.get_y(),200,self.get_y())

# ===== Stoplicht overlay =====
def lamp_color(name: str):
    if name=="red": return (0.85,0.15,0.15)
    if name=="yellow": return (0.95,0.75,0.10)
    return (0.20,0.80,0.30)

def bucket_for_score(score: float) -> str:
    if score < 2.5: return "red"
    if score < 3.5: return "yellow"
    return "green"

def build_stoplight_overlay(sections: list, values: list, out_path="stoplicht.png"):
    if not sections: return None
    base_img_path=ensure_model_image()
    if not base_img_path: return None
    try:
        from PIL import Image
        base_img=Image.open(base_img_path).convert("RGBA")
    except Exception:
        return None

    w_img, h_img = base_img.size
    dpi=100; fig_w, fig_h = w_img/dpi, h_img/dpi
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    ax.imshow(base_img, extent=[0, w_img, 0, h_img], aspect="auto", zorder=0)
    ax.set_xlim(0, w_img); ax.set_ylim(0, h_img)
    ax.axis("off"); fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    positions={
        "Asset Management Strategie": (0.50, 0.72),
        "Werkvoorbereiding": (0.77, 0.58),
        "Uitvoering onderhoud": (0.77, 0.28),
        "Werk afhandelen en controleren": (0.50, 0.14),
        "Analyse gegevens": (0.23, 0.28),
        "Maintenance & Reliability Engineering": (0.23, 0.58),
        "Inregelen onderhoudsplan": (0.50, 0.43)
    }

    radius = min(w_img, h_img) * 0.018
    padding = radius * 1.4
    housing_h = 2*padding + 6*radius
    housing_w = 2*padding + 2*radius

    for i, section_name in enumerate(sections):
        score = values[i] if i < len(values) else 3.0
        pos = positions.get(section_name)
        if not pos: continue
        fx, fy = pos
        cx = fx * w_img
        cy = fy * h_img
        top_y = cy + housing_h/2

        box_x = cx - housing_w/2
        box_y = top_y
        shadow = FancyBboxPatch((box_x+2, box_y+2), housing_w, housing_h,
                                boxstyle="round,pad=0.012,rounding_size=6",
                                linewidth=0.0, facecolor=(0,0,0,0.20))
        ax.add_patch(shadow)
        box = FancyBboxPatch((box_x, box_y), housing_w, housing_h,
                             boxstyle="round,pad=0.012,rounding_size=6",
                             linewidth=1.0, edgecolor=(1,1,1,0.9), facecolor=(0.15,0.17,0.20,0.85))
        ax.add_patch(box)

        centers=[(cx, box_y + padding + radius),
                 (cx, box_y + housing_h/2),
                 (cx, box_y + housing_h - padding - radius)]
        active=bucket_for_score(score)
        for idx,(lx,ly) in enumerate(centers):
            name=["red","yellow","green"][idx]
            col=lamp_color(name)
            if name!=active: col=(col[0]*0.45,col[1]*0.45,col[2]*0.45)
            ax.add_patch(plt.Circle((lx,ly), radius*1.25, color=(1,1,1,0.18), ec="none"))
            lw=2.2 if name==active else 1.0
            ax.add_patch(plt.Circle((lx,ly), radius, color=col, ec="white", lw=lw))

        ax.text(cx, box_y-6, f"{score:.1f}", ha="center", va="top", fontsize=11, color="white",
                bbox=dict(boxstyle="round,pad=0.25", fc=(0,0,0,0.55), ec="none"))

    fig.savefig(out_path, dpi=150, transparent=False)
    plt.close(fig)
    return out_path

# ===== routes =====
@app.route("/health", methods=["GET"])
def health(): return jsonify({"status":"ok"}), 200

@app.route("/version", methods=["GET"])
def version(): return jsonify({"version": VERSION}), 200

@app.route("/", methods=["GET"])
def home(): return "✅ Veerenstael Quick Scan backend is live"

@app.route("/submit", methods=["POST","OPTIONS"])
def submit():
    if request.method=="OPTIONS": return ("",204)
    try:
        data = request.json or {}

        # items: (vraag, antwoord, sectie, klantcijfer-string)
        items=[]
        for k in [k for k in data.keys() if k.endswith("_answer")]:
            prefix=k[:-7]
            vraag=data.get(prefix+"_label",k)
            antwoord=data.get(k,"")
            sect=prefix.rsplit("_",1)[0]
            cust_raw=data.get(prefix+"_customer_score",""); cust="-"
            try:
                if str(cust_raw).strip()!="": cust=str(int(cust_raw))
            except Exception: cust="-"
            items.append((vraag,antwoord,sect,cust))

        # PDF
        pdf=ReportPDF(); pdf.add_page(); pdf.set_auto_page_break(True,15)

        # metadata
        pdf.ln(2)
        now=datetime.now().strftime("%Y-%m-%d %H:%M")
        pdf.kv("Datum:",now)
        pdf.kv("Naam:",data.get("name",""))
        pdf.kv("Bedrijf:",data.get("company",""))
        pdf.kv("E-mail:",data.get("email",""))
        pdf.kv("Telefoon:",data.get("phone",""))
        pdf.ln(3)

        intro=data.get("introText","")
        if intro:
            pdf.section_title("Introductie QuickScan")
            pdf.ufont(11,False); pdf.multi_cell(0,7,pdf.utext(intro)); pdf.ln(2)

        # groeperen per onderwerp
        from collections import OrderedDict
        grouped=OrderedDict()
        for v,a,s,c in items: grouped.setdefault(s,[]).append((v,a,c))

        MIN_SPACE_FOR_SECTION=70
        radar_sections, radar_vals=[], []
        all_cust=[]

        pdf.section_title("Vragen en antwoorden")
        for sect, rows in grouped.items():
            remaining=pdf.h-pdf.b_margin-pdf.get_y()
            if remaining<MIN_SPACE_FOR_SECTION: pdf.add_page()
            pdf.ufont(12,True); pdf.set_text_color(*DARKBLUE)
            pdf.cell(0,7,pdf.utext(sect),ln=True); pdf.set_text_color(0,0,0)
            pdf.table_header()

            cust_scores=[]
            for vraag,antwoord,cust in rows:
                if cust!="-":
                    try: ci=int(cust); cust_scores.append(ci); all_cust.append(ci)
                    except Exception: pass
                pdf.row_two_cols(vraag, antwoord, cust)

            subj_avg=round(sum(cust_scores)/len(cust_scores),2) if cust_scores else 0
            radar_sections.append(sect); radar_vals.append(subj_avg); pdf.ln(1)

        avg_cust=round(sum(all_cust)/len(all_cust),2) if all_cust else 0

        pdf.ln(2); pdf.section_title("Scores")
        pdf.kv("Gemiddeld cijfer:", str(avg_cust if all_cust else "-"))

        # Eenvoudige samenvatting zonder AI
        summary_text = (f"U heeft in totaal {len(items)} vragen beantwoord over {len(grouped)} onderwerpen. "
                       f"Het gemiddelde cijfer is {avg_cust:.1f}. "
                       "De resultaten geven inzicht in de volwassenheid van uw asset management. "
                       "In een vervolggesprek kunnen we de mogelijkheden voor verbetering bespreken.")
        
        pdf.ln(3); pdf.section_title("Samenvatting")
        pdf.ufont(11,False); pdf.multi_cell(0,7,pdf.utext(summary_text))

        if radar_sections:
            # radar pagina
            pdf.add_page()
            def wrap_label(lbl: str)->str:
                l=lbl.strip()
                if l.lower()=="uitvoering onderhoud": return "Uitvoering\nonderhoud"
                if l=="Maintenance & Reliability Engineering": return "Maintenance &\nReliability\nEngineering"
                return l
            img_path="radar.png"
            try:
                labels=[wrap_label(s) for s in radar_sections]
                values=radar_vals; N=len(labels)
                values_cycle=values+values[:1]
                angles=np.linspace(0,2*np.pi,N,endpoint=False).tolist(); angles+=angles[:1]
                fig=plt.figure(figsize=(5,5)); ax=plt.subplot(111, polar=True)
                ax.set_theta_offset(np.pi/2); ax.set_theta_direction(-1)
                ax.set_xticks(angles[:-1]); ax.set_xticklabels(labels,fontsize=8)
                ax.set_rlabel_position(0); ax.set_yticks([1,2,3,4,5]); ax.set_yticklabels(["1","2","3","4","5"],fontsize=7)
                ax.set_ylim(0,5); ax.plot(angles,values_cycle); ax.fill(angles,values_cycle,alpha=0.25)
                fig.tight_layout(); fig.savefig(img_path,dpi=180,bbox_inches="tight"); plt.close(fig)
                pdf.section_title("Gemiddelde score per onderwerp"); pdf.image(img_path, w=180)
            except Exception as e:
                app.logger.error(f"Kon radargrafiek niet maken: {e}")

            # stoplicht laatste pagina
            overlay_path=build_stoplight_overlay(radar_sections, radar_vals, out_path="stoplicht.png")
            if overlay_path:
                pdf.add_page(); pdf.section_title("Stoplichtoverzicht per onderwerp"); pdf.image(overlay_path, w=180)

        filename="quickscan.pdf"; pdf.output(filename)

        # E-mail
        email_user=os.getenv("EMAIL_USER"); email_pass=os.getenv("EMAIL_PASS")
        email_to=data.get("email",""); email_sent=False
        if email_user and email_pass and email_to:
            try:
                msg=MIMEMultipart(); msg["From"]=email_user; msg["To"]=email_to
                msg["Cc"]=os.getenv("EMAIL_CC",""); msg["Subject"]="Resultaten Veerenstael Quick Scan"
                body=(f"Beste {data.get('name','')},\n\n"
                      "In de bijlage staat het rapport van de QuickScan met per vraag het antwoord en uw cijfer.\n\n"
                      f"Samenvatting:\n{summary_text}\n\nMet vriendelijke groet,\nVeerenstael")
                msg.attach(MIMEText(body))
                with open(filename,"rb") as f:
                    attach=MIMEApplication(f.read(), _subtype="pdf")
                    attach.add_header("Content-Disposition","attachment",filename=filename); msg.attach(attach)
                smtp_server=os.getenv("SMTP_SERVER","smtp.gmail.com"); smtp_port=int(os.getenv("SMTP_PORT","587"))
                s=smtplib.SMTP(smtp_server,smtp_port); s.starttls(); s.login(email_user,email_pass); s.send_message(msg); s.quit()
                email_sent=True
            except Exception as e:
                app.logger.error(f"E-mail verzenden mislukt: {e}")

        return jsonify({"total_score_customer": avg_cust if all_cust else "",
                        "summary": summary_text,
                        "email_sent": email_sent}), 200
    except Exception as e:
        app.logger.error(f"Fout in submit: {e}")
        return jsonify({"error": str(e)}), 500
