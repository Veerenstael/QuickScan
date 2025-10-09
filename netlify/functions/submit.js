const nodemailer = require('nodemailer');

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

    // Debug logging
    const emailUser = process.env.EMAIL_USER;
    const emailPass = process.env.EMAIL_PASS;
    const emailTo = data.email;

    console.log('=== EMAIL DEBUG ===');
    console.log('EMAIL_USER configured:', !!emailUser);
    console.log('EMAIL_PASS configured:', !!emailPass);
    console.log('Email TO from form:', emailTo);
    console.log('All checks:', { user: !!emailUser, pass: !!emailPass, to: !!emailTo });

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

    let email_sent = false;

    if (emailUser && emailPass && emailTo) {
      console.log('All email config present, attempting to send...');
      
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
          from: emailUser,
          to: emailTo,
          cc: process.env.EMAIL_CC || '',
          subject: 'Resultaten Veerenstael Quick Scan',
          text: `Beste ${data.name},\n\nBedankt voor het invullen van de QuickScan.\n\n${emailBody}\n\nMet vriendelijke groet,\nVeerenstael`
        };

        const info = await transporter.sendMail(mailOptions);
        console.log('Email sent successfully:', info.messageId);
        email_sent = true;
        
      } catch (emailError) {
        console.error('Email send error:', emailError.message);
        console.error('Full error:', emailError);
      }
    } else {
      console.log('Email config incomplete - skipping email');
      console.log('Missing:', {
        user: !emailUser ? 'EMAIL_USER' : null,
        pass: !emailPass ? 'EMAIL_PASS' : null,
        to: !emailTo ? 'form email' : null
      });
    }

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ 
        email_sent,
        debug: {
          has_user: !!emailUser,
          has_pass: !!emailPass,
          has_to: !!emailTo
        }
      })
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
