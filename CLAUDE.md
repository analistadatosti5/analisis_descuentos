# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es

Análisis de descuentos comerciales (ventas sectores 10, 15, 20, 21) leído de PostgreSQL `commercial_bi`
(**solo lectura**). Piezas independientes:

- **`main.py` + `consultas.py`**: CLI que genera la tabla base (`.xlsx` si el período es ≤ 31 días, `.parquet`
  si es más largo). Está documentada en detalle en `README.md` (columnas, fórmulas, rangos, limitaciones). Usa
  `SQL_DESCUENTOS` (bloque de arriba de `consultas.py`), que no separa devoluciones; no sigue la metodología de los
  reportes (ver abajo) y no se toca.
- **Dos notebooks de reportes**, que consultan la base cada vez con `consultas.descargar_mes()` (`SQL_REPORTES` +
  `calcular()`, bloque de abajo de `consultas.py`), sin Parquet, y procesan en memoria:
  - `Informe_Region_semanal.ipynb`: **reporte semanal** de avance (C.6), siempre las dos regiones. Se corre
    cambiando solo `CORTE_D`. Consulta el mes anterior + mes en curso (sin histórico; lo que el código heredado
    necesitaba del histórico lo pone `modo_corte()`). Guarda en `output/Informe_Avance_Region/`
    `Informe Semanal <región> <mes anterior> vs <mes en curso> al <día>.pptx` (`nombre_corte()`). La tabla del
    panorama (lámina 2, `panorama_corte()`) empieza con `ORDEN_PANORAMA`: kilos brutos, kilos devueltos, kilos
    netos, valor bruto, valor de devolución, valor ajuste de precio, valor neto, precio de lista y precio neto; luego
    los % y lo demás. Los nombres internos (`VENTA_KG`, `KG_DEV`, `KG_NETO`...) dan el formato (`formato_de()`) y
    en la lámina se muestran con `ROTULO_PANORAMA`.
  - `Reporte_Ejecutivo.ipynb`: **reporte ejecutivo diario**, una lámina (corte de ayer). Su A.6 agrega `base` =
    sumas por sociedad × canal de venta × canal de distribución × grupo de material 6 × periodo y `diario` = sumas
    por sociedad × día. C.2 arma la lámina con `resumen()` / `ruta()`
    (menor cumplimiento; canal de distribución y grupo con al menos `PARTICIPACION_MIN` % de la venta de su nivel) y
    `cumplimiento_por_tipo()` (L_AJ y L_FC). C.3 agrega una lámina por región (`reporte_region()`):
    `resumen_niveles()` abre por varios niveles con los dos motivos de ajuste, `figura_mapa()` es el mapa canal de
    venta × canal de distribución (cada celda, en dos líneas: % cumplimiento con su variación en puntos, y precio
    neto por kg (`PRECIO_NETO`) con su diferencia en pesos (`variacion_valor()`), ambos vs el mes anterior
    completo; fuera del mapa, en gris, los totales por canal de venta, por canal de distribución y de la región, con
    todos sus canales aunque no salgan en el mapa) y `figura_tendencia()` el cumplimiento acumulado por día del mes
    (mes en curso vs anterior, desde `diario`). Cada PowerPoint de región lleva una lámina 2 (`lamina_dia_a_dia()` →
    `figura_dia_a_dia()`): % cumplimiento de cada día (`linea_cumplimiento_dia()`, con el acumulado del mes en
    punteado) y barras de valor neto (`Venta Neta`) y kilos netos (`Venta Neta Kg` = `Venta Kg − Devolucion Kg`,
    que A.6 agrega a `diario`) con `barras_dia()`, valores completos y el acumulado del mes día a día en punteado en
    un eje secundario, día a día en línea de tiempo del 1 del mes anterior al corte, con el eje hasta el fin del
    mes en curso (`eje_linea_tiempo()`). Las tres gráficas llevan en el título el acumulado de cada mes y la frase
    de variación contra el mes anterior al mismo día (`titulo_y_variacion()`; en las barras, en valor y en % con
    `cambio_valor()`), y al final la etiqueta del acumulado con su variación (`etiqueta_acumulado()`). El pie de las
    láminas explica el cumplimiento con `NOTA_CUMPLIMIENTO`.

Todo el código, nombres de variables, comentarios y commits están en español; mantener ese idioma.

## Metodología de cálculo de los reportes (los dos notebooks)

Sale de `SQL_REPORTES` y se aplica igual en los dos notebooks (`indicadores()`, celda A.5) y por fila en
`consultas.calcular()`:

- **Devolución** = línea con `kilogram < 0` **y** `value < 0` (`es_devolucion` en el CTE `ventas`). Las demás
  líneas son venta, incluidas las de valor negativo sin kilos (p. ej. notas crédito), que restan del valor bruto.
- **Kilos brutos** (`Venta Kg`) = `SUM(kilogram)` sin devoluciones.
- **Kilos devueltos** (`Devolucion Kg`, en positivo) = `−SUM(kilogram)` de las devoluciones.
- **Kilos netos** = `SUM(kilogram)` de todas las líneas = `Venta Kg − Devolucion Kg`.
- **Valor bruto** (`Venta Bruta`) = `SUM(value + discount_value)` sin devoluciones.
- **Valor de devolución** (`Devolucion Valor`, en positivo) = `−SUM(value + discount_value)` de las devoluciones.
- **Valor ajuste de precio** (`Valor Total Descuento`, `P_GEN`) = `SUM(discount_value)` de todas las líneas.
- **Valor neto** (`Venta Neta`) = `SUM(value)` de todas las líneas. Cuadra: bruto − devolución − ajuste = neto.
- **Precio de lista** = valor bruto / kilos brutos; **precio neto** = valor neto / kilos netos (`SUM(value) /
  SUM(kilogram)`).
- **% cumplimiento del precio de lista** (`L_GEN`) = precio neto / precio de lista. Ya no es 100 − % de ajuste.
- **Por tipo de ajuste** (mercado y fecha corta, `L_AJ`, `L_FC`, `D_AJ`, `D_FC`), como antes: solo la venta (sin
  devoluciones) y sobre el valor bruto, como si fuera el único: (valor bruto − ese ajuste) / valor bruto. `D_GEN`
  = valor ajuste de precio / valor bruto.
- **Rangos por fila** (22 tramos, `Rango Total`): el % de lista de cada fila (fecha × cliente × grupo 6 ×
  distribuidora × canal × sector) también es precio neto / precio de lista; sin kilos netos positivos o sin venta
  bruta queda vacío y cae en `23. Sin venta bruta`. Los rangos por tipo de ajuste siguen sobre la venta bruta.

## Entorno y comandos

- Python del entorno virtual en `venv/` (no `.venv` como dice el README); el kernel del notebook es `venv`.
  Usar `venv/Scripts/python.exe`.
- Conexión: variables `DB_*` del `.env` de esta carpeta; si no existe, se usa `../Lista de precios/.env`.
- No hay tests, linter ni build.

```bash
py main.py --inicio 2026-09-01 --fin 2026-10-01                 # --fin es EXCLUSIVO
py main.py --inicio 2025-01-01 --fin 2026-10-01 --canal 10      # -> parquet, solo mayoreo
```

Los notebooks se corren completos en orden (*Run All*) desde VS Code. El semanal tiene su parámetro `CORTE_D` en
A.1; el ejecutivo siempre va a corte de ayer.

## Trabajar con el notebook

Los notebooks pueden pesar mucho por las salidas (imágenes embebidas). No leerlos enteros: extraer solo las fuentes
de las celdas, p. ej.

```bash
PYTHONIOENCODING=utf-8 venv/Scripts/python.exe -c "import json; nb=json.load(open('Reporte_Ejecutivo.ipynb',encoding='utf-8')); [print(f'=== [{i}] {c[\"cell_type\"]}\n'+''.join(c['source'])) for i,c in enumerate(nb['cells'])]"
```

y editar por celda. La consola de Windows es cp1252: sin `PYTHONIOENCODING=utf-8` los `print` con tildes o `−`
fallan.

## Arquitectura de los notebooks

Los dos conservan la numeración de secciones y celdas del notebook original del que salieron (A.1–A.6, B 2–12,
C.1–C.6), con saltos. **No comparten código:** cada uno tiene su propia copia de la preparación y de las funciones
que usa. Un cambio en una función compartida (p. ej. `indicadores`, `MEDIDAS`, `num`) hay que repetirlo en los dos.
En el semanal, `modo_corte()` reemplaza variables globales del notebook mientras dura el `with`, por eso el código
vive en los notebooks y no en un módulo `.py`.

Tres partes; las celdas dependen de variables globales de las anteriores, así que un cambio en A obliga a
re-ejecutar todo lo de abajo.

- **A. Preparación**: parámetros, conexión, periodo (1 del mes anterior hasta el corte incluido), A.5 constantes y
  formato (`SOCIEDADES`: `1000` = Región Oriente, `2000` = Región Occidente; `MEDIDAS`; nombres normalizados de
  indicadores `VENTA_BRUTA`, `L_GEN`, `P_AJ`...; `indicadores()`) y A.6 la consulta, reducida a tablas chicas en
  memoria. En el semanal: `diario_soc`, `cubo_d` (dimensión × miembro × sociedad × periodo × rango × motivo),
  `cruce_d`, `clientes_d`; el nivel `Año` contiene el período (mes anterior / mes en curso).
- **B. Funciones** de las láminas (semanal).
- **C. Salidas** (python-pptx), en `SALIDA` (se crea sola).

## Reglas de cálculo que no son obvias

- `daily_sales.value` ya es la venta **neta**; bruta = neta + `discount_value`; `discount_value` = ajuste de
  mercado (`discount_market_price_adjustment`) + fecha corta (`short_dated_discount`); foco va aparte (no está
  dentro del total).
- Todos los % se calculan **desde las sumas** (nunca promediando % de filas).
- Rangos de % de lista: cerrados abajo (`right=False`); los rótulos llevan número (`01.`..`23.`) para que se
  ordenen como texto.
- Códigos (cliente, lista, tipología, grupo 6) son texto con ceros a la izquierda.
- **Canal de venta** de cada línea: sale de la tipología de la venta (`client_typology`); si viene vacía, de la del
  maestro de clientes (`cliente_attr`), y si tampoco hay, `000`. `vw_dim_tipologias_cliente` lleva la tipología al
  canal; la `000` es canal `Directo`, segmento "Sin asignar". El canal `Directo` se muestra como `Amas de casa`.
- `cliente_attr` (un registro por cliente con `DISTINCT ON`) tiene que desempatar **del todo**: lista válida y
  menor, luego la fila **con** tipología, la tipología menor y el nombre. Un cliente puede tener varias filas con
  la misma lista, con y sin tipología; sin ese desempate, Postgres elegía una cualquiera en cada ejecución y la
  venta sin tipología saltaba entre su canal y `Directo` (cambiaban el precio neto y el cumplimiento por canal de
  venta, aunque los totales por canal de distribución cuadraban). Ya está corregido en `SQL_REPORTES`;
  `SQL_DESCUENTOS` (`main.py`) todavía tiene el orden sin desempate.

## Archivos generados

Los PowerPoint van a `output/<carpeta>/` (el semanal a `output/Informe_Avance_Region/`, el ejecutivo a
`output/Reporte_Ejecutivo/`). En `.gitignore` las carpetas de `output/` ignoran su contenido salvo el `.gitkeep`.
`.xlsx`, `.parquet` y `.csv` están en `.gitignore`. Los `.pptx` generados no están ignorados: no incluirlos en
commits salvo que se pida.
