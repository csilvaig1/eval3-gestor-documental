# Documento Técnico de Solución

Contiene el informe principal de la evaluación (`Eval_U3_Cloud_Carrasco.docx`),
el diagrama de arquitectura (`arquitectura.svg` / `.png`) y el script que genera
el `.docx` (`build.js`).

El informe está completo y con evidencia real del despliegue: 7 de 7 pruebas
Selenium aprobadas, prueba de carga con 23.426 peticiones, prueba de falla
controlada sin caída del servicio y alerta disparada, más las capturas del
sistema, de Grafana y de Prometheus.

## Pendiente antes de entregar

- Reemplazar el placeholder `[Nombre del docente VcM]` en la portada (dato no disponible).
- Informar al docente de la asignatura que la prueba de carga se hizo con un generador
  propio en Python en vez de Apache JMeter, porque JMeter requiere Java y su instalación
  necesitaba permisos de administrador no disponibles. La evaluación exige acordar
  previamente cualquier sustitución de herramienta.
- Comentarle también la restricción de cuota de la suscripción Azure for Students
  (6 vCPU por región y serie B x86 deshabilitada), que obligó a usar máquinas ARM64
  y a acotar el autoescalado a 1-2 instancias. Está documentado en las incidencias 1
  y 2 de la sección 7.5 del informe.
- Acordarse de desasignar la infraestructura cuando no se esté usando, para no gastar
  el crédito:

```bash
az vmss deallocate -g rg-chorombo-eval3 -n vmss-chorombo-app && az vm deallocate -g rg-chorombo-eval3 -n vm-chorombo-servicios
```

## Cómo regenerar el .docx y el PDF

Se ejecuta con Node de **Windows** (no desde dentro de WSL), porque el script
de PDF usa el Chrome instalado en Windows. Desde PowerShell o Git Bash, parado
en esta carpeta (`informe/`, accesible como
`\\wsl.localhost\ubuntu\home\<usuario>\eval3\informe`):

```bash
npm install              # una sola vez (instala docx, mammoth, puppeteer, sharp)
node build.js            # regenera Eval_U3_Cloud_Carrasco.docx a partir del contenido embebido en build.js
node convert-pdf.js      # convierte ese .docx a Eval_U3_Cloud_Carrasco.pdf (docx -> HTML con mammoth -> PDF con Chrome headless)
```

No hace falta LibreOffice ni permisos de administrador: `convert-pdf.js` usa el
Chrome ya instalado en `C:\Program Files\Google\Chrome\Application\chrome.exe`.
Si esa ruta no existe en tu equipo, cambia `CHROME` al inicio de `convert-pdf.js`.

También puedes abrir directamente `Eval_U3_Cloud_Carrasco.docx` en Word o
Google Docs y usar "Guardar como PDF" — el contenido es el mismo; solo cambia
el índice, que en Word sí calcula los números de página reales (clic derecho
sobre el índice → "Actualizar campo"), mientras que la versión generada por
`convert-pdf.js` arma un índice simple sin números de página.
