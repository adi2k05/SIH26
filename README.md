# SIH26 - MoSPI AirfareX Data Pipeline

A Python-based data pipeline for aggregating and analyzing airline fare data from multiple sources. This project implements web scraping for multiple airline booking platforms and stores the data in a SQLite database for indexing and analysis.

## 📋 Overview

SIH26 is designed to collect real-time airline fare information from multiple sources including:
- **EMT** (via scraper_emt.py)
- **Yatra** (via scraper_yatra.py)
- **SpiceJet** (via scraper_spicejet.py)
- **Akasa** (via scraper_akasa.py)
- **CMT** (via scraper_cmt.py)

The pipeline runs daily data collection cycles with multiple recovery passes to ensure comprehensive data coverage across all routes.

## ✨ Features

- **Multi-Source Aggregation**: Scrapes airline fare data from 5 different booking platforms
- **Intelligent Data Collection**: Three-pass system (Primary Extraction + 2 Recovery Sweeps) to capture missing data
- **SQLite Database**: Persistent storage with `airfare_index.db` for historical tracking
- **IST Timezone Support**: Automatically handles Indian Standard Time (IST) calculations
- **Smart Checkpointing**: Avoids redundant scraping with checkpoint system
- **Interactive Mode**: User prompts for force re-scrape, exit, or gap-filling options
- **Error Handling**: Robust error recovery with pass-based retry mechanism

## 🛠️ Technical Stack

- **Language**: Python 3
- **Database**: SQLite3
- **API Framework**: FastAPI
- **Web Server**: Uvicorn
- **Timezone Handling**: Python datetime with timedelta

## 📦 Installation

### Prerequisites
- Python 3.7+
- pip package manager

### Setup

1. Clone the repository:
```bash
git clone https://github.com/adi2k05/SIH26.git
cd SIH26
