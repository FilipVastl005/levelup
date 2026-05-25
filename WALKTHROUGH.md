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

## 5. Cloudflare Tunnel Setup

Since you are using **Cloudflare Tunnel**, you don't need to worry about Port 80/443 or Certbot.

1.  In your Cloudflare Dashboard, point your tunnel for `home.eggmanstudio.me` to `http://localhost:80` (the Nginx container).
2.  Nginx will handle the internal routing to the correct apps.
3.  FastAPI is already configured with `ProxyHeadersMiddleware` to handle HTTPS detection from Cloudflare.

---

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
