// Captura las pantallas de evidencia del despliegue real a archivos PNG.
const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer");

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const APP = "http://74.249.251.136";
const PROM = "http://20.9.93.241:9090";
const GRAFANA = "http://20.9.93.241:3000";
const OUT = path.join(__dirname, "capturas");

if (!fs.existsSync(OUT)) fs.mkdirSync(OUT);

const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ["--no-sandbox"] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1400, height: 950 });

  async function captura(nombre, url, antes) {
    try {
      await page.goto(url, { waitUntil: "networkidle2", timeout: 45000 });
      if (antes) await antes();
      await esperar(1500);
      await page.screenshot({ path: path.join(OUT, nombre + ".png"), fullPage: false });
      console.log("OK   ", nombre);
    } catch (e) {
      console.log("FALLO", nombre, "-", e.message.split("\n")[0]);
    }
  }

  // --- Prometheus ---
  await captura("prometheus-alertas", PROM + "/alerts", async () => {
    // Expandir las reglas para que se vean los detalles de la alerta activa
    const botones = await page.$$("button, .collapsible, a");
    for (const b of botones) {
      const t = await page.evaluate((el) => el.textContent || "", b);
      if (t.includes("InstanciaCaida")) { await b.click(); break; }
    }
  });
  await captura("prometheus-objetivos", PROM + "/targets");

  // --- Aplicacion: login ---
  await captura("app-login", APP + "/login");

  // --- Aplicacion: listado de documentos (requiere iniciar sesion) ---
  try {
    await page.goto(APP + "/login", { waitUntil: "networkidle2", timeout: 45000 });
    await page.type("#usuario", "directora");
    await page.type("#clave", "chorombo2026");
    await Promise.all([
      page.waitForNavigation({ waitUntil: "networkidle2", timeout: 45000 }),
      page.click("button[type=submit]"),
    ]);
    await esperar(1500);
    await page.screenshot({ path: path.join(OUT, "app-documentos.png") });
    console.log("OK    app-documentos");
  } catch (e) {
    console.log("FALLO app-documentos -", e.message.split("\n")[0]);
  }

  // --- Grafana (login admin/admin) ---
  try {
    await page.goto(GRAFANA + "/login", { waitUntil: "networkidle2", timeout: 45000 });
    await esperar(2000);
    await page.type('input[name="user"]', "admin");
    await page.type('input[name="password"]', "admin");
    await page.click('button[type="submit"]');
    await esperar(5000);
    await page.screenshot({ path: path.join(OUT, "grafana-inicio.png") });
    console.log("OK    grafana-inicio");

    // Explorador con una consulta de CPU por instancia
    const q = encodeURIComponent('100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)');
    await page.goto(`${GRAFANA}/explore?left=%7B%22datasource%22:%22Prometheus%22,%22queries%22:%5B%7B%22expr%22:%22${q}%22%7D%5D,%22range%22:%7B%22from%22:%22now-30m%22,%22to%22:%22now%22%7D%7D`, { waitUntil: "networkidle2", timeout: 45000 });
    await esperar(6000);
    await page.screenshot({ path: path.join(OUT, "grafana-cpu.png") });
    console.log("OK    grafana-cpu");
  } catch (e) {
    console.log("FALLO grafana -", e.message.split("\n")[0]);
  }

  await browser.close();
  console.log("\nCapturas en:", OUT);
  console.log(fs.readdirSync(OUT).join("\n"));
})().catch((e) => { console.error(e); process.exit(1); });
