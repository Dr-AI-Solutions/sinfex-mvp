"""
Fase 1 - Paso 1: Descarga de PDFs oficiales de protocolos de laboratorio.

Lee las URLs desde `enlaces_sinfex_por_id.txt`, descarga cada PDF en
`scripts/pdfs_origen/` con una pausa de 0.25 segundos entre peticiones,
es reanudable si se interrumpe y genera `scripts/mapa_urls.json` vinculando
cada archivo local con su URL oficial original.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
ENLACES_FILE = BASE_DIR / "enlaces_sinfex_por_id.txt"
PDFS_DIR = Path(__file__).resolve().parent / "pdfs_origen"
MAPA_URLS_FILE = Path(__file__).resolve().parent / "mapa_urls.json"

PAUSA_SEGUNDOS = 0.25
TIMEOUT_SEGUNDOS = 30
MAX_REINTENTOS = 3
GUARDAR_CADA = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*;q=0.8",
}


def cargar_urls(ruta: Path) -> list[str]:
    if not ruta.exists():
        print(f"Error: No se encontró el archivo {ruta}", file=sys.stderr)
        sys.exit(1)
    urls: list[str] = []
    vistos: set[str] = set()
    with ruta.open("r", encoding="utf-8") as f:
        for linea in f:
            url = linea.strip()
            if url and not url.startswith("#") and url not in vistos:
                vistos.add(url)
                urls.append(url)
    return urls


def cargar_mapa_existente(ruta: Path) -> dict[str, str]:
    if ruta.exists():
        try:
            with ruta.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def guardar_mapa(ruta: Path, mapa: dict[str, str]) -> None:
    tmp_ruta = ruta.with_suffix(".tmp")
    with tmp_ruta.open("w", encoding="utf-8") as f:
        json.dump(mapa, f, ensure_ascii=False, indent=2)
    tmp_ruta.replace(ruta)


def nombre_archivo_desde_url(url: str) -> str:
    doc_id = url.rstrip("/").split("/")[-1].strip()
    if not doc_id:
        doc_id = f"doc_{abs(hash(url))}"
    return f"{doc_id}.pdf"


def es_pdf_valido(ruta: Path) -> bool:
    if not ruta.exists() or ruta.stat().st_size < 100:
        return False
    try:
        with ruta.open("rb") as f:
            cabecera = f.read(5)
        return cabecera == b"%PDF-"
    except OSError:
        return False


def descargar_pdf(session: requests.Session, url: str, destino: Path) -> tuple[bool, str]:
    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=TIMEOUT_SEGUNDOS)
            if resp.status_code == 200:
                contenido = resp.content
                if contenido.startswith(b"%PDF-"):
                    tmp_dest = destino.with_suffix(".part")
                    with tmp_dest.open("wb") as f:
                        f.write(contenido)
                    tmp_dest.replace(destino)
                    return True, f"OK ({len(contenido) // 1024} KB)"
                content_type = resp.headers.get("Content-Type", "")
                return False, f"No es PDF válido (Content-Type: {content_type})"
            if resp.status_code in (429, 500, 502, 503, 504) and intento < MAX_REINTENTOS:
                time.sleep(1.5 * intento)
                continue
            return False, f"HTTP {resp.status_code}"
        except requests.RequestException as exc:
            if intento < MAX_REINTENTOS:
                time.sleep(1.5 * intento)
                continue
            return False, f"Error de red: {exc}"
    return False, "Falló tras reintentos"


def main() -> None:
    PDFS_DIR.mkdir(parents=True, exist_ok=True)
    urls = cargar_urls(ENLACES_FILE)
    total = len(urls)
    mapa = cargar_mapa_existente(MAPA_URLS_FILE)

    print(f"Total de URLs únicas a procesar: {total}")
    descargados = 0
    omitidos = 0
    errores: list[tuple[str, str]] = []

    session = requests.Session()
    try:
        for idx, url in enumerate(urls, start=1):
            nombre_archivo = nombre_archivo_desde_url(url)
            destino = PDFS_DIR / nombre_archivo

            if es_pdf_valido(destino):
                mapa[nombre_archivo] = url
                omitidos += 1
                if idx % 100 == 0 or idx == total:
                    print(f"[{idx}/{total}] Ya existentes: {omitidos} | Nuevos: {descargados} | Errores: {len(errores)}")
                continue

            exito, detalle = descargar_pdf(session, url, destino)
            if exito:
                mapa[nombre_archivo] = url
                descargados += 1
                print(f"[{idx}/{total}] Descargado {nombre_archivo} - {detalle}")
            else:
                errores.append((url, detalle))
                print(f"[{idx}/{total}] ERROR en {url}: {detalle}", file=sys.stderr)

            if idx % GUARDAR_CADA == 0:
                guardar_mapa(MAPA_URLS_FILE, mapa)

            if idx < total:
                time.sleep(PAUSA_SEGUNDOS)
    except KeyboardInterrupt:
        print("\nDescarga interrumpida por el usuario. Guardando progreso...")
    finally:
        guardar_mapa(MAPA_URLS_FILE, mapa)
        session.close()

    print("\n--- Resumen de descarga ---")
    print(f"Total URLs:       {total}")
    print(f"Ya existentes:    {omitidos}")
    print(f"Descargados hoy:  {descargados}")
    print(f"Errores:          {len(errores)}")
    print(f"Mapa guardado en: {MAPA_URLS_FILE}")

    if errores:
        log_errores = Path(__file__).resolve().parent / "errores_descarga.log"
        with log_errores.open("w", encoding="utf-8") as f:
            for url, detalle in errores:
                f.write(f"{url}\t{detalle}\n")
        print(f"Detalle de errores guardado en: {log_errores}")


if __name__ == "__main__":
    main()
