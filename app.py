import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# 1. 网页配置
st.set_page_config(page_title="專業定投分析工具", layout="wide")
st.title("🧡 定投全景分析：精准即时盈亏对齐版")

# --- UI 优化补丁 (确保卡片数字清晰) ---
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
    
    # 自由选择日
    target_day = 0
    if frequency == "每周":
        weekday_map = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6}
        selected_day = st.selectbox("选择每周定投日", list(weekday_map.keys()))
        target_day = weekday_map[selected_day]
    elif frequency == "每月":
        target_day = st.slider("选择每月定投号数", 1, 28, 1)

# --- 函数：CMC 实时价 ---
def get_cmc_price(symbol, api_key):
    if not api_key: return None
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': api_key}
    try:
        response = requests.get(url, headers=headers, params={'symbol': symbol, 'convert': 'USD'})
        return response.json()['data'][symbol]['quote']['USD']['price']
    except: return None

# --- 函数：数据对齐 ---
@st.cache_data(ttl=300)
def get_aligned_data(coin_sym, start):
    symbol = f"{coin_sym}-USD"
    df = yf.download(symbol, start=start, progress=False)
    if df.empty: return None
    # 强制破解多级索引
    if isinstance(df.columns, pd.MultiIndex):
        temp = df['Close'].iloc[:, 0]
    else:
        temp = df['Close']
    res = temp.to_frame(name='Close')
    res.index = res.index + timedelta(hours=8)
    return res.dropna()

try:
    hist_raw = get_aligned_data(coin, start_date)
    
    if hist_raw is not None:
        # --- 精准定投筛选 ---
        if frequency == "每天":
            dca = hist_raw.copy()
        elif frequency == "每周":
            dca = hist_raw[hist_raw.index.weekday == target_day].copy()
        elif frequency == "每月":
            dca = hist_raw[hist_raw.index.day == target_day].copy()
        
        # 排除未来
        now_bj = datetime.now() + timedelta(hours=8)
        dca = dca[dca.index < now_bj].dropna()
        
        # 获取 CMC 实时价
        realtime_p = get_cmc_price(coin, cmc_api_key)
        if realtime_p is None:
            realtime_p = hist_raw['Close'].iloc[-1]
            st.caption("⚠️ 使用备用实时行情")
        else:
            st.success(f"✅ CMC 实时价已对齐: ${realtime_p:,.2f}")

        # --- 核心盈亏逻辑深度重写 (修复705%报错) ---
        # 1. 累计投入本金 (阶梯式)
        dca['Cumulative_Cost'] = [amount * (i+1) for i in range(len(dca))]
        # 2. 累计持有代币数量
        dca['Cumulative_Qty'] = (amount / dca['Close']).cumsum()
        # 3. 截止到那天的账户总市值
        dca['Portfolio_Value_at_Time'] = dca['Cumulative_Qty'] * dca['Close']
        
        # --- 核心改进：移动平均盈亏计算 ---
        # A. 计算历史实时盈亏比 (ROI)，这一笔买入后总持仓的盈亏比
        # 修复：只保留两位小数
        dca['ROI_at_Time_Raw'] = (dca['Portfolio_Value_at_Time'] - dca['Cumulative_Cost']) / dca['Cumulative_Cost'] * 100
        dca['ROI_at_Time'] = dca['ROI_at_Time_Raw'].round(2)
        
        # B. 计算实时定投均价 (移动平均成本)
        dca['Avg_Cost_at_Time'] = (dca['Cumulative_Cost'] / dca['Cumulative_Qty']).round
