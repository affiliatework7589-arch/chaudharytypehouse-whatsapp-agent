FROM node:20-slim

# --- Python 3 for the AI engine (core/ai_engine.py) -------------------------
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Node dependencies (Baileys + QR) --------------------------------------
COPY package*.json ./
RUN npm install --omit=dev

# --- Python dependencies (bridge only) --------------------------------------
COPY requirements-bridge.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements-bridge.txt

# --- Project files ----------------------------------------------------------
COPY . .

# --- Runtime config ---------------------------------------------------------
ENV PYTHON=python3 \
    WA_AUTH_DIR=/app/auth_info_baileys \
    PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=production

# Session folder lives on the persistent disk (see render.yaml).
RUN mkdir -p /app/auth_info_baileys

CMD ["npm", "start"]
