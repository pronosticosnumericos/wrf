#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WRF T2 -> Temperatura media (°C) en rango de horas -> GeoTIFF EPSG:4326

Ejemplo:
  python3 t2prueba.py \
    --wrf /home/sig07/WRF/ARWpost/wrfout_d01_2025-09-19_12_00_00 \
    --hours 0:24 \
    --out tmp/tmean_20250919_00-24_4326.tif
"""
import argparse
from pathlib import Path
from typing import Tuple

import numpy as np
import xarray as xr
import rioxarray as rxr  # noqa: F401
from pyproj import CRS, Transformer
from affine import Affine


# ------------------------ utilidades IO ------------------------

def open_wrf(wrf_path: str) -> xr.Dataset:
    """Abrir wrfout probando backends comunes, sin decodificar tiempos."""
    try:
        return xr.open_dataset(wrf_path, engine="netcdf4", decode_times=False)
    except Exception as e1:
        try:
            return xr.open_dataset(wrf_path, engine="h5netcdf", decode_times=False)
        except Exception as e2:
            try:
                return xr.open_dataset(wrf_path, engine="scipy", decode_times=False)
            except Exception as e3:
                raise RuntimeError(
                    "No se pudo abrir el wrfout con netcdf4/h5netcdf/scipy.\n"
                    f"- netcdf4: {e1}\n- h5netcdf: {e2}\n- scipy: {e3}"
                )


def pick_time_dim(da: xr.DataArray) -> str:
    """Detecta el nombre de la dimensión temporal."""
    for cand in ("Time", "time", "Times"):
        if cand in da.dims:
            return cand
    for d in da.dims:
        if d not in ("west_east", "south_north", "x", "y",
                     "lon", "lat", "longitude", "latitude"):
            return d
    return list(da.dims)[0]


# ------------------------ cálculo físico ------------------------

def compute_t2_mean(ds: xr.Dataset, hours: str) -> xr.DataArray:
    """T2 media en °C en el rango [h0:h1)."""
    if "T2" not in ds:
        raise KeyError("No se encontró la variable 'T2' en el wrfout.")
    t2 = ds["T2"]
    tdim = pick_time_dim(t2)
    h0, h1 = [int(x) for x in hours.split(":")]
    ntime = int(t2.sizes.get(tdim, 1))
    h1 = min(h1, ntime)
    if h0 >= h1:
        raise ValueError(f"Rango de horas inválido: {h0}:{h1} con ntime={ntime}")
    t2c = (t2.isel({tdim: slice(h0, h1)}).mean(tdim) - 273.15).squeeze()
    t2c = t2c.rename("tmean")
    t2c.attrs.update(units="degC", long_name="Mean 2-m air temperature (°C)")
    return t2c


# ------------------------ georreferenciación robusta ------------------------

def build_lcc_from_attrs(ds: xr.Dataset) -> CRS:
    """CRS LCC desde attrs WRF."""
    try:
        tr1 = float(ds.attrs.get("TRUELAT1"))
        tr2 = float(ds.attrs.get("TRUELAT2"))
        cen_lat = float(ds.attrs.get("CEN_LAT"))
        std_lon = float(ds.attrs.get("STAND_LON"))
    except Exception as e:
        raise RuntimeError(
            "No se pudieron leer TRUELAT1/2, CEN_LAT, STAND_LON de attrs del WRF."
        ) from e
    return CRS.from_proj4(
        f"+proj=lcc +lat_1={tr1} +lat_2={tr2} +lat_0={cen_lat} +lon_0={std_lon} "
        f"+ellps=WGS84 +units=m +no_defs"
    )


def get_latlon(ds: xr.Dataset) -> Tuple[xr.DataArray, xr.DataArray]:
    """Obtiene XLAT/XLONG o XLAT_M/XLONG_M en 2D (sin dimensión Time)."""
    lat_name = "XLAT" if "XLAT" in ds.variables else ("XLAT_M" if "XLAT_M" in ds.variables else None)
    lon_name = "XLONG" if "XLONG" in ds.variables else ("XLONG_M" if "XLONG_M" in ds.variables else None)
    if lat_name is None or lon_name is None:
        raise KeyError("No encontré XLAT/XLONG (ni XLAT_M/XLONG_M) en el wrfout.")
    lat = ds[lat_name]
    lon = ds[lon_name]
    if "Time" in lat.dims:
        lat = lat.isel(Time=0)
    if "Time" in lon.dims:
        lon = lon.isel(Time=0)
    return lat, lon


def axes_from_latlon(lat2d: xr.DataArray, lon2d: xr.DataArray, lcc: CRS) -> Tuple[np.ndarray, np.ndarray]:
    """
    Transforma mallas lat/lon -> X,Y (LCC) y devuelve ejes 1D coherentes con el orden de la matriz:
      x_vec[j]  ~ mediana de X[:, j]
      y_vec[i]  ~ mediana de Y[i, :]
    Así el píxel [i, j] corresponde al centro (x_vec[j], y_vec[i]).
    """
    tf = Transformer.from_crs("EPSG:4326", lcc, always_xy=True)
    X, Y = tf.transform(lon2d.values, lat2d.values)  # 2D en metros
    x_vec = np.nanmedian(X, axis=0)  # tamaño = west_east
    y_vec = np.nanmedian(Y, axis=1)  # tamaño = south_north
    return x_vec, y_vec


def affine_from_axes(x_vec: np.ndarray, y_vec: np.ndarray) -> Affine:
    """Affine a partir de ejes 1D; el píxel [0,0] centra en (x_vec[0], y_vec[0])."""
    dx = float(np.nanmedian(np.diff(x_vec)))
    dy = float(np.nanmedian(np.diff(y_vec)))
    x0 = float(x_vec[0] - dx/2.0)
    y0 = float(y_vec[0] - dy/2.0)
    return Affine(dx, 0.0, x0, 0.0, dy, y0)  # dy puede ser negativo; Affine lo maneja.


def ensure_spatial_dims_xy(da: xr.DataArray) -> xr.DataArray:
    """
    Renombra dims espaciales a 'x'/'y', asigna coords 1D si no existen,
    y ordena como (y, x). Luego marca los ejes para rioxarray.
    """
    dims = list(da.dims)
    # Identifica nombres originales
    orig_x = "west_east" if "west_east" in dims else ("x" if "x" in dims else dims[-1])
    orig_y = "south_north" if "south_north" in dims else ("y" if "y" in dims else dims[-2])

    # Renombrar a x/y
    if orig_x != "x" or orig_y != "y":
        da = da.rename({orig_x: "x", orig_y: "y"})

    # Ordenar (y, x)
    if list(da.dims) != ["y", "x"]:
        da = da.transpose("y", "x")

    # Decirle a rioxarray cuáles son los ejes
    da = da.rio.set_spatial_dims(x_dim="x", y_dim="y", inplace=False)
    return da


# ------------------------ pipeline principal ------------------------

def tmean_24h_to_geotiff(wrf_path: str, hours: str, out_tif: str) -> None:
    ds = open_wrf(wrf_path)
    t2c = compute_t2_mean(ds, hours)  # °C

    # CRS LCC y ejes proyectados desde XLAT/XLONG
    lcc = build_lcc_from_attrs(ds)
    lat2d, lon2d = get_latlon(ds)
    x_vec, y_vec = axes_from_latlon(lat2d, lon2d, lcc)
    transform = affine_from_axes(x_vec, y_vec)

    # Renombrar dims a x/y y asignar coords 1D x/y
    dims = list(t2c.dims)
    orig_x = "west_east" if "west_east" in dims else ("x" if "x" in dims else dims[-1])
    orig_y = "south_north" if "south_north" in dims else ("y" if "y" in dims else dims[-2])

    if t2c.sizes[orig_x] != x_vec.size or t2c.sizes[orig_y] != y_vec.size:
        raise RuntimeError(
            f"Tamaño de ejes no coincide: {orig_x}={t2c.sizes[orig_x]} vs x_vec={x_vec.size}, "
            f"{orig_y}={t2c.sizes[orig_y]} vs y_vec={y_vec.size}"
        )

    da = t2c.rename({orig_x: "x", orig_y: "y"})
    da = da.assign_coords({"x": ("x", x_vec), "y": ("y", y_vec)})

    # Escribir CRS/transform y nodata, y marcar ejes
    da = (da
          .rio.write_crs(lcc)
          .rio.write_transform(transform)
          .rio.set_nodata(np.nan))
    da = ensure_spatial_dims_xy(da)

    # (opcional) invertir eje Y si la fila 0 no es la más norteña
    try:
        lat0 = float(lat2d.isel({lat2d.dims[0]: 0, lat2d.dims[1]: 0}))
        latN = float(lat2d.isel({lat2d.dims[0]: -1, lat2d.dims[1]: 0}))
        if lat0 < latN:
            da = da[::-1, :]
    except Exception:
        pass

    # Reproyectar a EPSG:4326 (deja que rioxarray elija resolución)
    da4326 = da.rio.reproject("EPSG:4326")

    # Guardar GeoTIFF
    out = Path(out_tif)
    out.parent.mkdir(parents=True, exist_ok=True)
    da4326.rio.to_raster(out, dtype="float32")


# ------------------------ CLI ------------------------

def main():
    ap = argparse.ArgumentParser(description="WRF T2 -> Tmean (°C) -> GeoTIFF EPSG:4326")
    ap.add_argument("--wrf", required=True, help="Ruta al wrfout_d01_*.nc")
    ap.add_argument("--hours", default="0:24", help="Rango de horas, ej. 0:24")
    ap.add_argument("--out", required=True, help="Salida GeoTIFF EPSG:4326")
    args = ap.parse_args()
    tmean_24h_to_geotiff(args.wrf, args.hours, args.out)


if __name__ == "__main__":
    main()

