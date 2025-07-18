import requests
from datetime import datetime, timezone
import pandas as pd
import time
import json  # Import json for parsing Gemini API response
from bs4 import BeautifulSoup  # Import BeautifulSoup for HTML parsing
import numpy as np  # Import numpy for handling NaN values
import urllib.parse  # Re-added: Needed for URL encoding in get_dynamic_build_id

# Gemini API key will be provided by the environment, so we leave it empty here.
# DO NOT hardcode your API key here.
GEMINI_API_KEY = ""  # User provided key, keeping it.
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# Constants for fee calculation
CATAWIKI_BROKERAGE_FEE_PERCENTAGE = 0.09  # 9%
FIXED_DELIVERY_FEE_EUR = 40.0  # Fixed delivery fee in EUR.


def get_dynamic_build_id(search_query=None):
    """
    Fetches the main Catawiki page (either category or search) to extract the dynamic build ID.
    """
    if search_query:
        # For search queries, the URL structure for getting the build ID is different
        # We need to URL-encode the search query for the initial page fetch
        encoded_query = urllib.parse.quote_plus(search_query)
        initial_url = f"https://www.catawiki.com/en/s?q={encoded_query}"
        print(f"Fetching search page to get dynamic build ID from: {initial_url}")
    else:
        # Default to the watches category page if no search query
        initial_url = "https://www.catawiki.com/en/c/333-watches"
        print(f"Fetching category page to get dynamic build ID from: {initial_url}")

    try:
        response = requests.get(initial_url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find the script tag with id="__NEXT_DATA__"
        next_data_script = soup.find('script', {'id': '__NEXT_DATA__'})

        if next_data_script:
            script_content = next_data_script.string
            data = json.loads(script_content)
            build_id = data.get("buildId")

            if build_id:
                print(f"Successfully extracted build ID: {build_id}")
                return build_id
            else:
                print("Error: 'buildId' not found in __NEXT_DATA__ script.")
                return None
        else:
            print("Error: __NEXT_DATA__ script tag not found on the page.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching initial page ({initial_url}): {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON from __NEXT_DATA__ script: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while getting dynamic build ID: {e}")
        return None


def fetch_page(page_num, build_id, search_query=None, sort_param="bidding_end_desc",
               filters_param="reserve_price%5B%5D=0&budget%5B%5D=-100"):
    """
    Fetches a single page of watch listings from Catawiki using the provided build_id,
    search query, sort, and filters.
    """
    # Determine the API path segment based on whether a search query is present
    if search_query:
        api_path_segment = "en/s.json"
    else:
        api_path_segment = "en/c/333-watches.json"  # Default category path

    base_api_url = f"https://www.catawiki.com/_next/data/{build_id}/{api_path_segment}"

    params = {
        "sort": sort_param,
        "filters": filters_param,
        "page": page_num
    }

    # Add search query parameter if provided
    if search_query:
        params["q"] = search_query
    else:
        # If no search query, ensure the category is set for the default path
        params["category"] = "333-watches"

    print(f"Fetching page {page_num} for query '{search_query if search_query else 'watches category'}'...")
    try:
        response = requests.get(base_api_url, params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()

        # The structure of the JSON response changes slightly for search results
        if search_query:
            lots = data["pageProps"]["searchLots"]["lots"]
            total_lots = data["pageProps"]["searchLots"]["total"]
        else:
            lots = data["pageProps"]["categoryLots"]["lots"]
            total_lots = data["pageProps"]["categoryLots"]["total"]

        return lots, total_lots
    except requests.exceptions.RequestException as e:
        print(f"Error fetching page {page_num} from {base_api_url} with params {params}: {e}")
        return [], 0
    except KeyError as e:
        print(
            f"Error parsing JSON response (missing key {e}). Response structure might have changed or no results for query. Response: {data}")
        return [], 0
    except Exception as e:
        print(f"An unexpected error occurred while fetching page: {e}")
        return [], 0


def format_time_remaining(bidding_end_ms):
    """
    Formats the remaining time until bidding ends.
    """
    now = datetime.now(timezone.utc)
    end_time = datetime.fromtimestamp(bidding_end_ms / 1000, tz=timezone.utc)
    delta = end_time - now
    if delta.total_seconds() <= 0:
        return "Ended"
    days = delta.days
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:  # Include hours if days exist, or if hours are positive
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def parse_lots_to_records(lots):
    """
    Parses raw lot data into a list of structured records.
    """
    records = []
    for lot in lots:
        buy_now = lot.get("buyNow")
        price_eur = buy_now.get("price_eur") if buy_now else None
        live = lot.get("live", {})
        highest_bid = live.get("bid", {}).get("EUR")
        bidding_end = live.get("biddingEndTime")
        time_remaining = format_time_remaining(bidding_end) if bidding_end else None

        record = {
            "ID": lot.get("id"),
            "Title": lot.get("title"),
            "Subtitle": lot.get("subtitle"),
            "Buy Now Price (EUR)": price_eur,
            "Highest Bid (EUR)": highest_bid,
            "Time Remaining": time_remaining,
            "Bidding Start": lot.get("biddingStartTime"),
            "URL": lot.get("url"),
            "Thumbnail": lot.get("thumbImageUrl")
        }
        records.append(record)
    return records


def get_market_estimate(title, buy_now_price, price_for_valuation):
    """
    Uses the Gemini API to get a market price estimate and valuation for a watch.
    The comparison is based on the provided price_for_valuation (total price).
    """
    prompt = (
        f"Estimate the current market price in EUR for the watch titled '{title}'. "
        f"The total estimated buyer's price (including bid, brokerage fees, and delivery) is {price_for_valuation if price_for_valuation is not None else 'N/A'} EUR. "
        f"The listed Buy Now price is {buy_now_price if buy_now_price is not None else 'N/A'} EUR. "
        "Provide a short price estimation as a number and state if the watch is 'overvalued', 'undervalued', or 'fairly valued' compared to this total estimated buyer's price. "
        "Format your response strictly as: 'Estimated market price: [NUMBER] EUR. Valuation: [VALUATION_STATUS].'"
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 60,
            "temperature": 0.7,
            "topP": 0.9,
            "topK": 40
        }
    }

    try:
        response = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload)
        )
        response.raise_for_status()

        result = response.json()

        if result.get("candidates") and result["candidates"][0].get("content") and result["candidates"][0][
            "content"].get("parts"):
            text = result["candidates"][0]["content"]["parts"][0]["text"].strip()

            est_price = None
            valuation = None

            import re
            price_match = re.search(r"Estimated market price:\s*(\d+(?:\.\d+)?)\s*EUR", text, re.IGNORECASE)
            if price_match:
                est_price = float(price_match.group(1))

            if "Valuation:" in text:
                valuation_match = re.search(r"Valuation:\s*(overvalued|undervalued|fairly valued)", text, re.IGNORECASE)
                if valuation_match:
                    valuation = valuation_match.group(1).lower()

            if est_price is None or valuation is None:
                print(f"Warning: Could not fully parse Gemini response: '{text}'")
                return text, None

            return est_price, valuation
        else:
            print(f"Gemini API response did not contain expected content structure: {result}")
            return None, None

    except requests.exceptions.RequestException as e:
        print(f"Error calling Gemini API: {e}")
        return None, None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from Gemini API response: {e}")
        return None, None
    except Exception as e:
        print(f"An unexpected error occurred during Gemini API call: {e}")
        return None, None


def main():
    """
    Main function to orchestrate fetching data, getting estimates, and displaying results.
    Configurable with direct parameters for search keyword, sort, filters, and lot limit.
    """
    # --- Configuration Parameters ---
    # Set your desired search keyword (e.g., "omega", "rolex", or None for general watches)
    search_keyword = "omega"  # Set to None for general watches category

    # Set your desired sort option
    # Options: "bidding_end_desc", "bidding_end_asc", "price_desc", "price_asc"
    sort_option = "bidding_end_desc"

    # Set your desired filters (URL-encoded format, combine with '&')
    filters_string = "reserve_price%5B%5D=0&budget%5B%5D=-500"

    # Set maximum number of lots to fetch
    # Set to a very high number (e.g., 999999) for a full scrape (be mindful of API rate limits!)
    max_lots = 5
    # --- End Configuration Parameters ---

    # Get the dynamic BUILD_ID based on the search query (or lack thereof)
    build_id = get_dynamic_build_id(search_query=search_keyword)
    if not build_id:
        print("Could not determine dynamic build ID. Exiting.")
        return

    all_records = []

    # Fetch first page to get total lots and lots per page
    first_page_lots, total_lots = fetch_page(1, build_id, search_keyword, sort_option, filters_string)
    if not first_page_lots:
        print("No lots found or error fetching the first page. Exiting.")
        return

    lots_per_page = len(first_page_lots)
    total_pages = (total_lots + lots_per_page - 1) // lots_per_page if lots_per_page > 0 else 0

    print(f"Total lots available: {total_lots}, Lots per page: {lots_per_page}, Estimated total pages: {total_pages}")

    # Add first page lots
    records = parse_lots_to_records(first_page_lots)
    all_records.extend(records)

    # Fetch subsequent pages until max_lots reached or no more pages
    for page_num in range(2, total_pages + 1):
        if len(all_records) >= max_lots:
            break
        lots, _ = fetch_page(page_num, build_id, search_keyword, sort_option, filters_string)
        if not lots:
            break
        records = parse_lots_to_records(lots)
        all_records.extend(records)

    # Trim to max_lots if overfetched
    all_records = all_records[:max_lots]

    # Initialize lists for estimates and valuations
    estimates = []
    valuations = []

    print(f"\nProcessing {len(all_records)} lots for market estimates and valuations...")
    for i, rec in enumerate(all_records):
        print(f"Getting estimate for lot {i + 1}/{len(all_records)}: '{rec['Title']}'")

        # Calculate fees and final price for the current record before calling Gemini
        highest_bid_val = rec["Highest Bid (EUR)"] if rec["Highest Bid (EUR)"] is not None else 0
        catawiki_fee_val = highest_bid_val * CATAWIKI_BROKERAGE_FEE_PERCENTAGE

        final_price_for_valuation = highest_bid_val + catawiki_fee_val + FIXED_DELIVERY_FEE_EUR

        est_price, valuation = get_market_estimate(
            rec["Title"],
            rec["Buy Now Price (EUR)"],
            final_price_for_valuation  # Pass the calculated final price for valuation
        )
        estimates.append(est_price)
        valuations.append(valuation)
        # Be kind to API rate limits and avoid hitting rate limits quickly
        time.sleep(1.5)

    df = pd.DataFrame(all_records)
    df["Market Price Estimate (EUR)"] = estimates

    # --- Calculations for Fees and Final Price ---
    df["Catawiki Fee (EUR)"] = df["Highest Bid (EUR)"].fillna(0) * CATAWIKI_BROKERAGE_FEE_PERCENTAGE
    df["Delivery Fee (EUR)"] = FIXED_DELIVERY_FEE_EUR
    df["Final Price (EUR)"] = df["Highest Bid (EUR)"].fillna(0) + df["Catawiki Fee (EUR)"] + df["Delivery Fee (EUR)"]

    # Calculate Ratio of Final Price vs. Market Estimate
    df["Final Price vs. Market Est. Ratio"] = np.nan  # Initialize with NaN
    valid_estimates_mask = (df["Market Price Estimate (EUR)"].notna()) & (df["Market Price Estimate (EUR)"] != 0)

    df.loc[valid_estimates_mask, "Final Price vs. Market Est. Ratio"] = (
            df["Final Price (EUR)"] / df["Market Price Estimate (EUR)"]
    )

    # Add the valuation column
    df["Valuation"] = valuations

    # --- Explicitly define the column order ---
    final_columns_order = [
        "ID",
        "Title",
        "Subtitle",
        "URL",
        "Thumbnail",
        "Time Remaining",
        "Bidding Start",
        "Buy Now Price (EUR)",
        "Highest Bid (EUR)",
        "Catawiki Fee (EUR)",
        "Delivery Fee (EUR)",
        "Final Price (EUR)",
        "Market Price Estimate (EUR)",
        "Final Price vs. Market Est. Ratio",
        "Valuation"
    ]
    df = df[final_columns_order]

    print("\n--- All Results ---")
    print(df.to_string())

    # Save to CSV:
    df.to_csv("catawiki_watches_with_gemini_valuation.csv", index=False)
    print("\nData saved to catawiki_watches_with_gemini_valuation.csv")

    # Save to JSON:
    df.to_json("catawiki_watches_with_gemini_valuation.json", orient="records", indent=4)
    print("Data saved to catawiki_watches_with_gemini_valuation.json")


if __name__ == "__main__":
    main()
