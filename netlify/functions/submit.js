const nodemailer = require('nodemailer');

exports.handler = async (event, context) => {
  // CORS headers
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

    // Verzamel form data
    const items = [];
    for (const key in data) {
      if (key.endsWith('_answer')) {
        const prefix = key.slice(0, -7);
        const vraag = data[prefix + '_label'] || key;
        const antwoord = data[key] || '';
        const cust = data[prefix + '_customer_score'] || '-';
        items.push({ vraag, antwoord, cust });
      }
    }

    // Email configuratie
    const transporter = nodemailer.createTransport({
      host: 'smtp.gmail.com',
      port: 587,
      secure: false,
      auth: {
        user: process.env.EMAIL_USER,
        pass: process.env.EMAIL_PASS
      }
    });

    // Email body (simpel, zonder PDF voorlopig)
    let emailBody = `Nieuwe QuickScan ontvangen\n\n`;
    emailBody += `Naam: ${data.name}\n`;
    emailBody += `Bedrijf: ${data.company}\n`;
    emailBody += `Email: ${data.email}\n`;
    emailBody += `Telefoon: ${data.phone}\n\n`;
    emailBody += `--- ANTWOORDEN ---\n\n`;
    
    items.forEach(item => {
      emailBody += `Vraag: ${item.vraag}\n`;
      emailBody += `Antwoord: ${item.antwoord}\n`;
      emailBody += `Cijfer: ${item.cust}\n\n`;
    });

    const mailOptions = {
      from: process.env.EMAIL_USER,
      to: data.email,
      cc: process.env.EMAIL_CC || '',
      subject: 'Resultaten Veerenstael Quick Scan',
      text: `Beste ${data.name},\n\nBedankt voor het invullen van de QuickScan.\n\n${emailBody}\n\nMet vriendelijke groet,\nVeerenstael`
    };

    let email_sent = false;
    if (process.env.EMAIL_USER && process.env.EMAIL_PASS && data.email) {
      try {
        await transporter.sendMail(mailOptions);
        email_sent = true;
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
