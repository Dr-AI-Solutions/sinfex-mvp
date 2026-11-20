/**
 * ============================================================================
 * ASISTENTE DE LABORATORIO CLÍNICO - DOCUMENTACIÓN PARA INFORMÁTICA (TI)
 * ============================================================================
 *
 * 1. ARQUITECTURA DESACOPLADA (100% ESTÁTICA / OFFLINE / SIN IA):
 *    - Esta aplicación funciona íntegramente en el navegador del cliente
 *      (HTML, CSS, JavaScript puro + Fuse.js vía CDN).
 *    - No requiere backend, PHP, Node.js, Python ni base de datos en el
 *      servidor del hospital. Basta con copiar la carpeta `web/` en cualquier
 *      servidor web estático (Nginx, Apache, IIS, SharePoint o S3).
 *    - Incluso funciona abriendo `index.html` con doble clic (`file://`)
 *      gracias al archivo complementario `datos_examenes.js` (`window.EXAMENES_DATA`).
 *    - Toda la búsqueda difusa se ejecuta en memoria en el dispositivo del
 *      usuario final, sin consumir CPU ni memoria del servidor hospitalario.
 *
 * 2. ORIGEN DE DATOS Y ACTUALIZACIÓN SIN PROGRAMAR (`web/admin.html`):
 *    - Por defecto, lee `base_examenes.json` con parámetro de versión diaria
 *      (`?v=YYYY-MM-DD`) para renovar la caché de los boxes médicos. Si se
 *      abre con `file://`, usa automáticamente `window.EXAMENES_DATA`.
 *    - Para actualizar o agregar protocolos SINFEX sin usar Python ni IA:
 *      1) Abra `web/admin.html` en su navegador.
 *      2) Cargue el `base_examenes.json` actual.
 *      3) Arrastre los PDFs nuevos o actualizados de SINFEX.
 *      4) Descargue los nuevos `base_examenes.json` y `datos_examenes.js` y
 *         reemplácelos en la carpeta `web/` del servidor.
 *    - Si en el futuro Informática desea conectar la interfaz a una API REST
 *      interna del hospital, modifique únicamente la constante `DATA_SOURCE_URL`.
 *
 * 3. ESQUEMA JSON ESPERADO (Array de objetos):
 *    [
 *      {
 *        "codigo_interno": "string",
 *        "nombre": "string",
 *        "nombres_examen": "string",
 *        "sinonimos": ["string", ...],
 *        "area": "string",
 *        "tiempo_respuesta": "string",
 *        "preparacion_paciente": "string",
 *        "muestra_requerida": "string",
 *        "color_tapa": "lila | celeste | amarillo | rojo | verde | gris | orina | otro",
 *        "estabilidad_envio": "string",
 *        "valores_referencia": "string",
 *        "informacion_clinica": "string",
 *        "actualizado_en": "string",
 *        "url_pdf": "string (URL absoluta al PDF oficial)"
 *      }
 *    ]
 * ============================================================================
 */

// Modificar esta constante si se desea apuntar a una API interna del hospital
const DATA_SOURCE_URL = "base_examenes.json";

const COLORES_TAPA_VALIDOS = new Set([
  "lila",
  "celeste",
  "amarillo",
  "rojo",
  "verde",
  "gris",
  "orina",
  "otro",
]);

const ETIQUETA_TAPA = {
  lila: "Tapa Lila (EDTA)",
  celeste: "Tapa Celeste (Citrato)",
  amarillo: "Tapa Amarilla (Gel)",
  rojo: "Tapa Roja (Sin aditivo)",
  verde: "Tapa Verde (Heparina)",
  gris: "Tapa Gris (Fluoruro)",
  orina: "Frasco de Orina",
  otro: "Otro envase / tubo",
};

// Mapeo de intenciones clínicas -> campos del JSON a resaltar en la tarjeta
const REGLAS_INTENCION = [
  {
    id: "tubo",
    etiqueta: "Muestra / Tubo consultado",
    campos: ["muestra_requerida"],
    patrones: [
      /\b(en\s+qu[eé]\s+tubo|qu[eé]\s+tubo|cu[aá]l\s+tubo|tubo\s+va|color\s+de\s+tapa|tapa|envase|frasco|muestra|tipo\s+de\s+muestra|anticoagulante|volumen|m[ií]nimo|ml)\b/i,
    ],
  },
  {
    id: "preparacion",
    etiqueta: "Preparación consultada",
    campos: ["preparacion_paciente"],
    patrones: [
      /\b(indicaciones|indicaci[oó]n|preparaci[oó]n|ayuno|requisitos|paciente|antes\s+de\s+tomar|recomendaciones)\b/i,
    ],
  },
  {
    id: "estabilidad",
    etiqueta: "Estabilidad / Envío consultado",
    campos: ["estabilidad_envio"],
    patrones: [
      /\b(transporte|traslado|estabilidad|env[ií]o|temperatura|refrigerar|congelad[oa]|hielo|conservar|almacenar|cu[aá]nto\s+dura)\b/i,
    ],
  },
  {
    id: "tiempo",
    etiqueta: "Plazo de entrega consultado",
    campos: ["tiempo_respuesta"],
    patrones: [
      /\b(cu[aá]nto\s+demora|tiempo\s+de\s+respuesta|plazo|entrega|demora|cu[aá]ndo\s+est[aá]|tat|resultado|d[ií]as\s+de\s+procesamiento)\b/i,
    ],
  },
  {
    id: "valores",
    etiqueta: "Valores de referencia consultados",
    campos: ["valores_referencia"],
    patrones: [
      /\b(valores?\s+de\s+referencia|intervalos?\s+de\s+referencia|rango\s+normal|valores?\s+normales?|valor\s+cr[ií]tico|referencia|par[aá]metros)\b/i,
    ],
  },
  {
    id: "clinica",
    etiqueta: "Información clínica consultada",
    campos: ["informacion_clinica"],
    patrones: [
      /\b(para\s+qu[eé]\s+sirve|sirve\s+para|utilidad|indicaci[oó]n\s+cl[ií]nica|qu[eé]\s+mide|qu[eé]\s+eval[uú]a|cu[aá]ndo\s+(?:se\s+)?pide|cu[aá]ndo\s+pedir|interpretaci[oó]n|por\s+qu[eé]\s+se\s+pide|informaci[oó]n\s+cl[ií]nica|qu[eé]\s+es)\b/i,
    ],
  },
];

// Frases y palabras de relleno frecuentes en español que se limpian antes de buscar
const FRASES_RELLENO = [
  /\b(para\s+qu[eé]\s+sirve(\s+el|\s+la|\s+los|\s+las)?)\b/gi,
  /\b(sirve\s+para)\b/gi,
  /\b(utilidad(\s+cl[ií]nica)?(\s+de|\s+del)?)\b/gi,
  /\b(indicaci[oó]n\s+cl[ií]nica(\s+de|\s+del|\s+para)?)\b/gi,
  /\b(informaci[oó]n\s+cl[ií]nica(\s+de|\s+del)?)\b/gi,
  /\b(interpretaci[oó]n(\s+de|\s+del)?)\b/gi,
  /\b(por\s+qu[eé]\s+se\s+pide(\s+el|\s+la)?)\b/gi,
  /\b(qu[eé]\s+es(\s+el|\s+la|\s+un|\s+una)?)\b/gi,
  /\b(qu[eé]\s+mide(\s+el|\s+la)?)\b/gi,
  /\b(qu[eé]\s+eval[uú]a(\s+el|\s+la)?)\b/gi,
  /\b(cu[aá]ndo\s+(?:se\s+)?pide(\s+el|\s+la)?)\b/gi,
  /\b(cu[aá]ndo\s+pedir(\s+el|\s+la)?)\b/gi,
  /\b(cu[aá]l\s+es(\s+el|\s+la)?)\b/gi,
  /\b(en\s+qu[eé]\s+tubo\s+va)\b/gi,
  /\b(qu[eé]\s+tubo\s+(usa|lleva|necesita|es))\b/gi,
  /\b(indicaciones\s+(para|del?|sobre))\b/gi,
  /\b(preparaci[oó]n\s+(para|del?))\b/gi,
  /\b(valores?\s+de\s+referencia\s+(para|del?)?)\b/gi,
  /\b(intervalos?\s+de\s+referencia\s+(para|del?)?)\b/gi,
  /\b(tiempo\s+de\s+respuesta\s+(para|del?)?)\b/gi,
  /\b(plazo\s+de\s+entrega\s+(para|del?)?)\b/gi,
  /\b(condiciones\s+de\s+(transporte|env[ií]o)\s+(para|del?)?)\b/gi,
  /\b(estabilidad\s+(para|del?)?)\b/gi,
  /\b(cu[aá]nto\s+demora(\s+el|\s+la)?)\b/gi,
  /\b(necesito\s+saber|quiero\s+saber|me\s+puedes\s+decir|por\s+favor|hola|buenos\s+d[ií]as|buenas\s+tardes)\b/gi,
  /\b(tubo|muestra|indicaciones|preparaci[oó]n|ayuno|demora|transporte|estabilidad|env[ií]o|volumen|m[ií]nimo|valores|intervalos|referencia|protocolo|examen|ex[aá]menes|prueba|c[oó]digo)\b/gi,
  /\b(para|del|de|la|el|los|las|un|una|en|con|sobre|al)\b/gi,
];

let examenesData = [];
let fuseInstance = null;

const dom = {
  chatMessages: document.getElementById("chat-messages"),
  chatForm: document.getElementById("chat-form"),
  userInput: document.getElementById("user-input"),
  statusBadge: document.getElementById("status-badge"),
  btnLimpiar: document.getElementById("btn-limpiar"),
  quickChips: document.getElementById("quick-chips"),
};

function obtenerVersionFecha() {
  const hoy = new Date();
  const yyyy = hoy.getFullYear();
  const mm = String(hoy.getMonth() + 1).padStart(2, "0");
  const dd = String(hoy.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function construirUrlConCacheBuster(baseUrl) {
  const separador = baseUrl.includes("?") ? "&" : "?";
  return `${baseUrl}${separador}v=${obtenerVersionFecha()}`;
}

function normalizarTexto(texto) {
  return (texto || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function detectarConversacionBasica(consultaOriginal) {
  const norm = normalizarTexto(consultaOriginal).replace(/[¿?¡!,.;:()]/g, "").trim();
  if (!norm) return null;

  if (/^(hola|buenos dias|buenas tardes|buenas noches|buenas|saludos|que tal|hi|hello)(\s+.*)?$/i.test(norm) && norm.split(/\s+/).length <= 4) {
    return "¡Hola! Soy el asistente de Laboratorio Clínico. Puedes preguntarme por el tubo, preparación, plazos o valores de referencia de cualquier examen, o buscar por patología si no recuerdas el nombre exacto.";
  }
  if (/^(gracias|muchas gracias|mil gracias|te pasaste|genial|perfecto|ok gracias)(\s+.*)?$/i.test(norm) && norm.split(/\s+/).length <= 5) {
    return "¡Con gusto! Si necesitas consultar otro protocolo, tubo o indicación, escríbeme el nombre, sigla o código SINFEX del examen.";
  }
  if (/^(ayuda|help|como funciona|que puedes hacer|instrucciones)(\s+.*)?$/i.test(norm)) {
    return "Puedes escribir el nombre o código SINFEX del examen para ver su ficha completa, o hacer preguntas directas como: \"¿En qué tubo va el Hemograma?\", \"Indicaciones para TRAb\", \"Estabilidad TTPK\" o buscar por patología (ej: \"celiaquía\").";
  }
  return null;
}

function analizarConsulta(consultaOriginal) {
  const intencionesDetectadas = [];
  const camposResaltados = new Set();
  let intencionPrincipal = "general";

  for (const regla of REGLAS_INTENCION) {
    if (regla.patrones.some((regex) => regex.test(consultaOriginal))) {
      if (intencionPrincipal === "general") {
        intencionPrincipal = regla.id;
      }
      intencionesDetectadas.push(regla.etiqueta);
      regla.campos.forEach((c) => camposResaltados.add(c));
    }
  }

  let terminoLimpio = consultaOriginal.replace(/[¿?¡!,.;:()]/g, " ");
  for (const patron of FRASES_RELLENO) {
    terminoLimpio = terminoLimpio.replace(patron, " ");
  }
  terminoLimpio = terminoLimpio.replace(/\s+/g, " ").trim();

  if (!terminoLimpio) {
    terminoLimpio = consultaOriginal.replace(/[¿?¡!,.;:()]/g, " ").trim();
  }

  return {
    consultaOriginal,
    terminoBusqueda: terminoLimpio,
    intencion: intencionPrincipal,
    camposResaltados,
    etiquetasIntencion: intencionesDetectadas,
  };
}

function buscarExamenes(termino) {
  if (!examenesData.length || !termino) return [];

  const terminoNorm = normalizarTexto(termino);
  if (!terminoNorm) return [];

  // ETAPA 1: Coincidencia directa (sin acentos y en minúsculas) en título, siglas o código
  const directas = examenesData.filter((ex) => {
    const cod = normalizarTexto(ex.codigo_interno);
    const nom = normalizarTexto(ex.nombre);
    const noms = normalizarTexto(ex.nombres_examen);
    const sinMatch =
      Array.isArray(ex.sinonimos) &&
      ex.sinonimos.some((s) => normalizarTexto(s).includes(terminoNorm));

    return (
      cod === terminoNorm ||
      nom.includes(terminoNorm) ||
      noms.includes(terminoNorm) ||
      sinMatch
    );
  });

  if (directas.length > 0) {
    directas.sort((a, b) => {
      const aExact =
        normalizarTexto(a.codigo_interno) === terminoNorm ||
        (Array.isArray(a.sinonimos) &&
          a.sinonimos.some((s) => normalizarTexto(s) === terminoNorm));
      const bExact =
        normalizarTexto(b.codigo_interno) === terminoNorm ||
        (Array.isArray(b.sinonimos) &&
          b.sinonimos.some((s) => normalizarTexto(s) === terminoNorm));
      if (aExact !== bExact) return aExact ? -1 : 1;
      return (a.nombre || "").length - (b.nombre || "").length;
    });
    return directas.slice(0, 4);
  }

  // ETAPA 2: Respaldo con Fuse.js (errores de tipeo o búsqueda por patología)
  if (!fuseInstance) return [];
  return fuseInstance.search(termino, { limit: 4 }).map((r) => r.item);
}

function generarTextoEnfermeria(examen) {
  const sinonimos =
    Array.isArray(examen.sinonimos) && examen.sinonimos.length > 0
      ? ` (${examen.sinonimos.join(", ")})`
      : "";

  const lineas = [
    `*${examen.nombre}*${sinonimos}`,
    `• Código SINFEX: ${examen.codigo_interno || "No especificado"} | Área: ${examen.area || "Laboratorio"}`,
    `• Muestra requerida: ${examen.muestra_requerida || "No especificado"} (Tapa: ${examen.color_tapa || "otro"})`,
    `• Preparación del paciente: ${examen.preparacion_paciente || "No especificado"}`,
    `• Estabilidad y envío: ${examen.estabilidad_envio || "No especificado"}`,
    `• Plazo de entrega: ${examen.tiempo_respuesta || "No especificado"}`,
  ];

  if (examen.url_pdf) {
    lineas.push(`• Protocolo PDF: ${examen.url_pdf}`);
  }

  return lineas.join("\n");
}

function agregarMensajeTexto(remitente, texto) {
  const row = document.createElement("div");
  row.className = `message-row ${remitente}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = texto;

  row.appendChild(bubble);
  dom.chatMessages.appendChild(row);
  desplazarAlFinal();
}

function crearTablaClinica(tablaEntrada) {
  const tituloTabla =
    tablaEntrada && !Array.isArray(tablaEntrada) && tablaEntrada.titulo_tabla
      ? tablaEntrada.titulo_tabla
      : "";
  const filas =
    tablaEntrada && !Array.isArray(tablaEntrada) && Array.isArray(tablaEntrada.filas)
      ? tablaEntrada.filas
      : Array.isArray(tablaEntrada)
      ? tablaEntrada
      : [];

  // Compactar celdas vacías producto de celdas combinadas en el PDF cuando todas las filas tienen igual cantidad de datos
  const compactas = filas.map((r) => r.filter((c) => c !== ""));
  const ancho = compactas[0] ? compactas[0].length : 0;
  const filasFinales =
    ancho > 0 && compactas.every((r) => r.length === ancho) ? compactas : filas;

  const wrap = document.createElement("div");
  wrap.className = "table-wrapper";

  if (tituloTabla) {
    const titleBar = document.createElement("div");
    titleBar.className = "table-title";
    titleBar.textContent = tituloTabla;
    wrap.appendChild(titleBar);
  }

  const table = document.createElement("table");
  table.className = "clinical-table";

  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  (filasFinales[0] || []).forEach((celda) => {
    const th = document.createElement("th");
    th.textContent = celda;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  for (let i = 1; i < filasFinales.length; i++) {
    const tr = document.createElement("tr");
    filasFinales[i].forEach((celda) => {
      const td = document.createElement("td");
      td.textContent = celda;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  wrap.appendChild(table);
  return wrap;
}

function crearCampoTarjeta(etiqueta, valor, nombreCampo, analisis, fullWidth = false, tabla = null) {
  const field = document.createElement("div");
  const resaltado = analisis.camposResaltados.has(nombreCampo);
  field.className = `exam-field${fullWidth ? " full-width" : ""}${resaltado ? " field-highlight" : ""}`;

  const labelRow = document.createElement("div");
  labelRow.className = "field-label-row";

  const labelEl = document.createElement("span");
  labelEl.className = "field-label";
  labelEl.textContent = etiqueta;
  labelRow.appendChild(labelEl);

  if (resaltado) {
    const tag = document.createElement("span");
    tag.className = "intent-tag";
    tag.textContent = "Dato consultado";
    labelRow.appendChild(tag);
  }

  field.appendChild(labelRow);

  // Normalizar a lista de tablas (soporta tabla única, objeto {titulo_tabla, filas} o múltiples tablas consecutivas)
  let listaTablas = [];
  if (Array.isArray(tabla) && tabla.length > 0) {
    const primero = tabla[0];
    if (primero && !Array.isArray(primero) && Array.isArray(primero.filas)) {
      listaTablas = tabla.filter((t) => t && Array.isArray(t.filas) && t.filas.length >= 2);
    } else if (Array.isArray(primero) && Array.isArray(primero[0])) {
      listaTablas = tabla.filter((t) => Array.isArray(t) && t.length >= 2);
    } else if (Array.isArray(primero) && tabla.length >= 2) {
      listaTablas = [tabla];
    }
  } else if (tabla && !Array.isArray(tabla) && Array.isArray(tabla.filas) && tabla.filas.length >= 2) {
    listaTablas = [tabla];
  }

  listaTablas.forEach((t) => {
    field.appendChild(crearTablaClinica(t));
  });

  const tieneTablas = listaTablas.length > 0;
  if (
    valor &&
    (!tieneTablas ||
      (!valor.startsWith("Ver tabla") && valor !== "No especificado en el protocolo."))
  ) {
    const valueEl = document.createElement("p");
    valueEl.className = "field-value";
    valueEl.textContent = valor;
    field.appendChild(valueEl);
  } else if (!tieneTablas) {
    const valueEl = document.createElement("p");
    valueEl.className = "field-value";
    valueEl.textContent = "No especificado en el protocolo.";
    field.appendChild(valueEl);
  }

  return field;
}

function agregarTarjetaExamen(examen, alternativas, analisis) {
  const row = document.createElement("div");
  row.className = "message-row bot";

  const colorTapa = COLORES_TAPA_VALIDOS.has((examen.color_tapa || "").toLowerCase())
    ? examen.color_tapa.toLowerCase()
    : "otro";

  const card = document.createElement("article");
  card.className = "exam-card";
  card.setAttribute("data-tapa", colorTapa);

  // Header de la tarjeta
  const header = document.createElement("div");
  header.className = "exam-card-header";

  const titleGroup = document.createElement("div");
  titleGroup.className = "exam-title-group";

  const metaRow = document.createElement("div");
  metaRow.className = "exam-area-code";

  const codePill = document.createElement("span");
  codePill.className = "code-pill";
  codePill.textContent = `SINFEX ${examen.codigo_interno || "S/C"}`;
  metaRow.appendChild(codePill);

  const areaSpan = document.createElement("span");
  areaSpan.textContent = examen.area || "Laboratorio Clínico";
  metaRow.appendChild(areaSpan);

  if (examen.actualizado_en) {
    const updPill = document.createElement("span");
    updPill.className = "updated-pill";
    updPill.textContent = examen.actualizado_en;
    metaRow.appendChild(updPill);
  }

  const titleEl = document.createElement("h2");
  titleEl.className = "exam-title";
  titleEl.textContent = examen.nombre || "Examen sin nombre";

  titleGroup.appendChild(metaRow);
  titleGroup.appendChild(titleEl);

  if (Array.isArray(examen.sinonimos) && examen.sinonimos.length > 0) {
    const synEl = document.createElement("p");
    synEl.className = "exam-synonyms";
    synEl.textContent = `Siglas / sinónimos: ${examen.sinonimos.join(", ")}`;
    titleGroup.appendChild(synEl);
  }

  const tubeBadge = document.createElement("div");
  tubeBadge.className = "tube-badge";
  const dot = document.createElement("span");
  dot.className = "tube-dot";
  dot.setAttribute("data-tapa", colorTapa);
  const tubeText = document.createElement("span");
  tubeText.textContent = ETIQUETA_TAPA[colorTapa] || colorTapa;
  tubeBadge.appendChild(dot);
  tubeBadge.appendChild(tubeText);

  header.appendChild(titleGroup);
  header.appendChild(tubeBadge);
  card.appendChild(header);

  // Grilla de datos clínicos SINFEX (focalizada si hay intención específica)
  const esFocalizada = analisis.intencion !== "general" && analisis.camposResaltados.size > 0;
  const esClinica = analisis.intencion === "clinica";

  const definicionCampos = [
    { label: "Muestra Requerida", val: examen.muestra_requerida, key: "muestra_requerida", full: true, tabla: null },
    { label: "Preparación del Paciente", val: examen.preparacion_paciente, key: "preparacion_paciente", full: esFocalizada, tabla: null },
    { label: "Plazo de Entrega / Procesamiento", val: examen.tiempo_respuesta, key: "tiempo_respuesta", full: esFocalizada, tabla: null },
    { label: "Estabilidad y Envío al Laboratorio", val: examen.estabilidad_envio, key: "estabilidad_envio", full: true, tabla: examen.tabla_estabilidad },
    { label: "Intervalos de Referencia / Valor Crítico", val: examen.valores_referencia, key: "valores_referencia", full: true, tabla: examen.tablas_referencia || examen.tabla_referencia },
  ];

  if (esClinica) {
    definicionCampos.unshift({
      label: "Información Clínica",
      val: examen.informacion_clinica || "No especificada en el protocolo.",
      key: "informacion_clinica",
      full: true,
    });
  }

  const grid = document.createElement("div");
  grid.className = "exam-grid";

  const extraContainer = document.createElement("div");
  extraContainer.className = esFocalizada ? "extra-fields-hidden" : "";

  const extraGrid = document.createElement("div");
  extraGrid.className = "exam-grid";
  if (esFocalizada) {
    extraGrid.style.paddingTop = "0";
  }

  definicionCampos.forEach((c) => {
    const el = crearCampoTarjeta(c.label, c.val, c.key, analisis, c.full, c.tabla);
    if (!esFocalizada || analisis.camposResaltados.has(c.key)) {
      grid.appendChild(el);
    } else {
      extraGrid.appendChild(el);
    }
  });

  card.appendChild(grid);

  // Acordeón desplegable opcional para Información Clínica (cuando no es el foco principal)
  let clinicaDetails = null;
  if (!esClinica && examen.informacion_clinica && examen.informacion_clinica !== "No especificada en el protocolo.") {
    clinicaDetails = document.createElement("details");
    clinicaDetails.className = "clinical-accordion";

    const summary = document.createElement("summary");
    summary.textContent = "Información Clínica (desplegar)";

    const body = document.createElement("div");
    body.className = "clinical-accordion-body";
    body.textContent = examen.informacion_clinica;

    clinicaDetails.appendChild(summary);
    clinicaDetails.appendChild(body);
  }

  if (esFocalizada) {
    extraContainer.appendChild(extraGrid);
    if (clinicaDetails) extraContainer.appendChild(clinicaDetails);
    card.appendChild(extraContainer);
  } else if (clinicaDetails) {
    card.appendChild(clinicaDetails);
  }

  // Botones de acción
  const actions = document.createElement("div");
  actions.className = "exam-card-actions";

  const btnPdf = document.createElement("a");
  btnPdf.className = `btn-action btn-pdf${examen.url_pdf ? "" : " disabled"}`;
  btnPdf.textContent = "Abrir PDF Oficial";
  if (examen.url_pdf) {
    btnPdf.href = examen.url_pdf;
    btnPdf.target = "_blank";
    btnPdf.rel = "noopener noreferrer";
  } else {
    btnPdf.href = "#";
    btnPdf.setAttribute("aria-disabled", "true");
  }

  const btnCopy = document.createElement("button");
  btnCopy.type = "button";
  btnCopy.className = "btn-action btn-copy";
  btnCopy.textContent = "Copiar para Enfermería";
  btnCopy.addEventListener("click", async () => {
    const resumen = generarTextoEnfermeria(examen);
    try {
      await navigator.clipboard.writeText(resumen);
      btnCopy.textContent = "¡Copiado para Enfermería!";
      btnCopy.classList.add("copied");
      setTimeout(() => {
        btnCopy.textContent = "Copiar para Enfermería";
        btnCopy.classList.remove("copied");
      }, 2200);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = resumen;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      btnCopy.textContent = "¡Copiado!";
      btnCopy.classList.add("copied");
      setTimeout(() => {
        btnCopy.textContent = "Copiar para Enfermería";
        btnCopy.classList.remove("copied");
      }, 2200);
    }
  });

  actions.appendChild(btnPdf);
  actions.appendChild(btnCopy);

  if (esFocalizada) {
    const btnToggle = document.createElement("button");
    btnToggle.type = "button";
    btnToggle.className = "btn-action btn-toggle-full";
    btnToggle.textContent = "Ver ficha completa";
    btnToggle.addEventListener("click", () => {
      const oculto = extraContainer.classList.toggle("extra-fields-hidden");
      btnToggle.textContent = oculto ? "Ver ficha completa" : "Ocultar ficha completa";
    });
    actions.appendChild(btnToggle);
  }

  card.appendChild(actions);

  row.appendChild(card);

  if (alternativas.length > 0) {
    const altBox = document.createElement("div");
    altBox.className = "alternatives-box";
    const altLabel = document.createElement("span");
    altLabel.textContent = "Otros exámenes coincidentes:";
    altBox.appendChild(altLabel);

    alternativas.forEach((alt) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "alt-chip";
      const textoChip = `${alt.nombre} (${alt.codigo_interno || "S/C"})`;
      chip.textContent = textoChip.length > 60 ? textoChip.slice(0, 57).trimEnd() + "..." : textoChip;
      chip.title = textoChip;
      chip.addEventListener("click", () => {
        procesarConsultaUsuario(alt.codigo_interno || alt.nombre);
      });
      altBox.appendChild(chip);
    });

    row.appendChild(altBox);
  }

  dom.chatMessages.appendChild(row);
  desplazarAlFinal();
}

const STORAGE_KEY_FRECUENTES = "sinfex_consultas_frecuentes_v1";

const CONSULTAS_POR_DEFECTO = [
  "¿En qué tubo va el Dímero D?",
  "Transporte y estabilidad Amonio",
  "Indicaciones para PTGO",
  "¿En qué tubo va el Hemograma?",
];

function leerHistorialFrecuentes() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_FRECUENTES);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function registrarBusquedaExitosa(examen) {
  if (!examen) return;
  const clave = String(examen.codigo_interno || examen.nombre || "").trim();
  if (!clave) return;
  try {
    const historial = leerHistorialFrecuentes();
    const actual = historial[clave] || {
      codigo: examen.codigo_interno || "",
      nombre: examen.nombre || clave,
      count: 0,
    };
    actual.count += 1;
    actual.last = Date.now();
    actual.nombre = examen.nombre || actual.nombre;
    actual.codigo = examen.codigo_interno || actual.codigo;
    historial[clave] = actual;
    localStorage.setItem(STORAGE_KEY_FRECUENTES, JSON.stringify(historial));
    renderizarChipsFrecuentes();
  } catch {
    // Ignorar si localStorage no está disponible
  }
}

function renderizarChipsFrecuentes() {
  if (!dom.quickChips) return;
  const historial = leerHistorialFrecuentes();
  const entradas = Object.values(historial)
    .filter((item) => item && item.count > 0 && item.nombre)
    .sort((a, b) => b.count - a.count || (b.last || 0) - (a.last || 0))
    .slice(0, 4);

  dom.quickChips.innerHTML = "";

  if (entradas.length > 0) {
    entradas.forEach((item) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chip";
      const texto = item.nombre.length > 38 ? item.nombre.slice(0, 35).trimEnd() + "..." : item.nombre;
      btn.textContent = texto;
      btn.title = `${item.nombre} (${item.count} consulta${item.count > 1 ? "s" : ""})`;
      btn.setAttribute("data-query", item.codigo || item.nombre);
      dom.quickChips.appendChild(btn);
    });
    return;
  }

  CONSULTAS_POR_DEFECTO.forEach((consulta) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip";
    btn.textContent = consulta;
    btn.setAttribute("data-query", consulta);
    dom.quickChips.appendChild(btn);
  });
}

function desplazarAlFinal() {
  dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
}

function mostrarBienvenida() {
  dom.chatMessages.innerHTML = "";
  agregarMensajeTexto(
    "bot",
    "Hola. Soy el Asistente de Laboratorio Clínico. Puedes consultar por nombre del examen, sigla (ej: ELP, TTPK, TRAb, C4) o código SINFEX, o preguntar directamente por el tubo, preparación, estabilidad o plazo de entrega."
  );
}

function procesarConsultaUsuario(textoCrudo) {
  const consulta = (textoCrudo || "").trim();
  if (!consulta) return;

  agregarMensajeTexto("user", consulta);

  const respuestaConversacional = detectarConversacionBasica(consulta);
  if (respuestaConversacional) {
    agregarMensajeTexto("bot", respuestaConversacional);
    return;
  }

  if (!fuseInstance || examenesData.length === 0) {
    agregarMensajeTexto(
      "bot",
      "La base de protocolos aún no está disponible. Verifica que `base_examenes.json` o `datos_examenes.js` estén accesibles."
    );
    return;
  }

  const analisis = analizarConsulta(consulta);
  const resultados = buscarExamenes(analisis.terminoBusqueda);

  if (resultados.length === 0) {
    agregarMensajeTexto(
      "bot",
      `No encontré protocolos para "${consulta}". Intenta con el nombre oficial del examen, una sigla clínica o su código SINFEX.`
    );
    return;
  }

  const [principal, ...alternativas] = resultados;
  registrarBusquedaExitosa(principal);
  agregarTarjetaExamen(principal, alternativas, analisis);
}

function configurarBuscador(data) {
  examenesData = data;
  fuseInstance = new Fuse(examenesData, {
    includeScore: true,
    threshold: 0.35,
    ignoreLocation: true,
    minMatchCharLength: 4,
    keys: [
      { name: "nombre", weight: 0.75 },
      { name: "sinonimos", weight: 0.2 },
      { name: "informacion_clinica", weight: 0.05 },
    ],
  });

  dom.statusBadge.textContent = `${examenesData.length} protocolos activos`;
  dom.statusBadge.className = "status-badge status-ready";
}

async function inicializarBaseDatos() {
  try {
    const url = construirUrlConCacheBuster(DATA_SOURCE_URL);
    const resp = await fetch(url, { cache: "no-store" });
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    const data = await resp.json();
    if (!Array.isArray(data)) {
      throw new Error("El archivo JSON no contiene un arreglo válido.");
    }
    configurarBuscador(data);
  } catch (err) {
    if (Array.isArray(window.EXAMENES_DATA) && window.EXAMENES_DATA.length > 0) {
      configurarBuscador(window.EXAMENES_DATA);
      return;
    }
    console.error("Error cargando protocolos:", err);
    dom.statusBadge.textContent = "Error al cargar base";
    dom.statusBadge.className = "status-badge status-error";
    agregarMensajeTexto(
      "bot",
      "No fue posible cargar `base_examenes.json` ni `datos_examenes.js`. Verifica que ambos archivos existan en la carpeta `web/`."
    );
  }
}

document.addEventListener("DOMContentLoaded", () => {
  mostrarBienvenida();
  renderizarChipsFrecuentes();
  inicializarBaseDatos();

  dom.chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const query = dom.userInput.value;
    dom.userInput.value = "";
    procesarConsultaUsuario(query);
    dom.userInput.focus();
  });

  dom.btnLimpiar.addEventListener("click", () => {
    mostrarBienvenida();
    dom.userInput.focus();
  });

  dom.quickChips.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    const query = chip.getAttribute("data-query");
    if (query) {
      procesarConsultaUsuario(query);
    }
  });
});
