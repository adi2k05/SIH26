# SIH26 - MoSPI AirfareX Data Pipeline

An enterprise-grade, Python-based data pipeline and analytics engine for aggregating airline fare data across multiple Indian OTAs and direct carrier platforms. Developed for the Smart India Hackathon (SIH26), this project implements high-stealth web scraping to bypass advanced WAFs (Web Application Firewalls) and stores the data in a unified SQLite architecture for macroeconomic price indexing and machine learning analysis.

### API DASHBOARD : https://airfarex-api.onrender.com/

## 📋 Overview

AirfareX is designed to collect, clean, and index real-time airline fare information to track market inflation, establish route price floors, and monitor platform pricing parity. The pipeline currently supports high-density Indian domestic corridors (e.g., DEL-BOM, BLR-DEL) with predictive scraping up to T+45 days in advance.

**Supported Platforms:**

- **MakeMyTrip (MMT)** (`scraper_mmt.py`)

- **Goibibo** (`scraper_goibibo.py`)

- **Indigo** (`scraper_indigo.py`)

- **Air India Express** (`scraper_airindia_express.py`)

- **Akasa Air** (`scraper_akasa.py`)

- **Air India** (`scraper_airinda.py`)

- **EaseMyTrip (EMT)** (`scraper_emt.py`)

- **Yatra** (`scraper_yatra.py`)

- **SpiceJet** (`scraper_spicejet.py`)

- **ClearTrip (CT)** (`scraper_ct.py`)

- **Ixigo** (`scraper_ixigo.py`)

## ✨ Key Features

- **Enterprise-Grade WAF Bypass (Akamai/DataDome):** Utilizes `patchright` (Chromium) and `undetected_chromedriver` to mask TLS signatures. Implements humanized mouse trajectory simulations, randomized intercept clicks during skeleton loading phases, CDP (Chrome DevTools Protocol) session purging, and hard-process hardware shedding to bypass stringent rate limits ("Take a Break" blocks).

- **Robust DOM Extraction:** Adapts to heavily obfuscated DOM class names (e.g., Goibibo) using regex-based text block parsing and fallback extraction layers to ensure zero data loss.

- **Intelligent Data Collection:** Employs a multi-tier execution strategy—Primary Extraction, Fallback Single-Reloads, and full Hard Resets—managed through a checkpoint system to avoid redundant scraping.

- **Advanced Analytics API (FastAPI):** Features a highly interactive, animated developer dashboard with dedicated analytical endpoints designed for direct Pandas/scikit-learn ingestion.

- **Unified SQLite Architecture:** Persistent storage using `airfare_index.db` with dynamic `UNION ALL` queries across archived historical databases for seamless time-series querying.

- **Timezone & Hardware Management:** Automatically aligns timestamps to Indian Standard Time (IST) and explicitly manages browser hardware footprints to prevent permanent ISP/IP bans.

## 🛠️ Technical Stack

- **Language:** Python 3.10+

- **Automation Engines:** Playwright (via Patchright), Selenium (undetected-chromedriver)

- **Database:** SQLite3

- **API Framework:** FastAPI, Uvicorn

- **Data Serialization:** JSON, CSV Export natively supported via API

## 📦 Installation & Setup

### Prerequisites

- Python 3.10 or higher

- Google Chrome installed locally

- pip package manager

### Setup

1. **Clone the repository:**

```
git clone https://github.com/adi2k05/SIH26.git
cd SIH26

```

2. **Install dependencies:**

```
pip install -r requirements.txt
playwright install chromium
patchright install chromium
```

3. **Run the Scraping Pipeline:**

```
python AUTOMATED_PIPELINE.py

```

_(You can also run individual scrapers like `python scraper_goibibo.py`)_

4. **Launch the Analytics API & Dashboard:**

```
uvicorn api_service:app --reload --host 0.0.0.0 --port 8000

```

_Navigate to `http://localhost:8000` to view the interactive API dashboard._

## 📊 API Endpoints

The API is structured to power the SIH dashboard visualizations and ML models:

- **`GET /api/fares/raw`**: Retrieves flat, unaggregated ticket price records with limit/offset pagination. Used for feeding raw data into ML pricing models.

- **`GET /api/fares/compare`**: The Platform Rivalry endpoint. Identifies pricing parity by returning the absolute lowest fare, average price tier, and flight inventory counts strictly grouped by OTA/Airline for a requested route and window.

- **`GET /api/fares/matrix`**: The Advance Booking Curve endpoint. Builds a 2D macroeconomic pricing grid, determining the "price floor" (minimum available fare) and market averages across all routes and advance booking windows over the last 24 hours.

- **`GET /api/fares/export/csv`**: Generates a clean, flat CSV file of the raw indexing data for offline analysis.
