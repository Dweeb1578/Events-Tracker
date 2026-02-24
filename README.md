# Event Detection System

A multi-agent AI pipeline designed to automatically monitor competitor and industry companies to detect upcoming events they are organizing or attending.

## Overview

The Zenskar Event Detection System periodically scrapes target company websites and their LinkedIn pages to find event announcements, webinars, and conferences. It utilizes Large Language Models (LLMs) to intelligently parse unstructured text, extract key event details (Name, Date, URL, Description), and assign a relevance score so you only see high-quality signals.

The system outputs the detected events into a formatted Excel file, with separate sheets for events sourced from websites and events sourced from LinkedIn.

## Features

- **Multi-Source Scraping**: Monitors dedicated event pages (e.g., `stripe.com/events`) and recent LinkedIn posts (via Apify) for event announcements.
- **LLM-Powered Classification**: Uses Groq and Google GenAI to understand messy scraped data, identify actual events, and extract their details.
- **Relevance Scoring**: Automatically scores events (1-10) to filter out noise and highlight highly relevant events.
- **Automated Scheduling**: Run the pipeline on a daily or weekly schedule.
- **Formatted Excel Export**: Generates timestamped Excel reports with dedicated sheets for Web and LinkedIn events.
- **Caching**: Supports caching scraped data for faster LLM prompt testing and reduced API costs.

## Prerequisites

- Python 3.8+
- [Apify](https://apify.com/) API Token (for LinkedIn scraping)
- [Groq](https://groq.com/) API Key (for fast LLM inference)
- [Google GenAI / Gemini](https://ai.google.dev/) API Key (alternative LLM fallback/processing)

## Installation

1. Clone the repository or navigate to the project directory.
2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv .venv
   
   # Windows
   .venv\Scripts\activate
   
   # macOS/Linux
   source .venv/bin/activate
   ```
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Playwright browsers installation (required for web scraping):
   ```bash
   playwright install
   ```

## Configuration

1. Create a `.env` file in the root directory by copying the example:
   ```bash
   cp .env.example .env
   ```
2. Fill in your API keys in the `.env` file:
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   GROQ_API_KEY=your_groq_api_key_here
   APIFY_API_TOKEN=your_apify_api_token_here
   ```
3. Edit `config/companies.yaml` to configure the list of companies, event pages, and LinkedIn URLs you want to monitor.

## Usage

The main entry point for the pipeline is `main.py`.

### Run Once Immediately

```bash
python main.py
```

### Run on a Schedule

Run daily at 9:00 AM:
```bash
python main.py --schedule daily --time "09:00"
```

Run weekly on Mondays at 9:00 AM:
```bash
python main.py --schedule weekly --time "09:00"
```

### Filtering Events

Only include events with a relevance score of 7 or higher:
```bash
python main.py --min-relevance 7
```

### Skipping Specific Steps

Preview the detected events without writing to an Excel file:
```bash
python main.py --dry-run
```

Skip LinkedIn scraping (useful if you don't have an Apify token set up):
```bash
python main.py --skip-linkedin
```

Skip live scraping and use previously collected data (useful for testing LLM extraction prompts quickly without hitting websites again):
```bash
python main.py --use-cache
```

## Output

After a successful run, the system will generate an Excel file in the `output/` directory named with the current date and time (e.g., `events_20260224_232000.xlsx`). 

The Excel file contains two sheets:
- **Events**: Events detected from the companies' website URLs.
- **LinkedIn Events**: Events extracted from the companies' recent LinkedIn posts.
