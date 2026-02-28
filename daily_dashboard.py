import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import re
from io import StringIO
import os
import feedparser  # pip install feedparser

# =========================================================
# COMMON HEADERS
# =========================================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

# =========================================================
# 1. OKDIARIO HEADLINES – Reliable RSS feed
# =========================================================
def scrape_okdiario_headlines(limit=8):
    try:
        feed_url = "https://okdiario.com/feed/"
        feed = feedparser.parse(feed_url)
        headlines = []
        for entry in feed.entries[:limit]:
            if hasattr(entry, 'title'):
                title = entry.title.strip()
                if title:  # skip empty
                    headlines.append(title)
        return headlines if headlines else ["No recent headlines available"]
    except Exception as e:
        print(f"⚠️ OKDiario RSS failed: {e}")
        return ["Headlines unavailable at the moment"]

# =========================================================
# 2. ENERGY PRICES – Flexible column detection
# =========================================================
def scrape_energy_prices(top_n=10):
    url = "https://www.energyprices.eu/"
    try:
        response = requests.get(url, headers=HEADERS, timeout=12)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table")
        if not table:
            print("⚠️ Energy table not found")
            return pd.DataFrame(columns=["Region", "Change %", "Avg Price", "High", "Low"])

        data = []
        for row in table.find_all("tr")[1:]:  # skip header
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) < 3:
                continue

            # Clean region name (remove rank # or flags)
            region = re.sub(r'^\d+\s*', '', cols[0]).strip()

            # Detect where % change is (often column 1 or 2)
            change = ""
            avg_start = 1
            if "%" in cols[1]:
                change = cols[1]
                avg_start = 2
            elif len(cols) > 2 and "%" in cols[2]:
                change = cols[2]
                avg_start = 3

            avg = cols[avg_start] if len(cols) > avg_start else ""
            high = cols[avg_start + 1] if len(cols) > avg_start + 1 else ""
            low = cols[avg_start + 2] if len(cols) > avg_start + 2 else ""

            data.append({
                "Region": region,
                "Change %": change,
                "Avg Price": avg,
                "High": high,
                "Low": low
            })

        df = pd.DataFrame(data)
        return df.head(top_n) if not df.empty else pd.DataFrame(columns=["Region", "Change %", "Avg Price", "High", "Low"])
    except Exception as e:
        print(f"⚠️ Energy prices failed: {e}")
        return pd.DataFrame(columns=["Region", "Change %", "Avg Price", "High", "Low"])

# =========================================================
# 3. EU MARKET CAP – CSV is stable
# =========================================================
def scrape_eu_market_cap(top_n=15):
    url = "https://companiesmarketcap.com/european-union/largest-companies-in-the-eu-by-market-cap/?download=csv"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text))
        df.columns = [str(c).strip().lower().replace(" ", "") for c in df.columns]

        rank_col   = next((c for c in df.columns if "rank" in c), df.columns[0])
        name_col   = next((c for c in df.columns if "name" in c or "company" in c), df.columns[1])
        mcap_col   = next((c for c in df.columns if "marketcap" in c or "market" in c), df.columns[2])
        change_col = next((c for c in df.columns if "today" in c or "change" in c or "1d" in c), None)

        selected = [rank_col, name_col, mcap_col]
        if change_col:
            selected.append(change_col)
        clean_df = df[selected].head(top_n).copy()

        col_names = ["Rank", "Company", "Market Cap"]
        if change_col:
            col_names.append("Daily %")
        clean_df.columns = col_names

        def format_mcap(v):
            try:
                v = float(str(v).replace("$", "").replace(",", "").replace("B", "").replace("T", ""))
                if "T" in str(v): v *= 1e12
                elif "B" in str(v): v *= 1e9
                if v >= 1e12: return f"${v/1e12:.2f}T"
                if v >= 1e9:  return f"${v/1e9:.2f}B"
                return f"${v:,.0f}"
            except:
                return str(v)

        clean_df["Market Cap"] = clean_df["Market Cap"].apply(format_mcap)

        if "Daily %" in clean_df.columns:
            clean_df["Daily %"] = clean_df["Daily %"].apply(
                lambda x: f"{float(str(x).replace('%','')):.2f}%" if pd.notnull(x) and str(x).strip() else ""
            )

        return clean_df
    except Exception as e:
        print(f"⚠️ EU Market Cap failed: {e}")
        return pd.DataFrame(columns=["Rank", "Company", "Market Cap"])

# =========================================================
# 4. MADRID HOURLY FORECAST – Open-Meteo (fixed URL)
# =========================================================
def get_madrid_hourly_forecast(hours_to_show=12):
    # Clean URL – no %2F needed, API accepts / or %2F
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=40.4168&longitude=-3.7038"
        "&hourly=temperature_2m,apparent_temperature,precipitation_probability,precipitation"
        "&timezone=Europe/Madrid"
        "&forecast_days=1"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        hourly = data["hourly"]
        times = hourly["time"][:hours_to_show]
        temps = hourly["temperature_2m"][:hours_to_show]
        feels = hourly["apparent_temperature"][:hours_to_show]
        rain_p = hourly["precipitation_probability"][:hours_to_show]
        rain_mm = hourly["precipitation"][:hours_to_show]

        rows = []
        for i in range(len(times)):
            t_str = datetime.fromisoformat(times[i]).strftime("%H:%M")
            cond = "Rain" if rain_mm[i] > 0.1 else "Clear/Cloudy"
            rows.append({
                "Time": t_str,
                "Temp": f"{temps[i]} °C",
                "Feels": f"{feels[i]} °C",
                "Rain %": f"{rain_p[i]}%",
                "Rain mm": f"{rain_mm[i]:.1f} mm",
                "Condition": cond
            })
        return pd.DataFrame(rows)
    except Exception as e:
        print(f"⚠️ Open-Meteo failed: {e}")
        return pd.DataFrame(columns=["Time", "Temp", "Feels", "Rain %", "Rain mm", "Condition"])

# =========================================================
# 5. GLOBAL MARKETS – Placeholder (Trading Economics unreliable)
# =========================================================
def scrape_global_markets():
    # You can later replace with Yahoo Finance or similar
    data = [
        {"Index": "S&P 500",      "Weekly": "+1.4%", "Monthly": "+4.2%", "YTD": "+9.8%", "YoY": "+19%"},
        {"Index": "Euro Stoxx 50","Weekly": "-0.3%", "Monthly": "+2.8%", "YTD": "+5.1%", "YoY": "+13%"},
        {"Index": "DAX",          "Weekly": "+0.9%", "Monthly": "+3.1%", "YTD": "+6.7%", "YoY": "+15%"},
    ]
    return pd.DataFrame(data)

# =========================================================
# COLORIZE PERCENTAGES
# =========================================================
def color_percentages(html_str):
    # Red for negative, Green for positive
    html_str = re.sub(
        r'>([+-]?\d+\.?\d*%)<',
        lambda m: f'><span style="color:{"#d62728" if m.group(1).startswith("-") else "#2ca02c"}; font-weight:600;">{m.group(1)}</span><',
        html_str
    )
    return html_str

# =========================================================
# GENERATE HTML DASHBOARD
# =========================================================
def generate_html_report(headlines, energy_df, market_df, stocks_df, forecast_df):
    now = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    
    energy_html   = color_percentages(energy_df.to_html(index=False, classes="styled", escape=False))   if not energy_df.empty   else "<p>Data currently unavailable</p>"
    market_html   = color_percentages(market_df.to_html(index=False, classes="styled", escape=False))   if not market_df.empty   else "<p>Data currently unavailable</p>"
    stocks_html   = color_percentages(stocks_df.to_html(index=False, classes="styled", escape=False))   if not stocks_df.empty   else "<p>Data currently unavailable</p>"
    forecast_html = color_percentages(forecast_df.to_html(index=False, classes="styled", escape=False)) if not forecast_df.empty else "<p>Data currently unavailable</p>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Executive Intelligence Dashboard</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; background: #f4f6f9; margin:0; padding:0; color:#333; }}
        header {{ background: linear-gradient(90deg, #1f4e79, #163a5f); color:white; padding:2.5rem; text-align:center; }}
        .container {{ max-width:1200px; margin:0 auto; padding:2rem; }}
        .card {{ background:white; border-radius:12px; box-shadow:0 4px 15px rgba(0,0,0,0.1); padding:1.8rem; margin-bottom:2.5rem; }}
        h1, h2 {{ margin:0.5rem 0; }}
        h2 {{ color:#163a5f; }}
        table.styled {{ width:100%; border-collapse:collapse; font-size:0.95rem; }}
        table.styled th {{ background:#163a5f; color:white; padding:0.9rem; text-align:left; }}
        table.styled td {{ padding:0.8rem; border-bottom:1px solid #eee; }}
        table.styled tr:nth-child(even) {{ background:#f8fbff; }}
        ul {{ padding-left:1.4rem; line-height:1.6; list-style-type:disc; }}
    </style>
</head>
<body>
<header>
    <h1>📊 Executive Intelligence Dashboard</h1>
    <p>Generated: {now}</p>
</header>
<div class="container">
    <div class="card">
        <h2>📰 Top Headlines (OKDiario)</h2>
        <ul>{''.join(f"<li>{h}</li>" for h in headlines)}</ul>
    </div>
    
    <div class="card">
        <h2>⚡ European Energy Prices</h2>
        {energy_html}
    </div>
    
    <div class="card">
        <h2>🏢 Largest EU Companies by Market Cap</h2>
        {market_html}
    </div>
    
    <div class="card">
        <h2>📈 Global Stock Indices (Placeholder)</h2>
        {stocks_html}
    </div>
    
    <div class="card">
        <h2>🌤 Madrid Hourly Forecast (Next 12h)</h2>
        {forecast_html}
    </div>
</div>
</body>
</html>"""

    os.makedirs("docs", exist_ok=True)
    output_path = "docs/index.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Dashboard generated successfully: {output_path}")

# =========================================================
# MAIN EXECUTION
# =========================================================
if __name__ == "__main__":
    print("Starting daily dashboard generation...")
    headlines   = scrape_okdiario_headlines(limit=8)
    energy_df   = scrape_energy_prices(top_n=10)
    market_df   = scrape_eu_market_cap(top_n=15)
    stocks_df   = scrape_global_markets()
    forecast_df = get_madrid_hourly_forecast(hours_to_show=12)

    generate_html_report(headlines, energy_df, market_df, stocks_df, forecast_df)
    print("Generation complete.")
