// Convierte el .docx a PDF sin necesidad de Word ni LibreOffice:
//   docx --> HTML (mammoth) --> PDF (Chrome headless via puppeteer)
const fs = require("fs");
const path = require("path");
const mammoth = require("mammoth");
const puppeteer = require("puppeteer");

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const DOCX = path.join(__dirname, "Eval_U3_Cloud_Carrasco.docx");
const PDF = path.join(__dirname, "Eval_U3_Cloud_Carrasco.pdf");

const CSS = `
  @page { size: A4; margin: 2.5cm 2.5cm 2.2cm 2.5cm; }
  body { font-family: Arial, sans-serif; font-size: 12pt; line-height: 1.5; color: #000; margin: 0; }
  p { text-align: justify; margin: 0 0 8pt 0; }
  h1 { font-size: 15pt; color: #1B3A5C; margin: 20pt 0 10pt 0; page-break-after: avoid; }
  h2 { font-size: 13pt; color: #1B3A5C; margin: 14pt 0 7pt 0; page-break-after: avoid; }
  h3 { font-size: 12pt; font-style: italic; margin: 11pt 0 6pt 0; page-break-after: avoid; }
  ul { margin: 0 0 8pt 0; padding-left: 20pt; }
  li { text-align: justify; margin-bottom: 4pt; }
  img { max-width: 100%; height: auto; display: block; margin: 10pt auto; }
  table { border-collapse: collapse; width: 100%; margin: 8pt 0 12pt 0; font-size: 9.5pt; page-break-inside: avoid; }
  td, th { border: 1px solid #999; padding: 5pt 6pt; vertical-align: middle; text-align: left; line-height: 1.25; }
  tr:first-child td { background: #1B3A5C; color: #fff; font-weight: bold; }
  .portada { text-align: center; page-break-after: always; padding-top: 4cm; }
  .portada p { text-align: center; }
  /* mammoth entrega la imagen en su tamano original; en la portada hay que
     acotarla para que no ocupe todo el ancho de la pagina */
  .portada img { max-width: 8.5cm; margin: 0 auto 0.6cm auto; }
  .indice { page-break-after: always; }
  /* los titulos ya traen su propio numero de seccion, asi que la lista no
     debe agregar otro */
  .indice ol { padding-left: 0; list-style: none; }
  .indice li { margin-bottom: 5pt; text-align: left; }
`;

(async () => {
  const { value: html, messages } = await mammoth.convertToHtml(
    { path: DOCX },
    { styleMap: ["p[style-name='Heading 1'] => h1:fresh", "p[style-name='Heading 2'] => h2:fresh", "p[style-name='Heading 3'] => h3:fresh"] }
  );
  const warns = messages.filter((m) => m.type === "warning").length;
  console.log("mammoth listo,", warns, "avisos");

  // La portada es todo lo que va antes del primer encabezado de nivel 1
  // (que es "1. Resumen ejecutivo..."). Ahí dentro queda tambien el titulo
  // "Índice" y el campo de indice de Word, que al convertir viene vacio: se
  // descartan y mas abajo se arma un indice propio.
  const idx = html.indexOf("<h1>");
  let portada = "", resto = html;
  if (idx > -1) {
    // El titulo "Índice" del docx puede venir envuelto en <strong> u otras
    // etiquetas, por eso se quita cualquier parrafo cuyo texto plano sea "Índice"
    portada = html.slice(0, idx).replace(
      /<p>(?:(?!<\/p>).)*?<\/p>/gs,
      (m) => (m.replace(/<[^>]+>/g, "").trim() === "Índice" ? "" : m)
    );
    portada = `<div class="portada">${portada}</div>`;
    resto = html.slice(idx);
  }
  const titulos = [...resto.matchAll(/<h1>(.*?)<\/h1>/g)].map((m) => m[1]);
  const indice = `<div class="indice"><h1>Índice</h1><ol>${titulos
    .map((t) => `<li>${t}</li>`)
    .join("")}</ol></div>`;

  const full = `<!doctype html><html><head><meta charset="utf-8"><style>${CSS}</style></head><body>${portada}${indice}${resto}</body></html>`;
  fs.writeFileSync(path.join(__dirname, "informe.html"), full);

  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-sandbox"] });
  const page = await browser.newPage();
  await page.setContent(full, { waitUntil: "networkidle0" });
  await page.pdf({
    path: PDF,
    format: "A4",
    printBackground: true,
    margin: { top: "2.5cm", bottom: "2.2cm", left: "2.5cm", right: "2.5cm" },
    displayHeaderFooter: true,
    headerTemplate: "<div></div>",
    footerTemplate:
      '<div style="width:100%;font-family:Arial;font-size:9pt;text-align:center;color:#333;"><span class="pageNumber"></span></div>',
  });
  await browser.close();
  console.log("PDF generado:", fs.statSync(PDF).size, "bytes");
})().catch((e) => { console.error(e); process.exit(1); });
