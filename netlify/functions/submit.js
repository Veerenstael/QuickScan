const nodemailer = require('nodemailer');
const PDFDocument = require('pdfkit');
const fs = require('fs');

exports.handler = async (event, context) => {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Content-Type': 'application/json'
  };

  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  try {
    const data = JSON.parse(event.body);

    // Verzamel form data per sectie
    const sections = {};
    for (const key in data) {
      if (key.endsWith('_answer')) {
        const prefix = key.slice(0, -7);
        const sectionName = prefix.split('_').slice(0, -1).join(' ');
        const vraag = data[prefix + '_label'] || key;
        const antwoord = data[key] || '';
        const cijfer = data[prefix + '_customer_score'] || '-';
        
        if (!sections[sectionName]) {
          sections[sectionName] = [];
        }
        sections[sectionName].push({ vraag, antwoord, cijfer });
      }
    }

    // Bereken gemiddelden per sectie
    const sectionAverages = {};
    for (const [section, items] of Object.entries(sections)) {
      const cijfers = items
        .map(item => parseInt(item.cijfer))
        .filter(c => !isNaN(c));
      
      if (cijfers.length > 0) {
        const avg = (cijfers.reduce((a, b) => a + b, 0) / cijfers.length).toFixed(1);
        sectionAverages[section] = avg;
      }
    }

    // Genereer PDF
    const pdfPath = '/tmp/quickscan.pdf';
    const doc = new PDFDocument({ margin: 50 });
    const stream = fs.createWriteStream(pdfPath);
    doc.pipe(stream);

    // Header/Titel
    doc.fontSize(20).fillColor('#223344').text('Veerenstael Quick Scan', { align: 'center' });
    doc.moveDown();

    // Metadata
    doc.fontSize(11).fillColor('#000000');
    doc.text(`Datum: ${new Date().toLocaleDateString('nl-NL')}`);
    doc.text(`Naam: ${data.name || ''}`);
    doc.text(`Bedrijf: ${data.company || ''}`);
    doc.text(`E-mail: ${data.email || ''}`);
    doc.text(`Telefoon: ${data.phone || ''}`);
    doc.moveDown(2);

    // Vragen per sectie
    doc.fontSize(14).fillColor('#13d17c').text('Vragen en Antwoorden', { underline: true });
    doc.moveDown();

    for (const [section, items] of Object.entries(sections)) {
      // Sectie titel
      doc.fontSize(12).fillColor('#223344').text(section, { underline: true });
      doc.moveDown(0.5);

      // Items
      items.forEach(item => {
        doc.fontSize(10).fillColor('#000000');
        doc.text(`Vraag: ${item.vraag}`, { indent: 10 });
        doc.text(`Antwoord: ${item.antwoord}`, { indent: 10 });
        doc.text(`Cijfer: ${item.cijfer}`, { indent: 10 });
        doc.moveDown(0.8);
      });

      doc.moveDown();
    }

    // Gemiddelde scores per sectie
    doc.addPage();
    doc.fontSize(14).fillColor('#13d17c').text('Gemiddelde Scores per Onderwerp', { underline: true });
    doc.moveDown();

    doc.fontSize(11).fillColor('#000000');
    for (const [section, avg] of Object.entries(sectionAverages)) {
      doc.text(`${section}: ${avg}/5`, { indent: 10 });
    }

    // Footer
    doc.fontSize(8).fillColor('#888888');
    doc.text('Veerenstael Quick Scan · Netlify Function', {
      align: 'center',
      y: doc.page.height - 50
    });

    doc.end();

    // Wacht tot PDF klaar is
    await new Promise((resolve, reject) => {
      stream.on('finish', resolve);
      stream.on('error', reject);
    });

    // Email configuratie
    const emailUser = process.env.EMAIL_USER;
    const emailPass = process.env.EMAIL_PASS;
    const emailTo = data.email;
    let email_sent = false;

    if (emailUser && emailPass && emailTo) {
      try {
        const transporter = nodemailer.createTransport({
          host: 'smtp.gmail.com',
          port: 587,
          secure: false,
          auth: {
            user: emailUser,
            pass: emailPass
          }
        });

        const mailOptions = {
          from: emailUser,
          to: emailTo,
          cc: process.env.EMAIL_CC || '',
          subject: 'Resultaten Veerenstael Quick Scan',
          text: `Beste ${data.name},\n\nIn de bijlage staat het rapport van de QuickScan met per vraag het antwoord en uw cijfer.\nAchterin vindt u de gemiddelde scores per onderwerp.\n\nMet vriendelijke groet,\nVeerenstael`,
          attachments: [
            {
              filename: 'quickscan.pdf',
              path: pdfPath
            }
          ]
        };

        await transporter.sendMail(mailOptions);
        email_sent = true;
        console.log('Email met PDF verzonden!');
      } catch (emailError) {
        console.error('Email error:', emailError.message);
      }
    }

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ email_sent })
    };

  } catch (error) {
    console.error('Function error:', error);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ error: error.message })
    };
  }
};
