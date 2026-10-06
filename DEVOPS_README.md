# DevOps & Cloud Deployment Guide

Pipeline: `git push` → GitHub Actions (test → build Docker images → push to GHCR) → self-hosted runner on your Ubuntu desktop → k3s Kubernetes → live app.

**Everything is free and open source:** Git/GitHub (free plan), GitHub Actions, GitHub Container Registry (ghcr.io), Docker, k3s (Kubernetes), kubectl, Nginx, MySQL.

## Why a self-hosted runner?
GitHub's cloud runners cannot reach a Kubernetes cluster on your home/college desktop (it sits behind a router). So the **test and build jobs run on GitHub's free cloud runners**, and only the **deploy job runs on a runner installed on your own Ubuntu desktop**, right next to the cluster. That's what lets "push → live" work with zero paid services.

```
git push ─► GitHub Actions
             ├─ test-backend  (pytest)         [GitHub cloud]
             ├─ test-frontend (vite build)     [GitHub cloud]
             ├─ build-push    (Docker → ghcr)  [GitHub cloud]
             └─ deploy        (kubectl)        [your Ubuntu desktop]
                                  └─► k3s: frontend pods ─► backend pods ─► mysql pod
```

---

## Step 0 – Install tools on Ubuntu desktop (one time)

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 git curl
sudo usermod -aG docker $USER && newgrp docker      # run docker without sudo
sudo snap install kubectl --classic
```

Install **k3s** (lightweight, production-grade Kubernetes) and give your user access:

```bash
curl -sfL https://get.k3s.io | sh -
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $USER:$USER ~/.kube/config
kubectl get nodes          # should show 1 node in Ready state
```

## Step 1 – Run locally with Docker first (sanity check)

```bash
docker compose up --build
```
Open http://localhost:8080 (admin: `admin@grocery.com` / `admin123`). Stop with `Ctrl+C`, then `docker compose down`.

## Step 2 – Push the project to GitHub

1. Create a new **public** repository on github.com (e.g. `grocery-store`), no README.
2. In the project folder:
```bash
git init -b main
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<your-username>/grocery-store.git
git push -u origin main
```
(Use a Personal Access Token as the password, or `gh auth login`.)

The first push starts the pipeline. `test` and `build-push` will pass; `deploy` will wait because no runner exists yet. That's expected.

## Step 3 – Install the self-hosted runner (on your Ubuntu desktop)

1. GitHub repo → **Settings → Actions → Runners → New self-hosted runner → Linux x64**.
2. Copy and run the commands GitHub shows (download, extract, `./config.sh --url ... --token ...`). Press Enter for defaults.
3. Install it as a background service so it survives reboots:
```bash
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status
```
The runner shows **Idle** (green) on the Runners page. It uses `~/.kube/config` from Step 0.

## Step 4 – Make the images public (one time)

GHCR packages are private by default; k3s needs to pull them.
GitHub profile → **Packages** → open `grocery-backend` → **Package settings → Change visibility → Public**. Repeat for `grocery-frontend`.

Then re-run the pipeline: repo → **Actions → CI-CD → Re-run all jobs** (or push any small change).

## Step 5 – Verify the deployment

```bash
kubectl -n grocery get pods          # 2 backend, 2 frontend, 1 mysql – all Running
kubectl -n grocery get svc
kubectl -n grocery logs deploy/backend
```
Open **http://localhost:30080**. 🎉

From now on every `git push` to `main` redeploys automatically.

---

## What each file does

| File | Purpose |
|---|---|
| `backend/Dockerfile`, `frontend/Dockerfile` | Build the container images (frontend is multi-stage: Node build → Nginx) |
| `docker-compose.yml` | Local run for development |
| `.github/workflows/ci-cd.yml` | The CI/CD pipeline |
| `k8s/00-namespace.yaml` | `grocery` namespace |
| `k8s/01-config.yaml` | **ConfigMap** (DB host/name/user) and **Secret** (passwords, JWT key) |
| `k8s/02-mysql.yaml` | MySQL Deployment + PersistentVolumeClaim + Service |
| `k8s/03-backend.yaml` | Flask Deployment (2 pods), Service, HorizontalPodAutoscaler, health probes |
| `k8s/04-frontend.yaml` | React/Nginx Deployment (2 pods) + NodePort Service (30080) |

---

## Hackathon live demo script

**1. Pods, Deployments, Services**
```bash
kubectl -n grocery get deploy,pods,svc -o wide
```

**2. Scaling**
```bash
kubectl -n grocery scale deployment backend --replicas=4
kubectl -n grocery get pods -w
kubectl -n grocery scale deployment backend --replicas=2
```
Auto-scaling is also configured: `kubectl -n grocery get hpa` (2 to 5 pods at 70% CPU).

**3. Self-healing** – delete a pod, Kubernetes recreates it instantly:
```bash
kubectl -n grocery delete pod -l app=backend --wait=false
kubectl -n grocery get pods -w
```
The website keeps working because the other pod serves traffic.

**4. Rolling update via CI/CD (the main demo)**
Change something visible (e.g. the heading in `frontend/src/App.jsx`), then:
```bash
git add . && git commit -m "Change heading" && git push
kubectl -n grocery rollout status deployment/frontend
kubectl -n grocery rollout history deployment/frontend
```
Show the Actions tab turning green: Test → Build → Push → Deploy. Refresh the browser to see the new version with zero downtime (`maxUnavailable: 0`).

**5. Rollback**
```bash
kubectl -n grocery rollout undo deployment/frontend
```

**6. ConfigMap and Secret**
```bash
kubectl -n grocery get configmap grocery-config -o yaml
kubectl -n grocery get secret grocery-secret -o yaml    # values are base64 encoded
```

**7. Service discovery** – the frontend reaches Flask at `http://backend:5000`, and Flask reaches MySQL at `mysql:3306`, using only Kubernetes DNS names.

**8. Data survives restarts** (PersistentVolume)
```bash
kubectl -n grocery delete pod -l app=mysql
# wait for it to restart, then log in again: products and orders are still there
```

---

## Optional: free public URL for the demo

Judges can't open `localhost`. Use a free Cloudflare quick tunnel (no account needed):
```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o cf.deb
sudo dpkg -i cf.deb
cloudflared tunnel --url http://localhost:30080
```
It prints a `https://....trycloudflare.com` link. Keep the terminal open during the demo.

## Optional: "real cloud server" version (still free)

Oracle Cloud "Always Free" gives a permanent free Ubuntu VM. Install Docker + k3s there with the same Step 0 commands, install the self-hosted runner on that VM (Step 3), and the pipeline works unchanged. Open port 30080 in the VM's security list. (Signup needs a card for identity verification; it is not charged on Always Free resources.)

## Troubleshooting

| Problem | Fix |
|---|---|
| Pods in `ImagePullBackOff` | Make both GHCR packages **public** (Step 4); check `kubectl -n grocery describe pod <name>` |
| Deploy job stays "Waiting for a runner" | `sudo ./svc.sh status` in the runner folder; the runner must be Idle/online |
| `kubectl: connection refused` in the deploy job | Re-do the `~/.kube/config` copy from Step 0 (as the same user the runner runs as) |
| Backend pod restarts a few times at first | Normal: it waits for MySQL to be ready (retries up to ~2 minutes) |
| MySQL pod `Pending` | `kubectl -n grocery describe pvc mysql-pvc` (k3s ships a default `local-path` storage class) |
| Check app errors | `kubectl -n grocery logs deploy/backend` |

## Cleanup
```bash
kubectl delete namespace grocery
/usr/local/bin/k3s-uninstall.sh      # removes k3s entirely
```

## Security notes (mention to judges)
`k8s/01-config.yaml` holds demo passwords for convenience. In production, create secrets with `kubectl create secret` (or use Sealed Secrets) and never commit them; also change the default admin password and `JWT_SECRET`.
