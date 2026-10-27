"""SQL de la tabla base de descuentos (origen: commercial_bi, solo lectura).

Parte de la vista `daily_sales_sector_10_15_20_21` (sectores 10, 15, 20, 21, sin el
material 10363), igual que el proyecto de lista de precios.

DESCUENTOS (columnas de daily_sales):
  - `value` es la venta NETA (ya descontada). Bruta = value + discount_value.
  - `discount_value` es el descuento TOTAL y ya incluye la fecha corta.
  - fecha corta / rotacion = short_dated_discount
  - ajuste de precio mercado = discount_value - short_dated_discount
    (misma formula que la columna discount_market_price_adjustment de la vista)
  - foco = focus_discount (se informa aparte; casi siempre viene vacio)

GRANO: fecha x cliente x grupo de material 6 x distribuidora x canal x sector.
El % de lista y el rango se calculan en pandas sobre ese grano.
"""

SQL_DESCUENTOS = """
WITH cliente_attr AS (
    -- Un unico registro por cliente (misma regla que lista de precios:
    -- price_group valido y el menor alfabeticamente).
    SELECT DISTINCT ON (cc.client)
        cc.client,
        NULLIF(cc.price_group, '')       AS price_group,
        cc.name                          AS nombre_cliente,
        NULLIF(cc.customer_typology, '') AS tipologia
    FROM public.commercial_clients cc
    ORDER BY cc.client,
             (cc.price_group IS NULL OR cc.price_group = '') ASC,
             cc.price_group ASC
)
SELECT
    v.date                                           AS fecha,
    v.client                                         AS cliente,
    cp.nombre_cliente,
    cp.price_group                                   AS lista_precio,
    m.gr6                                            AS grupo_material_6,
    g6.name                                          AS nombre_gr6,
    dc.distribution_channel_name                     AS canal_distribucion,
    cdd.new_zone_code                                AS distribuidora,
    regexp_replace(cdd.new_zone_name, '^[^-]*-', '') AS nombre_distribuidora,
    -- La tipologia de la venta es la del momento; si viene vacia, la del maestro
    LPAD(COALESCE(NULLIF(v.client_typology, ''), cp.tipologia, '0'), 3, '0') AS tipologia,
    t.name                                           AS nombre_tipologia,
    t.sales_channel_name                             AS canal_venta,
    m.sector,
    SUM(v.kilogram)                                  AS venta_kg,
    SUM(v.value)                                     AS venta_neta,
    SUM(v.value + COALESCE(v.discount_value, 0))     AS venta_bruta,
    SUM(COALESCE(v.discount_value, 0))               AS descuento_total,
    SUM(v.discount_market_price_adjustment)          AS descuento_ajuste_mercado,
    SUM(COALESCE(v.short_dated_discount, 0))         AS descuento_fecha_corta,
    SUM(COALESCE(v.focus_discount, 0))               AS descuento_foco
FROM public.daily_sales_sector_10_15_20_21 v
LEFT JOIN public.materials m
       ON v.material::integer = m.code
LEFT JOIN public.material_groups_6 g6
       ON g6.code = m.gr6
LEFT JOIN public.commercial_distributors_details cdd
       ON v.id_commercial_distributors = cdd.id
LEFT JOIN public.distribution_channels dc
       ON v.distribution_channel = dc.distribution_channel
LEFT JOIN cliente_attr cp
       ON v.client = cp.client
LEFT JOIN public.vw_dim_tipologias_cliente t
       ON t.client_typology_id = LPAD(COALESCE(NULLIF(v.client_typology, ''), cp.tipologia, '0'), 3, '0')
WHERE v.date >= :fecha_inicio
  AND v.date <  :fecha_fin                 -- fin EXCLUSIVO
  {filtro_canal}
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13
HAVING COALESCE(SUM(v.value), 0) <> 0
    OR COALESCE(SUM(v.kilogram), 0) <> 0
ORDER BY fecha, cliente, grupo_material_6;
"""


# =====================================================================================================================
# Datos del mes para los reportes diario y semanal (Informe_Diario_Canal_Venta.ipynb e
# Informe_Region_semanal.ipynb). Separado de lo de arriba, que usa main.py tal cual.
#
# SQL_REPORTES trae ademas la sociedad (company_code) y las DEVOLUCIONES aparte (lineas con kilogram < 0 y value < 0):
#   kilos brutos (venta_kg)        = SUM(kilogram) sin devoluciones
#   kilos devueltos (devolucion_kg) = -SUM(kilogram) de las devoluciones;  kilos netos = SUM(kilogram) de todo
#   valor bruto (venta_bruta)      = SUM(value + discount_value) sin devoluciones
#   valor devolucion               = -SUM(value + discount_value) de las devoluciones
#   valor ajuste (descuento_total) = SUM(discount_value) de todo;  valor neto (venta_neta) = SUM(value) de todo
#   precio de lista = valor bruto / kilos brutos;  precio neto = valor neto / kilos netos
#   % cumplimiento del precio de lista = precio neto / precio de lista
# Los ajustes por tipo (mercado, fecha corta, foco) son solo de la venta y sus % siguen sobre la venta bruta.
# descargar_mes() consulta y devuelve un DataFrame: los notebooks procesan en memoria, sin Parquet.
# =====================================================================================================================
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text

AQUI = Path(__file__).resolve().parent

FILAS_POR_PARTE = 500_000

SQL_REPORTES = """
WITH ventas AS (
    -- Devolucion: linea con kg negativo Y valor negativo. Las demas son venta, incluidas las de valor negativo sin
    -- kg (p. ej. notas credito), que restan del valor bruto.
    SELECT v.*, COALESCE(v.kilogram < 0 AND v.value < 0, FALSE) AS es_devolucion
    FROM public.daily_sales_sector_10_15_20_21 v
    WHERE v.date >= :fecha_inicio
      AND v.date <  :fecha_fin             -- fin EXCLUSIVO
),
cliente_attr AS (
    -- Un unico registro por cliente (misma regla que lista de precios: price_group valido y el menor
    -- alfabeticamente). El orden tiene que desempatar del todo: un cliente puede tener varias filas con la misma
    -- lista, con y sin tipologia, y sin desempate Postgres elige una cualquiera en cada ejecucion (la venta sin
    -- tipologia saltaba entre su canal y Directo, que es la tipologia 000). Primero la fila con tipologia.
    SELECT DISTINCT ON (cc.client)
        cc.client,
        NULLIF(cc.price_group, '')       AS price_group,
        cc.name                          AS nombre_cliente,
        NULLIF(cc.customer_typology, '') AS tipologia
    FROM public.commercial_clients cc
    ORDER BY cc.client,
             (cc.price_group IS NULL OR cc.price_group = '') ASC,
             cc.price_group ASC,
             (cc.customer_typology IS NULL OR cc.customer_typology = '') ASC,
             cc.customer_typology ASC,
             cc.name ASC
)
SELECT
    v.date                                           AS fecha,
    v.client                                         AS cliente,
    cp.nombre_cliente,
    cp.price_group                                   AS lista_precio,
    m.gr6                                            AS grupo_material_6,
    g6.name                                          AS nombre_gr6,
    dc.distribution_channel_name                     AS canal_distribucion,
    cdd.new_zone_code                                AS distribuidora,
    regexp_replace(cdd.new_zone_name, '^[^-]*-', '') AS nombre_distribuidora,
    cdd.company_code::text                           AS sociedad,
    -- La tipologia de la venta es la del momento; si viene vacia, la del maestro
    LPAD(COALESCE(NULLIF(v.client_typology, ''), cp.tipologia, '0'), 3, '0') AS tipologia,
    t.name                                           AS nombre_tipologia,
    t.sales_channel_name                             AS canal_venta,
    m.sector,
    -- Brutos (kilos, valor y los ajustes por tipo): solo la venta, sin las devoluciones. Valor neto (SUM(value)) y
    -- ajuste total (SUM(discount_value)): todas las lineas. Asi bruto - devolucion - ajuste = neto.
    COALESCE(SUM(v.kilogram) FILTER (WHERE NOT v.es_devolucion), 0)                                AS venta_kg,
    COALESCE(SUM(v.value), 0)                                                                      AS venta_neta,
    COALESCE(SUM(v.value + COALESCE(v.discount_value, 0)) FILTER (WHERE NOT v.es_devolucion), 0)   AS venta_bruta,
    COALESCE(SUM(COALESCE(v.discount_value, 0)), 0)                                                AS descuento_total,
    COALESCE(SUM(v.discount_market_price_adjustment) FILTER (WHERE NOT v.es_devolucion), 0)        AS descuento_ajuste_mercado,
    COALESCE(SUM(COALESCE(v.short_dated_discount, 0)) FILTER (WHERE NOT v.es_devolucion), 0)       AS descuento_fecha_corta,
    COALESCE(SUM(COALESCE(v.focus_discount, 0)) FILTER (WHERE NOT v.es_devolucion), 0)             AS descuento_foco,
    -- Devoluciones, en positivo: kg y valor devueltos (valor con su descuento, value + discount_value)
    -COALESCE(SUM(v.kilogram) FILTER (WHERE v.es_devolucion), 0)                                   AS devolucion_kg,
    -COALESCE(SUM(v.value + COALESCE(v.discount_value, 0)) FILTER (WHERE v.es_devolucion), 0)      AS devolucion_valor
FROM ventas v
LEFT JOIN public.materials m
       ON v.material::integer = m.code
LEFT JOIN public.material_groups_6 g6
       ON g6.code = m.gr6
LEFT JOIN public.commercial_distributors_details cdd
       ON v.id_commercial_distributors = cdd.id
LEFT JOIN public.distribution_channels dc
       ON v.distribution_channel = dc.distribution_channel
LEFT JOIN cliente_attr cp
       ON v.client = cp.client
LEFT JOIN public.vw_dim_tipologias_cliente t
       ON t.client_typology_id = LPAD(COALESCE(NULLIF(v.client_typology, ''), cp.tipologia, '0'), 3, '0')
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14
-- Fuera solo las filas sin ningun valor: una venta devuelta en la misma fila suma 0 neto, pero tiene bruto,
-- devolucion y ajuste
HAVING SUM(ABS(COALESCE(v.value, 0)) + ABS(COALESCE(v.kilogram, 0)) + ABS(COALESCE(v.discount_value, 0))) <> 0
ORDER BY fecha, cliente, grupo_material_6;
"""

# Rangos: (limite inferior del % de lista, rotulo), de mayor a menor. El numero del rotulo ordena los tramos.
RANGOS = [(100, "100% O MAS"), (97, "Mas de 97 menos de 100%"), (95, "Mas de 95 menos de 97%"),
          (93, "Mas de 93 menos de 95%"), (90, "Mas de 90 menos de 93%"), (87, "Mas de 87 menos de 90%"),
          (85, "Mas de 85 menos de 87%"), (83, "Mas de 83 menos de 85%"), (80, "Mas de 80 menos de 83%"),
          (77, "Mas de 77 menos de 80%"), (75, "Mas de 75 menos de 77%"), (73, "Mas de 73 menos de 75%"),
          (70, "Mas de 70 menos de 73%"), (67, "Mas de 67 menos de 70%"), (65, "Mas de 65 menos de 67%"),
          (63, "Mas de 63 menos de 65%"), (60, "Mas de 60 menos de 63%"), (57, "Mas de 57 menos de 60%"),
          (55, "Mas de 55 menos de 57%"), (53, "Mas de 53 menos de 55%"), (50, "Mas de 50 menos de 53%")]

_ROTULOS = [f"{i:02d}. {r}" for i, (_, r) in enumerate(RANGOS, start=1)] + [f"{len(RANGOS) + 1:02d}. Menos de 50%"]

_ROTULO_SIN_BRUTA = f"{len(RANGOS) + 2:02d}. Sin venta bruta"

_BORDES = [float("-inf")] + [limite for limite, _ in reversed(RANGOS)] + [float("inf")]

MOTIVOS_FILA = {"descuento_fecha_corta": "Fecha corta", "descuento_ajuste_mercado": "Ajuste mercado",
                "descuento_foco": "Foco"}

COLUMNAS = {
    "fecha": "Fecha", "cliente": "Codigo SAP Cliente", "nombre_cliente": "Nombre Cliente",
    "lista_precio": "Lista de Precios", "venta_kg": "Venta Kg", "venta_neta": "Venta Neta",
    "venta_bruta": "Venta Bruta", "descuento_total": "Valor Total Descuento",
    "descuento_ajuste_mercado": "Descuento Ajuste Precio Mercado",
    "descuento_fecha_corta": "Descuento Rotacion / Fecha Corta", "descuento_foco": "Descuento Foco",
    "pct_descuento_total": "% Descuento Total", "pct_descuento_ajuste": "% Descuento Ajuste Mercado",
    "pct_descuento_fecha_corta": "% Descuento Rotacion / Fecha Corta", "pct_descuento_foco": "% Descuento Foco",
    "precio_promedio": "Precio Promedio", "grupo_material_6": "Grupo Material 6", "nombre_gr6": "Nombre GR6",
    "canal_distribucion": "Canal de Distribucion", "distribuidora": "Distribuidora",
    "nombre_distribuidora": "Nombre Distribuidora", "sociedad": "Sociedad", "tipologia": "Tipologia Cliente",
    "nombre_tipologia": "Nombre Tipologia", "canal_venta": "Canal de Venta", "sector": "Sector",
    "pct_lista": "% Lista Total", "pct_lista_rotacion": "% Lista Dcto Rotacion",
    "pct_lista_ajuste": "% Lista Dcto Ajuste", "pct_lista_foco": "% Lista Dcto Foco",
    "rango": "Rango Total", "rango_rotacion": "Rango Dcto Rotacion", "rango_ajuste": "Rango Dcto Ajuste",
    "rango_foco": "Rango Dcto Foco", "motivo": "Motivo Descuento",
    "devolucion_kg": "Devolucion Kg", "devolucion_valor": "Devolucion Valor",
}

def rango(pct_: pd.Series) -> pd.Series:
    """% de lista (0 a 100) -> rotulo del tramo. [97, 100) es 'Mas de 97 menos de 100%'."""
    tramos = pd.cut(pct_, bins=_BORDES, labels=list(reversed(_ROTULOS)), right=False)
    return tramos.astype(str).where(pct_.notna(), _ROTULO_SIN_BRUTA)

def calcular(df: pd.DataFrame) -> pd.DataFrame:
    """Medidas, % sobre la venta bruta, % de lista, rangos y motivo de cada fila."""
    medidas = ["venta_kg", "venta_neta", "venta_bruta", "descuento_total",
               "descuento_ajuste_mercado", "descuento_fecha_corta", "descuento_foco", "devolucion_kg",
               "devolucion_valor"]
    df[medidas] = df[medidas].astype(float)
    kg_neto = df["venta_kg"] - df["devolucion_kg"]            # kilos netos: SUM(kilogram) de todas las lineas
    precio_neto = df["venta_neta"] / kg_neto.where(kg_neto > 0)   # SUM(value) / SUM(kilogram)
    df["precio_promedio"] = precio_neto.round(0)
    bruta = df["venta_bruta"].where(df["venta_bruta"] > 0)   # filas sin venta bruta (solo devoluciones): sin %
    precio_lista = bruta / df["venta_kg"].where(df["venta_kg"] > 0)

    def sobre_bruta(serie: pd.Series) -> pd.Series:
        return (serie / bruta * 100).round(2)

    df["pct_descuento_total"] = sobre_bruta(df["descuento_total"])
    df["pct_descuento_ajuste"] = sobre_bruta(df["descuento_ajuste_mercado"])
    df["pct_descuento_fecha_corta"] = sobre_bruta(df["descuento_fecha_corta"])
    df["pct_descuento_foco"] = sobre_bruta(df["descuento_foco"])
    # % de lista: el total es precio neto / precio de lista (sin kilos netos o sin venta bruta: vacio, rango "Sin
    # venta bruta"); los otros aislan un solo descuento sobre la venta bruta, como si fuera el unico
    df["pct_lista"] = (precio_neto / precio_lista * 100).round(2)
    df["pct_lista_rotacion"] = sobre_bruta(df["venta_bruta"] - df["descuento_fecha_corta"])
    df["pct_lista_ajuste"] = sobre_bruta(df["venta_bruta"] - df["descuento_ajuste_mercado"])
    df["pct_lista_foco"] = sobre_bruta(df["venta_bruta"] - df["descuento_foco"])
    for sufijo in ("", "_rotacion", "_ajuste", "_foco"):
        df["rango" + sufijo] = rango(df["pct_lista" + sufijo])
    partes = [df[col].gt(0).map({True: nombre + " + ", False: ""}) for col, nombre in MOTIVOS_FILA.items()]
    texto_ = pd.concat(partes, axis=1).sum(axis=1).str.removesuffix(" + ")
    df["motivo"] = texto_.where(texto_ != "", "Sin descuento")
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df[list(COLUMNAS)].rename(columns=COLUMNAS)


def engine():
    """Conexion de origen (commercial_bi, solo lectura) con las variables DB_* del .env de esta carpeta o, si no hay,
    del proyecto de lista de precios."""
    load_dotenv(AQUI / ".env") or load_dotenv(AQUI.parent / "Lista de precios" / ".env")
    faltan = [v for v in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD") if not os.getenv(v)]
    if faltan:
        raise RuntimeError(f"Faltan en el .env: {', '.join(faltan)}. "
                           f"Copie .env.example como .env en {AQUI} y completelo.")
    url = URL.create("postgresql+psycopg2", username=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
                     host=os.environ["DB_HOST"], port=int(os.getenv("DB_PORT", "5432")),
                     database=os.environ["DB_NAME"])
    return create_engine(url, pool_pre_ping=True)


def descargar_mes(fecha_inicio, fecha_fin, columnas=None, motor=None) -> pd.DataFrame:
    """Consulta SQL_REPORTES de fecha_inicio a fecha_fin (EXCLUSIVO) y devuelve un DataFrame con calcular() aplicado.

    Lee por partes de FILAS_POR_PARTE filas (el servidor las entrega con un cursor de servidor) y de cada parte deja
    solo `columnas`, si se dan, para no tener en memoria lo que no se usa. motor: una conexion ya creada (engine())."""
    motor = motor or engine()
    partes, filas = [], 0
    with motor.connect() as c:
        c = c.execution_options(stream_results=True)
        for parte in pd.read_sql(text(SQL_REPORTES), c, chunksize=FILAS_POR_PARTE,
                                 params={"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin}):
            parte = calcular(parte)
            partes.append(parte[columnas] if columnas else parte)
            filas += len(parte)
            print(f"  {filas:,} filas")
    if not partes:
        raise RuntimeError(f"La consulta no devolvio filas entre {fecha_inicio} y {fecha_fin} (exclusivo).")
    return pd.concat(partes, ignore_index=True)
