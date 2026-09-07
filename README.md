# Gestor Documental — Escuela Básica G-733 Chorombo Bajo

Proyecto de la Evaluación Unidad 3 — Arquitectura de Soluciones Cloud (IF304IINF)
Instituto Profesional San Sebastián — Álvaro Carrasco

Solución cloud para que el equipo directivo de la escuela cargue y consulte su
documentación institucional (memos, oficios, citaciones de apoderados, acuerdos,
documentos de reuniones comunales y permisos administrativos).

---

## Qué se despliega

| Componente | Servicio | Para qué |
|---|---|---|
| Aplicación web | VM Scale Set (2 a 4 instancias, Ubuntu 22.04) | Corre el Gestor Documental |
| Balanceador | Azure Load Balancer | Reparte el tráfico y saca del pool las instancias caídas |
| Autoescalado | Azure Monitor Autoscale | Agrega instancias cuando la CPU supera 70% |
| Base de datos | PostgreSQL en VM de servicios | Metadatos de los documentos |
| Almacenamiento | Azure Blob Storage | Los archivos en sí |
| Monitoreo | Prometheus + Grafana | Métricas, panel y alertas |

Las instancias se reparten entre las zonas de disponibilidad 1 y 2, de modo que
la caída de una zona no deja el servicio abajo.

---

## Antes de empezar

Necesitas tener instalado (todo dentro de WSL/Ubuntu):

```bash
sudo apt update && sudo apt install -y unzip curl git python3-pip ansible
```

**Azure CLI:**
```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
az --version
```

**Terraform:**
```bash
wget -O - https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform -y
terraform version
```

**Colección de Ansible para PostgreSQL:**
```bash
ansible-galaxy collection install community.postgresql
```

**Clave SSH** (si no tienes una):
```bash
ssh-keygen -t rsa -b 4096 -N "" -f ~/.ssh/id_rsa
```

> **Importante:** trabaja siempre dentro del sistema de archivos de WSL
> (`~/eval3`), **nunca** en `/mnt/c/...` ni dentro de OneDrive. Las claves SSH
> necesitan permisos `600` que Windows no respeta, y OneDrive puede corromper el
> archivo de estado de Terraform al sincronizarlo.

---

## Paso 1 — Subir el código a un repositorio

Las instancias descargan la aplicación desde Git al arrancar, así que el
repositorio debe existir y ser público (o accesible) antes de desplegar.

```bash
cd ~/eval3
git init
git add .
git commit -m "Proyecto EVA3 - Gestor Documental Chorombo Bajo"
git remote add origin https://github.com/TU_USUARIO/eval3-gestor-documental.git
git push -u origin main
```

La evaluación pide adjuntar o enlazar el repositorio, así que este paso además
te sirve como evidencia.

---

## Paso 2 — Conectarse a Azure

```bash
az login
az account show
```

Se abre el navegador. Inicia sesión con `alvaro.carrasco.silva@estudiante.ipss.cl`
(la cuenta de Azure for Students).

---

## Paso 3 — Configurar las variables

```bash
cd ~/eval3/terraform
cp terraform.tfvars.ejemplo terraform.tfvars
curl ifconfig.me    # esta es tu IP pública, anótala
nano terraform.tfvars
```

Completa los cuatro valores: tu IP (con `/32` al final), la URL de tu
repositorio, una contraseña para PostgreSQL y la ruta de tu clave SSH.

> Si tu conexión de internet cambia de IP, tendrás que actualizar `mi_ip` y
> volver a aplicar, o te quedarás fuera por SSH.

---

## Paso 4 — Desplegar la infraestructura

```bash
terraform init
terraform plan      # revisa lo que va a crear antes de aceptar
terraform apply     # escribe "yes" para confirmar
```

Demora entre 5 y 10 minutos. Al terminar entrega las URLs:

```
url_aplicacion       = "http://X.X.X.X"
ip_vm_servicios      = "Y.Y.Y.Y"
url_grafana          = "http://Y.Y.Y.Y:3000"
url_prometheus       = "http://Y.Y.Y.Y:9090"
```

**Captura esta salida**: es evidencia del indicador 3.1 (construcción de la
infraestructura).

---

## Paso 5 — Configurar la VM de servicios con Ansible

```bash
cd ~/eval3/ansible
cp inventario.ini.ejemplo inventario.ini
nano inventario.ini      # reemplaza X.X.X.X por la ip_vm_servicios del paso 4

ansible -i inventario.ini servicios -m ping        # verifica la conexión
ansible-playbook -i inventario.ini playbook-servicios.yml \
  -e "clave_bd=LA_MISMA_CLAVE_DEL_TFVARS"
```

**Captura la salida del playbook** (el resumen `PLAY RECAP` con los `ok` y
`changed`): es evidencia de automatización con Ansible.

El playbook deja creadas la base de datos, el usuario y la tabla
`documentos` (cada instancia de la app abre su propia conexión por
petición, así que no hace falta reiniciarlas para que "tomen" la base:
en cuanto el playbook termina, ya pueden usarla). Igual conviene
reiniciarlas una vez, como verificación de que todo quedó bien conectado:

```bash
az vmss restart --resource-group rg-chorombo-eval3 --name vmss-chorombo-app
```

---

## Paso 6 — Verificar que funciona

1. Abre `http://<url_aplicacion>` en el navegador
2. Entra con usuario `directora` / clave `chorombo2026`
3. Sube un documento de prueba y descárgalo
4. Recarga varias veces y mira el pie de página: debería alternar entre
   instancias distintas (eso demuestra el balanceo)
5. Abre Grafana en `http://<ip_servicios>:3000` (usuario `admin`, clave `admin`,
   te pedirá cambiarla) y arma un panel con las métricas de CPU
6. Abre Prometheus en `http://<ip_servicios>:9090` → pestaña **Alerts** para ver
   las tres reglas cargadas

---

## Paso 7 — Ejecutar las pruebas

### Pruebas funcionales (Selenium)

```bash
cd ~/eval3/pruebas/selenium
pip install -r requirements.txt
export URL_APP=http://<url_aplicacion>
pytest -v test_gestor.py --html=reporte.html
```

Genera `reporte.html` con el resultado de cada caso. **Esa es tu evidencia**
del indicador 3.2.

### Prueba de carga (JMeter)

```bash
cd ~/eval3/pruebas/jmeter
~/apache-jmeter-5.6.3/bin/jmeter -n -t plan_carga.jmx \
  -Jhost=<ip_del_balanceador> -l resultados.jtl -e -o reporte-html
```

Dura 7 minutos con 100 usuarios simulados. Mientras corre:

- En **Grafana / Prometheus** vas a ver la CPU subir sobre el 70%
- A los ~2 minutos se dispara la alerta **CpuAltaEnInstancias** (captúrala en
  Prometheus → Alerts, en estado `FIRING`)
- A los ~5 minutos el autoescalado agrega una instancia. Verifícalo con:
  ```bash
  az vmss list-instances --resource-group rg-chorombo-eval3 \
    --name vmss-chorombo-app -o table
  ```

Captura las tres cosas: el reporte de JMeter, la alerta disparada y el
Scale Set con la instancia nueva.

---

## Paso 8 — Prueba de falla controlada

Esto es lo que exige la evaluación: tumbar un recurso a propósito y documentar
qué pasa.

```bash
# 1. Ver las instancias activas
az vmss list-instances --resource-group rg-chorombo-eval3 \
  --name vmss-chorombo-app -o table

# 2. Apagar una de ellas (reemplaza 0 por el ID que corresponda)
az vmss stop --resource-group rg-chorombo-eval3 \
  --name vmss-chorombo-app --instance-ids 0
```

Qué debes observar y capturar:

1. **El sitio sigue funcionando** — recarga `http://<url_aplicacion>`: responde
   igual, pero el pie muestra siempre la misma instancia
2. **El balanceador la sacó del pool** — Azure Portal → Load Balancer →
   Backend pools, aparece la instancia como no saludable
3. **Se disparó la alerta** `InstanciaCaida` en Prometheus → Alerts
4. **Recuperación** — vuelve a encenderla y anota cuánto tarda en volver al pool:
   ```bash
   az vmss start --resource-group rg-chorombo-eval3 \
     --name vmss-chorombo-app --instance-ids 0
   ```

---

## Paso 9 — Apagar todo cuando termines

**Esto es importante.** Tienes US$100 de crédito y no se renuevan. Dejar todo
corriendo 24/7 se come el crédito en unas semanas.

Si vas a seguir trabajando mañana, apaga sin destruir:

```bash
az vmss deallocate --resource-group rg-chorombo-eval3 --name vmss-chorombo-app
az vm deallocate --resource-group rg-chorombo-eval3 --name vm-chorombo-servicios
```

Cuando ya tengas toda la evidencia capturada y no necesites más el entorno:

```bash
cd ~/eval3/terraform
terraform destroy
```

Revisa el gasto en el portal de Azure → **Cost Management** de vez en cuando.

---

## Evidencia que hay que capturar (checklist)

- [ ] Salida de `terraform apply` con los recursos creados
- [ ] Recursos visibles en el portal de Azure
- [ ] `PLAY RECAP` del playbook de Ansible
- [ ] Aplicación funcionando (login, subida, listado, descarga)
- [ ] Pie de página alternando entre instancias (balanceo)
- [ ] Reporte HTML de Selenium
- [ ] Reporte de JMeter
- [ ] Panel de Grafana con las métricas
- [ ] Prometheus → Alerts con las 3 reglas cargadas
- [ ] Alerta `CpuAltaEnInstancias` en estado FIRING durante la carga
- [ ] Scale Set con la instancia adicional tras el autoescalado
- [ ] Alerta `InstanciaCaida` en estado FIRING durante la prueba de falla
- [ ] Servicio respondiendo con una instancia caída

---

## Estructura del repositorio

```
eval3/
├── app/                     Aplicación web (Flask)
│   ├── app.py
│   ├── requirements.txt
│   └── templates/
├── terraform/               Infraestructura como código
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── cloud-init-app.yaml
├── ansible/                 Configuración de la VM de servicios
│   ├── playbook-servicios.yml
│   └── files/
│       ├── prometheus.yml
│       └── alertas.yml
└── pruebas/
    ├── selenium/            Pruebas funcionales
    └── jmeter/              Prueba de carga
```
