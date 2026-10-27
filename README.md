# Análisis de descuentos

Análisis del cumplimiento del precio de lista y de los descuentos comerciales (ventas de los sectores 10, 15, 20
y 21). Lee de PostgreSQL (`commercial_bi`, **solo lectura**) y tiene dos partes independientes:

| Pieza | Qué genera | Dónde |
| --- | --- | --- |
| `Reporte_Ejecutivo.ipynb` | Reporte ejecutivo **diario** (corte de ayer), en PowerPoint | `output/Reporte_Ejecutivo/` |
| `Informe_Region_semanal.ipynb` | Informe **semanal** de avance por región, en PowerPoint | `output/Informe_Avance_Region/` |
| `main.py` | Tabla base de ventas con el detalle de los descuentos (`.xlsx` o `.parquet`) | esta carpeta |

`consultas.py` tiene las consultas y los cálculos que usan las dos partes (ver [Datos](#datos-consultaspy)).

## Instalación

```bash
python -m venv venv
venv\Scripts\activate            # Windows
pip install -r requirements.txt
```

En VS Code, elegir `venv` como kernel de los notebooks.

Copiar `.env.example` como `.env` en esta carpeta y completar la conexión `DB_*`.
Si no hay `.env` aquí, se usa el de la carpeta hermana `../Lista de precios/`.

## Reportes en PowerPoint

Los dos notebooks comparan **el mes anterior completo contra el mes en curso** hasta el corte y traen los datos
con `consultas.descargar_mes()`: cada corrida consulta la base (unos 2 a 3 minutos) y procesa todo en memoria,
sin escribir Parquet. Se corren completos en orden (*Run All*).

| Reporte | Notebook | Corte | Archivos |
| --- | --- | --- | --- |
| Ejecutivo diario | `Reporte_Ejecutivo.ipynb` | Siempre **ayer**, sin parámetros | `Informe Diario Cumplimiento precio lista [<región>] <mes anterior> vs <mes en curso> al <día>.pptx` |
| Semanal por región | `Informe_Region_semanal.ipynb` | `CORTE_D` en A.1 | `Informe Semanal <región> <mes anterior> vs <mes en curso> al <día>.pptx` |

En el semanal, antes de correr, poner en `CORTE_D` el último día que debe entrar, p. ej. `date(2026, 10, 17)`
para cortar al sábado 17 (`None` = ayer). **`CORTE_D` es inclusivo**: ese día entra en el informe.

### Metodología de los reportes

Es la misma en los dos notebooks (sale de `SQL_REPORTES` en `consultas.py`):

- **Devolución:** línea con kilos negativos **y** valor negativo. Las demás líneas son venta, incluidas las de
  valor negativo sin kilos (p. ej. notas crédito), que restan del valor bruto.
- **Kilos brutos** = kilos sin devoluciones; **kilos devueltos** (en positivo); **kilos netos** = kilos brutos −
  kilos devueltos.
- **Valor bruto** = neto + ajuste, sin devoluciones; **valor de devolución** (en positivo); **valor ajuste de
  precio** = `discount_value`; **valor neto** = `value`. Valor bruto − devolución − ajuste = valor neto.
- **Precio de lista** = valor bruto / kilos brutos; **precio neto** = valor neto / kilos netos.
- **% cumplimiento del precio de lista** = precio neto / precio de lista.
- **Por tipo de ajuste** (ajuste de precio de mercado y fecha corta): solo la venta y sobre el valor bruto, como
  si fuera el único: (valor bruto − ese ajuste) / valor bruto.

Todos los % se calculan desde las sumas, nunca promediando % de filas.

### Reporte ejecutivo diario (`Reporte_Ejecutivo.ipynb`)

Genera tres PowerPoint en `output/Reporte_Ejecutivo/`.

**Lámina ejecutiva** (un archivo, total compañía y las dos regiones):
- el **% de cumplimiento general** a corte, con la variación contra el mes anterior;
- el cumplimiento por **canal de venta**, con el menor resaltado;
- la **ruta** donde menos se cumple: canal de venta → canal de distribución → grupo de material 6. El canal de
  distribución y el grupo son los de menor cumplimiento entre los que pesan al menos `PARTICIPACION_MIN` (5%) de
  la venta de su nivel;
- el **cumplimiento por tipo de ajuste**: ajuste de precio de mercado y fecha corta, con su variación.

**Un archivo por región** (Región Oriente y Región Occidente), con dos láminas:
1. **Cómo voy, por qué y dónde:** el cumplimiento y los ajustes en % de la lista con su variación, y las
   devoluciones; el **mapa** canal de venta × canal de distribución (en cada celda, el % de cumplimiento con su
   variación en puntos y el precio neto por kg con su diferencia en pesos, contra el mes anterior completo; fuera
   del mapa, los totales por canal y de la región); y la **tendencia** del cumplimiento acumulado del mes, día a
   día, contra el mes anterior.
2. **Día a día:** el % de cumplimiento de cada día y las barras de valor neto y kilos netos, del 1 del mes
   anterior al corte, con el acumulado del mes en punteado y la variación contra el mes anterior a igual día.

### Informe semanal por región (`Informe_Region_semanal.ipynb`)

Genera un PowerPoint por región (Región Oriente y Región Occidente) en `output/Informe_Avance_Region/`:

| Láminas | Contenido |
| --- | --- |
| Portada | |
| Panorama | Tabla de indicadores (kilos y valor brutos, devueltos y netos, ajuste de precio, precio de lista y neto, % de cumplimiento) y tendencia día a día del precio de lista y neto y de la venta neta con el % de cumplimiento |
| Rangos | Rangos de % de cumplimiento del total, por canal de distribución, canal de venta y grupo de material, con la tabla resumen de cada uno |
| Distribuidoras | Concentración del ajuste |
| Clientes | Top de clientes de Mayoreo y de Puntos de Venta |

### Datos (`consultas.py`)

`consultas.py` tiene dos bloques:

- **`SQL_DESCUENTOS`**: la consulta de `main.py` (tabla base). No separa devoluciones ni sigue la metodología de
  los reportes.
- **`SQL_REPORTES`** + `calcular()` (% de lista, rangos y motivo por fila) + `descargar_mes(inicio, fin)`, que
  devuelve un DataFrame: lo usan los dos notebooks. Un cambio en la consulta o en los cálculos de los reportes se
  hace ahí una sola vez.

Los notebooks no comparten el resto del código: cada uno tiene su copia de la preparación y de las funciones, así
que un cambio en una función común (p. ej. `indicadores()`) hay que repetirlo en los dos.

## Tabla base con `main.py`

Los comandos se corren desde esta carpeta. `--fin` **no se incluye** (es exclusivo).

```bash
py main.py --inicio 2026-09-01 --fin 2026-10-01      # un mes  -> .xlsx
py main.py --inicio 2025-01-01 --fin 2026-10-01      # 2025-26 -> .parquet
py main.py --inicio ... --fin ... --canal 10         # solo mayoreo (por defecto, todos los canales)
py main.py --inicio ... --fin ... --formato xlsx     # forzar el formato
py main.py --inicio ... --fin ... --salida nombre    # la extension la pone el formato
```

| Período | Salida por defecto | Por qué |
| --- | --- | --- |
| Hasta 31 días | `.xlsx` | ~450 mil filas por mes: cabe en una hoja |
| Más de 31 días | `.parquet` | 2025–2026 son ~9,6 millones de filas; Excel admite 1.048.576 por hoja |

El Parquet se escribe por partes de 500 mil filas, así que no hace falta tener toda la
consulta en memoria. Si la corrida falla a mitad, el archivo incompleto se borra.

## Qué trae cada fila

Una fila = **día × cliente × grupo de material 6 × distribuidora × canal × tipología
× sector**. Solo sectores 10, 15, 20 y 21 (vista `daily_sales_sector_10_15_20_21`).

| Grupo | Columnas |
| --- | --- |
| Dimensiones | Fecha, Código SAP Cliente, Nombre Cliente, Lista de Precios, Grupo Material 6, Nombre GR6, Canal de Distribución, Distribuidora, Nombre Distribuidora, Tipología Cliente, Nombre Tipología, Canal de Venta, Sector |
| Valores | Venta Kg, Venta Neta, Venta Bruta, Valor Total Descuento, Descuento Ajuste Precio Mercado, Descuento Rotación / Fecha Corta, Descuento Foco, Precio Promedio |
| % de descuento | % Descuento Total, % Descuento Ajuste Mercado, % Descuento Rotación / Fecha Corta, % Descuento Foco |
| % de lista | % Lista Total, % Lista Dcto Rotación, % Lista Dcto Ajuste, % Lista Dcto Foco |
| Clasificación | Rango Total, Rango Dcto Rotación, Rango Dcto Ajuste, Rango Dcto Foco, Motivo Descuento |

Origen de las dimensiones: la lista de precios sale de `commercial_clients.price_group`;
el grupo 6 de `materials.gr6` → `material_groups_6`; el canal de venta de
`vw_dim_tipologias_cliente` según la tipología (la de la venta y, si viene vacía, la
del maestro de clientes).

## Cómo se calcula

Esto es para la tabla base de `main.py`; los reportes usan su propia metodología (ver
[Metodología de los reportes](#metodología-de-los-reportes)). En `daily_sales`, `value` ya es la venta **neta** y `discount_value` es el descuento
**total** (incluye la fecha corta).

| Concepto | Fórmula |
| --- | --- |
| Venta bruta (a precio de lista) | neta + descuento total |
| Descuento rotación / fecha corta | `short_dated_discount` |
| Descuento ajuste de mercado | descuento total − fecha corta |
| Descuento foco | `focus_discount` (aparte; no está dentro del total) |
| Precio promedio | venta neta / kilos |
| % de cada descuento | descuento / venta bruta × 100 |
| **% Lista Total** | **venta neta / venta bruta × 100** |
| % Lista Dcto Rotación | (bruta − fecha corta) / bruta × 100 |
| % Lista Dcto Ajuste | (bruta − ajuste) / bruta × 100 |
| % Lista Dcto Foco | (bruta − foco) / bruta × 100 |

`% Lista Total` es lo que realmente se cobró. Los otros tres aíslan un solo descuento,
como si fuera el único.

### Rangos

Cada `% Lista` se clasifica en 22 tramos, de `01. 100% O MAS` a `22. Menos de 50%`,
más `23. Sin venta bruta` para devoluciones o bruta en cero. El número al inicio es
para que una tabla dinámica los ordene sola. Los límites son cerrados abajo: 97,00%
cae en `02. Mas de 97 menos de 100%`.

`Motivo Descuento` dice qué descuentos tuvo la fila: `Fecha corta`, `Ajuste mercado`,
`Foco`, sus combinaciones (`Fecha corta + Ajuste mercado`) o `Sin descuento`.

### Vistas sugeridas

- **Por qué se descuenta en cada rango:** filas `Rango Total`, columnas
  `Motivo Descuento`, valores `Venta Bruta` como % del total de la fila.
- **Impacto aislado de la fecha corta:** filas `Rango Dcto Rotacion`, valores
  `Venta Bruta` como % del total.
- **2025 vs 2026:** agregar año / mes de `Fecha` en columnas.

**No sumar ni promediar las columnas de %** en una dinámica: el promedio pesa igual
una venta chica que una grande. Recalcularlas con un campo calculado, p. ej.
`% Lista = 'Venta Neta' / 'Venta Bruta'`.

## Abrir el Parquet

- **Power BI Desktop** (recomendado): *Obtener datos → Parquet*. Maneja los millones
  de filas sin problema.
- **Excel (Microsoft 365)**: *Datos → Obtener datos → Desde archivo → Desde Parquet*.
  No cabe completo en una hoja (más de 1.048.576 filas), así que en Power Query hay
  que **agrupar o filtrar antes de cargar** (p. ej. por año, mes, rango y grupo 6).
  Con Excel de 32 bits tampoco conviene cargarlo al Modelo de datos.

Los códigos (lista de precios, tipología, grupo 6, cliente) van como **texto**, con
sus ceros a la izquierda (`'01'`, `'018'`).

## Limitaciones conocidas

- **Maestro de clientes con registros repetidos.** Unos 2.200 clientes tienen varios
  registros con la misma lista de precios y tipologías distintas, y la consulta toma
  uno de ellos sin un criterio fijo. Cuando la venta trae la tipología vacía, dos
  corridas sobre los mismos datos pueden diferir en tipología / canal de venta (y por
  eso en algún rango) para unas pocas ventas. Los totales no cambian. Solo afecta a
  `main.py`: la consulta de los reportes (`SQL_REPORTES`) ya desempata.
- **Descuento foco casi vacío.** En 2026 hay una sola línea con valor; sus columnas
  quedan listas para cuando se registre.
- **La base es en vivo.** Recorrer el mismo período dos veces puede dar unas pocas
  filas distintas si entretanto se cargaron o corrigieron ventas.
