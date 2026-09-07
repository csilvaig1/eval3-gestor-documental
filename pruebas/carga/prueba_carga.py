"""
Prueba de carga y concurrencia del Gestor Documental.

Sustituye a Apache JMeter en el entorno de trabajo usado, donde no fue posible
instalar Java (requiere privilegios de administrador). Usa solo la biblioteca
estandar de Python, por lo que corre en cualquier equipo sin instalar nada.

Genera carga concurrente sobre el listado de documentos (la operacion mas
frecuente del equipo directivo) y reporta throughput, latencias y errores.

Uso:
    python3 prueba_carga.py --url http://<ip-balanceador> --usuarios 40 --duracion 300
"""

import argparse
import http.cookiejar
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

resultados_lock = threading.Lock()
latencias = []
errores = 0
peticiones = 0
instancias_vistas = {}
detener = threading.Event()


def sesion_iniciada(url, usuario, clave):
    """Abre una sesion y devuelve el opener con la cookie ya cargada."""
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    datos = urllib.parse.urlencode({"usuario": usuario, "clave": clave}).encode()
    opener.open(f"{url}/login", datos, timeout=30).read()
    return opener


def trabajador(url, usuario, clave):
    global errores, peticiones
    try:
        opener = sesion_iniciada(url, usuario, clave)
    except Exception:
        with resultados_lock:
            errores += 1
        return

    while not detener.is_set():
        inicio = time.time()
        try:
            with opener.open(f"{url}/documentos", timeout=30) as r:
                cuerpo = r.read().decode("utf-8", "ignore")
                ok = r.status == 200
            transcurrido = time.time() - inicio

            marca = "Atendido por la instancia:"
            instancia = "desconocida"
            if marca in cuerpo:
                instancia = cuerpo.split(marca)[1].split("<")[0].strip()

            with resultados_lock:
                peticiones += 1
                latencias.append(transcurrido)
                instancias_vistas[instancia] = instancias_vistas.get(instancia, 0) + 1
                if not ok:
                    errores += 1
        except Exception:
            with resultados_lock:
                peticiones += 1
                errores += 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--usuarios", type=int, default=40)
    p.add_argument("--duracion", type=int, default=300)
    p.add_argument("--usuario", default="directora")
    p.add_argument("--clave", default="chorombo2026")
    args = p.parse_args()

    print("=" * 60)
    print(" PRUEBA DE CARGA - Gestor Documental Chorombo Bajo")
    print("=" * 60)
    print(f" URL objetivo:        {args.url}")
    print(f" Usuarios simulados:  {args.usuarios}")
    print(f" Duracion:            {args.duracion} segundos")
    print(f" Inicio:              {time.strftime('%H:%M:%S')}")
    print("-" * 60)

    hilos = [threading.Thread(target=trabajador, args=(args.url, args.usuario, args.clave), daemon=True)
             for _ in range(args.usuarios)]
    for h in hilos:
        h.start()

    inicio = time.time()
    try:
        while time.time() - inicio < args.duracion:
            time.sleep(30)
            with resultados_lock:
                n, e = peticiones, errores
                prom = statistics.mean(latencias[-500:]) if latencias else 0
            transcurrido = int(time.time() - inicio)
            print(f"  {time.strftime('%H:%M:%S')} | {transcurrido:4d}s | "
                  f"peticiones={n:6d} | errores={e:4d} | latencia_media={prom*1000:7.1f} ms")
    except KeyboardInterrupt:
        pass

    detener.set()
    time.sleep(2)

    print("-" * 60)
    print(" RESULTADOS")
    print("-" * 60)
    total = time.time() - inicio
    with resultados_lock:
        if latencias:
            ordenadas = sorted(latencias)
            p95 = ordenadas[int(len(ordenadas) * 0.95)]
            p99 = ordenadas[int(len(ordenadas) * 0.99)]
            print(f"  Peticiones totales:      {peticiones}")
            print(f"  Errores:                 {errores} ({errores / max(peticiones, 1) * 100:.2f}%)")
            print(f"  Throughput:              {peticiones / total:.1f} peticiones/segundo")
            print(f"  Latencia media:          {statistics.mean(latencias) * 1000:.1f} ms")
            print(f"  Latencia mediana:        {statistics.median(latencias) * 1000:.1f} ms")
            print(f"  Latencia percentil 95:   {p95 * 1000:.1f} ms")
            print(f"  Latencia percentil 99:   {p99 * 1000:.1f} ms")
            print(f"  Latencia maxima:         {max(latencias) * 1000:.1f} ms")
            print()
            print("  Reparto entre instancias (evidencia del balanceador):")
            for inst, cuenta in sorted(instancias_vistas.items()):
                print(f"    {inst:32s} {cuenta:6d} peticiones "
                      f"({cuenta / max(peticiones, 1) * 100:5.1f}%)")
        else:
            print("  No se registraron peticiones exitosas.")
    print(f"\n  Fin: {time.strftime('%H:%M:%S')}")


if __name__ == "__main__":
    main()
