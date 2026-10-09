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
