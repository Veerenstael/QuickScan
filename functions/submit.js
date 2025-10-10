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

    // Verzamel data per sectie
    const sections = {};
    const sectionScores = {};
    
    for (const key in data) {
      if (key.endsWith('_answer')) {
        const prefix = key.slice(0, -7);
        const sectionName = prefix.split('_').slice(0, -1).join(' ');
        const vraag = data[prefix + '_label'] || key;
        const antwoord = data[key] || '';
        const cijfer = data[prefix + '_customer_score'] || '-';
        
        if (!sections[sectionName]) {
          sections[sectionName] = [];
          sectionScores[sectionName] = [];
        }
        sections[sectionName].push({ vraag, antwoord, cijfer });
        
        if (cijfer !== '-') {
          const num = parseInt(cijfer);
          if (!isNaN(num)) {
            sectionScores[sectionName].push(num);
          }
        }
      }
    }

    // Bereken gemiddelden
    const averages = {};
    for (const [section, scores] of Object.entries(sectionScores)) {
      if (scores.length > 0) {
        const avg = (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1);
        averages[section] = avg;
      }
    }

    // Genereer PDF
    const pdfPath = '/tmp/quickscan.pdf';
    const doc = new PDFDocument({ margin: 50 });
    const stream = fs.createWriteStream(pdfPath);
    doc.pipe(stream);

    // Header
    doc.fillColor('#223344')
       .fontSize(24)
       .text('Veerenstael Quick Scan', { align: 'center' });
    doc.moveDown();

    // Metadata
    doc.fillColor('#000000')
       .fontSize(11)
       .text(`Datum: ${new Date().toLocaleDateString('nl-NL')}`);
    doc.text(`Naam: ${data.name || ''}`);
    doc.text(`Bedrijf: ${data.company || ''}`);
    doc.text(`E-mail: ${data.email || ''}`);
    doc.text(`Telefoon: ${data.phone || ''}`);
    doc.moveDown(2);

    // Vragen per sectie
    doc.fillColor('#13d17c')
       .fontSize(16)
       .text('Vragen en Antwoorden', { underline: true });
    doc.moveDown();

    for (const [section, items] of Object.entries(sections)) {
      doc.fillColor('#223344')
         .fontSize(14)
         .text(section, { underline: true });
      doc.moveDown(0.5);

      items.forEach(item => {
        doc.fillColor('#000000')
           .fontSize(10)
           .text(`Vraag: ${item.vraag}`, { indent: 10 });
        doc.text(`Antwoord: ${item.antwoord}`, { indent: 10 });
        doc.text(`Cijfer: ${item.cijfer}`, { indent: 10 });
        doc.moveDown(0.8);
      });

      doc.moveDown();
    }

    // Gemiddelde scores
    doc.addPage();
    doc.fillColor('#13d17c')
       .fontSize(16)
       .text('Gemiddelde Scores per Onderwerp', { underline: true });
    doc.moveDown();

    doc.fillColor('#000000')
       .fontSize(11);
    for (const [section, avg] of Object.entries(averages)) {
      doc.text(`${section}: ${avg}/5`, { indent: 10 });
    }

    // Footer
    doc.fillColor('#888888')
       .fontSize(8)
       .text('Veerenstael Quick Scan', {
         align: 'center',
         y: doc.page.height - 50
       });

    doc.end();

    // Wacht tot PDF klaar is
    await new Promise((resolve, reject) => {
      stream.on('finish', resolve);
      stream.on('error', reject);
    });

    // Email via Gmail SMTP (werkt op Netlify!)
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

        await transporter.sendMail({
          from: emailUser,
          to: emailTo,
          cc: process.env.EMAIL_CC || '',
          subject: 'Resultaten Veerenstael Quick Scan',
          text: `Beste ${data.name},\n\nIn de bijlage staat het rapport van de QuickScan met alle vragen, antwoorden en cijfers.\n\nMet vriendelijke groet,\nVeerenstael`,
          attachments: [{
            filename: 'quickscan.pdf',
            path: pdfPath
          }]
        });

        email_sent = true;
        console.log('Email met PDF verzonden!');
      } catch (emailError) {
        console.error('Email error:', emailError);
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
