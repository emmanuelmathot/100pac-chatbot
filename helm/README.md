# Chatbot infrastructure

## Déploiement 100PAC — ce que contient le chart

Le chart `chatbot/` déploie :

- **Deployment `api`** (FastAPI, port 8000) — l'agent et ses outils. Lit la clé
  `MISTRAL_API_KEY` depuis le secret, et les artefacts depuis un **volume de données**
  monté en lecture seule (`PAC_ZARR_PATH`, `PAC_CHROMA_DIR`, `PAC_REPORT_PDF`).
- **Deployment `chat`** (Streamlit, port 8501) — l'UI, qui parle à l'API via
  `API_BASE_URL` (service interne).
- **Services** ClusterIP + **Ingress** (TLS Let's Encrypt) pour les deux hôtes.
- **Secret** (clé Mistral + credentials registre) et **PVC** des artefacts.

### 1. Construire et pousser l'image

```bash
cd backend && scripts/build-docker-image --tag v1 --push
# ou via le workflow GitHub Actions « CD » (workflow_dispatch).
```

### 2. Provisionner les artefacts sur le volume

Les fichiers source (xlsx) et les artefacts générés (`pac.zarr`, index Chroma) ne sont
**pas** dans l'image (volumineux / confidentiels). Générez-les puis copiez-les sur le PVC
`<release>-data` (monté sur `/data`), par exemple :

```bash
# Génération locale (cf. backend/README.md) :
cd backend && scripts/ingest-data && scripts/build-index

# Copie vers un pod montant le PVC (ou via un Job d'init) :
kubectl cp ../data/pac.zarr               <pod>:/data/pac.zarr
kubectl cp store/chroma                   <pod>:/data/chroma
kubectl cp ../docs/Performance-PAC-Rapport-final.pdf <pod>:/data/Performance-PAC-Rapport-final.pdf
```

### 3. Déployer

Copiez `chatbot/example.values.yaml` en `chatbot/values.yaml`, renseignez le registre,
la clé `MISTRAL_API_KEY` et les hôtes, puis :

```bash
helm upgrade --install 100pac helm/chatbot -f helm/chatbot/values.yaml
```

> Note : cette itération **prépare** le déploiement ; aucun `helm upgrade` n'est lancé
> automatiquement.

## Prerequisites

To develop within the `helm` directory, you will need:

- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [helm](https://helm.sh/docs/intro/install/)
- [docker](https://docs.docker.com/engine/install/)
- [k9s](https://k9scli.io/) - Optional, but handy!

## `KUBECONFIG` 

To interact with the `k8s` cluster in OVH, you will need a `KUBECONFIG` set up

You will be given a `kubeconfig.yaml` file, place it within `helm/` and then, in the same directory, run:

```bash
export KUBECONFIG=<full-path-to>/kubeconfig.yaml
```

You can confirm this works with:

```bash
kubectl get nodes
```

```bash
NAME                                      STATUS   ROLES    AGE     VERSION
dev-sprint-loic-houpert-np1-node-166f82   Ready    <none>   2m45s   v1.33.2
dev-sprint-loic-houpert-np1-node-bc9663   Ready    <none>   2m48s   v1.33.2
dev-sprint-loic-houpert-np1-node-fc5712   Ready    <none>   2m35s   v1.33.2
```

## Scripts To Rule Them All 💍

Within `scripts/` you will find:

- `scripts/diff` - Uses `helm diff` plugin to visualise what would change on your k8s cluster _if_ you applied a `helm upgrade`, with an optional `--tag` parameter (representing an image tag)
- `scripts/upgrade` - Uses `helm upgrade` to apply the contents of the `helm/chatbot` chart

## Helm

Within `chatbot/` you'll find the following: `templates/` which contains helm templates to create various k8s resources, `Chart.yaml` which defines the chatbot chart, and `example.values.yaml` which should be copied and renamed to `values.yaml`, with `MISTRAL_API_KEY` and the docker registry `password` values populated (we will give those to you)

# Cluster setup (In case it's not there)

## A cluster

You will require a cluster, this should be available, otherwise, shout!

## Ingress-Nginx Controller

The Ingress-NGINX Controller is a Kubernetes component that manages external access to services running inside a Kubernetes cluster. It’s essentially a reverse proxy and load balancer that uses NGINX under the hood to route HTTP(S) traffic. It does so by reading
`Ingress` resource definitions and routing to services accordingly.

The cluster will have this installed, but should it not be there, you can add it using:

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm -n ingress-nginx install ingress-nginx ingress-nginx/ingress-nginx --create-namespace
```

## Cert Manager

The Cert Manager enables us to use services like Lets Encrypt to generate and renew TLS certificates for our domains. (Allows you to use https://)

The cluster will have this installed, but should it not be there, you can add it using:

```bash
helm repo add jetstack https://charts.jetstack.io
helm repo update
helm install cert-manager jetstack/cert-manager \
--namespace cert-manager --create-namespace \
--version v1.18.2 \
--set crds.enabled=true
```

You can then configure Lets Encrypt by creating a file named `cluster-issuer.yaml` with the following contents:

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ciaran@developmentseed.org
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
```

And then run:

```bash
kubectl apply -f cluster-issuer.yaml
```
