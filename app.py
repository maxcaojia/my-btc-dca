import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# 1. 网页配置
st.set_page_config(page_title="專業定投分析工具", layout="wide")
st.title("BTC定投")

# --- UI 优化补丁 ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: max(14px, 1.6vw) !important; white-space: nowrap; }
    [data-testid="stMetricLabel"] { font-size: 0.9vw !important; }
    </style>
    """, unsafe_allow_html=True)

# 2. API Key 获取
cmc_api_key = st.secrets.get("CMC_API_KEY") if "CMC_API_KEY" in st.secrets else None

# 3. 侧边栏设置
with st.sidebar:
    st.header("⚙️ 策略设置")
    coin = st.selectbox("选择币种", ["BTC", "ETH", "BNB", "SOL", "XRP"])
    start_date = st.date_input("开始定投日期", value=datetime(2020, 1, 1))
    amount = st.number_input("每期定投金额 ($)", min_value=1, value=100)
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月"], index=2)
    
    target_day = 0
    if frequency == "每周":
        weekday_map = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6}
        selected_day = st.selectbox("选择每周定投日", list(weekday_map.keys()))
        target_day = weekday_map[selected_day]
    elif frequency == "每月":
        target_day = st.slider("选择每月定投号数", 1, 28, 1)

# --- 数据抓取函数 ---
@st.cache_data(ttl=300)
def get_aligned_data(coin_sym, start):
    symbol = f"{coin_sym}-USD"
    df = yf.download(symbol, start=start, progress=False)
    if df.empty: return None
    temp = df['Close'].iloc[:, 0] if isinstance(df.columns, pd.MultiIndex) else df['Close']
    res = temp.to_frame(name='Close')
    res.index = res.index + timedelta(hours=8)
    return res.dropna()

def get_cmc_price(symbol, api_key):
    if not api_key: return None
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': api_key}
    try:
        response = requests.get(url, headers=headers, params={'symbol': symbol, 'convert': 'USD'})
        return response.json()['data'][symbol]['quote']['USD']['price']
    except: return None

# --- 核心逻辑开始 ---
try:
    hist_raw = get_aligned_data(coin, start_date)
    
    if hist_raw is not None:
        # A. 筛选定投点
        if frequency == "每天":
            dca = hist_raw.copy()
        elif frequency == "每周":
            dca = hist_raw[hist_raw.index.weekday == target_day].copy()
        elif frequency == "每月":
            dca = hist_raw[hist_raw.index.day == target_day].copy()
        
        now_bj = datetime.now() + timedelta(hours=8)
        dca = dca[dca.index < now_bj].dropna()
        
        # B. 获取最新价
        realtime_p = get_cmc_price(coin, cmc_api_key) or hist_raw['Close'].iloc[-1]
        if cmc_api_key: st.success(f"✅ CMC 实时价已同步: ${realtime_p:,.2f}")

        # C. 核心计算 (修复 ROI 逻辑)
        dca['Cumulative_Cost'] = [amount * (i+1) for i in range(len(dca))]
        dca['Cumulative_Qty'] = (amount / dca['Close']).cumsum()
        dca['Avg_Cost_at_Time'] = (dca['Cumulative_Cost'] / dca['Cumulative_Qty']).round(2)
        dca['Portfolio_Value_at_Time'] = dca['Cumulative_Qty'] * dca['Close']
        dca['ROI_at_Time'] = ((dca['Close'] - dca['Avg_Cost_at_Time']) / dca['Avg_Cost_at_Time'] * 100).round(2)

        # 头部指标
        f_cost = dca['Cumulative_Cost'].iloc[-1]
        f_qty = dca['Cumulative_Qty'].iloc[-1]
        f_avg = dca['Avg_Cost_at_Time'].iloc[-1]
        f_val = f_qty * realtime_p
        f_roi = ((f_val - f_cost) / f_cost * 100).round(2)
        p_diff = ((realtime_p - f_avg) / f_avg * 100).round(2)

        cols = st.columns(5)
        cols[0].metric("累计投入", f"${f_cost:,.0f}")
        cols[1].metric(f"持仓 {coin}", f"{f_qty:.4f}")
        cols[2].metric("持仓均价", f"${f_avg:,.2f}")
        cols[3].metric("实时价 vs 均价", f"{p_diff:+.2f}%", delta_color="inverse")
        cols[4].metric("实时市值", f"${f_val:,.0f}", f"{f_roi:+.2f}%")

        # D. 橙色图表
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dca.index, y=dca['Portfolio_Value_at_Time'], name="市值", 
            fill='tonexty', line=dict(color='#FF8C00', width=3),
            fillcolor='rgba(255, 140, 0, 0.1)',
            hovertemplate="日期: %{x}<br>币价: $%{y:,.2f}<br>均价: $%{customdata[0]:,.2f}<br>盈亏: %{customdata[1]:+.2f}%<extra></extra>",
            customdata=dca[['Avg_Cost_at_Time', 'ROI_at_Time']].values
        ))
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Cumulative_Cost'], name="本金", line=dict(color='gray', dash='dash')))
        
        # 减半线
        for hd in ['2020-04-11', '2024-04-20']:
            hd_bj = pd.to_datetime(hd) + timedelta(hours=8)
            if hd_bj >= dca.index.min() and hd_bj <= dca.index.max():
                fig.add_vline(x=hd_bj.timestamp() * 1000, line_dash="dot", line_color="red", annotation_text="减半")

        fig.update_layout(template="plotly_white", hovermode="x unified", height=500)
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"❌ 运行异常: {e}") # <--- 就是这里，之前可能漏了这两行
