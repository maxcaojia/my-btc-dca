import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import requests

# 1. 网页配置
st.set_page_config(page_title="CMC 专业定投分析", layout="wide")
st.title("💎 CMC 实时联动：专业定投分析器")

# 2. API Key 获取
cmc_api_key = st.secrets.get("CMC_API_KEY") if "CMC_API_KEY" in st.secrets else None

# 侧边栏设置
with st.sidebar:
    st.header("⚙️ 策略设置")
    coin = st.selectbox("选择币种", ["BTC", "ETH", "BNB", "SOL", "XRP"])
    start_date = st.date_input("开始定投日期", value=datetime(2020, 1, 1))
    amount = st.number_input("每期定投金额 ($)", min_value=1, value=100)
    
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月初"], index=1)
    
    # --- 新增：自由选择周几 ---
    weekday_map = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6}
    target_weekday = 0
    if frequency == "每周":
        selected_day = st.selectbox("选择每周定投日", list(weekday_map.keys()))
        target_weekday = weekday_map[selected_day]

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
        # --- 核心逻辑：精准对齐与自由选日 ---
        if frequency == "每周":
            # 过滤出用户指定的周几
            dca = hist_raw[hist_raw.index.weekday == target_weekday].copy()
        else:
            # 每天或每月初
            freq_code = "D" if frequency == "每天" else "MS"
            dca = hist_raw['Close'].resample(freq_code).first().to_frame()
        
        # 确保不含未完成的今天
        now = datetime.now()
        dca = dca[dca.index < now].dropna()
        
        # 获取 CMC 实时价
        realtime_p = get_cmc_price(coin, cmc_api_key)
        if realtime_p is None:
            realtime_p = hist_raw['Close'].iloc[-1]
            st.caption("⚠️ 使用雅虎备用实时行情")
        else:
            st.success(f"✅ 已通过 CMC 获取实时报价: ${realtime_p:,.2f}")

        # --- 指标计算 ---
        total_invested = len(dca) * amount
        qty_list = amount / dca['Close']
        total_qty_held = qty_list.sum()
        my_avg_price = total_invested / total_qty_held
        
        # 修正变量名报错
        current_market_val = total_qty_held * realtime_p
        total_roi = (current_market_val - total_invested) / total_invested * 100
        price_diff_pct = (realtime_p - my_avg_price) / my_avg_price * 100

        # --- UI 指标卡片 (5个卡片) ---
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("累计投入本金", f"${total_invested:,.0f}")
        m2.metric(f"累计持仓 {coin}", f"{total_qty_held:.4f}")
        m3.metric("持仓均价", f"${my_avg_price:,.2f}")
        
        # 溢价/折价显示
        m4.metric("实时价 vs 均价", f"{price_diff_pct:+.2f}%", 
                  delta=f"{'折价' if price_diff_pct < 0 else '溢价'}", 
                  delta_color="inverse")
        
        m5.metric("实时账户市值", f"${current_market_val:,.0f}", f"{total_roi:.2f}%")

        # --- 恢复曲线图 ---
        # 准备绘图数据
        dca['Cumulative_Qty'] = (amount / dca['Close']).cumsum()
        dca['Portfolio_Value'] = dca['Cumulative_Qty'] * dca['Close']
        dca['Cumulative_Cost'] = [amount * (i+1) for i in range(len(dca))]

        fig = go.Figure()
        # 市值线
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Portfolio_Value'], name="账户市值", fill='tonexty', line=dict(color='#00d1b2')))
        # 本金阶梯线
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Cumulative_Cost'], name="投入本金", line=dict(color='gray', dash='dash')))
        
        fig.update_layout(title=f"{coin} 定投增长曲线 ({frequency})", template="plotly_white", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📂 查看详细定投记录"):
            st.dataframe(dca[['Close', 'Cumulative_Cost', 'Cumulative_Qty', 'Portfolio_Value']].style.format("{:.2f}"))

except Exception as e:
    st.error(f"计算中出错: {e}")
