# ORDER-03 F-0027 / D-0049. The UI is built HERE, from source, so a stale
# bundle is impossible rather than merely detectable. Before this, api/static/
# was committed and a deploy that forgot `npm run build` shipped the old
# interface against a new API with no signal of any kind.
#
# package.json and the lockfile are copied first so `npm ci` is cached on its
# own layer: a change to ui/src rebuilds the bundle without re-installing
# dependencies. `npm ci` rather than `npm install` - it installs exactly the
# lockfile, so the same commit produces the same bundle.
FROM node:22-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.11-slim as builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /root/.local /root/.local
COPY . .

# After `COPY . .`, so the built UI is what ends up being served. api/static/
# is also in .dockerignore, so nothing else can land here - the build output is
# the only source of this directory and there is no ordering subtlety to get
# wrong later.
COPY --from=ui /ui/dist/ /app/api/static/

ENV PATH=/root/.local/bin:$PATH PYTHONUNBUFFERED=1 PORT=8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 CMD python -c "import requests; r=requests.get('http://localhost:8000/api/health', timeout=5); raise SystemExit(0 if r.ok else 1)" || exit 1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
