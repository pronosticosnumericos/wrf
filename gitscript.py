#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from git import Repo, GitCommandError, InvalidGitRepositoryError, NoSuchPathError

TOKEN = os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    raise SystemExit("No se encontró la variable de entorno GITHUB_TOKEN.")

USERNAME    = "pronosticosnumericos"
REPO_NAME   = "wrf"  # repo remoto que usas para GitHub Pages
REMOTE_PLAIN = f"https://github.com/{USERNAME}/{REPO_NAME}.git"
REMOTE_AUTH  = f"https://{USERNAME}:{TOKEN}@github.com/{USERNAME}/{REPO_NAME}.git"

REPO_PATH   = "/home/sig07/website_nuevo"
BRANCH      = "main"

# Patrones a ignorar (pero OJO: aquí ya NO está *.png)
IGNORE_LINES = [
    ".venv/",
    "__pycache__/",
    "*.nc",
    "*.nc4",
    "*.grb",
    "*.grb2",
    "*.grib",
    "*.grib2",
    "*.tif",
    "*.tiff",
    "*.zip",
    "*.tar",
    "*.tar.gz",
    "*.tar.bz2",
    "raw/",
    "gfs_out/",
    "ecmwf_out/",
    "prcp_matrix.json",
    "prcp/prcp_matrix.json",
]


def ensure_repo(path: str) -> Repo:
    """Abre el repo si existe, o lo inicializa si no."""
    try:
        repo = Repo(path)
    except (InvalidGitRepositoryError, NoSuchPathError):
        repo = Repo.init(path)
        with repo.config_writer() as cw:
            cw.set_value("user", "name",  "Julio (website_nuevo)")
            cw.set_value("user", "email", "you@example.com")
    return repo


def append_unique_lines(file_path: str, lines):
    """Agrega líneas a .gitignore sin duplicarlas."""
    existing = set()
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            existing = {ln.rstrip("\n") for ln in f}
    to_add = [ln for ln in lines if ln not in existing]
    if to_add:
        with open(file_path, "a" if existing else "w", encoding="utf-8") as f:
            for ln in to_add:
                f.write(f"{ln}\n")
        return True
    return False


repo = ensure_repo(REPO_PATH)
git = repo.git

# Asegura rama BRANCH
if repo.head.is_detached:
    if BRANCH in repo.heads:
        git.branch("-f", BRANCH, "HEAD")
        git.checkout(BRANCH)
    else:
        git.checkout("-b", BRANCH)
else:
    if BRANCH in repo.heads:
        git.checkout(BRANCH)
    else:
        git.checkout("-b", BRANCH)

# Actualiza .gitignore
gi_path = os.path.join(REPO_PATH, ".gitignore")
changed_ignore = append_unique_lines(gi_path, IGNORE_LINES)
if changed_ignore:
    repo.index.add([gi_path])

# Si no hay cambios en el árbol de trabajo, no hacemos nada
if not repo.is_dirty(untracked_files=True):
    print("No hay cambios que subir.")
    raise SystemExit(0)

# Stage de TODO lo que no esté ignorado por .gitignore
git.add(all=True)

# ¿Ya existe al menos un commit?
has_commits = True
try:
    _ = repo.head.commit
except (ValueError, GitCommandError, TypeError):
    has_commits = False

if has_commits:
    # Actualiza SIEMPRE el mismo commit (no crees historial largo)
    git.commit("--amend", "--no-edit")
    print("Commit actualizado con --amend.")
else:
    repo.index.commit("Snapshot inicial del sitio")
    print("Commit inicial creado.")

# Configura remoto origin sin token
try:
    repo.create_remote("origin", REMOTE_PLAIN)
except GitCommandError:
    git.remote("set-url", "origin", REMOTE_PLAIN)

# Push forzado al remoto, usando la URL con token (no se guarda en la config)
try:
    git.push("--force", "-u", REMOTE_AUTH, f"{BRANCH}:{BRANCH}")
    print("Push forzado OK.")
except GitCommandError as e:
    print(f"Error en push: {e}")
    raise SystemExit(1)

print("Push realizado correctamente (sin persistir el token en el remote).")
#rm -rf .git
