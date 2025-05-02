import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# 페이지 설정
st.set_page_config(page_title="📊 Binance vs Bybit Spread Monitor", layout="wide")
st.title("💹 Binance vs Bybit 스프레드 모니터링")

# 사용자 설정
spread_threshold = st.sidebar.slider("🚨 스프레드 기준(%)", 0.0, 2.0, 0.1, 0.1)
volume_threshold = st.sidebar.slider("📊 거래량 기준 (USDT)", 0, 10_000_000, 500_000, step=100_000)
refresh_interval = st.sidebar.slider("⏱️ 갱신 주기 (초)", 1, 30, 5)
st_autorefresh(interval=refresh_interval * 1000, key="refresh")

# 기본 탭을 '실시간 가격 리스트'로
tab_options = ["📈 스프레드 차트", "💰 실시간 가격 리스트"]
selected_tab = st.radio("탭 선택", tab_options, horizontal=True, index=1)

# 캐시 API
@st.cache_data(ttl=30)
def get_binance_futures_symbols():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    r = requests.get(url)
    data = r.json()
    return set(
        item['symbol']
        for item in data['symbols']
        if item.get("contractType") == "PERPETUAL"
        and item.get("quoteAsset") == "USDT"
        and item.get("status") == "TRADING"
    )

@st.cache_data(ttl=30)
def get_binance_prices():
    url = "https://fapi.binance.com/fapi/v1/ticker/price"
    r = requests.get(url)
    return {item['symbol']: float(item['price']) for item in r.json()}

@st.cache_data(ttl=30)
def get_bybit_prices():
    url = "https://api.bybit.com/v5/market/tickers?category=linear"
    r = requests.get(url)
    data = r.json()['result']['list']
    return {item['symbol']: float(item['lastPrice']) for item in data}, set(item['symbol'] for item in data)

@st.cache_data(ttl=30)
def get_binance_24h_volume():
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    r = requests.get(url)
    return {item['symbol']: float(item['quoteVolume']) for item in r.json()}

@st.cache_data(ttl=30)
def get_binance_funding_rates():
    url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    r = requests.get(url)
    return {item["symbol"]: float(item["lastFundingRate"]) * 100 for item in r.json()}

@st.cache_data(ttl=30)
def get_bybit_funding_rates():
    url = "https://api.bybit.com/v5/market/tickers?category=linear"
    r = requests.get(url)
    data = r.json()["result"]["list"]
    return {
        item["symbol"]: float(item["fundingRate"]) * 100
        for item in data if item.get("fundingRate") not in (None, '', 'null')
    }

# 세션 상태 초기화
if "chart_data" not in st.session_state:
    st.session_state.chart_data = {}

now = datetime.now().strftime("%H:%M:%S")

# 데이터 수집
binance_symbols = get_binance_futures_symbols()
binance_prices = get_binance_prices()
bybit_prices, bybit_symbols = get_bybit_prices()
binance_volumes = get_binance_24h_volume()
binance_funding = get_binance_funding_rates()
bybit_funding = get_bybit_funding_rates()

common_symbols = [
    s for s in binance_symbols & bybit_symbols
    if s in binance_prices and s in bybit_prices and binance_volumes.get(s, 0) >= volume_threshold
]

# 스프레드 및 펀딩 데이터 계산
spread_list = []
for symbol in common_symbols:
    b_price = binance_prices[symbol]
    y_price = bybit_prices[symbol]
    spread = abs(b_price - y_price)
    spread_pct = spread / min(b_price, y_price) * 100
    spread_list.append({
        "symbol": symbol,
        "binance": b_price,
        "bybit": y_price,
        "spread": spread,
        "spread_pct": round(spread_pct, 4),
        "volume": binance_volumes.get(symbol, 0),
        "binance_funding": binance_funding.get(symbol, 0.0),
        "bybit_funding": bybit_funding.get(symbol, 0.0)
    })

spread_list = sorted(spread_list, key=lambda x: x["spread_pct"], reverse=True)
top_spreads = spread_list[:12]

# ----------------------------------------------------
# 📈 탭 1: 스프레드 차트
# ----------------------------------------------------
if selected_tab == "📈 스프레드 차트":
    for i in range(0, len(top_spreads), 3):
        row = st.columns(3)
        for j in range(3):
            if i + j < len(top_spreads):
                data = top_spreads[i + j]
                symbol = data['symbol']
                binance_price = data['binance']
                bybit_price = data['bybit']
                spread = data['spread']
                spread_pct = data['spread_pct']

                if symbol not in st.session_state.chart_data:
                    st.session_state.chart_data[symbol] = pd.DataFrame(columns=["Time", "Spread (%)"])
                df = st.session_state.chart_data[symbol]
                df.loc[len(df)] = [now, spread_pct]
                if len(df) > 60:
                    df = df.iloc[-60:]
                st.session_state.chart_data[symbol] = df

                with row[j]:
                    st.markdown(f"### <span style='font-size:18px'>{symbol}</span>", unsafe_allow_html=True)
                    st.markdown(
                        f"<span style='font-size:14px'>"
                        f"Binance: ${binance_price:,.2f}    <vs>  "
                        f"Bybit: ${bybit_price:,.2f}<br>"
                        f"차이: ${spread:,.2f}<br>"
                        f"차이율: {spread_pct:.4f}%"
                        f"</span>", unsafe_allow_html=True
                    )

                    fig = px.line(df, x="Time", y="Spread (%)")
                    spread_min = df["Spread (%)"].min()
                    spread_max = df["Spread (%)"].max()
                    y_min = max(0, spread_min - (spread_max - spread_min) * 0.2)
                    y_max = spread_max + (spread_max - spread_min) * 0.2
                    fig.update_layout(height=250, margin=dict(l=10, r=10, t=20, b=10), showlegend=False)
                    fig.update_yaxes(range=[y_min, y_max])
                    st.plotly_chart(fig, use_container_width=True, key=f"chart_{symbol}")

                    if spread_pct > spread_threshold:
                        st.error(f"🚨 {symbol} 스프레드 {spread_pct:.4f}% 초과!")

# ----------------------------------------------------
# 💰 탭 2: 실시간 가격 리스트
# ----------------------------------------------------
elif selected_tab == "💰 실시간 가격 리스트":
    st.markdown("### 💵 실시간 가격 비교 (Binance vs Bybit)")
    filtered = [item for item in spread_list if item['spread_pct'] >= spread_threshold]
    if not filtered:
        st.info("해당 기준 이상의 종목이 없습니다.")
    else:
        price_df = pd.DataFrame(filtered)
        price_df = price_df[[
            "symbol", "binance", "bybit", "spread", "spread_pct", "volume",
            "binance_funding", "bybit_funding"
        ]]
        price_df.columns = [
            "심볼", "Binance 가격", "Bybit 가격", "가격 차이 ($)", "차이율 (%)",
            "거래량 (USDT)", "Binance 펀딩피 (%)", "Bybit 펀딩피 (%)"
        ]
        price_df["🚨 알림"] = price_df["차이율 (%)"].apply(lambda x: "🔔" if x > spread_threshold else "")

        formatted_df = price_df.sort_values("차이율 (%)", ascending=False).copy()
        formatted_df["Binance 가격"] = formatted_df["Binance 가격"].map("${:,.2f}".format)
        formatted_df["Bybit 가격"] = formatted_df["Bybit 가격"].map("${:,.2f}".format)
        formatted_df["가격 차이 ($)"] = formatted_df["가격 차이 ($)"].map("${:,.2f}".format)
        formatted_df["차이율 (%)"] = formatted_df["차이율 (%)"].map("{:.4f}%".format)
        formatted_df["거래량 (USDT)"] = formatted_df["거래량 (USDT)"].map("{:,.0f}".format)
        formatted_df["Binance 펀딩피 (%)"] = formatted_df["Binance 펀딩피 (%)"].map("{:.4f}%".format)
        formatted_df["Bybit 펀딩피 (%)"] = formatted_df["Bybit 펀딩피 (%)"].map("{:.4f}%".format)

        st.write(formatted_df)
