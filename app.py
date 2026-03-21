import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# 1. 网页配置
st.set_page_config(page_title="专业定投回测工具", layout="wide")
st.title("🧡 定投深度回测：北京时间 8:00 联动版")

# 2. API Key 获取 (从 Secrets 读取)
cmc_api_key = st.secrets.get("CMC_API_KEY") if "CMC_API_KEY" in st.secrets else None

# 3. 侧边栏设置
with st.sidebar:
    st.header("⚙️ 策略设置")
    coin = st.selectbox("选择币种", ["BTC", "ETH", "BNB", "SOL", "XRP"])
    start_date = st.date_input("开始定投日期", value=datetime(2020, 1, 1))
    amount = st.number_input("每期定投金额 ($)", min_value=1, value=100)
    
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月"], index=2)
    
    # --- 自由选择定投日逻辑 ---
    target_day = 0
    if frequency == "每周":
        weekday_map = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6}
        selected_day = st.selectbox("选择每周定投日", list(weekday_map.keys()))
        target_day = weekday_map[selected_day]
    elif frequency == "每月":
        target_day = st.slider("选择每月定投号数", 1, 28, 1) # 选到28号避开2月问题

# --- 函数：CMC 实时报价 ---
def get_cmc_price(symbol, api_key):
    if not api_key: return None
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': api_key}
    try:
        response = requests.get(url, headers=headers, params={'symbol': symbol, 'convert': 'USD'})
        return response.json()['data'][symbol]['quote']['USD']['price']
    except: return None

# --- 函数：数据抓取与对齐 ---
@st.cache_data(ttl=600)
def get_aligned_data(coin_sym, start):
    symbol = f"{coin_sym}-USD"
    df = yf.download(symbol, start=start, progress=False)
    if df.empty: return None
    # 强制破解多级索引并重命名
    if isinstance(df.columns, pd.MultiIndex):
        temp = df['Close'].iloc[:, 0]
    else:
        temp = df['Close']
    
    # 转换为北京时间 8:00 (雅虎数据通常是 UTC 0:00，刚好对应北京 8:00)
    res = temp.to_frame(name='Close')
    res.index = res.index + timedelta(hours=8)
    return res.dropna()

try:
    hist_raw = get_aligned_data(coin, start_date)
    
    if hist_raw is not None:
        # --- 精准定投点筛选 ---
        if frequency == "每天":
            dca = hist_raw.copy()
        elif frequency == "每周":
            # weekday() 0是周一，北京时间对齐
            dca = hist_raw[hist_raw.index.weekday == target_day].copy()
        elif frequency == "每月":
            # 筛选出每月指定的号数
            dca = hist_raw[hist_raw.index.day == target_day].copy()
        
        # 排除未发生的今天
        now_bj = datetime.now() + timedelta(hours=8)
        dca = dca[dca.index < now_bj].dropna()
        
        # 获取 CMC 实时价
        realtime_p = get_cmc_price(coin, cmc_api_key)
        if realtime_p is None:
            realtime_p = hist_raw['Close'].iloc[-1]
            st.caption("⚠️ 使用备用实时行情")
        else:
            st.success(f"✅ CMC 实时报价已对齐: ${realtime_p:,.2f}")

        # --- 指标计算 ---
        total_invested = len(dca) * amount
        qty_held = (amount / dca['Close']).sum()
        my_avg_price = total_invested / qty_held
        current_val = qty_held * realtime_p
        total_roi = (current_val - total_invested) / total_invested * 100
        price_diff_pct = (realtime_p - my_avg_price) / my_avg_price * 100

        # --- UI 卡片 ---
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("累计投入", f"${total_invested:,.0f}")
        m2.metric(f"累计持仓 {coin}", f"{qty_held:.4f}")
        m3.metric("持仓均价", f"${my_avg_price:,.2f}")
        m4.metric("实时价 vs 均价", f"{price_diff_pct:+.2f}%", delta_color="inverse")
        m5.metric("实时市值", f"${current_val:,.0f}", f"{total_roi:.2f}%")

        # --- 橙色系图表 ---
        dca['Cumulative_Qty'] = (amount / dca['Close']).cumsum()
        dca['Portfolio_Value'] = dca['Cumulative_Qty'] * dca['Close']
        dca['Cumulative_Cost'] = [amount * (i+1) for i in range(len(dca))]

        fig = go.Figure()
        # 市值线 (橙色填充)
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Portfolio_Value'], name="账户市值", 
                                 fill='tonexty', line=dict(color='#FF8C00', width=3),
                                 fillcolor='rgba(255, 140, 0, 0.2)'))
        # 本金线
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Cumulative_Cost'], name="投入本金", 
                                 line=dict(color='gray', dash='dash')))
        
        fig.update_layout(title=f"{coin} 定投增长曲线 ({frequency} 定投)", 
                          template="plotly_white", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📂 查看详细定投账单 (北京时间 8:00)"):
            st.dataframe(dca[['Close', 'Cumulative_Cost', 'Cumulative_Qty', 'Portfolio_Value']].style.format("{:.2f}"))

except Exception as e:
    st.error(f"分析出错: {e}")
