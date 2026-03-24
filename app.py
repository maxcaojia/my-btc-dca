import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import time

# 1. 网页基础配置
st.set_page_config(page_title="CRYPTO定投專業分析", layout="wide")

# --- UI 样式优化 ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: max(14px, 1.6vw) !important; white-space: nowrap; color: #FF8C00; }
    div[data-baseweb="datepicker"], div[data-baseweb="popover"] { z-index: 999999 !important; }
    section[data-testid="stSidebar"] > div { padding-bottom: 300px !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🧡 CRYPTO定投全景分析 (終極穩定版)")

# 2. 获取 API Key
cmc_api_key = st.secrets.get("CMC_API_KEY")

# 3. 侧边栏
with st.sidebar:
    st.header("📅 时间区间设置")
    start_date = st.date_input("定投开始日期", value=datetime(2024, 3, 15))
    end_date = st.date_input("定投截止日期", value=datetime(2025, 4, 15))
    
    st.header("⚙️ 资产与频率")
    coin = st.selectbox("选择切换币种", ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA"])
    amount = st.number_input("每期定投金额 ($)", min_value=1, value=100)
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月"], index=0)
    
    # 强制刷新按钮 (一劳永逸的关键：清理卡死缓存)
    if st.button("🔄 强制刷新数据 (清理缓存)"):
        st.cache_data.clear()
        st.rerun()

# --- 增强型数据抓取：带自动重试功能 ---
@st.cache_data(ttl=600)
def fetch_data_with_retry(coin_sym, start, end, retries=3):
    symbol = f"{coin_sym}-USD"
    for i in range(retries):
        try:
            data = yf.download(symbol, start=start, end=end + timedelta(days=1), progress=False, timeout=15)
            if not data.empty:
                # 处理索引
                if isinstance(data.columns, pd.MultiIndex):
                    df = data.xs('Close', axis=1, level=0)[symbol].to_frame(name='Price')
                else:
                    df = data[['Close']].rename(columns={'Close': 'Price'})
                df.index = df.index + timedelta(hours=8)
                return df.dropna()
        except Exception:
            if i < retries - 1:
                time.sleep(1) # 等待1秒后重试
                continue
    return None

def fetch_cmc_price(symbol, api_key):
    if not api_key: return None
    try:
        url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
        r = requests.get(url, headers={'X-CMC_PRO_API_KEY': api_key}, params={'symbol': symbol, 'convert': 'USD'}, timeout=8)
        return r.json()['data'][symbol]['quote']['USD']['price']
    except:
        return None

# --- 执行引擎 ---
try:
    df = fetch_data_with_retry(coin, start_date, end_date)
    
    if df is not None:
        # 1. 核心财务计算
        if frequency == "每天": df['Is_DCA'] = True
        elif frequency == "每周": df['Is_DCA'] = df.index.weekday == 0 # 默认为周一
        else: df['Is_DCA'] = df.index.day == 1 # 默认为1号

        df['Cost_Step'] = df['Is_DCA'].apply(lambda x: amount if x else 0)
        df['Qty_Step'] = df.apply(lambda r: r['Cost_Step'] / r['Price'] if r['Is_DCA'] else 0, axis=1)
        df['Cum_Cost'] = df['Cost_Step'].cumsum()
        df['Cum_Qty'] = df['Qty_Step'].cumsum()
        df['Avg_Price'] = (df['Cum_Cost'] / df['Cum_Qty']).fillna(0)
        df['Market_Value'] = df['Cum_Qty'] * df['Price']
        df['ROI_Pct'] = (((df['Price'] - df['Avg_Price']) / df['Avg_Price']) * 100).fillna(0).round(2)

        # 2. 实时价格同步
        is_to_now = end_date >= datetime.now().date()
        live_p = fetch_cmc_price(coin, cmc_api_key) if is_to_now else None
        
        final_p = live_p if (live_p and is_to_now) else df['Price'].iloc[-1]
        final_cost = df['Cum_Cost'].iloc[-1]
        final_qty = df['Cum_Qty'].iloc[-1]
        final_avg = final_cost / final_qty if final_qty > 0 else 0
        final_val = final_qty * final_p
        final_roi = ((final_val - final_cost) / final_cost * 100) if final_cost > 0 else 0

        # 3. UI 渲染
        st.info(f"📊 统计区间：{start_date} 至 {end_date}")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("区间总投入", f"${final_cost:,.0f}")
        m2.metric(f"累计持仓", f"{final_qty:.4f}")
        m3.metric("持仓均价", f"${final_avg:,.2f}")
        m4.metric("实时对比", f"{(final_p-final_avg)/final_avg*100:+.2f}%")
        m5.metric("最终市值", f"${final_val:,.0f}", f"{final_roi:+.2f}%")

        # 4. 图表
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df.index, y=df['Market_Value'], name="市值", fill='tonexty', 
            line=dict(color='#FF8C00', width=2),
            hovertemplate="<b>日期: %{x}</b><br>累计投入: $%{customdata[1]:,.0f}<br>市值: $%{y:,.0f}<br>盈亏: %{customdata[2]:+.2f}%<extra></extra>",
            customdata=df[['Price', 'Cum_Cost', 'ROI_Pct']].values
        ))
        fig.add_trace(go.Scatter(x=df.index, y=df['Cum_Cost'], name="本金", line=dict(color='gray', dash='dash')))
        fig.update_layout(template="plotly_white", hovermode="x unified", height=600)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("📉 雅虎数据源响应超时。请点击左侧按钮【强制刷新数据】重新建立连接。")

except Exception as e:
    st.error(f"❌ 系统暂时不可用，请稍后再试或检查侧边栏设置。")
