FROM node:20-slim

# Install Python for the AI engine
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Node deps
COPY package*.json ./
RUN npm install --production

# Copy project
COPY . .

# Ensure python3 is used
ENV PYTHON=python3

CMD ["npm", "start"]
"