import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import re
from io import StringIO


# Common headers for all requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Referer": "https://www.google.com/"
}


# =========================================================
# 1️⃣ OKDIARIO HEADLINES
# =========================================================

def scrape_okdiario_headlines(limit=5):
    url = "https://okdiario.com"
    response = requests.get(url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")

    headlines = [
        h.get_text(strip=True)
        for h in soup.find_all(["h1", "h2"])
    ][:limit]

    return headlines


# =========================================================
# 2️⃣ ENERGY PRICES
# =========================================================

def scrape_energy_prices():
    url = "https://www.energyprices.eu/"
    response = requests.get(url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table")

    data = []
    if table:
        for row in table.find_all("tr")[1:]:
            cols = row.find_all("td")
            if len(cols) < 4:
                continue

            data.append({
                "Region": cols[0].get_text(strip=True),
                "Change %": cols[1].get_text(strip=True),
                "Avg Price": cols[2].get_text(strip=True),
                "High": cols[3].get_text(strip=True),
                "Low": cols[4].get_text(strip=True) if len(cols) > 4 else ""
            })
    else:
        print("Warning: Energy prices table not found.")

    return pd.DataFrame(data)


# =========================================================
# 3️⃣ EU MARKET CAP (WITH GROWTH + FORMAT)
# =========================================================

def format_market_cap(value):
    try:
        value = float(value)
        if value >= 1_000_000_000_000:
            return f"${value/1_000_000_000_000:.2f}T"
        elif value >= 1_000_000_000:
            return f"${value/1_000_000_000:.2f}B"
        else:
            return f"${value:,.0f}"
    except:
        return value


def scrape_eu_market_cap(top_n=20):
    url = "https://companiesmarketcap.com/european-union/largest-companies-in-the-eu-by-market-cap/?download=csv"
    response = requests.get(url, headers=HEADERS, timeout=15)
    df = pd.read_csv(StringIO(response.text))

    # Clean column names
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Detect columns by name
    rank_col = next((c for c in df.columns if "rank" in c), None)
    name_col = next((c for c in df.columns if "name" in c), None)
    mcap_col = next((c for c in df.columns if "market" in c), None)
    change_col = next((c for c in df.columns if "change" in c), None)

    # Fall back to positions if detection fails
    if not rank_col: rank_col = df.columns[0]
    if not name_col: name_col = df.columns[1]
    if not mcap_col: mcap_col = df.columns[2]

    # Include change if available
    selected_cols = [rank_col, name_col, mcap_col]
    if change_col: selected_cols.append(change_col)

    clean_df = df[selected_cols].head(top_n)

    # Rename columns
    col_names = ["Rank", "Company", "Market Cap"]
    if change_col:
        col_names.append("Daily %")
    clean_df.columns = col_names

    # Format market cap numbers
    def format_market_cap_inner(value):
        try:
            value = float(value)
            if value >= 1_000_000_000_000: return f"${value/1_000_000_000_000:.2f}T"
            if value >= 1_000_000_000: return f"${value/1_000_000_000:.2f}B"
            return f"${value:,.0f}"
        except:
            return value

    clean_df["Market Cap"] = clean_df["Market Cap"].apply(format_market_cap_inner)

    # Format growth %
    if "Daily %" in clean_df.columns:
        clean_df["Daily %"] = clean_df["Daily %"].apply(
            lambda x: f"{x:.2f}%" if pd.notnull(x) else ""
        )

    return clean_df


# =========================================================
# 4️⃣ WEATHER — YOUR EXACT DATA STRUCTURE (ADAPTED)
# =========================================================

def get_madrid_hourly_forecast(hours_to_show=12):
    url = "https://www.timeanddate.com/weather/spain/madrid/hourly?unit=metric"
    response = requests.get(url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", id="wt-hbh")

    data = []

    if not table:
        print("Warning: Weather forecast table not found.")
        return pd.DataFrame(data)

    rows = table.select("tbody tr")[:hours_to_show]

    for row in rows:
        cells = row.find_all(["th", "td"])
        if len(cells) < 8:
            continue

        # Time → keep only HH:MM
        time_raw = cells[0].get_text(strip=True)
        time_match = re.search(r'(\d{1,2}:\d{2}\s*[ap]m)', time_raw)
        time = time_match.group(1).replace(" ", "") if time_match else time_raw[:5]

        temp = cells[1].get_text(strip=True)
        condition = cells[2].get_text(strip=True).rstrip(".").strip()
        feels = cells[3].get_text(strip=True)

        chance = cells[6].get_text(strip=True).replace(" ", "")
        amount_raw = cells[7].get_text(strip=True)

        rain_mm_match = re.search(r'([\d.]+)\s*mm', amount_raw)
        rain_mm = rain_mm_match.group(1) + " mm" if rain_mm_match else "0.0 mm"

        if "°C" not in temp:
            temp = temp.replace(" ", "") + "°C"
        if "°C" not in feels:
            feels = feels.replace(" ", "") + "°C"

        data.append({
            "Time": time,
            "Temp": temp,
            "Feels": feels,
            "Rain %": chance,
            "Rain mm": rain_mm,
            "Condition": condition
        })

    return pd.DataFrame(data)


# =========================================================
# 5️⃣ TRADING ECONOMICS
# =========================================================

def scrape_trading_economics():
    url = "https://tradingeconomics.com/stocks"
    response = requests.get(url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(response.content, "html.parser")
    table = soup.find("table", {"class": "table-hover"})

    if not table:
        # Save HTML for debugging
        with open("debug_trading.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        raise RuntimeError("Trading Economics table not found. Saved page as debug_trading.html")

    data = []
    for row in table.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) > 8:
            data.append({
                "Index": cols[1].text.strip(),
                "Weekly": cols[5].text.strip(),
                "Monthly": cols[6].text.strip(),
                "YTD": cols[7].text.strip(),
                "YoY": cols[8].text.strip(),
            })

    return pd.DataFrame(data)


# =========================================================
# 6️⃣ COLOR PERCENTAGES
# =========================================================

def color_percentages(html):
    html = re.sub(r'>(-\d+\.?\d*%)<',
                  r'><span style="color:#d62728;font-weight:600;">\1</span><',
                  html)
    html = re.sub(r'>(\+?\d+\.?\d*%)<',
                  r'><span style="color:#2ca02c;font-weight:600;">\1</span><',
                  html)
    return html


# =========================================================
# 7️⃣ GENERATE DASHBOARD
# =========================================================

def generate_html_report(headlines, energy_df, market_df, stocks_df, forecast_df):

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    energy_html = color_percentages(energy_df.to_html(index=False, classes="styled"))
    stocks_html = color_percentages(stocks_df.to_html(index=False, classes="styled"))
    market_html = color_percentages(market_df.to_html(index=False, classes="styled"))
    forecast_html = forecast_df.to_html(index=False, classes="styled")

    html = f"""
    <html>
    <head>
        <title>Executive Dashboard</title>
        <style>
            body {{
                font-family: 'Segoe UI', sans-serif;
                background: #f4f6f9;
                margin: 0;
            }}
            header {{
                background: linear-gradient(90deg,#1f4e79,#163a5f);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .container {{ padding: 40px; }}
            .card {{
                background: white;
                padding: 25px;
                border-radius: 12px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.08);
                margin-bottom: 40px;
            }}
            table.styled {{
                border-collapse: collapse;
                width: 100%;
                font-size: 14px;
            }}
            table.styled th {{
                background: #163a5f;
                color: white;
                padding: 12px;
                text-align: left;
            }}
            table.styled td {{
                padding: 10px;
                border-bottom: 1px solid #eee;
            }}
            table.styled tr:nth-child(even) {{
                background-color: #f8fbff;
            }}
        </style>
    </head>
    <body>

    <header>
        <h1>📊 Executive Intelligence Dashboard</h1>
        <p>Generated: {now}</p>
    </header>

    <div class="container">

        <div class="card">
            <h2>📰 Headlines</h2>
            <ul>
                {''.join(f"<li>{h}</li>" for h in headlines)}
            </ul>
        </div>

        <div class="card">
            <h2>⚡ Energy Prices</h2>
            {energy_html}
        </div>

        <div class="card">
            <h2>🏢 EU Market Cap</h2>
            {market_html}
        </div>

        <div class="card">
            <h2>📈 Global Markets</h2>
            {stocks_html}
        </div>

        <div class="card">
            <h2>🌤 Madrid Forecast</h2>
            {forecast_html}
        </div>

    </div>

    </body>
    </html>
    """

    import os

    os.makedirs("docs", exist_ok=True)
    with open("docs/daily_report.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("✅ Dashboard generated successfully: docs/daily_report.html")


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    headlines = scrape_okdiario_headlines()
    energy_df = scrape_energy_prices()
    market_df = scrape_eu_market_cap()
    stocks_df = scrape_trading_economics()
    forecast_df = get_madrid_hourly_forecast()

    generate_html_report(
        headlines,
        energy_df,
        market_df,
        stocks_df,
        forecast_df
    )
