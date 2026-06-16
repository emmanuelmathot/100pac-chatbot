# Déploiement sur NAS (Docker Compose)

Déploiement de la stack 100PAC (API FastAPI + UI Streamlit) sur un hôte Docker, par
ex. un **NAS UGREEN** (x86), via [`docker-compose.yml`](../docker-compose.yml).

L'image est commune aux deux services ; les **artefacts** (modèle Zarr, index
vectoriel, rapport) sont **montés en volumes** car ils sont volumineux et non
versionnés.

## 1. Récupérer l'image

Deux options.

**A. Image publiée (recommandé)** — le workflow GitHub Actions
[`docker-publish.yml`](../.github/workflows/docker-publish.yml) publie l'image sur
GHCR à chaque push sur `main` (et sur tags `v*`). Sur le NAS :

```bash
# .env : IMAGE=ghcr.io/emmanuelmathot/100pac-chatbot:latest
docker compose pull
```

Si le package GHCR est privé : `docker login ghcr.io` avec un Personal Access Token
(scope `read:packages`).

**B. Build local** — `docker compose build` (nécessite le code source sur l'hôte).

## 2. Fournir les artefacts

Générés sur une machine de dev (cf. [README](../README.md)) :

```bash
cd backend && scripts/ingest-data /chemin/vers/les/log_csv && scripts/build-index
```

Puis copiés sur le NAS (dans un dossier persistant, ex. `/volume1/docker/100pac/`) :

```
data/pac.zarr                              (modèle de données, ~650 Mo)
backend/store/chroma                       (index vectoriel, ~11 Mo)
docs/Performance-PAC-Rapport-final.pdf     (rapport)
```

Pointez les volumes via `.env` (cf. `.env.example`) :

```bash
PAC_ZARR_HOST=/volume1/docker/100pac/pac.zarr
PAC_CHROMA_HOST=/volume1/docker/100pac/chroma
PAC_REPORT_HOST=/volume1/docker/100pac/Performance-PAC-Rapport-final.pdf
```

## 3. Configurer et démarrer

```bash
cp .env.example .env     # renseigner MISTRAL_API_KEY (+ IMAGE / ports / chemins)
docker compose up -d
docker compose ps        # api doit être "healthy"
```

- UI : `http://<nas>:8501` (port `CHAT_PORT`)
- API : `http://<nas>:8000` (port `API_PORT`), `GET /health`

L'UI joint l'API via le réseau interne de compose (`API_BASE_URL=http://api:8000`).

## Exposition HTTPS via Traefik (VPS, provider fichier)

Si un **Traefik** tourne sur un VPS et route vers le NAS par hostname (provider
fichier), le chatbot tourne sur le NAS (compose ci-dessus, UI publiée sur
`CHAT_PORT`) et Traefik publie le domaine. Déposer
[`deploy/traefik/100pac.mathot.org.yml`](../deploy/traefik/100pac.mathot.org.yml)
dans `~/traefik/config/conf.d/` sur le VPS :

```yaml
http:
  routers:
    100pac:
      rule: "Host(`100pac.mathot.org`)"
      entryPoints: [websecure]
      service: 100pac
      tls:
        certresolver: le
  services:
    100pac:
      loadBalancer:
        servers:
          - url: "http://nas-manu-et:8501"   # NAS + CHAT_PORT
```

Adapter le hostname/port du backend au NAS et au `CHAT_PORT` publié. Traefik gère
l'upgrade WebSocket de Streamlit ; côté UI, `--server.enableCORS=false` et
`--server.enableXsrfProtection=false` sont déjà activés (TLS terminé par Traefik).
Pointer l'enregistrement DNS `100pac.mathot.org` vers le VPS. L'API n'est pas exposée
publiquement (l'UI la joint en interne).

## Mise à jour

```bash
docker compose pull && docker compose up -d   # nouvelle image
```

Après régénération des artefacts, il suffit de remplacer les fichiers montés et de
redémarrer : `docker compose restart api`.

## Notes

- Ressources : prévoir ~1–2 Go de RAM pour l'API (ouverture lazy du Zarr + index).
- Le Zarr et le rapport sont montés en lecture seule ; **l'index Chroma doit être
  monté en lecture-écriture** (SQLite crée des fichiers `-wal`/`-shm`, échoue sinon
  avec « attempt to write a readonly database »).
- Pour exposer en HTTPS, placez un reverse proxy (Traefik / Nginx Proxy Manager,
  souvent disponibles sur NAS) devant les ports 8000/8501.
