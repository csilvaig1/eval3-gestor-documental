"""
Pruebas funcionales del Gestor Documental con Selenium
Evaluacion Unidad 3 - Arquitectura de Soluciones Cloud
Alvaro Carrasco - IPSS

Ejecutar:
    export URL_APP=http://<ip-del-balanceador>
    pytest -v test_gestor.py --html=reporte.html

Cada prueba corresponde a un caso documentado en el plan de pruebas
del informe (CP-01 a CP-06).
"""

import os
import time
import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

URL = os.environ.get("URL_APP", "http://localhost:8000")
USUARIO = "directora"
CLAVE = os.environ.get("PASS_DIRECTORA", "chorombo2026")

# Archivo de prueba que se sube en CP-02
ARCHIVO_PRUEBA = os.path.abspath("documento_prueba.txt")


@pytest.fixture(scope="function")
def navegador():
    """Abre Chrome en modo headless antes de cada prueba y lo cierra al final."""
    opciones = Options()
    opciones.add_argument("--headless=new")
    opciones.add_argument("--no-sandbox")
    opciones.add_argument("--window-size=1280,900")
    driver = webdriver.Chrome(options=opciones)
    driver.implicitly_wait(10)
    yield driver
    driver.quit()


def iniciar_sesion(navegador, usuario=USUARIO, clave=CLAVE):
    """Funcion auxiliar: hace login y deja el navegador en la lista."""
    navegador.get(f"{URL}/login")
    navegador.find_element(By.ID, "usuario").send_keys(usuario)
    navegador.find_element(By.ID, "clave").send_keys(clave)
    navegador.find_element(By.CSS_SELECTOR, "button[type=submit]").click()


def crear_archivo_prueba():
    """Genera el archivo que se usa en la prueba de subida."""
    with open(ARCHIVO_PRUEBA, "w", encoding="utf-8") as f:
        f.write("Citacion a reunion de apoderados - documento de prueba automatizada\n")


# ---------------------------------------------------------------------------
# CP-01: Acceso al sistema
# ---------------------------------------------------------------------------
def test_cp01_login_correcto(navegador):
    """Un usuario del equipo directivo con credenciales validas entra al sistema."""
    iniciar_sesion(navegador)
    WebDriverWait(navegador, 10).until(EC.url_contains("/documentos"))
    assert "Documentos cargados" in navegador.page_source


def test_cp01b_login_incorrecto(navegador):
    """Con una contrasena invalida el sistema rechaza el acceso."""
    iniciar_sesion(navegador, clave="clave-equivocada")
    assert "incorrectos" in navegador.page_source
    assert "/documentos" not in navegador.current_url


# ---------------------------------------------------------------------------
# CP-02: Carga de un documento (frontend -> backend -> Blob Storage)
# ---------------------------------------------------------------------------
def test_cp02_subir_documento(navegador):
    """Se sube un archivo y queda visible en el listado."""
    crear_archivo_prueba()
    iniciar_sesion(navegador)

    navegador.find_element(By.ID, "archivo").send_keys(ARCHIVO_PRUEBA)
    Select(navegador.find_element(By.ID, "categoria")).select_by_visible_text(
        "Citacion de apoderados")
    navegador.find_element(By.ID, "descripcion").send_keys(
        "Prueba automatizada CP-02")
    navegador.find_element(By.CSS_SELECTOR,
                           "form[action='/subir'] button").click()

    WebDriverWait(navegador, 15).until(
        EC.presence_of_element_located((By.CLASS_NAME, "mensaje")))
    assert "cargado correctamente" in navegador.page_source
    assert "documento_prueba.txt" in navegador.page_source


# ---------------------------------------------------------------------------
# CP-03: Filtro por categoria
# ---------------------------------------------------------------------------
def test_cp03_filtrar_por_categoria(navegador):
    """El listado se puede filtrar por el tipo de documento."""
    iniciar_sesion(navegador)
    navegador.get(f"{URL}/documentos?categoria=Citacion+de+apoderados")

    filas = navegador.find_elements(By.CSS_SELECTOR, "tbody tr")
    # Todas las filas mostradas deben ser de la categoria filtrada
    for fila in filas:
        assert "Citacion de apoderados" in fila.text


# ---------------------------------------------------------------------------
# CP-04: Descarga de un documento
# ---------------------------------------------------------------------------
def test_cp04_descargar_documento(navegador):
    """El enlace de descarga responde correctamente (no da error 404 ni 500)."""
    iniciar_sesion(navegador)
    enlace = navegador.find_elements(By.PARTIAL_LINK_TEXT, "Descargar")
    assert len(enlace) > 0, "No hay documentos cargados para descargar"

    url_descarga = enlace[0].get_attribute("href")
    navegador.get(url_descarga)
    # Si la descarga falla, la aplicacion muestra un mensaje de error
    assert "no existe" not in navegador.page_source.lower()


# ---------------------------------------------------------------------------
# CP-05: Persistencia de los datos
# ---------------------------------------------------------------------------
def test_cp05_persistencia(navegador):
    """
    El documento sigue apareciendo despues de cerrar sesion y volver a entrar.
    Esto valida que los datos estan en la base compartida y no en memoria
    de una instancia puntual.
    """
    iniciar_sesion(navegador)
    navegador.get(f"{URL}/logout")
    iniciar_sesion(navegador)
    # Hay que esperar la redireccion al listado: sin esta espera la prueba
    # revisa el HTML de la pagina de login y falla aunque el dato si persista.
    WebDriverWait(navegador, 10).until(EC.url_contains("/documentos"))
    assert "documento_prueba.txt" in navegador.page_source


# ---------------------------------------------------------------------------
# CP-06: Balanceo de carga entre instancias
# ---------------------------------------------------------------------------
def test_cp06_balanceo_entre_instancias(navegador):
    """
    Se recarga la pagina varias veces y se registra que instancia respondio.
    La aplicacion muestra su hostname al pie, asi que si el balanceador
    esta repartiendo, deberian aparecer al menos dos nombres distintos.
    """
    iniciar_sesion(navegador)
    instancias = set()

    for _ in range(15):
        navegador.get(f"{URL}/documentos")
        pie = navegador.find_element(By.CLASS_NAME, "pie").text
        instancias.add(pie.replace("Atendido por la instancia:", "").strip())
        time.sleep(0.5)

    print(f"\nInstancias que respondieron: {instancias}")
    assert len(instancias) >= 2, (
        f"Solo respondio una instancia ({instancias}). "
        "Revisar que el Scale Set tenga 2 instancias activas y sanas.")
