// De vragen per categorie
const QUESTIONS = {
  "Asset Management Strategie": [
    "Zijn rollen, verantwoordelijkheden en bevoegdheden binnen onderhoudsprocessen helder belegd (bijv. tussen opdrachtgever, werkvoorbereider, coördinator en monteurs)?",
    "Is het binnen de organisatie duidelijk welke technische doelen worden nagestreefd (denk aan SAMP, line-of-sight)?"
  ],
  "Werkvoorbereiding": [
    "Is er een actuele korte én lange termijn planning (tot 5 jaar) waarop onderhoudswerkzaamheden worden afgestemd?",
    "Zijn alle benodigde resources (mensen, materiaal, onderaannemers) tijdig inzichtelijk en beschikbaar voor de uitvoering?"
  ],
  "Uitvoering onderhoud": [
    "Zijn er duidelijke werkinstructies beschikbaar waarin kwaliteit geborgd is?",
    "Worden storingen en inspectieresultaten systematisch geregistreerd?"
  ],
  "Werk afhandelen en controleren": [
    "Wordt de kwaliteit van uitgevoerd werk (en dat van onderaannemers) structureel gecontroleerd en vastgelegd?",
    "Vindt er standaard evaluatie plaats om afwijkingen of restpunten op te volgen?"
  ],
  "Analyse gegevens": [
    "Worden prestaties van assets en onderhoud zichtbaar gemaakt met dashboards of rapportages?",
    "Worden terugkerende storingen en trendanalyses gebruikt om te verbeteren?"
  ],
  "Maintenance & Reliability Engineering": [
    "Is er een proces om technische risico’s en faalkosten in kaart te brengen en te beheersen (bijv. met RCM of LCC)?",
    "Worden onderhoudsplannen en sparepartsbeleid periodiek herzien?"
  ],
  "Inregelen onderhoudsplan": [
    "Zijn onderhoudsplannen geborgd in systemen (OMS/EAM) en worden deze periodiek herzien?",
    "Wordt er gewerkt met een continu verbeterproces (bijv. met PDCA) om plannen, SLA’s en KPI's bij te sturen?"
  ]
};

// Helpers
function createOption(v) {
  const o = document.createElement("option");
  o.value = String(v);
  o.textContent = String(v);
  return o;
}

// Dynamisch de vragen inladen (textarea + score 1-5 + hidden label voor PDF)
const qContainer = document.getElementById("questions");
Object.entries(QUESTIONS).forEach(([section, qs]) => {
  const h3 = document.createElement("h3");
  h3.innerText = section;
  qContainer.appendChild(h3);

  qs.forEach((q, i) => {
    const label = document.createElement("label");
    label.innerText = q;

    // textarea voor toelichting
    const textarea = document.createElement("textarea");
    const baseName = `${section}_${i}`; // gebruikt als prefix
    textarea.name = `${baseName}_answer`;
    textarea.rows = 3;
    textarea.style.width = "100%";

    // hidden input met de originele vraagtekst zodat de backend de nette vraag kan tonen
    const hiddenLabel = document.createElement("input");
    hiddenLabel.type = "hidden";
    hiddenLabel.name = `${baseName}_label`;
    hiddenLabel.value = q;

    // select voor klantcijfer 1-5
    const scoreLabel = document.createElement("div");
    scoreLabel.className = "score-row";
    const scoreText = document.createElement("span");
    scoreText.textContent = "Uw cijfer (1–5):";
    const select = document.createElement("select");
    select.name = `${baseName}_customer_score`;
    select.required = false;
    select.appendChild(new Option("-", ""));
    [1,2,3,4,5].forEach(v => select.appendChild(createOption(v)));
    scoreLabel.appendChild(scoreText);
    scoreLabel.appendChild(select);

    // plaatsen
    qContainer.appendChild(label);
    qContainer.appendChild(textarea);
    qContainer.appendChild(hiddenLabel);
    qContainer.appendChild(scoreLabel);
  });
});

// Intro-tekst ook meesturen zodat deze in de PDF komt
const introEl = document.getElementById("intro");

// Form versturen
document.getElementById("quickscan-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const formData = new FormData(e.target);
  const data = Object.fromEntries(formData.entries());

  // voeg de zichtbare intro HTML-tekst toe als platte tekst
  if (introEl) {
    const p = introEl.querySelector("p");
    data.introText = p ? p.innerText : "";
  }

  try {
    const res = await fetch("https://veerenstael-quickscan-backend.onrender.com/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });

    if (!res.ok) throw new Error("Backend niet bereikbaar");

    const json = await res.json();

    document.getElementById("result").innerHTML = `
      <div class="result-block">
        <h2>Resultaten QuickScan</h2>
        <p><strong>Gemiddeld cijfer AI:</strong> ${json.total_score_ai}</p>
        <p><strong>Gemiddeld cijfer klant:</strong> ${json.total_score_customer}</p>
        <p><strong>Samenvatting:</strong><br/>${json.summary}</p>
        <p>Bedankt ${data.name}! Een PDF met de resultaten is verstuurd naar <strong>${data.email}</strong> (kopie ook naar Veerenstael).</p>
      </div>
    `;
  } catch (err) {
    document.getElementById("result").innerHTML = `
      <div class="result-block">
        <h2>Er ging iets mis</h2>
        <p>De QuickScan kon niet worden verstuurd. Controleer of de backend bereikbaar is en probeer opnieuw.</p>
      </div>
    `;
    console.error(err);
  }
});
