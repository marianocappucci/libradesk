# syntax=docker/dockerfile:1

# Stage separado para el frontend (React+Vite, mismo patron que
# Gestiolibra/MedLibra/VentaLibra, ver ADR-019 de Gestiolibra): node no
# hace falta en la imagen final, solo el resultado del build
# (frontend/dist). frontend/package.json referencia libra-ui via
# git+https (funciona tambien en dev local sin identidad SSH propia); el
# build real usa su propia deploy key de solo lectura
# (id_ed25519_libra_ui en el VPS, ya existente — compartida por el resto
# de la familia).
FROM node:20-slim AS frontend-build
WORKDIR /frontend
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client && rm -rf /var/lib/apt/lists/*
RUN mkdir -p -m 0700 /root/.ssh && ssh-keyscan github.com >> /root/.ssh/known_hosts 2>/dev/null
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=ssh,id=libra-ui,target=/tmp/ssh-libra-ui.sock \
    SSH_AUTH_SOCK=/tmp/ssh-libra-ui.sock \
    sh -c 'git config --global url."ssh://git@github.com/marianocappucci/libra-ui.git".insteadOf "https://github.com/marianocappucci/libra-ui.git" && \
           npm ci'
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends openssl git openssh-client && rm -rf /var/lib/apt/lists/*

# pyproject.toml referencia libraauth, libracore y libragenda via git+https
# (dev local sin identidad SSH propia funciona igual); el build real reescribe
# esas URLs a git+ssh, cada una con su propia deploy key de solo lectura
# (id_ed25519_libraauth / id_ed25519_libracore / id_ed25519_libragenda en el
# VPS, las tres ya existentes). Mismo patron IdentityFile+IdentityAgent que
# Gestiolibra/MedLibra/VentaLibra — necesario para que ssh sepa que
# fingerprint pedirle al agente del mount puntual, no el agente default
# del host.
#
# `pip install .` resuelve LAS TRES en un solo comando, asi que no alcanza un
# SSH_AUTH_SOCK global (apunta a un socket a la vez): cada dependencia
# necesita su propio alias de Host. El `IdentityFile` apunta a la clave
# PUBLICA (no es secreta, se hornea) solo para que ssh sepa que
# fingerprint pedirle a ese agente; sin el, ssh ofrece los paths default
# (id_rsa/...) que no existen en la imagen y nunca consulta al agente.
#
# 🔴 libragenda entro el 2026-08-04 con la fase B del pedido 42, y el pin se
# agrego SIN tocar este archivo: el CI de GitHub Actions quedo cableado pero el
# build del VPS no, asi que el primer `docker compose build` posterior al merge
# fallo clonando libragenda. Regla: **una dependencia privada nueva se cablea en
# los DOS lados** —`.github/workflows/ci.yml` y este Dockerfile mas el `ssh:` de
# docker-compose.yml— o el deploy se entera antes que nadie.
RUN mkdir -p -m 0700 /root/.ssh \
    && ssh-keyscan github.com >> /root/.ssh/known_hosts 2>/dev/null \
    && printf 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAID0FOGgyaywQLO6J583j9+MG71a13oNpXoxOAAcV9Cbp vps-donweb-libraauth-deploy-readonly\n' > /root/.ssh/id_libraauth.pub \
    && printf 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIG7oB3H2Rd+xsO/qCUk5aCA14/5GaQFMSh1U0ErJjG55 vps-donweb-libracore-deploy-key\n' > /root/.ssh/id_libracore.pub \
    && printf 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIG4hVY2CmSWj0Na3K8DeryjTDM6URpN8Wj4htLaiLK+L deploy-key-libragenda-readonly\n' > /root/.ssh/id_libragenda.pub \
    && printf 'Host github-libraauth\n  HostName github.com\n  User git\n  HostKeyAlias github.com\n  IdentityFile /root/.ssh/id_libraauth.pub\n  IdentityAgent /tmp/ssh-libraauth.sock\n  IdentitiesOnly yes\n\nHost github-libracore\n  HostName github.com\n  User git\n  HostKeyAlias github.com\n  IdentityFile /root/.ssh/id_libracore.pub\n  IdentityAgent /tmp/ssh-libracore.sock\n  IdentitiesOnly yes\n\nHost github-libragenda\n  HostName github.com\n  User git\n  HostKeyAlias github.com\n  IdentityFile /root/.ssh/id_libragenda.pub\n  IdentityAgent /tmp/ssh-libragenda.sock\n  IdentitiesOnly yes\n' > /root/.ssh/config \
    && chmod 600 /root/.ssh/config /root/.ssh/id_libraauth.pub /root/.ssh/id_libracore.pub /root/.ssh/id_libragenda.pub

COPY . .
# Horneado FUERA de /app a proposito (mismo motivo que el resto de la
# familia, ver ADR-022 de Gestiolibra): el docker-compose.yml de dev
# monta ./:/app entero para el --reload de Python, lo que taparia
# cualquier build copiado dentro de /app con el checkout del host.
COPY --from=frontend-build /frontend/dist /opt/frontend-dist
RUN --mount=type=ssh,id=libraauth,target=/tmp/ssh-libraauth.sock \
    --mount=type=ssh,id=libracore,target=/tmp/ssh-libracore.sock \
    --mount=type=ssh,id=libragenda,target=/tmp/ssh-libragenda.sock \
    for r in libraauth libracore libragenda; do \
      ssh -T -o StrictHostKeyChecking=no "git@github-$r" 2>&1 | grep -q "Hi marianocappucci/$r!" \
        || { echo "ERROR: la deploy key de $r no saluda a ese repo"; exit 1; }; \
    done \
    && git config --global url."ssh://git@github-libraauth/marianocappucci/libraauth.git".insteadOf "https://github.com/marianocappucci/libraauth.git" \
    && git config --global url."ssh://git@github-libracore/marianocappucci/libracore.git".insteadOf "https://github.com/marianocappucci/libracore.git" \
    && git config --global url."ssh://git@github-libragenda/marianocappucci/libragenda.git".insteadOf "https://github.com/marianocappucci/libragenda.git" \
    && pip install --no-cache-dir . \
    && git config --global --unset url."ssh://git@github-libraauth/marianocappucci/libraauth.git".insteadOf \
    && git config --global --unset url."ssh://git@github-libracore/marianocappucci/libracore.git".insteadOf \
    && git config --global --unset url."ssh://git@github-libragenda/marianocappucci/libragenda.git".insteadOf

EXPOSE 8000

CMD ["uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
