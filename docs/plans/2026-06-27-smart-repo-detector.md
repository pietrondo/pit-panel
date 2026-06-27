# Smart GitHub Repo Analyzer for /apps

## Goal
In `/apps`, incolli un URL GitHub → sistema clona e analizza il repo → rileva lo stack → auto-deploy (se confidenza > 90%).

## Architecture

### 1. `src/pit_panel/core/repo_detector.py` (nuovo modulo)

```python
@dataclass
class DetectedStack:
    stack_type: str      # "nodejs", "wordpress", "python-fastapi", "python-flask", "ghost", "static-nginx", "custom-compose"
    display_name: str
    confidence: int      # 0-100
    indicators: list[str]

async def analyze_repo(repo_url: str) -> DetectedStack
async def clone_repo(repo_url: str, dest: Path) -> None
def detect_stack(repo_path: Path) -> DetectedStack
def cleanup(repo_path: Path) -> None
```

### 2. Detection Rules (root dir only)

| Stack | Indicators | Confidence |
|-------|-----------|------------|
| WordPress | `wp-config.php` o `wp-content/` | 95 |
| Ghost | `ghost-config.js` o `config.production.json` | 95 |
| Next.js | `package.json` + `next.config.js`/`.mjs` | 95 |
| Node.js | `package.json` (no PHP, no Next.js) | 85 |
| Python FastAPI | `requirements.txt`/`Pipfile` + `main.py` con `FastAPI` | 95 |
| Python Flask | `requirements.txt`/`Pipfile` + `app.py` con `Flask` | 95 |
| Python generico | `requirements.txt` o `Pipfile` | 80 |
| Static | `index.html` + nessun altro indicatore | 90 |
| Docker | `Dockerfile` | 70 |

### 3. Git Clone
- `git clone --depth 1 <url> /tmp/pit-panel-repo-<hash>`
- Cleanup dopo analisi o deploy

### 4. Nuova Route
- `POST /apps/analyze-repo` → accetta `{"repo_url": "..."}`, restituisce `DetectedStack`
- Riutilizza `POST /apps/deploy` esistente per il deploy

### 5. UI
- Form con input URL GitHub nella pagina `/apps`
- Mostra risultato detection (stack + confidenza + indicatori trovati)
- Bottone "Deploy" che usa il flusso esistente
