# meteogram_api.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Meteogram API")

# Permitir peticiones del navegador (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # si quieres, pon aquí tu dominio en vez de "*"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sirve archivos estáticos desde ~/website_nuevo/data
app.mount(
    "/data",
    StaticFiles(directory="/home/sig07/website_nuevo/data"),
    name="data",
)

# Alias por si arrancas con APP:
APP = app

