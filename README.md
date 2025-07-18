# Catawiki Price Analyzer

This project is a tool for watch enthusiasts to analyze watch prices on Catawiki. It is intended for personal, non-commercial use.

## Description

This script scrapes watch auction data from Catawiki, analyzes it using the Gemini API, and provides insights into pricing trends. It's a fun project for anyone interested in watches and data analysis.

## Features

*   Scrapes watch data from Catawiki.
*   Analyzes prices using the Gemini API.
*   Allows customization of scraping parameters, including filter sorting and lot limits.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/catawiki_price_analyzer.git
    cd catawiki_price_analyzer
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Set up your Gemini API Key:**
    You will need to obtain a Gemini API key from Google AI Studio. Once you have your key, create a `.env` file in the root of the project and add your key like this:

    ```
    GEMINI_API_KEY="your_api_key_here"
    ```

## Usage

To run the script, execute the `main.py` file:

```bash
python main.py
```

### Customization

You can customize the scraping process by modifying the following parameters in `main.py`:

*   **Filter Sorting:** Change the `sort` parameter to control the order of the scraped lots.
*   **Lot Limit:** Adjust the `limit` parameter to change the number of lots to scrape. To perform a full scrape of all available lots, set this to a very high number.

## Disclaimer

*   This tool is not intended for commercial use.
*   The Gemini API has a free tier with rate limits. Be mindful of the number of requests you make to avoid being rate-limited. For more information, see the Gemini API documentation.
