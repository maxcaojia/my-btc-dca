import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import requests

# 1. 网页配置
st.set_page_config(page_title="CMC 实时定投工具", layout="wide")
st.title("💎 CMC 实时联动：定投精准分析 (对齐版)")

# 2. 自动获取 API Key (优先从 Secrets 读取)
if "CMC_API_KEY" in st.secrets:
    cmc_api_key = st.secrets["CMC_API_KEY"]
else:
    with st.sidebar:
        st.warning("🔑 未在后台检测到 Key，请在此手动输入：")
        cmc_api_key = st.text_input("CMC API Key", type="password")

# 侧边栏设置
with st.sidebar:
    st.header("⚙️ 策略设置")
    coin = st.selectbox("选择币种", ["BTC", "ETH", "BNB", "SOL", "XRP"])
    start_date = st.date_input("开始定投日期", value=datetime(2020, 1, 1))
    amount = st.number_input("每期定投金额 ($)", min_value=1, value=100)
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月初"], index=2)
    freq_map = {"每天": "D", "每周": "W", "每月初": "MS"}

# --- 函数：CMC 实时报价 ---
def get_cmc_price(symbol, api_key):
    if not api_key: return None
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': api_key}
    try:
        response = requests.get(url, headers=headers, params={'symbol': symbol, 'convert': 'USD'})
        return response.json()['data'][symbol]['quote']['USD']['price']
    except: return None

# --- 函数：历史数据抓取 ---
@st.cache_data(ttl=600)
def get_hist_data(coin_sym, start):
    symbol = f"{coin_sym}-USD"
    df = yf.download(symbol, start=start, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        temp = df['Close'].iloc[:, 0]
    else:
        temp = df['Close']
    return temp.to_frame(name='Close').dropna()

try:
    hist_raw = get_hist_data(coin, start_date)
    
    if hist_raw is not None:
        # --- 核心逻辑：精准对齐 ---
        # 1. 提取历史周期点 (例如每个月1号)
        dca = hist_raw['Close'].resample(freq_map[frequency]).first().to_frame()
        
        # 2. 关键：只保留“已发生”的扣款，不含今天这个未完成周期
        # 比如今天是21号，选“每月初”，则本月1号算一笔，但本月本金不再增加
        now = datetime.now()
        dca = dca[dca.index < now]
        
        # 3. 获取 CMC 实时价
        realtime_p = get_cmc_price(coin, cmc_api_key)
        if realtime_p is None:
            realtime_p = hist_raw['Close'].iloc[-1]
            st.caption("⚠️ 正在使用雅虎备用实时数据")
        else:
            st.success(f"✅ 已通过 CMC 获取实时报价: ${realtime_p:,.2f}")

        # 4. 核心指标计算
        total_invested = len(dca) * amount
        total_qty = (amount / dca['Close']).sum()
        my_avg_price = total_invested / total_qty
        
        # 实时表现
        current_market_val = total_qty * realtime_p
        total_roi = (current_market_val - total_invested) / total_invested * 100
        # 精准差价：实时价相对于均价的百分比
        price_diff_pct = (realtime_p - my_avg_price) / my_avg_price * 100

        # 5. UI 指标卡片
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("累计投入本金", f"${total_invested:,.0f}")
        col2.metric("我的持仓均价", f"${my_avg_price:,.2f}")
        
        # 第三格：实时对比（如果实时价低于均价，delta 会变红/变绿提示补仓）
        col3.metric("实时价 vs 均价", f"{price_diff_pct:+.2f}%", 
                    delta=f"{'折价' if price_diff_pct < 0 else '溢价'}", 
                    delta_color="inverse")
        
        col4.metric("实时账户市值", f"${current_market_value:,.0f}", f"{total_roi:.2f}%")

        # 6. 图表
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Close']*total_qty, name="历史市值路径", fill='tonexty', line=dict(color='#11d3bc')))
        fig.add_trace(go.Scatter(x=dca.index, y=[amount*(i+1) for i in range(len(dca))], name="投入本金", line=dict(color='gray', dash='dash')))
        fig.update_layout(title=f"{coin} 定投实时联动分析", template="plotly_white", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"正在同步 CMC 数据... {e}")
