import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import re
from io import StringIO
import os
import feedparser  # Add this import (it's lightweight & usually pre-installed in Actions ubuntu)

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
# 1️⃣ OKDIARIO HEADLINES → Use RSS (reliable, no JS)
# =========================================================
def scrape_okdiario_headlines(limit=8):
    try:
        feed_url = "https://okdiario.com/feed/"
        feed = feedparser.parse(feed_url)
        headlines = [entry.title for entry in feed.entries[:limit] if hasattr(entry, 'title')]
        return headlines if headlines else ["No headlines available (RSS fetch issue)"]
    except Exception as e:
        print(f"⚠️ OKDiario RSS failed: {e}")
        return ["Headlines unavailable"]

# =========================================================
# 2️⃣ ENERGY PRICES – Flexible parsing
# =========================================================
def scrape_energy_prices():
    url = "https://www.energyprices.eu/"
    try:
        response = requests.get(url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table")
        if not table:
            print("⚠️ No table found on energyprices.eu")
            return pd.DataFrame(columns=["Region", "Avg Price", "High", "Low"])

        data = []
        for row in table.find_all("tr")[1:]:  # skip header
            cols = [c.get_text(strip=True) for c in row.find_all("td")]
            if len(cols) < 3:
                continue
            region = cols[0]
            # Sometimes % is before avg, sometimes separate
            avg = cols[1] if len(cols) > 1 else ""
            high = cols[2] if len(cols) > 2 else ""
            low  = cols[3] if len(cols) > 3 else ""
            data.append({"Region": region, "Avg Price": avg, "High": high, "Low": low})
        df = pd.DataFrame(data)
        return df if not df.empty else pd.DataFrame(columns=["Region", "Avg Price", "High", "Low"])
    except Exception as e:
        print(f"⚠️ Energy prices failed: {e}")
        return pd.DataFrame(columns=["Region", "Avg Price", "High", "Low"])

# =========================================================
# 3️⃣ EU MARKET CAP (unchanged – works)
# =========================================================
def scrape_eu_market_cap(top_n=15):
    url = "https://companiesmarketcap.com/european-union/largest-companies-in-the-eu-by-market-cap/?download=csv"
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text))
        df.columns = [str(c).strip().lower() for c in df.columns]
        rank_col = next((c for c in df.columns if "rank" in c.lower()), df.columns[0])
        name_col = next((c for c in df.columns if "name" in c.lower()), df.columns[1])
        mcap_col = next((c for c in df.columns if "market cap" in c.lower() or "market" in c.lower()), df.columns[2])
        change_col = next((c for c in df.columns if "today" in c.lower() or "change" in c.lower()), None)

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
                v = float(str(v).replace("$","").replace(",",""))
                if v >= 1e12: return f"${v/1e12:.2f}T"
                if v >= 1e9:  return f"${v/1e9:.2f}B"
                return f"${v:,.0f}"
            except:
                return str(v)
        clean_df["Market Cap"] = clean_df["Market Cap"].apply(format_mcap)

        if "Daily %" in clean_df.columns:
            clean_df["Daily %"] = clean_df["Daily %"].apply(lambda x: f"{float(x):.2f}%" if pd.notnull(x) else "")
        return clean_df
    except Exception as e:
        print(f"⚠️ EU Market Cap failed: {e}")
        return pd.DataFrame(columns=["Rank", "Company", "Market Cap"])

# =========================================================
# 4️⃣ MADRID WEATHER – Switch to Open-Meteo (free JSON API, no JS, reliable)
# =========================================================
def get_madrid_hourly_forecast(hours_to_show=12):
    url = "https://api.open-meteo.com/v1/forecast?latitude=40.4168&longitude=-3.7038&hourly=temperature_2m,apparent_temperature,precipitation_probability,precipitation,weathercode&timezone=Europe%2FMadrid&forecast_days=1"
    try:
        resp = requests.get(url, timeout=10).json()
        hourly = resp["hourly"]
        times = hourly["time"][:hours_to_show]
        temps = hourly["temperature_2m"][:hours_to_show]
        feels = hourly["apparent_temperature"][:hours_to_show]
        rain_p = hourly["precipitation_probability"][:hours_to_show]
        rain_mm = hourly["precipitation"][:hours_to_show]

        data = []
        for i in range(len(times)):
            t = datetime.fromisoformat(times[i]).strftime("%H:%M")
            cond = "Rain" if rain_mm[i] > 0.1 else "Clear/Cloudy"  # simple; can improve with weathercode
            data.append({
                "Time": t,
                "Temp": f"{temps[i]} °C",
                "Feels": f"{feels[i]} °C",
                "Rain %": f"{rain_p[i]}%",
                "Rain mm": f"{rain_mm[i]} mm",
                "Condition": cond
            })
        return pd.DataFrame(data)
    except Exception as e:
        print(f"⚠️ Weather API failed: {e}")
        return pd.DataFrame(columns=["Time","Temp","Feels","Rain %","Rain mm","Condition"])

# =========================================================
# 5️⃣ GLOBAL MARKETS – Fallback / placeholder (Trading Economics often blocked)
# =========================================================
def scrape_global_markets():
    # For now: placeholder. Consider switching to https://finance.yahoo.com/world-indices/ later
    print("⚠️ Trading Economics likely blocked → using placeholder")
    data = [
        {"Index": "S&P 500", "Weekly": "+1.2%", "Monthly": "+3.5%", "YTD": "+8.1%", "YoY": "+18%"},
        {"Index": "Euro Stoxx 50", "Weekly": "-0.4%", "Monthly": "+2.1%", "YTD": "+4.8%", "YoY": "+12%"},
    ]
    return pd.DataFrame(data)

# =========================================================
# COLOR & HTML generation (minor tweak: use index.html)
# =========================================================
def color_percentages(html):
    html = re.sub(r'>([+-]?\d+\.?\d*%)<', lambda m: f'><span style="color:{"#d62728" if m.group(1).startswith("-") else "#2ca02c"};font-weight:600;">{m.group(1)}</span><', html)
    return html

def generate_html_report(headlines, energy_df, market_df, stocks_df, forecast_df):
    now = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    energy_html = color_percentages(energy_df.to_html(index=False, classes="styled", escape=False))
    market_html = color_percentages(market_df.to_html(index=False, classes="styled", escape=False))
    stocks_html = color_percentages(stocks_df.to_html(index=False, classes="styled", escape=False))
    forecast_html = forecast_df.to_html(index=False, classes="styled", escape=False)

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Executive Dashboard</title>
        <style>
            body {{ font-family: 'Segoe UI', sans-serif; background: #f4f6f9; margin:0; padding:0; }}
            header {{ background: linear-gradient(90deg,#1f4e79,#163a5f); color:white; padding:2.5rem; text-align:center; }}
            .container {{ max-width:1200px; margin:0 auto; padding:2rem; }}
            .card {{ background:white; border-radius:12px; box-shadow:0 4px 15px rgba(0,0,0,0.1); padding:1.8rem; margin-bottom:2.5rem; }}
            h2 {{ color:#163a5f; margin-top:0; }}
            table.styled {{ width:100%; border-collapse:collapse; font-size:0.95rem; }}
            table.styled th {{ background:#163a5f; color:white; padding:0.9rem; text-align:left; }}
            table.styled td {{ padding:0.8rem; border-bottom:1px solid #eee; }}
            table.styled tr:nth-child(even) {{ background:#f8fbff; }}
            ul {{ padding-left:1.4rem; line-height:1.6; }}
        </style>
    </head>
    <body>
    <header>
        <h1>📊 Executive Intelligence Dashboard</h1>
        <p>Generated: {now}</p>
    </header>
    <div class="container">
        <div class="card">
            <h2>📰 Top Headlines</h2>
            <ul>{''.join(f"<li>{h}</li>" for h in headlines)}</ul>
        </div>
        <div class="card"><h2>⚡ European Energy Prices</h2>{energy_html or "<p>Data unavailable</p>"}</div>
        <div class="card"><h2>🏢 Largest EU Companies by Market Cap</h2>{market_html or "<p>Data unavailable</p>"}</div>
        <div class="card"><h2>📈 Global Stock Indices (Placeholder)</h2>{stocks_html or "<p>Data unavailable</p>"}</div>
        <div class="card"><h2>🌤 Madrid Hourly Forecast</h2>{forecast_html or "<p>Data unavailable</p>"}</div>
    </div>
    </body>
    </html>
    """
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:  # ← changed to index.html
        f.write(html)
    print("✅ Dashboard generated: docs/index.html")

# =========================================================
# MAIN
# =========================================================
if __name__ == "__main__":
    headlines   = scrape_okdiario_headlines()
    energy_df   = scrape_energy_prices()
    market_df   = scrape_eu_market_cap()
    stocks_df   = scrape_global_markets()          # changed name & fallback
    forecast_df = get_madrid_hourly_forecast()
    generate_html_report(headlines, energy_df, market_df, stocks_df, forecast_df)
