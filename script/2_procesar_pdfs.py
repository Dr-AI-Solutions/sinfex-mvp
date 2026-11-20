"""
Fase 1 - Paso 2 (Determinista, 100% Offline, Sin IA):
Extractor estructurado de protocolos SINFEX usando `pypdf` y expresiones regulares.

Lee todos los PDFs en `scripts/pdfs_origen/`, extrae las secciones oficiales
de la plantilla SINFEX y genera:
  - `web/base_examenes.json`
  - `web/datos_examenes.js` (`window.EXAMENES_DATA = [...]` para uso sin servidor `file://`)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pdfplumber
from pypdf import PdfReader

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
PDFS_DIR = SCRIPTS_DIR / "pdfs_origen"
MAPA_URLS_FILE = SCRIPTS_DIR / "mapa_urls.json"
SALIDA_JSON = BASE_DIR / "web" / "base_examenes.json"
SALIDA_JS = BASE_DIR / "web" / "datos_examenes.js"

# Encabezados oficiales de la plantilla SINFEX (orden flexible, permite notas al pie como "6" o "2,3" antes de ":")
SECCIONES_SINFEX: list[tuple[str, str]] = [
    ("codigo_interno", r"C[oó]digo\s+del\s+Examen"),
    ("nombres_examen", r"Nombres?\s+del\s+Examen"),
    ("laboratorios", r"Laboratorios?\s+de\s+Procesamiento"),
    ("preparacion_paciente", r"Preparaci[oó]n\s+del\s+Paciente"),
    ("muestra_requerida", r"Muestra\s+Requerida"),
    ("estabilidad_muestra", r"Estabilidad\s+de\s+la\s+Muestra"),
    ("condiciones_envio", r"Condiciones\s+de\s+Env[ií]o\s+al\s+Laboratorio"),
    ("metodo_utilizado", r"M[eé]todo\s+Utilizado"),
    ("valores_referencia", r"(?:Intervalos?|Valores?)\s+de\s+Referencia"),
    ("valor_critico", r"Valor(?:es)?\s+(?:Cr[ií]ticos?|de\s+Alerta)"),
    ("parametros_desempeno", r"Par[aá]metros\s+de\s+Desempe[ñn]o"),
    ("informacion_clinica", r"Informaci[oó]n\s+Cl[ií]nica"),
    ("referencias", r"Referencias"),
]

PATRON_SECCIONES = re.compile(
    r"(?:^|\n)\s*(?:"
    + "|".join(f"(?P<{clave}>{patron})" for clave, patron in SECCIONES_SINFEX)
    + r")(?:\s*[\d,\s\-–]*)?\s*(?::|(?<=\bDesempe[ñn]o)(?=\s*\n|\s+\d))",
    re.IGNORECASE,
)

# Cortes de seguridad estrictos para evitar arrastre entre secciones
PATRON_CORTE_VALORES = re.compile(
    r"(?:^|\n)\s*(?:Par[aá]metros\s+de\s+Desempe[ñn]o|Informaci[oó]n\s+Cl[ií]nica|Referencias\s*:|\d+\s+de\s+\d+\s*$)",
    re.IGNORECASE,
)
PATRON_CORTE_ESTABILIDAD = re.compile(
    r"(?:^|\n)\s*(?:M[eé]todo\s+Utilizado|(?:Intervalos?|Valores?)\s+de\s+Referencia)",
    re.IGNORECASE,
)


def cortar_antes_de(texto: str, patron: re.Pattern[str]) -> str:
    if not texto:
        return ""
    m = patron.search(texto)
    if m:
        return texto[: m.start()].strip()
    return texto.strip()


def limpiar_tabla(raw_table: list[list[str | None]]) -> tuple[str, list[list[str]]]:
    """
    Limpia saltos de línea internos, detecta fila 0 de título combinado (banner/colspan),
    elimina columnas 100% vacías y compacta desplazamiento horizontal.
    Retorna (titulo_tabla, filas_limpias).
    """
    if not raw_table:
        return "", []
    filas_limpias: list[list[str]] = []
    max_cols = max((len(r) for r in raw_table), default=0)
    if max_cols == 0:
        return "", []

    for row in raw_table:
        limpia = [
            re.sub(r"\s+", " ", (cell or "").replace("\n", " ")).strip()
            for cell in row
        ]
        while len(limpia) < max_cols:
            limpia.append("")
        if any(limpia):
            filas_limpias.append(limpia)

    if not filas_limpias:
        return "", []

    # 0. Detectar fila 0 de título combinado (solo 1 celda con texto y filas siguientes >= 3 columnas con datos)
    titulo_tabla = ""
    if len(filas_limpias) >= 3:
        no_vacios_r0 = [c for c in filas_limpias[0] if c]
        max_datos_sig = max(
            (len([c for c in r if c]) for r in filas_limpias[1:]),
            default=0,
        )
        if len(no_vacios_r0) == 1 and max_datos_sig >= 3:
            titulo_tabla = no_vacios_r0[0]
            filas_limpias = filas_limpias[1:]

    # 1. Eliminar columnas completamente vacías
    cols_activas = [
        c for c in range(max_cols) if any(row[c] for row in filas_limpias)
    ]
    if not cols_activas:
        return titulo_tabla, []

    tabla = [[row[c] for c in cols_activas] for row in filas_limpias]

    # 2. Compactación incondicional fila por fila
    if len(tabla) >= 2:
        encabezados = [c.strip() for c in tabla[0] if c and c.strip()]
        n_cols = len(encabezados)
        if n_cols >= 2:
            no_vacios_r1 = [c.strip() for c in tabla[1] if c and c.strip()]
            fila_unidades_alineada = False
            if len(no_vacios_r1) == n_cols - 1 and no_vacios_r1[0].startswith("("):
                tabla[1] = [""] + no_vacios_r1
                fila_unidades_alineada = True

            nueva_tabla: list[list[str]] = []
            for idx, r in enumerate(tabla):
                if idx == 1 and fila_unidades_alineada:
                    nueva_tabla.append(r)
                    continue
                no_vacios = [c.strip() for c in r if c and c.strip()]
                if len(no_vacios) == n_cols:
                    nueva_tabla.append(no_vacios)
                elif len(r) > n_cols and len(no_vacios) < n_cols:
                    nueva_tabla.append(no_vacios + [""] * (n_cols - len(no_vacios)))
                else:
                    nueva_tabla.append(r)

            max_len = max(n_cols, max((len(r) for r in nueva_tabla), default=n_cols))
            for r in nueva_tabla:
                while len(r) < max_len:
                    r.append("")

            cols_finales = [
                c for c in range(max_len) if any(r[c] for r in nueva_tabla)
            ]
            if cols_finales:
                tabla = [[r[c] for c in cols_finales] for r in nueva_tabla]

    return titulo_tabla, tabla


EXCLUIR_TABLA_KW = (
    "loda",
    "loqb",
    "lod",
    "loq",
    "cv%",
    "cv %",
    "cv c",
    "veracidad",
    "linealidad",
    "recuperación",
    "recuperacion",
    "esteroide",
    "concentración",
    "concentracion",
    "días de procesamiento",
    "dias de procesamiento",
    "plazo de entrega",
    "sistema de información",
)


def es_tabla_valida(tabla: list[list[str]]) -> bool:
    """Filtra falsos positivos: al menos 2 filas y 2 columnas con datos reales."""
    if len(tabla) < 2 or len(tabla[0]) < 2:
        return False
    celdas_con_texto = sum(1 for row in tabla for c in row if c)
    return celdas_con_texto >= 4


def encontrar_limite_y_corte(pdf) -> tuple[int, float] | None:
    """Encuentra (page_idx, top_y) donde comienza Parámetros de Desempeño o Información Clínica."""
    for p_idx, page in enumerate(pdf.pages):
        words = page.extract_words() or []
        for i, w in enumerate(words):
            t = w.get("text", "").lower()
            if t in ("parámetros", "parametros", "información", "informacion"):
                siguiente = words[i + 1].get("text", "").lower() if i + 1 < len(words) else ""
                if (t.startswith("par") and siguiente == "de") or (
                    t.startswith("info") and siguiente.startswith("cl")
                ):
                    return (p_idx, float(w["top"]))
    return None


def encontrar_inicio_referencia(pdf) -> tuple[int, float] | None:
    """Encuentra (page_idx, top_y) donde comienza Intervalo(s)/Valor(es) de Referencia."""
    for p_idx, page in enumerate(pdf.pages):
        words = page.extract_words() or []
        for i, w in enumerate(words):
            t = w.get("text", "").lower()
            if t in ("intervalo", "intervalos", "valor", "valores"):
                w1 = words[i + 1].get("text", "").lower() if i + 1 < len(words) else ""
                w2 = words[i + 2].get("text", "").lower() if i + 2 < len(words) else ""
                if w1 == "de" and w2.startswith("referencia"):
                    return (p_idx, float(w["top"]))
    return None


def empaquetar_tabla(titulo_tabla: str, filas: list[list[str]]) -> dict | list[list[str]]:
    if titulo_tabla:
        return {"titulo_tabla": titulo_tabla, "filas": filas}
    return filas


def extraer_tablas_hibrido(pdf) -> tuple[list[list[str]], list]:
    """
    Detección híbrida con pdfplumber:
    1) Tablas estándar con bordes (page.find_tables()).
    2) Si no se detectan tablas de referencia, segundo intento con estrategia 'text'
       acotado al área de Intervalo(s) de Referencia.
    Respeta estrictamente el límite antes de Parámetros de Desempeño / Información Clínica.
    """
    inicio_ref = encontrar_inicio_referencia(pdf)
    limite = encontrar_limite_y_corte(pdf)
    tabla_estabilidad: list[list[str]] = []
    tablas_referencia: list = []

    def dentro_de_limite(p_idx: int, top_y: float) -> bool:
        if limite is None:
            return True
        lim_p, lim_y = limite
        if p_idx < lim_p:
            return True
        if p_idx > lim_p:
            return False
        return top_y < lim_y - 2

    def despues_de_referencia(p_idx: int, top_y: float) -> bool:
        if inicio_ref is None:
            return False
        ref_p, ref_y = inicio_ref
        if p_idx > ref_p:
            return True
        if p_idx < ref_p:
            return False
        return top_y >= ref_y - 2

    for p_idx, page in enumerate(pdf.pages):
        for t_obj in page.find_tables() or []:
            top_y = float(t_obj.bbox[1])
            if not dentro_de_limite(p_idx, top_y):
                continue
            titulo_tabla, tabla = limpiar_tabla(t_obj.extract())
            if not es_tabla_valida(tabla):
                continue

            header_str = " ".join(tabla[0]).lower()
            if any(k in header_str for k in EXCLUIR_TABLA_KW):
                continue

            if not tabla_estabilidad and "muestra" in header_str and any(
                k in header_str for k in ("ambiente", "refrigerada", "congelada")
            ):
                tabla_estabilidad = tabla
                continue

            # Toda tabla clínica válida dentro de la sección Intervalo(s) de Referencia -> Valor Crítico
            if despues_de_referencia(p_idx, top_y):
                tablas_referencia.append(empaquetar_tabla(titulo_tabla, tabla))
                continue

            # Respaldo por palabras clave si no se detectó el título de sección por coordenadas
            if (
                "analito" in header_str
                or "unidades" in header_str
                or "intervalo" in header_str
                or "referencia" in header_str
                or "edad" in header_str
                or "adulto" in header_str
                or "alerta" in header_str
                or "parámetro" in header_str
                or "parametro" in header_str
                or "eritrocitos" in header_str
                or "leucocitos" in header_str
                or "plaquetas" in header_str
                or "sedimentación" in header_str
            ):
                tablas_referencia.append(empaquetar_tabla(titulo_tabla, tabla))

    # Segundo intento: estrategia 'text' solo si no se detectaron tablas de referencia estándar
    if not tablas_referencia:
        text_settings = {
            "vertical_strategy": "text",
            "horizontal_strategy": "text",
            "snap_tolerance": 4,
        }
        for p_idx, page in enumerate(pdf.pages):
            words = page.extract_words() or []
            ref_top = None
            for i, w in enumerate(words):
                t = w.get("text", "").lower()
                if t in ("intervalos", "intervalo", "valores", "valor"):
                    sig = words[i + 1].get("text", "").lower() if i + 1 < len(words) else ""
                    sig2 = words[i + 2].get("text", "").lower() if i + 2 < len(words) else ""
                    if sig == "de" and sig2.startswith("referencia"):
                        ref_top = float(w["top"])
                        break
            if ref_top is None:
                continue

            bottom_limit = float(page.height) - 20
            if limite and limite[0] == p_idx:
                bottom_limit = min(bottom_limit, limite[1] - 2)
            if bottom_limit <= ref_top + 20:
                continue

            crop = page.crop((0, max(0, ref_top + 12), float(page.width), bottom_limit))
            for t_obj in crop.find_tables(table_settings=text_settings) or []:
                titulo_tabla, tabla = limpiar_tabla(t_obj.extract())
                if not es_tabla_valida(tabla):
                    continue
                header_str = " ".join(tabla[0]).lower()
                if any(k in header_str for k in EXCLUIR_TABLA_KW):
                    continue
                tablas_referencia.append(empaquetar_tabla(titulo_tabla, tabla))

    return tabla_estabilidad, tablas_referencia


def limpiar_encabezados_pagina(texto: str) -> str:
    """Elimina cabeceras repetitivas de página de SINFEX."""
    lineas = texto.splitlines()
    limpias: list[str] = []
    for linea in lineas:
        s = linea.strip()
        if not s:
            limpias.append("")
            continue
        if re.match(r"^Sistema\s+de\s+Informaci[oó]n\s+de\s+Ex[aá]menes,\s*SINFEX$", s, re.IGNORECASE):
            continue
        if re.match(r"^\d+\s+.+?\s+\d+\s+de\s+\d+$", s, re.IGNORECASE):
            continue
        limpias.append(linea.rstrip())
    return "\n".join(limpias)


def normalizar_espacios(texto: str) -> str:
    """Limpia espacios múltiples preservando saltos de línea útiles."""
    lineas = [re.sub(r"[ \t]+", " ", l).strip() for l in texto.splitlines()]
    resultado: list[str] = []
    vacias_seguidas = 0
    for l in lineas:
        if not l:
            vacias_seguidas += 1
            if vacias_seguidas <= 1 and resultado:
                resultado.append("")
        else:
            vacias_seguidas = 0
            resultado.append(l)
    return "\n".join(resultado).strip()


def truncar_nombre(nombre: str, max_len: int = 110) -> str:
    """Regla de seguridad: trunca cualquier nombre a un máximo de 110 caracteres."""
    limpio = re.sub(r"\s+", " ", (nombre or "")).strip()
    if len(limpio) <= max_len:
        return limpio
    corte = limpio[: max_len - 3].rfind(" ")
    if corte > 40:
        return limpio[:corte].strip() + "..."
    return limpio[: max_len - 3].strip() + "..."


def es_instructivo_paciente(texto: str) -> bool:
    """Detecta documentos tipo Instructivo (IP-xxx / IL-xxx)."""
    if re.search(r"Estimad[oa]\s+paciente\s*:", texto, re.IGNORECASE):
        return True
    if re.search(
        r"^\s*(?:\([A-Z]{2}-\d+\)\s*)?(?:\d+(?:\s+de\s+\d+)?\s+)?Revisado\s+(?:por\b|[A-Z]{2,})",
        texto,
        re.IGNORECASE,
    ):
        return True
    return False


def extraer_datos_instructivo(texto_completo: str, fallback_codigo: str) -> tuple[str, str, str, str]:
    """
    Para instructivos (IP-xxx / IL-xxx):
    Retorna (nombre, actualizado_en, codigo_instructivo, cuerpo_preparacion).
    """
    plano = re.sub(r"\s+", " ", texto_completo).strip()

    actualizado = ""
    m_act = re.search(r"[ÚU]ltima\s+actualizaci[oó]n\s*:\s*([^/\n]+)", texto_completo, re.IGNORECASE)
    if m_act:
        actualizado = f"Actualizado en {m_act.group(1).strip()}"

    codigo = fallback_codigo
    m_cod = re.search(r"\b((?:IP|IL)-\d+)\b", texto_completo, re.IGNORECASE)
    if m_cod:
        codigo = m_cod.group(1).upper()

    # Quitar cabecera "1 Revisado ... Revisión 04"
    sin_cabecera = re.sub(
        r"^(?:\([A-Z]{2}-\d+\)\s*)?(?:\d+(?:\s+de\s+\d+)?\s+)?Revisado\b.*?(?:Revisi[oó]n\s+\d+|Aprobado\s+por[^\n]*?)\s*",
        "",
        plano,
        flags=re.IGNORECASE,
    ).strip()

    # Extraer título en mayúsculas antes de "(Aplicable para..."
    nombre = ""
    m_ap = re.search(r"^(.*?)\(\s*Aplicable\s+para\b", sin_cabecera, re.IGNORECASE)
    if m_ap:
        nombre = m_ap.group(1).strip(" -:")
    else:
        # Si no hay "(Aplicable para...", tomar el bloque inicial en mayúsculas
        m_mayus = re.match(r"^([A-ZÁÉÍÓÚÑ0-9\s,&/\-\.]{6,110}?)(?=\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]|\s+Estimad[oa]\b|$)", sin_cabecera)
        if m_mayus:
            nombre = m_mayus.group(1).strip(" -:")
        else:
            nombre = sin_cabecera[:110]

    # El resto del texto desde "Estimado/a paciente:" o después del título va a preparacion_paciente
    m_est = re.search(r"Estimad[oa]\s+paciente\s*:.*", texto_completo, re.IGNORECASE | re.DOTALL)
    if m_est:
        cuerpo = normalizar_espacios(m_est.group(0))
    else:
        cuerpo = normalizar_espacios(sin_cabecera[len(nombre):].strip())

    return truncar_nombre(nombre), actualizado, codigo, cuerpo


def extraer_titulo_y_actualizacion(pagina1_raw: str) -> tuple[str, str]:
    """Extrae el título principal y la línea 'Actualizado en...' de la página 1."""
    actualizado = ""
    m_act = re.search(
        r"((?:Actualizado|Elaborado)\s+en\s+[^\n]+?)(?:\s+por\b|\n|$)",
        pagina1_raw,
        re.IGNORECASE,
    )
    if m_act:
        actualizado = re.sub(r"\s+", " ", m_act.group(1)).strip(" .")

    limpio = limpiar_encabezados_pagina(pagina1_raw)
    corte = len(limpio)
    for marcador in (
        r"Actualizado\s+en\b",
        r"Elaborado\s+en\b",
        r"Revisado\s+y\s+Aprobado\b",
        r"C[oó]digo\s+del\s+Examen\b",
    ):
        m = re.search(marcador, limpio, re.IGNORECASE)
        if m and m.start() < corte:
            corte = m.start()

    bloque_titulo = limpio[:corte].strip()
    bloque_titulo = re.sub(r"^\d+\s+de\s+\d+\s+", "", bloque_titulo)
    lineas_titulo = [re.sub(r"\s+", " ", l).strip() for l in bloque_titulo.splitlines() if l.strip()]
    titulo = " ".join(lineas_titulo)
    return truncar_nombre(titulo), actualizado


def extraer_secciones(texto_limpio: str) -> dict[str, str]:
    """Divide el texto limpio usando los encabezados oficiales de SINFEX."""
    matches = list(PATRON_SECCIONES.finditer(texto_limpio))
    secciones: dict[str, str] = {}
    for i, match in enumerate(matches):
        clave = match.lastgroup
        if not clave:
            continue
        inicio = match.end()
        fin = matches[i + 1].start() if i + 1 < len(matches) else len(texto_limpio)
        contenido = normalizar_espacios(texto_limpio[inicio:fin])
        if clave not in secciones or len(contenido) > len(secciones[clave]):
            secciones[clave] = contenido
    return secciones


def extraer_sinonimos(titulo: str, nombres_examen: str) -> list[str]:
    """Extrae siglas entre paréntesis y alias cortos tras comas."""
    fuente = f"{titulo} | {nombres_examen}"
    vistos: set[str] = set()
    sinonimos: list[str] = []

    def agregar(candidato: str) -> None:
        c = re.sub(r"\s+", " ", candidato).strip(" .,;:")
        if not c or len(c) < 2 or len(c) > 40:
            return
        clave = c.lower()
        if clave not in vistos:
            vistos.add(clave)
            sinonimos.append(c)

    for m in re.finditer(r"\(([^()]{2,40})\)", fuente):
        agregar(m.group(1))

    # También capturar siglas/abreviaturas tras coma en "Nombres del Examen" (ej: ", TRAb" o ", FVW:AG")
    for parte in re.split(r"[,;/]", nombres_examen):
        p = parte.strip()
        if p and len(p) <= 18 and re.search(r"[A-ZÁÉÍÓÚ]{2,}", p):
            agregar(p)

    return sinonimos


def detectar_color_tapa(muestra_requerida: str) -> str:
    """Detecta el color de tapa por palabras clave en Muestra Requerida."""
    t = muestra_requerida.lower()
    if "tapa roja" in t or "tapa rojo" in t:
        return "rojo"
    if "tapa lila" in t or "edta" in t:
        return "lila"
    if "tapa celeste" in t or "citrato" in t:
        return "celeste"
    if "tapa amarilla" in t or "tapa amarillo" in t or "con gel" in t or "gel separador" in t:
        return "amarillo"
    if "tapa verde" in t or "heparina" in t:
        return "verde"
    if "tapa gris" in t or "fluoruro" in t:
        return "gris"
    if "orina" in t:
        return "orina"
    return "otro"


def separar_area_y_tiempo(laboratorios_raw: str) -> tuple[str, str]:
    """Separa el nombre del laboratorio/área y los plazos de procesamiento/entrega."""
    if not laboratorios_raw:
        return "Laboratorio Clínico", "No especificado"

    # Limpiar cabecera de tabla típica de SINFEX
    sin_cabecera = re.sub(
        r"Laboratorio\s+D[ií]as\s+de\s+Procesamiento\s+Plazo\s+de\s+Entrega\s+de\s+Resultados",
        "",
        laboratorios_raw,
        flags=re.IGNORECASE,
    ).strip()

    lineas = [l.strip() for l in sin_cabecera.splitlines() if l.strip()]
    if not lineas:
        return "Laboratorio Clínico", "No especificado"

    # Buscar dónde comienzan los días o plazos para aislar el área
    area_lineas: list[str] = []
    tiempo_lineas: list[str] = []
    patron_tiempo = re.compile(
        r"\b(lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo|diario|seg[uú]n\s+demanda|hasta\s+\d+|d[ií]as?\s+h[aá]biles|horas?|minutos?)\b",
        re.IGNORECASE,
    )

    encontro_tiempo = False
    for linea in lineas:
        if not encontro_tiempo and patron_tiempo.search(linea):
            encontro_tiempo = True
        if encontro_tiempo:
            tiempo_lineas.append(linea)
        else:
            area_lineas.append(linea)

    area = " ".join(area_lineas).strip() if area_lineas else lineas[0]
    tiempo = "\n".join(tiempo_lineas).strip() if tiempo_lineas else sin_cabecera
    return area, tiempo


def resumir_informacion_clinica(texto: str, max_chars: int = 900) -> str:
    """Devuelve la información clínica limpia (limitada a un tamaño legible)."""
    if not texto:
        return "No especificada en el protocolo."
    if len(texto) <= max_chars:
        return texto
    corte = texto[:max_chars].rfind(".")
    if corte > 200:
        return texto[: corte + 1].strip()
    return texto[:max_chars].strip() + "..."


def procesar_pdf(ruta_pdf: Path, url_pdf: str) -> dict | None:
    paginas_raw: list[str] = []
    tabla_estabilidad: list[list[str]] = []
    tablas_referencia: list[list[list[str]]] = []

    with pdfplumber.open(str(ruta_pdf)) as pdf:
        if not pdf.pages:
            return None
        for page in pdf.pages:
            paginas_raw.append(page.extract_text() or "")
        tabla_estabilidad, tablas_referencia = extraer_tablas_hibrido(pdf)

    texto_completo_raw = "\n".join(paginas_raw)
    if not texto_completo_raw.strip():
        reader = PdfReader(str(ruta_pdf))
        paginas_raw = [(p.extract_text() or "") for p in reader.pages]
        texto_completo_raw = "\n".join(paginas_raw)
        if not texto_completo_raw.strip():
            return None

    texto_limpio = limpiar_encabezados_pagina(texto_completo_raw)
    sec = extraer_secciones(texto_limpio)

    codigo_raw = sec.get("codigo_interno", "").strip()
    m_cod = re.search(r"([A-Za-z0-9\-]+)", codigo_raw)
    codigo_interno = m_cod.group(1) if m_cod else (codigo_raw or ruta_pdf.stem)

    preparacion_instructivo = ""
    if es_instructivo_paciente(texto_limpio):
        titulo, act_inst, cod_inst, preparacion_instructivo = extraer_datos_instructivo(
            texto_limpio, codigo_interno
        )
        actualizado_en = act_inst or ""
        if not codigo_raw:
            codigo_interno = cod_inst
    else:
        titulo, actualizado_en = extraer_titulo_y_actualizacion(paginas_raw[0])

    nombres_examen = sec.get("nombres_examen", "")
    nombre = titulo if titulo else (nombres_examen.splitlines()[0] if nombres_examen else ruta_pdf.stem)
    nombre = truncar_nombre(nombre)

    sinonimos = extraer_sinonimos(nombre, nombres_examen)
    area, tiempo_respuesta = separar_area_y_tiempo(sec.get("laboratorios", ""))
    preparacion_paciente = sec.get("preparacion_paciente") or preparacion_instructivo or "No especificada en el protocolo."

    muestra_requerida = sec.get("muestra_requerida", "No especificada en el protocolo.")
    color_tapa = detectar_color_tapa(muestra_requerida)

    estabilidad = cortar_antes_de(sec.get("estabilidad_muestra", ""), PATRON_CORTE_ESTABILIDAD)
    envio = cortar_antes_de(sec.get("condiciones_envio", ""), PATRON_CORTE_ESTABILIDAD)
    partes_estab = []
    if estabilidad and not tabla_estabilidad:
        partes_estab.append(f"Estabilidad:\n{estabilidad}")
    if envio:
        partes_estab.append(f"Envío al laboratorio:\n{envio}")
    estabilidad_envio = "\n\n".join(partes_estab) if partes_estab else ("Ver tabla de estabilidad adjunta." if tabla_estabilidad else "No especificado en el protocolo.")

    val_ref = cortar_antes_de(sec.get("valores_referencia", ""), PATRON_CORTE_VALORES)
    val_crit = cortar_antes_de(sec.get("valor_critico", ""), PATRON_CORTE_VALORES)
    partes_ref = []
    if val_ref:
        if tablas_referencia:
            # Conservar solo notas (ej. "* No se han establecido...") fuera de las tablas
            notas_ref = [l for l in val_ref.splitlines() if l.strip().startswith("*")]
            if notas_ref:
                partes_ref.append("\n".join(notas_ref))
        else:
            partes_ref.append(val_ref)
    def tiene_alerta_en_tablas() -> bool:
        for t in tablas_referencia:
            filas_t = t["filas"] if isinstance(t, dict) else t
            if filas_t and "alerta" in " ".join(filas_t[0]).lower():
                return True
        return False

    if val_crit and not tiene_alerta_en_tablas():
        if val_crit.lower() not in ("no aplica", "no aplica."):
            partes_ref.append(f"Valor Crítico / Alerta: {val_crit}")
        else:
            partes_ref.append(f"Valor Crítico: {val_crit}")
    valores_referencia = "\n\n".join(partes_ref) if partes_ref else ("Ver tablas de referencia adjuntas." if tablas_referencia else "No especificado en el protocolo.")

    return {
        "codigo_interno": codigo_interno,
        "nombre": nombre,
        "nombres_examen": nombres_examen,
        "sinonimos": sinonimos,
        "area": area,
        "tiempo_respuesta": tiempo_respuesta,
        "preparacion_paciente": preparacion_paciente,
        "muestra_requerida": muestra_requerida,
        "color_tapa": color_tapa,
        "estabilidad_envio": estabilidad_envio,
        "tabla_estabilidad": tabla_estabilidad,
        "valores_referencia": valores_referencia,
        "tablas_referencia": tablas_referencia,
        "informacion_clinica": resumir_informacion_clinica(sec.get("informacion_clinica", "")),
        "actualizado_en": actualizado_en,
        "url_pdf": url_pdf,
    }


def main() -> None:
    if not PDFS_DIR.exists():
        print(f"Error: No existe {PDFS_DIR}", file=sys.stderr)
        sys.exit(1)

    mapa_urls: dict[str, str] = {}
    if MAPA_URLS_FILE.exists():
        with MAPA_URLS_FILE.open("r", encoding="utf-8") as f:
            mapa_urls = json.load(f)

    pdfs = sorted(PDFS_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No se encontraron PDFs en {PDFS_DIR}", file=sys.stderr)
        sys.exit(1)

    examenes: list[dict] = []
    errores = 0

    for idx, pdf_path in enumerate(pdfs, start=1):
        url_pdf = mapa_urls.get(pdf_path.name, "")
        try:
            item = procesar_pdf(pdf_path, url_pdf)
            if item:
                examenes.append(item)
            else:
                errores += 1
                print(f"[{idx}/{len(pdfs)}] Sin texto extraíble: {pdf_path.name}", file=sys.stderr)
        except Exception as exc:
            errores += 1
            print(f"[{idx}/{len(pdfs)}] Error en {pdf_path.name}: {exc}", file=sys.stderr)

        if idx % 200 == 0 or idx == len(pdfs):
            print(f"Procesados {idx}/{len(pdfs)} PDFs ({len(examenes)} válidos, {errores} errores)")

    # Ordenar alfabéticamente por nombre para una base prolija
    examenes.sort(key=lambda x: x.get("nombre", "").lower())

    SALIDA_JSON.parent.mkdir(parents=True, exist_ok=True)
    with SALIDA_JSON.open("w", encoding="utf-8") as f:
        json.dump(examenes, f, ensure_ascii=False, indent=2)

    with SALIDA_JS.open("w", encoding="utf-8") as f:
        f.write("// Archivo generado automáticamente por scripts/2_procesar_pdfs.py o web/admin.html\n")
        f.write("// Permite abrir web/index.html directamente con doble clic (protocolo file://)\n")
        f.write("window.EXAMENES_DATA = ")
        json.dump(examenes, f, ensure_ascii=False, indent=2)
        f.write(";\n")

    print("\n--- Resumen de extracción determinista ---")
    print(f"Total PDFs leídos:      {len(pdfs)}")
    print(f"Exámenes extraídos:     {len(examenes)}")
    print(f"Errores / vacíos:       {errores}")
    print(f"JSON guardado en:       {SALIDA_JSON}")
    print(f"JS (file://) guardado:  {SALIDA_JS}")


if __name__ == "__main__":
    main()
