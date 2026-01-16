#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import numpy as np
import pandas as pd
import xarray as xr

# wrf-python helpers
from wrf import getvar, ll_to_xy, to_np, latlon_coords

# -----------------------
# Ciudades ~50 (nombre, lat, lon)
# -----------------------
CITIES = [
    ("Ciudad de México", 19.433, -99.133),
    ("Guadalajara", 20.673, -103.346),
    ("Monterrey", 25.686, -100.316),
    ("Puebla", 19.043, -98.198),
    ("Tijuana", 32.514, -117.038),
    ("León", 21.122, -101.684),
    ("Juárez", 31.690, -106.425),
    ("Zapopan", 20.723, -103.384),
    ("Nezahualcóyotl", 19.400, -99.033),
    ("Chihuahua", 28.635, -106.089),
    ("Mérida", 20.967, -89.623),
    ("San Luis Potosí", 22.156, -100.985),
    ("Querétaro", 20.588, -100.389),
    ("Saltillo", 25.423, -101.005),
    ("Aguascalientes", 21.882, -102.283),
    ("Mexicali", 32.624, -115.452),
    ("Hermosillo", 29.073, -110.956),
    ("Culiacán", 24.804, -107.394),
    ("Morelia", 19.705, -101.195),
    ("Reynosa", 26.093, -98.277),
    ("Tlalnepantla", 19.538, -99.194),
    ("Acapulco", 16.863, -99.882),
    ("Cancún", 21.161, -86.851),
    ("Toluca", 19.286, -99.653),
    ("Torreón", 25.542, -103.406),
    ("Villahermosa", 17.989, -92.928),
    ("Xalapa", 19.543, -96.910),
    ("Veracruz", 19.173, -96.134),
    ("Oaxaca", 17.060, -96.726),
    ("Tuxtla Gutiérrez", 16.753, -93.116),
    ("Tampico", 22.255, -97.869),
    ("Durango", 24.027, -104.653),
    ("Tepic", 21.505, -104.895),
    ("La Paz", 24.142, -110.312),
    ("Ensenada", 31.866, -116.600),
    ("Mazatlán", 23.249, -106.411),
    ("Celaya", 20.522, -100.814),
    ("Irapuato", 20.676, -101.356),
    ("Pachuca", 20.101, -98.759),
    ("Cuernavaca", 18.924, -99.221),
    ("Colima", 19.243, -103.725),
    ("Campeche", 19.845, -90.523),
    ("Zacatecas", 22.773, -102.573),
    ("Guanajuato", 21.017, -101.257),
    ("Coatzacoalcos", 18.149, -94.442),
    ("Poza Rica", 20.533, -97.459),
    ("Playa del Carmen", 20.629, -87.074),
    ("Puerto Vallarta", 20.653, -105.225),
    ("Uruapan", 19.414, -102.057),
    ("Chilpancingo", 17.551, -99.503),
]

def round3(x: float) -> float:
    return float(f"{x:.3f}")

def ensure_outdir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def concat_time(wrf_paths):
    """
    Abre varios wrfout_* y concatena en el eje tiempo.
    Mantiene variables necesarias, decodifica tiempos.
    """
    def _preprocess(ds):
        # Mantén solo variables necesarias para bajar RAM (opcional)
        keep = [v for v in ds.data_vars]
        # No filtramos aquí para no romper wrf.getvar que usa campos auxiliares.
        return ds

    ds = xr.open_mfdataset(
        wrf_paths,
        combine='by_coords',
        preprocess=_preprocess,
        parallel=False,
        engine='netcdf4',
        decode_times=True
    )
    return ds

def compute_latlon(ds):
    # wrf-python: devuelve 2D lat/lon
    lats, lons = latlon_coords(getvar(ds, "T2", timeidx=0))
    return to_np(lats), to_np(lons)

def nearest_ij(ds, lat, lon):
    """
    Usa ll_to_xy (wrf) para obtener el punto de grilla más cercano.
    """
    # getvar devuelve DataArray; usar T2 solo para sacar proyección
    t2 = getvar(ds, "T2", timeidx=0)
    j_i = ll_to_xy(ds, lat, lon, meta=False)  # (x, y) = (i, j)
    i_idx = int(j_i[0])
    j_idx = int(j_i[1])
    # Asegura límites
    ny, nx = t2.shape[-2], t2.shape[-1]
    i_idx = max(0, min(nx-1, i_idx))
    j_idx = max(0, min(ny-1, j_idx))
    return j_idx, i_idx

def to_celsius(k):
    return k - 273.15

def wind_speed_kmh(u10, v10):
    # u10,v10 en m/s -> velocidad km/h
    spd = np.sqrt(u10**2 + v10**2)
    return spd * 3.6

def rh2_percent(ds):
    """
    Intenta obtener humedad relativa a 2m con wrf.getvar('rh2').
    Si falla, calcula aproximado usando T2 (K), Q2 (kg/kg) y PSFC (Pa).
    """
    try:
        rh2 = getvar(ds, "rh2")  # [%]
        return rh2
    except Exception:
        # Aproximación (Tetens); Q2 ~ razón de mezcla (kg/kg).
        T2 = getvar(ds, "T2")  # K
        Q2 = getvar(ds, "Q2")  # kg/kg
        PSFC = getvar(ds, "PSFC")  # Pa

        # presión en hPa
        p_hpa = PSFC / 100.0
        # temp en °C
        T_c = T2 - 273.15

        # presión de vapor de saturación (hPa) Tetens
        es = 6.112 * np.exp((17.67 * T_c) / (T_c + 243.5))
        # mezcla de saturación (kg/kg), usando aproximación: qs = 0.622 * es / (p - 0.378*es)
        qs = 0.622 * es / (p_hpa - 0.378 * es)
        # humedad relativa
        rh = (Q2 / qs) * 100.0
        rh = xr.where(rh < 0, 0, rh)
        rh = xr.where(rh > 100, 100, rh)
        return rh

def rain_rate_mm_per_h(ds):
    """
    mm/h a partir de acumulados (RAINC + RAINNC).
    Si el paso de tiempo no es 1h, se normaliza a mm/h.
    """
    try:
        rainc = getvar(ds, "RAINC")  # mm, acumulado convectivo
    except Exception:
        rainc = 0
    try:
        rainnc = getvar(ds, "RAINNC")  # mm, no convectivo
    except Exception:
        rainnc = 0

    if isinstance(rainc, int):
        rain_acc = rainnc
    elif isinstance(rainnc, int):
        rain_acc = rainc
    else:
        rain_acc = rainc + rainnc  # mm acumulados

    # diferencia temporal
    rain_diff = rain_acc.diff(dim=rain_acc.dims[0], label='upper')  # mm en Δt
    # tiempo entre pasos (horas). Asume coord 'Time' (decodificada)
    time = rain_acc[ rain_acc.dims[0] ].to_index()
    # vector de horas entre pasos (al tamaño de diff)
    dt_hours = []
    for t0, t1 in zip(time[:-1], time[1:]):
        dt = (pd.to_datetime(t1) - pd.to_datetime(t0)).total_seconds()/3600.0
        dt_hours.append(dt if dt>0 else 1.0)
    dt_hours = xr.DataArray(np.array(dt_hours), dims=[rain_diff.dims[0]])

    rate = rain_diff / dt_hours  # mm/h
    # igualamos longitud con time original insertando un 0 al inicio
    rate_full = xr.concat([rate.isel({rate.dims[0]: 0})*0, rate], dim=rate.dims[0])
    rate_full = rate_full.assign_coords({rate_full.dims[0]: rain_acc[rain_acc.dims[0]]})
    return rate_full

def extract_series(ds, j, i):
    """
    Extrae series en el punto (j,i). Devuelve dict con arrays nativos de Python.
    """
    # Temperatura 2m (°C)
    T2 = getvar(ds, "T2")  # K
    t2m = to_celsius(T2[:, j, i]).values

    # Viento 10m (km/h)
    U10 = getvar(ds, "U10")  # m/s
    V10 = getvar(ds, "V10")  # m/s
    wind = wind_speed_kmh(U10[:, j, i].values, V10[:, j, i].values)

    # Humedad relativa 2m (%)
    RH2 = rh2_percent(ds)
    rh = RH2[:, j, i].values

    # Precipitación mm/h
    rain_rate = rain_rate_mm_per_h(ds)
    tp = rain_rate[:, j, i].values

    # Timestamps ISO (UTC)
    timevar = getvar(ds, "times", meta=False)  # array de strings b'YYYY-MM-DD_HH:MM:SS'
    # Convierte a ISO "YYYY-MM-DDTHH:MMZ"
    ts = []
    for t in to_np(timevar):
        s = t.decode() if isinstance(t, (bytes, bytearray)) else str(t)
        # WRF típicamente "YYYY-MM-DD_HH:MM:SS"
        s = s.replace("_", "T") + "Z"
        ts.append(s)

    return {
        "timestamps": ts,
        "t2m": [round(float(x), 1) for x in t2m],
        "tp":  [round(float(x), 2) for x in tp],
        "wind": [int(round(float(x))) for x in wind],
        "rh":   [int(round(float(x))) for x in rh]
    }

def save_json(outdir: Path, lat: float, lon: float, data: dict):
    lat3 = round3(lat)
    lon3 = round3(lon)
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / f"{lat3},{lon3}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return path

def main():
    ap = argparse.ArgumentParser(description="Genera JSON de meteograma para ciudades desde wrfout_*")
    ap.add_argument("--wrf", nargs="+", required=True, help="Rutas a wrfout_* (acepta comodines si tu shell expande)")
    ap.add_argument("--outdir", default="data/meteogram/wrf", help="Directorio de salida (default: data/meteogram/wrf)")
    ap.add_argument("--cities_csv", default=None, help="CSV opcional con columnas name,lat,lon")
    args = ap.parse_args()

    wrf_paths = sorted(args.wrf)
    if not wrf_paths:
        raise SystemExit("No se encontraron archivos WRF (wrfout_*)")

    outdir = Path(args.outdir)
    ensure_outdir(outdir)

    # Carga ciudades
    cities = []
    if args.cities_csv and Path(args.cities_csv).exists():
        df = pd.read_csv(args.cities_csv)
        for _, r in df.iterrows():
            cities.append((str(r["name"]), float(r["lat"]), float(r["lon"])))
    else:
        cities = CITIES

    print(f"[INFO] Abriendo {len(wrf_paths)} archivos WRF…")
    ds = concat_time(wrf_paths)

    # Validación rápida
    time_len = ds.dims.get("Time") or ds.dims.get("time") or None
    if not time_len:
        print("[WARN] No se detectó dimensión temporal explícita; wrf.getvar manejará 'times' igualmente.")
    else:
        print(f"[INFO] Pasos de tiempo: {time_len}")

    # Para ll_to_xy se usa ds completo. Calculamos una vez T2 para shape y proyección.
    _ = getvar(ds, "T2", timeidx=0)

    # Procesa ciudades
    for name, lat, lon in cities:
        try:
            j, i = nearest_ij(ds, lat, lon)
            series = extract_series(ds, j, i)
            path = save_json(outdir, lat, lon, series)
            print(f"[OK] {name:20s} → {path}")
        except Exception as e:
            print(f"[ERR] {name}: {e}")

    print("[DONE] JSONs listos.")

if __name__ == "__main__":
    main()

