# Descuentos — tabla base

Genera una tabla base de ventas con el detalle de los **tres descuentos** (ajuste de
precio de mercado, rotación / fecha corta y foco) y clasifica cada venta en **rangos
de % de lista**, para analizar cuánto de la venta se cobra a precio de lista y por qué
motivo se descuenta.

Lee de PostgreSQL (`commercial_bi`, solo lectura) y escribe un `.xlsx` cuando el
período es de un mes o menos, o un `.parquet` cuando es más largo. Los informes en
PowerPoint se generan con los notebooks (ver [Reportes semanales](#reportes-semanales)).

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
```

Copiar `.env.example` como `.env` en esta carpeta y completar la conexión `DB_*`.
Si no hay `.env` aquí, el script usa el de la carpeta hermana `../Lista de precios/`.

## Reportes diario y semanal

Los PowerPoint se generan con notebooks (en VS Code, con el kernel del entorno virtual). Los dos
reportes usan **el mes anterior completo contra el mes en curso** y traen los datos con
`consultas.descargar_mes()`: cada corrida consulta la base (unos 2 a 3 minutos) y procesa todo en
memoria, sin escribir Parquet.

| Reporte | Notebook | Corte | Salida |
| --- | --- | --- | --- |
| Diario | `Informe_Diario_Canal_Venta.ipynb` | Siempre **ayer**, sin parámetros | `output/Informe_Diario_Canal_Venta/` |
| Semanal | `Informe_Region_semanal.ipynb` | `CORTE_D` en A.1 | `output/Informe_Avance_Region/` |

Para correr cualquiera de los dos: *Run All*. En el semanal, antes, poner en `CORTE_D` el último día
que debe entrar, p. ej. `date(2026, 10, 17)` para cortar al sábado 17 (`None` = ayer). **`CORTE_D` es
inclusivo**: ese día entra en el informe.

### Informe semanal de avance por región

**Metodología del informe:** el precio de lista, el precio neto y los % de cumplimiento se calculan
**sin las devoluciones** (líneas de venta con valor negativo, que se registran a precio neto y sin
descuento). Las devoluciones se muestran aparte en el panorama (kg y valor devueltos).

Contenido de cada PowerPoint: portada; panorama (tabla con devoluciones y tendencia diaria de precio
de lista y neto, y de venta neta con % de cumplimiento); rangos del total, por canal de distribución,
canal de venta y grupo de material; distribuidoras; y una lámina con el top 15 de clientes de Mayoreo
y de Puntos de Venta.

### Informe diario por canal de venta

**`Informe_Diario_Canal_Venta.ipynb`** genera 8 PowerPoint (Región Oriente y Región Occidente ×
Institucional, Amas de casa, Modernos y Tradicional) en `output/Informe_Diario_Canal_Venta/`. Cada uno
lleva 6 láminas del informe de avance, con toda la información filtrada por ese canal de venta:
portada, panorama, tendencia diaria, rangos de % de cumplimiento, resumen por canal de distribución y
resumen por grupo de material 6. Va siempre a corte de ayer (no tiene `CORTE_D`).

### Reporte ejecutivo diario

**`Reporte_Ejecutivo.ipynb`** genera una sola lámina, a corte de ayer contra el mes anterior completo, en
`output/Reporte_Ejecutivo/`. Para el total compañía y cada región muestra:
- el **% de cumplimiento general** a corte, con la variación contra el mes anterior;
- el cumplimiento por **canal de venta**, con el menor resaltado;
- la **ruta** donde menos se cumple: canal de venta → canal de distribución → grupo de material 6. El canal de
  distribución y el grupo son los de menor cumplimiento entre los que pesan al menos `PARTICIPACION_MIN` (5%) de
  la venta de su nivel;
- el **cumplimiento por tipo de descuento**: ajuste de precio de mercado y fecha corta, cada uno como si fuera el
  único descuento, con su variación.

Además genera **una lámina por región** (`Reporte_Ejecutivo_Region_<región>_…pptx`) con más detalle:
- **Cómo voy y por qué se descuenta:** el cumplimiento, el ajuste de precio de mercado y la fecha corta en % de la
  lista con su variación, y las devoluciones.
- **Dónde:** mapa de calor canal de venta × canal de distribución; rojo, por debajo del cumplimiento general de la
  región.
- **Tendencia:** el cumplimiento acumulado del mes, día a día, del mes en curso contra el mes anterior, con la
  comparación a igual día del mes.

Se corre igual que el diario (*Run All*, sin parámetros) y usa la misma `consultas.descargar_mes()`.

### Datos (`consultas.py`)

`consultas.py` tiene, además del `SQL_DESCUENTOS` que usa `main.py`, la consulta de los reportes
(`SQL_REPORTES`, con la sociedad y las devoluciones aparte), los cálculos por fila (`calcular()`: % de
lista, rangos y motivo) y `descargar_mes(inicio, fin)`, que devuelve un DataFrame. Un cambio en la
consulta o en los cálculos de los reportes se hace ahí una sola vez y lo toman el diario y el semanal.

### Otros informes

| Notebook | Genera | Carpeta |
| --- | --- | --- |
| `Informe_Ajustes_Region.ipynb` | Informe general 2025 vs 2026 por región y Excel del panorama | `output/Informe_Ajustes_Region/` |
| `Top_Clientes.ipynb` | Top de clientes del mes de `MES_CLIENTES` | `output/Top_Clientes/` |
| `Informe_Cliente.ipynb` | Informe de un cliente (`CLIENTE`) | `output/Informe_Cliente/` |
| `Descuentos.ipynb` | El notebook original, que genera todo junto | `output/General/` |

Estos sí leen el histórico 2025–2026 (`FECHA_INICIO` a `FECHA_FIN`, un Parquet de ~500 MB que
tarda varios minutos en consultarse). Con `GENERAR_PARQUET = False` reutilizan el Parquet que ya
exista con las mismas fechas.

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

En `daily_sales`, `value` ya es la venta **neta** y `discount_value` es el descuento
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
  eso en algún rango) para unas pocas ventas. Los totales no cambian.
- **Descuento foco casi vacío.** En 2026 hay una sola línea con valor; sus columnas
  quedan listas para cuando se registre.
- **La base es en vivo.** Recorrer el mismo período dos veces puede dar unas pocas
  filas distintas si entretanto se cargaron o corrigieron ventas.
