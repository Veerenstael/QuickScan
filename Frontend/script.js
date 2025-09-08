// De vragen per categorie
const QUESTIONS = {
  "Organisatie": [
    "Zijn rollen, verantwoordelijkheden en bevoegdheden binnen onderhoudsprocessen helder belegd?",
    "Is er een duidelijke overleg- en rapportagestructuur waardoor informatie uit tactische analyses en operationele uitvoering goed samenkomt?"
  ],
  "Werkvoorbereiding": [
    "Is er een actuele korte én lange termijn planning (tot 5 jaar)?",
    "Zijn alle benodigde resources tijdig inzichtelijk en beschikbaar?"
  ],
  "Uitvoeren onderhoud": [
    "Zijn er duidelijke werkinstructies waarin veiligheid en kwaliteit geborgd zijn?",
    "Worden storingen en inspectieresultaten systematisch geregistreerd en gebruikt?"
  ],
  "Werk afhandelen en controleren": [
    "Wordt de kwaliteit van uitgevoerd werk en dat van onderaannemers gecontroleerd?",
    "Vindt er standaard nacalculatie en evaluatie plaats?"
  ],
  "Analyseren gegevens": [
    "Worden prestaties inzichtelijk gemaakt met dashboards of rapportages?",
    "Worden terugkerende storingen en trendanalyses gebruikt om verbeteracties te sturen?"
  ],
  "Maintenance & Reliability Engineering": [
    "Worden risico’s en faalkosten in kaart gebracht en beheerst?",
    "Worden onderhoudsplannen en sparepartsbeleid structureel verbeterd?"
  ],
  "Inregelen onderhoudsplan": [
    "Zijn onderhoudsplannen geborgd in systemen en periodiek herzien?",
    "Wordt PDCA gebruikt om plannen en SLA’s bij te sturen?"
  ]
};

// Dynamisch de vragen inladen
const qContainer = document.getElementById("questions");
Object.entries(QUESTIONS).forEach(([section, qs]) => {
  const h3 = document.createElement("h3");
  h3.innerText = section;
  qContainer.appendChild(h3);

  qs.forEach((q, i) => {
    const label = document.createElement("label");
    label.innerText = q;
    const textarea = document.createElement("textarea");
    textarea.name = `${section}_${i}`;
    textarea.rows = 3;
    textarea.style.width = "100%";
    qContainer.appendChild(label);
    qContainer.appendChild(textarea);
  });
});

// Form versturen
document.getElementById("quickscan-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const formData = new FormData(e.target);
  const data = Object.fromEntries(formData.entries());

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
        <p><strong>Totaalscore:</strong> ${json.total_score}</p>
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
