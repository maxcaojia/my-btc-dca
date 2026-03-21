import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# 1. 网页配置
st.set_page_config(page_title="BTC 定投回测工具", layout="wide")
st.title("🚀 BTC/Altcoin 定投回测工具 (稳定版)")

# 2. 侧边栏设置
with st.sidebar:
    st.header("⚙️ 策略设置")
    coin = st.selectbox("选择币种", ["BTC", "ETH", "BNB", "SOL"])
    symbol = f"{coin}-USD" # 雅虎财经的格式是 BTC-USD
    start_date = st.date_input("开始定投日期", value=datetime(2023, 1, 1))
    amount = st.number_input("每次投入金额 ($)", min_value=10, value=100)
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月初"], index=1)

# 3. 获取数据
@st.cache_data(ttl=3600)
def get_data(symbol, start):
    df = yf.download(symbol, start=start, progress=False)
    return df

try:
    df_raw = get_data(symbol, start_date)
    
    if df_raw.empty:
        st.warning("⚠️ 该日期范围内没有数据，请尝试更早或更晚的日期。")
    else:
        #4. 定投逻辑计算 (更加兼容的写法)
        resample_freq = "D" if frequency == "每天" else ("W" if frequency == "每周" else "MS")
        
        # 提取收盘价并确保它是 DataFrame 格式
        close_prices = df_raw['Close']
        dca = close_prices.resample(resample_freq).first()
        
        # 如果 resample 后还是 Series，将其转为 DataFrame
        if isinstance(dca, pd.Series):
            dca = dca.to_frame()
        
        # 重命名列名，防止索引混乱
        dca.columns = ['Close']
        
        dca['Cumulative_Cost'] = [amount * (i + 1) for i in range(len(dca))]
        dca['Bought_Qty'] = amount / dca['Close']
        dca['Total_Qty'] = dca['Bought_Qty'].cumsum()
        dca['Portfolio_Value'] = dca['Total_Qty'] * dca['Close']
        
        # 5. 核心指标看板
        final_cost = dca['Cumulative_Cost'].iloc[-1]
        final_value = dca['Portfolio_Value'].iloc[-1]
        avg_price = final_cost / dca['Total_Qty'].iloc[-1]
        current_price = dca['Close'].iloc[-1]
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
        fig.update_layout(title=f"{coin} 定投增长曲线", xaxis_title="日期", yaxis_title="金额 (USD)")
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"❌ 获取数据失败: {e}")
