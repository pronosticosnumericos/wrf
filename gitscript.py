import os
from git import Repo, GitCommandError

# Obtén el token desde la variable de entorno (asegúrate de haberlo exportado, e.g., export GITHUB_TOKEN="tu_token")
token = os.environ.get("GITHUB_TOKEN")
if not token:
    raise Exception("No se encontró la variable de entorno GITHUB_TOKEN.")

username = "pronosticosnumericos"
# Construye la URL remota con el token
remote_url = f"https://{username}:{token}@github.com/{username}/wrf.git"

# Ruta al repositorio local
repo_path = "/home/sig07/website_nuevo"

try:
    # Abre o inicializa el repositorio existente
    repo = Repo(repo_path)
    
    # Asegúrate de estar en la rama 'main'
    if "main" not in repo.heads:
        repo.git.checkout("-b", "main")
    else:
        repo.git.checkout("main")
    
    # Agrega todos los archivos y haz commit
    repo.git.add(A=True)
    # Solo realiza commit si hay cambios
    if repo.is_dirty(untracked_files=True):
        repo.index.commit("Agregar WRF")
    else:
        print("No hay cambios para commitear.")
    
    # Configura el remoto 'origin'
    try:
        repo.create_remote("origin", remote_url)
    except GitCommandError:
        repo.git.remote("set-url", "origin", remote_url)
    
    # Fuerza el push a la rama main
    repo.git.push("--force", "-u", "origin", "main")
    print("Push realizado correctamente.")
    
except Exception as e:
    print(f"Ocurrió un error: {e}")

