import os
from git import Repo, GitCommandError, InvalidGitRepositoryError, NoSuchPathError

TOKEN = os.environ.get("GITHUB_TOKEN")
if not TOKEN:
    raise SystemExit("No se encontró la variable de entorno GITHUB_TOKEN.")

USERNAME   = "pronosticosnumericos"
REMOTE_URL = f"https://{USERNAME}:{TOKEN}@github.com/{USERNAME}/wrf.git"
REPO_PATH  = "/home/sig07/website_nuevo"
BRANCH     = "main"

def ensure_repo(path: str) -> Repo:
    try:
        return Repo(path)
    except (InvalidGitRepositoryError, NoSuchPathError):
        # Inicializa un repo nuevo
        repo = Repo.init(path)
        # Opcional: configura identidad si Git no la tiene globalmente
        with repo.config_writer() as cw:
            cw.set_value("user", "name",  "Julio (website_nuevo)")
            cw.set_value("user", "email", "you@example.com")
        return repo

repo = ensure_repo(REPO_PATH)
git = repo.git

# Crea o cambia a la rama principal
if repo.head.is_detached:
    if BRANCH in repo.heads:
        git.branch("-f", BRANCH, "HEAD")
    else:
        git.checkout("-b", BRANCH)
else:
    if BRANCH in repo.heads:
        git.checkout(BRANCH)
    else:
        git.checkout("-b", BRANCH)

# (Opcional) evita volver a versionar JSON gigantes
ignore_lines = ["prcp_matrix.json", "prcp/prcp_matrix.json"]
gi_path = os.path.join(REPO_PATH, ".gitignore")
if os.path.exists(gi_path):
    with open(gi_path, "a", encoding="utf-8") as f:
        for line in ignore_lines:
            f.write(f"{line}\n")
else:
    with open(gi_path, "w", encoding="utf-8") as f:
        for line in ignore_lines:
            f.write(f"{line}\n")

# Stage + commit (primer commit si no hay HEAD)
repo.git.add(A=True)
made_commit = False
try:
    # Si no hay commits, HEAD fallará: hacemos commit inicial
    repo.head.commit
    if repo.is_dirty(untracked_files=True):
        repo.index.commit("Snapshot inicial tras limpiar .git")
        made_commit = True
except ValueError:
    repo.index.commit("Snapshot inicial tras limpiar .git")
    made_commit = True

# Configura el remoto origin
try:
    repo.create_remote("origin", REMOTE_URL)
except GitCommandError:
    git.remote("set-url", "origin", REMOTE_URL)

# Push (historia nueva; usa --force-with-lease por seguridad)
# Si no hubo cambios por alguna razón, igual empuja la rama/refs
git.push("--force-with-lease", "-u", "origin", BRANCH)
print("Push realizado correctamente.")

