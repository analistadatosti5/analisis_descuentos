# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es

Análisis de descuentos comerciales (ventas sectores 10, 15, 20, 21) leído de PostgreSQL `commercial_bi`
(**solo lectura**). Dos piezas independientes:

- **`main.py` + `consultas.py`**: CLI que genera la tabla base (`.xlsx` si el período es ≤ 31 días, `.parquet`
  si es más largo). Está documentada en detalle en `README.md` (columnas, fórmulas, rangos, limitaciones).
- **Un notebook por informe** (generan sus propios Parquet, los analizan y producen los entregables):
  - `Informe_Ajustes_Region.ipynb`: informe general por región (C.2) y Excel del panorama (C.5).
  - `Informe_Avance_Region_dos_meses.ipynb`: informe de avance (C.6), siempre las dos regiones (guarda en
    `output/Informe_Avance_Region/`). Como Res, solo consulta y lee
    el mes anterior + mes en curso hasta `CORTE_D` (su sección 2 lleva la tabla y solo la gráfica de venta kg /
    pesos por día).
  - `Res.ipynb`: PowerPoint de Res por región × canal de venta (C.7). Se corre **cada semana** cambiando solo
    `CORTE_D`; consulta y lee solo el Parquet del mes anterior + mes en curso (no tiene el histórico: sin A.3
    histórico ni lectura del Parquet 2025–2026; su lectura del mes es A.6). Todo lo que necesitaba del histórico
    lo pone `modo_corte()`. La consulta trae todos los materiales porque la nota "días con venta" es de toda la región.
  - `Top_Clientes.ipynb`: top de clientes (C.3).
  - `Informe_Cliente.ipynb`: informe de un cliente (C.4).
- **`Descuentos.ipynb`**: el notebook original, que hace todo junto y del que salieron los cuatro anteriores
  (copiando el código tal cual). Se conserva como referencia.

Todo el código, nombres de variables, comentarios y commits están en español; mantener ese idioma.

## Entorno y comandos

- Python del entorno virtual en `venv/` (no `.venv` como dice el README); el kernel del notebook es `venv`.
  Usar `venv/Scripts/python.exe`.
- Conexión: variables `DB_*` del `.env` de esta carpeta; si no existe, se usa `../Lista de precios/.env`.
- No hay tests, linter ni build.

```bash
py main.py --inicio 2026-09-01 --fin 2026-10-01                 # --fin es EXCLUSIVO
py main.py --inicio 2025-01-01 --fin 2026-10-01 --canal 10      # -> parquet, solo mayoreo
```

El notebook se corre completo en orden (*Run All*) desde VS Code. Los parámetros están todos en la celda A.1
(`FECHA_FIN`, `MES_CLIENTES`, `CORTE_D`, `CLIENTE`, `FOCO`, `GENERAR_PARQUET*`, topes de tablas). Con
`GENERAR_PARQUET*=True` vuelve a consultar la base (varios minutos, ~10 millones de filas).

## Trabajar con el notebook

Los notebooks pueden pesar decenas de MB por las salidas (imágenes embebidas; `Descuentos.ipynb` ~30 MB). No
leerlos enteros: extraer solo las fuentes de las celdas, p. ej.

```bash
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -c "import json; nb=json.load(open('Descuentos.ipynb',encoding='utf-8')); [print(f'=== [{i}] {c[\"cell_type\"]}\n'+''.join(c['source'])) for i,c in enumerate(nb['cells'])]"
```

y editar con NotebookEdit por índice de celda. La consola de Windows es cp1252: sin `PYTHONIOENCODING=utf-8`
los `print` con tildes o `−` fallan.

## Arquitectura de los notebooks

Los cuatro notebooks por informe conservan la numeración de secciones y celdas del original (A.1–A.7, B 1–12,
C.1–C.7), pero cada uno trae solo lo que usa su informe, así que hay saltos (p. ej. `Top_Clientes` no tiene A.4 ni
A.7). **No comparten código:** cada uno tiene su propia copia de la preparación y de las funciones que usa. Un
cambio en una función compartida (p. ej. `figura_rangos`, `indicadores`, `lamina`) hay que repetirlo en cada notebook
que la tenga. `modo_corte()` y `solo_canal()` reemplazan variables globales del notebook mientras dura el
`with`, por eso el código vive en los notebooks y no en un módulo `.py`. Los Parquet son los mismos
archivos para todos: con `GENERAR_PARQUET*=False` se reutilizan los que ya generó otro notebook. `Res` e
`Informe_Avance_Region_dos_meses` tienen el mismo código de consulta y lectura del mes: con el mismo `CORTE_D` usan el mismo Parquet. Flujo
semanal: `Res` con `GENERAR_PARQUET_D=True` (consulta) y luego el avance, que por defecto tiene `False` y reutiliza
ese archivo (solo consulta si no existe).

Tres partes; las celdas dependen de variables globales de las anteriores, así que un cambio en A obliga a
re-ejecutar todo lo de abajo.

- **A. Preparación**
  - A.3 genera el Parquet histórico (`FECHA_INICIO`..`FECHA_FIN`) y A.4 el del avance (1 del mes anterior hasta
    `CORTE_D` incluido; por defecto ayer). Los nombres llevan las fechas (`Descuentos_AAAAMMDD_AAAAMMDD.parquet`),
    así que cada corte crea un archivo nuevo.
  - **El SQL, `RANGOS`, `calcular()` y `escribir_parquet()` están duplicados en la celda A.3** respecto a
    `consultas.py`/`main.py`, y la copia del notebook agrega la columna `sociedad` (`cdd.company_code`) que el
    CLI no trae. Un cambio en las fórmulas o en el SQL hay que hacerlo en ambos lados.
  - A.5 define constantes y formato compartidos: `SOCIEDADES` (`1000` = Región Oriente, `2000` = Región
    Occidente), `DIMENSIONES`, nombres normalizados de indicadores (`VENTA_BRUTA`, `L_GEN`, `P_AJ`...), colores
    y helpers de formato/tablas/gráficas.
  - A.6 / A.7 leen el Parquet **una sola vez por lotes** y lo reducen a tablas chicas en memoria: `mensual_soc`,
    `cubo` (dimensión × miembro × sociedad × año × rango × motivo), `cruce`, `clientes`, `clientes_det` y sus
    equivalentes `_d` del avance (`diario_soc`, `cubo_d`, `foco_d`...). En las tablas `_d` el nivel `Año` contiene
    el período (mes anterior / mes en curso), para que las mismas funciones de B y C sirvan sin cambios.
    Si el Parquet no trae `Sociedad`, se asigna por distribuidora consultando la base.
- **B. Análisis**: secciones numeradas igual que el informe (2–9 acumulado 2025 vs 2026, 10 avance del mes,
  11 Foco Res, 12 hallazgos). Las funciones de cada sección (`figura_*`, `tabla_*`, `resumen_*`) se reutilizan
  en C para las láminas. Los textos de hallazgos (sección 12) son los mismos que van al PowerPoint.
- **C. Salidas** (python-pptx / openpyxl), en `SALIDA` = `output/<nombre del notebook>/` (se crea sola): C.2 informe general por región,
  C.3 top de clientes, C.4 informe de un cliente (con su propio `SQL_CLIENTE`), C.5 Excel del panorama con
  fórmulas, C.6 informe de avance, C.7 Res por región × canal de venta (`Res_<región>_<canal>_...pptx`).

## Reglas de cálculo que no son obvias

- `daily_sales.value` ya es la venta **neta**; bruta = neta + `discount_value`; ajuste de mercado =
  `discount_value − short_dated_discount`; foco va aparte (no está dentro del total).
- Todos los % se calculan **desde las sumas** (nunca promediando % de filas), sobre la venta bruta; con bruta
  ≤ 0 quedan vacíos y caen en el rango `23. Sin venta bruta`.
- Rangos de % de lista: cerrados abajo (`right=False`); los rótulos llevan número (`01.`..`23.`) para que se
  ordenen como texto.
- Códigos (cliente, lista, tipología, grupo 6) son texto con ceros a la izquierda.
- El canal de venta `Directo` se muestra como `Amas de casa`.

## Archivos generados

Los PowerPoint y el Excel de cada notebook van a `output/<carpeta>/` (`Descuentos.ipynb`, el original, a
`output/General/`; el avance, a `output/Informe_Avance_Region/`). En `.gitignore` las carpetas de `output/` ignoran su
contenido salvo el `.gitkeep` (`output/Informe_Avance_Region/` todavía no está en `.gitignore`). Los Parquet quedan en la raíz porque los comparten los cuatro notebooks y `main.py`.
`.xlsx`, `.parquet` y `.csv` están en `.gitignore` (el Parquet 2025–2026 pesa ~500 MB). Los `.pptx` generados
no están ignorados: no incluirlos en commits salvo que se pida.
