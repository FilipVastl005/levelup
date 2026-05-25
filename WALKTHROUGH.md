# Eggman Studio - Multi-App Architecture Walkthrough

This document explains how to set up and deploy the Eggman Studio ecosystem, which includes the **LevelUp** app and the **Víte, co jíte? (Food App)**, all under a single domain with shared authentication.

## 1. Architecture Overview

The system consists of three main web applications and one background service:

- **Home App (`home_app`)**: The main landing page (`/`), handling global login, signup, and app switching.
- **LevelUp App (`levelup_app`)**: The existing gamified life-tracker, now mounted at `/levelup`.
- **Food App (`food_app`)**: The new product transparency platform, mounted at `/food`.
- **Food Scraper (`food_scraper`)**: A background service that classifies products using AI and scrapes supermarket data.
- **Nginx**: A reverse proxy that routes traffic based on the URL path and handles SSL (HTTPS).
- **Ollama**: Provides the AI engine (LLaVA) for log verification and product classification.

All apps share a single SQLite database (`/mnt/storage/levelup.db`) for users, sessions, and product data.

## 2. Prerequisites

- A Linux server (e.g., your T530).
- Docker and Docker Compose installed.
- A domain name (e.g., `home.eggmanstudio.me`) pointing to your server's IP.
- Ports 80 and 443 open in your firewall.

## 3. Initial Setup

### Step A: Environment Variables
Create a `.env` file in the project root:
```bash
SECRET_KEY=your_very_secret_key
ADMIN_PASSWORD=your_admin_password
DB_PATH=/mnt/storage/levelup.db
QUEUE_PATH=/mnt/storage/queue
```

### Step B: Directories
Ensure the storage directories exist:
```bash
sudo mkdir -p /mnt/storage/queue/{pending,processing,completed,failed,screenshots}
sudo mkdir -p /mnt/storage/ollama
sudo chown -R $USER:$USER /mnt/storage
```

## 4. Deployment

Start the entire stack using Docker Compose:
```bash
docker compose up -d --build
```

This will start:
1. `aura_home` (Port 3000 internally)
2. `aura_levelup` (Port 3000 internally)
3. `aura_food` (Port 3000 internally)
4. `aura_food_scraper` (Background)
5. `aura_nginx` (Ports 80 & 443)
6. `levelup_ollama` (Port 11434 internally)

## 5. HTTPS Setup (Free via Let's Encrypt)

We use Nginx with Certbot for automated HTTPS.

### Step A: Initial Certificate Request
Run the following command (replace with your email and domain):
```bash
docker run -it --rm --name certbot \
  -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
  -v "$(pwd)/certbot/www:/var/www/certbot" \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d home.eggmanstudio.me --email your-email@example.com --agree-tos --no-eff-email
```

### Step B: Update Nginx for HTTPS
Once you have the certificates, update `nginx/default.conf` to use them:

```nginx
server {
    listen 80;
    server_name home.eggmanstudio.me;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl;
    server_name home.eggmanstudio.me;

    ssl_certificate /etc/letsencrypt/live/home.eggmanstudio.me/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/home.eggmanstudio.me/privkey.pem;

    location / {
        proxy_pass http://home_app:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /levelup {
        proxy_pass http://levelup_app:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /food {
        proxy_pass http://food_app:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Then restart Nginx: `docker compose restart nginx`.

## 6. How the Food App Logic Works

1. **Scanning**: User scans a barcode (EAN) using the browser camera.
2. **Lookup**:
   - The app first checks the **Local SQLite Database**.
   - If not found, it queries **Open Food Facts (OFF)** API.
   - If found in OFF, it caches the result locally.
3. **Scraping**: If a product is missing, the `food_scraper` (background) is designed to eventually pick up these missing items by scraping Rohlik.cz and Tesco CZ.
4. **AI Classification**: Every night, the `food_scraper` runs a job that takes all "pending" products and uses AI (via Ollama/LLaVA) to classify them as:
   - **Real Food**: Minimal ingredients, natural.
   - **Obelisk of Food**: Processed but still recognizable as food.
   - **Chemical Paste**: Highly processed, lots of additives.

## 7. Admin Panel

- **LevelUp Admin**: Still available at `home.eggmanstudio.me/levelup/admin`.
- **Food App Admin**: (Future) Will allow manual override of AI classifications.

---
**Enjoy your new Eggman Studio Ecosystem!**
