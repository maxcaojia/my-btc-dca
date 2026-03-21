import streamlit as st
import ccxt
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# 1. 网页配置
st.set_page_config(page_title="币安实时定投模拟器", layout="wide")
st.title("🚀 币安 BTC/Altcoin 定投回测工具")

# 2. 侧边栏设置
with st.sidebar:
    st.header("⚙️ 策略设置")
    symbol = st.selectbox("选择交易对", ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT"])
    start_date = st.date_input("开始定投日期", value=datetime(2023, 1, 1))
    amount = st.number_input("每次投入金额 ($)", min_value=10, value=100)
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月初"], index=1)
    freq_map = {"每天": "1d", "每周": "1w", "每月初": "1MS"}

# 3. 抓取币安数据
@st.cache_data(ttl=3600) # 缓存一小时，避免频繁请求
def get_data(symbol, start_date):
    exchange = ccxt.binance()
    since = exchange.parse8601(start_date.strftime('%Y-%m-%dT00:00:00Z'))
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1d', since=since)
    df = pd.DataFrame(ohlcv, columns=['ts', 'open', 'high', 'low', 'close', 'vol'])
    df['Date'] = pd.to_datetime(df['ts'], unit='ms')
    return df.set_index('Date')

try:
    df_raw = get_data(symbol, start_date)
    
    # 4. 定投逻辑计算
    resample_freq = "D" if frequency == "每天" else ("W" if frequency == "每周" else "MS")
    dca = df_raw.resample(resample_freq).first().copy()
    
    dca['Cumulative_Cost'] = range(amount, (len(dca)+1)*amount, amount)
    dca['Bought_Qty'] = amount / dca['close']
    dca['Total_Qty'] = dca['Bought_Qty'].cumsum()
    dca['Portfolio_Value'] = dca['Total_Qty'] * dca['close']
    
    # 5. 核心指标看板
    final_cost = dca['Cumulative_Cost'].iloc[-1]
    final_value = dca['Portfolio_Value'].iloc[-1]
    avg_price = final_cost / dca['Total_Qty'].iloc[-1]
    current_price = dca['close'].iloc[-1]
    roi = (final_value - final_cost) / final_cost * 100

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("累计投入", f"${final_cost:,.2f}")
    col2.metric("持仓均价", f"${avg_price:,.2f}")
    col3.metric("当前市值", f"${final_value:,.2f}", f"{roi:.2f}%")
    col4.metric("最新币价", f"${current_price:,.2f}")

    # 6. 交互式图表
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dca.index, y=dca['Cumulative_Cost'], name="投入本金", line=dict(color='gray', dash='dash')))
    fig.add_trace(go.Scatter(x=dca.index, y=dca['Portfolio_Value'], name="账户市值", fill='tonexty', line=dict(color='#F3BA2F')))
    fig.update_layout(title=f"{symbol} 定投增长曲线", xaxis_title="日期", yaxis_title="金额 (USD)")
    st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"连接币安失败，请检查网络或日期设定。错误: {e}")
