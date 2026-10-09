"""Tabla base de descuentos -> Excel (un mes) o Parquet (rangos largos).

Uso (desde esta carpeta):
    py main.py --inicio 2026-09-01 --fin 2026-10-01                    # -> .xlsx
    py main.py --inicio 2025-01-01 --fin 2026-10-01                    # -> .parquet
    py main.py --inicio 2026-08-01 --fin 2026-10-01 --formato xlsx --canal 10

--fin es EXCLUSIVO. Sin --formato: hasta DIAS_EXCEL dias sale .xlsx; mas largo,
.parquet, porque a nivel cliente un año no cabe en una hoja de Excel (~450 mil
filas por mes). Usa la conexion DB_* (origen) del .env del proyecto de lista de
precios, salvo que haya un .env en esta carpeta.
"""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text

from consultas import SQL_DESCUENTOS

AQUI = Path(__file__).resolve().parent
MAX_FILAS_HOJA = 1_000_000  # Excel admite 1.048.576 filas por hoja
DIAS_EXCEL = 31             # hasta aqui la salida por defecto es .xlsx
FILAS_POR_PARTE = 500_000   # el Parquet se lee y escribe por partes de este tamaño

# (limite inferior del % de lista, rotulo). Se recorre de mayor a menor.
RANGOS = [
    (100, "100% O MAS"),
    (97, "Mas de 97 menos de 100%"),
    (95, "Mas de 95 menos de 97%"),
    (93, "Mas de 93 menos de 95%"),
    (90, "Mas de 90 menos de 93%"),
    (87, "Mas de 87 menos de 90%"),
    (85, "Mas de 85 menos de 87%"),
    (83, "Mas de 83 menos de 85%"),
    (80, "Mas de 80 menos de 83%"),
    (77, "Mas de 77 menos de 80%"),
    (75, "Mas de 75 menos de 77%"),
    (73, "Mas de 73 menos de 75%"),
    (70, "Mas de 70 menos de 73%"),
    (67, "Mas de 67 menos de 70%"),
    (65, "Mas de 65 menos de 67%"),
    (63, "Mas de 63 menos de 65%"),
    (60, "Mas de 60 menos de 63%"),
    (57, "Mas de 57 menos de 60%"),
    (55, "Mas de 55 menos de 57%"),
    (53, "Mas de 53 menos de 55%"),
    (50, "Mas de 50 menos de 53%"),
]
MENOS_50 = "Menos de 50%"
SIN_BRUTA = "Sin venta bruta"

# Los rotulos llevan numero ("01. 100% O MAS" ... "23. Sin venta bruta") para que
# Excel ordene los tramos solo: una dinamica ordena por texto.
_ROTULOS = [f"{i:02d}. {r}" for i, (_, r) in enumerate(RANGOS, start=1)]
_ROTULOS.append(f"{len(RANGOS) + 1:02d}. {MENOS_50}")
_ROTULO_SIN_BRUTA = f"{len(RANGOS) + 2:02d}. {SIN_BRUTA}"
_BORDES = [float("-inf")] + [limite for limite, _ in reversed(RANGOS)] + [float("inf")]

# Motivo del descuento: que descuentos tuvo la fila (los que son > 0)
MOTIVOS = {
    "descuento_fecha_corta": "Fecha corta",
    "descuento_ajuste_mercado": "Ajuste mercado",
    "descuento_foco": "Foco",
}
SIN_DESCUENTO = "Sin descuento"

COLUMNAS = {
    "fecha": "Fecha",
    "cliente": "Codigo SAP Cliente",
    "nombre_cliente": "Nombre Cliente",
    "lista_precio": "Lista de Precios",
    "venta_kg": "Venta Kg",
    "venta_neta": "Venta Neta",
    "venta_bruta": "Venta Bruta",
    "descuento_total": "Valor Total Descuento",
    "descuento_ajuste_mercado": "Descuento Ajuste Precio Mercado",
    "descuento_fecha_corta": "Descuento Rotacion / Fecha Corta",
    "descuento_foco": "Descuento Foco",
    "pct_descuento_total": "% Descuento Total",
    "pct_descuento_ajuste": "% Descuento Ajuste Mercado",
    "pct_descuento_fecha_corta": "% Descuento Rotacion / Fecha Corta",
    "pct_descuento_foco": "% Descuento Foco",
    "precio_promedio": "Precio Promedio",
    "grupo_material_6": "Grupo Material 6",
    "nombre_gr6": "Nombre GR6",
    "canal_distribucion": "Canal de Distribucion",
    "distribuidora": "Distribuidora",
    "nombre_distribuidora": "Nombre Distribuidora",
    "tipologia": "Tipologia Cliente",
    "nombre_tipologia": "Nombre Tipologia",
    "canal_venta": "Canal de Venta",
    "sector": "Sector",
    "pct_lista": "% Lista Total",
    "pct_lista_rotacion": "% Lista Dcto Rotacion",
    "pct_lista_ajuste": "% Lista Dcto Ajuste",
    "pct_lista_foco": "% Lista Dcto Foco",
    "rango": "Rango Total",
    "rango_rotacion": "Rango Dcto Rotacion",
    "rango_ajuste": "Rango Dcto Ajuste",
    "rango_foco": "Rango Dcto Foco",
    "motivo": "Motivo Descuento",
}


def rango(pct: pd.Series) -> pd.Series:
    """% de lista (0 a 100) -> rotulo del tramo. [97, 100) es 'Mas de 97 menos de 100%'."""
    tramos = pd.cut(pct, bins=_BORDES, labels=list(reversed(_ROTULOS)), right=False)
    return tramos.astype(str).where(pct.notna(), _ROTULO_SIN_BRUTA)


def motivo(df: pd.DataFrame) -> pd.Series:
    """'Fecha corta', 'Ajuste mercado', 'Fecha corta + Ajuste mercado', ... o 'Sin descuento'."""
    partes = [df[col].gt(0).map({True: nombre + " + ", False: ""}) for col, nombre in MOTIVOS.items()]
    texto = pd.concat(partes, axis=1).sum(axis=1).str.removesuffix(" + ")
    return texto.where(texto != "", SIN_DESCUENTO)


def calcular(df: pd.DataFrame) -> pd.DataFrame:
    medidas = ["venta_kg", "venta_neta", "venta_bruta", "descuento_total",
               "descuento_ajuste_mercado", "descuento_fecha_corta", "descuento_foco"]
    df[medidas] = df[medidas].astype(float)
    df["precio_promedio"] = (df["venta_neta"] / df["venta_kg"].where(df["venta_kg"] != 0)).round(0)
    # Todos los % son sobre la venta BRUTA (= neta + descuento total), de 0 a 100.
    # Si la bruta es 0 o negativa (devoluciones) quedan vacios.
    bruta = df["venta_bruta"].where(df["venta_bruta"] > 0)

    def pct(serie: pd.Series) -> pd.Series:
        return (serie / bruta * 100).round(2)

    df["pct_descuento_total"] = pct(df["descuento_total"])
    df["pct_descuento_ajuste"] = pct(df["descuento_ajuste_mercado"])
    df["pct_descuento_fecha_corta"] = pct(df["descuento_fecha_corta"])
    df["pct_descuento_foco"] = pct(df["descuento_foco"])
    # % de lista: cuanto de la bruta se cobro. El total usa la neta (todos los
    # descuentos); los otros tres aislan un solo descuento, como si fuera el unico.
    df["pct_lista"] = pct(df["venta_neta"])
    df["pct_lista_rotacion"] = pct(df["venta_bruta"] - df["descuento_fecha_corta"])
    df["pct_lista_ajuste"] = pct(df["venta_bruta"] - df["descuento_ajuste_mercado"])
    df["pct_lista_foco"] = pct(df["venta_bruta"] - df["descuento_foco"])
    for sufijo in ("", "_rotacion", "_ajuste", "_foco"):
        df["rango" + sufijo] = rango(df["pct_lista" + sufijo])
    df["motivo"] = motivo(df)
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df[list(COLUMNAS)].rename(columns=COLUMNAS)


def engine():
    load_dotenv(AQUI / ".env") or load_dotenv(AQUI.parent / "Lista de precios" / ".env")
    faltan = [v for v in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD") if not os.getenv(v)]
    if faltan:
        raise SystemExit(f"[ERROR] Faltan en el .env: {', '.join(faltan)}. "
                         f"Copie .env.example como .env en {AQUI} y completelo.")
    url = URL.create(
        "postgresql+psycopg2",
        username=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"], port=int(os.getenv("DB_PORT", "5432")),
        database=os.environ["DB_NAME"],
    )
    return create_engine(url, pool_pre_ping=True)


def escribir_excel(df: pd.DataFrame, salida: Path) -> None:
    with pd.ExcelWriter(salida, engine="openpyxl", datetime_format="DD-MM-YYYY") as xw:
        for i, ini in enumerate(range(0, max(len(df), 1), MAX_FILAS_HOJA), start=1):
            hoja = "BASE" if len(df) <= MAX_FILAS_HOJA else f"BASE_{i}"
            df.iloc[ini:ini + MAX_FILAS_HOJA].to_excel(xw, sheet_name=hoja, index=False)


def _tipo_parquet(serie: pd.Series) -> pa.DataType:
    if pd.api.types.is_datetime64_any_dtype(serie):
        return pa.timestamp("ms")
    if pd.api.types.is_numeric_dtype(serie):
        return pa.float64()
    return pa.string()


def escribir_parquet(partes, salida: Path) -> int:
    """Escribe parte por parte: 2025-2026 a nivel cliente son ~10 millones de filas
    y no caben en memoria de una vez. Devuelve las filas escritas.

    El esquema se fija con la primera parte, forzando texto en lo que no es numero
    ni fecha: si no, una columna que en esa parte viniera toda vacia quedaria con
    tipo 'null' y las partes siguientes no encajarian. Si algo falla a mitad, se
    borra el archivo: uno incompleto es peor que ninguno.
    """
    escritor, filas = None, 0
    try:
        for df in partes:
            if escritor is None:
                esquema = pa.schema([(c, _tipo_parquet(df[c])) for c in df.columns])
                escritor = pq.ParquetWriter(salida, esquema)
            escritor.write_table(pa.Table.from_pandas(df, schema=esquema, preserve_index=False))
            filas += len(df)
            print(f"  {filas:,} filas")
    except BaseException:
        if escritor is not None:
            escritor.close()
            salida.unlink(missing_ok=True)
        raise
    if escritor is not None:
        escritor.close()
    return filas


def main() -> int:
    p = argparse.ArgumentParser(description="Tabla base de descuentos")
    p.add_argument("--inicio", type=date.fromisoformat, required=True)
    p.add_argument("--fin", type=date.fromisoformat, required=True, help="EXCLUSIVO")
    p.add_argument("--canal", help="canal de distribucion, p.ej. 10 (mayoreo). Por defecto todos")
    p.add_argument("--formato", choices=["xlsx", "parquet"],
                   help=f"por defecto xlsx hasta {DIAS_EXCEL} dias y parquet si el rango es mas largo")
    p.add_argument("--salida", help="ruta del archivo (la extension la define el formato)")
    a = p.parse_args()

    formato = a.formato or ("xlsx" if (a.fin - a.inicio).days <= DIAS_EXCEL else "parquet")
    salida = Path(a.salida or f"Descuentos_{a.inicio:%Y%m%d}_{a.fin:%Y%m%d}").with_suffix("." + formato)

    filtro = "AND v.distribution_channel = :canal" if a.canal else ""
    params = {"fecha_inicio": a.inicio, "fecha_fin": a.fin}
    if a.canal:
        params["canal"] = a.canal
    sql = text(SQL_DESCUENTOS.format(filtro_canal=filtro))

    print(f"Consultando {a.inicio} -> {a.fin} (exclusivo), salida .{formato}...")
    with engine().connect() as c:
        if formato == "parquet":
            # stream_results: el servidor entrega las filas por partes (cursor de
            # servidor) en vez de mandarlas todas de una
            c = c.execution_options(stream_results=True)
            partes = pd.read_sql(sql, c, params=params, chunksize=FILAS_POR_PARTE)
            filas = escribir_parquet((calcular(parte) for parte in partes), salida)
        else:
            df = pd.read_sql(sql, c, params=params)
            filas = len(df)
            if filas:
                print(f"  {filas:,} filas")
                escribir_excel(calcular(df), salida)
    if not filas:
        print("[ERROR] La consulta no devolvio filas.")
        return 1
    print(f"Listo: {filas:,} filas en {salida.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
