import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# 1. 网页基础配置
st.set_page_config(page_title="CRYPTO定投專業分析", layout="wide")

# --- UI 样式优化补丁 ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: max(14px, 1.6vw) !important; white-space: nowrap; color: #FF8C00; }
    div[data-baseweb="datepicker"], div[data-baseweb="popover"] { z-index: 999999 !important; }
    section[data-testid="stSidebar"] > div { padding-bottom: 300px !important; }
    .stSuccess { background-color: rgba(255, 140, 0, 0.1) !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🧡 CRYPTO定投全景分析 (穩定強化版)")

# 2. 从后台获取 API Key
cmc_api_key = st.secrets.get("CMC_API_KEY")

# 3. 侧边栏
with st.sidebar:
    st.header("📅 时间区间设置")
    start_date = st.date_input("定投开始日期", value=datetime(2024, 3, 15))
    end_date = st.date_input("定投截止日期", value=datetime(2025, 4, 15))
    
    if start_date >= end_date:
        st.error("❌ 错误：开始日期必须早于截止日期")
        st.stop()

    st.header("⚙️ 资产与频率")
    coin = st.selectbox("选择切换币种", ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA"])
    amount = st.number_input("每期定投金额 ($)", min_value=1, value=100)
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月"], index=0)
    
    target_day = 0
    if frequency == "每周":
        weekday_map = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6}
        selected_day = st.selectbox("选择每周定投日", list(weekday_map.keys()))
        target_day = weekday_map[selected_day]
    elif frequency == "每月":
        target_day = st.slider("选择月定投日期", 1, 28, 1)

# --- 增强型数据抓取 (带超时控制) ---
@st.cache_data(ttl=600)
def get_crypto_data_safe(coin_sym, start, end):
    symbol = f"{coin_sym}-USD"
    try:
        # 增加超时限制，防止卡死
        df_raw = yf.download(symbol, start=start, end=end + timedelta(days=1), progress=False, timeout=10)
        if df_raw.empty: return None
        
        if isinstance(df_raw.columns, pd.MultiIndex):
            temp = df_raw.xs('Close', axis=1, level=0)[symbol]
        else:
            temp = df_raw['Close']
        
        res = temp.to_frame(name='Price')
        res.index = res.index + timedelta(hours=8)
        return res.dropna()
    except Exception as e:
        st.warning(f"⚠️ 雅虎财经数据抓取暂不可用: {e}")
        return None

def get_cmc_price_safe(symbol, api_key):
    if not api_key: return None
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': api_key}
    try:
        r = requests.get(url, headers=headers, params={'symbol': symbol, 'convert': 'USD'}, timeout=5)
        return r.json()['data'][symbol]['quote']['USD']['price']
    except Exception as e:
        st.warning(f"⚠️ CMC 实时价格同步超时: {e}")
        return None

# --- 执行主逻辑 ---
try:
    with st.spinner(f'🚀 正在同步全球数据市场...'):
        df = get_crypto_data_safe(coin, start_date, end_date)
        
        if df is not None:
            # 标记定投日 & 财务计算 (逻辑保持不变)
            if frequency == "每天":
                df['Is_DCA'] = True
            elif frequency == "每周":
                df['Is_DCA'] = df.index.weekday == target_day
            else:
                df['Is_DCA'] = df.index.day == target_day

            df['Cost_Step'] = df['Is_DCA'].apply(lambda x: amount if x else 0)
            df['Qty_Step'] = df.apply(lambda row: row['Cost_Step'] / row['Price'] if row['Is_DCA'] else 0, axis=1)
            df['Cum_Cost'] = df['Cost_Step'].cumsum()
            df['Cum_Qty'] = df['Qty_Step'].cumsum()
            df['Avg_Price'] = (df['Cum_Cost'] / df['Cum_Qty']).fillna(0)
            df['Market_Value'] = df['Cum_Qty'] * df['Price']
            df['ROI_Pct'] = (((df['Price'] - df['Avg_Price']) / df['Avg_Price']) * 100).fillna(0).round(2)

            # 实时价联动
            is_to_now = end_date >= datetime.now().date()
            live_p = get_cmc_price_safe(coin, cmc_api_key) if is_to_now else None
            
            final_p = live_p if (live_p and is_to_now) else df['Price'].iloc[-1]
            final_cost = df['Cum_Cost'].iloc[-1]
            final_qty = df['Cum_Qty'].iloc[-1]
            final_avg = final_cost / final_qty if final_qty > 0 else 0
            final_val = final_qty * final_p
            final_roi = ((final_val - final_cost) / final_cost * 100) if final_cost > 0 else 0

            # 渲染顶部指标
            st.info(f"📊 统计区间：{start_date} 至 {end_date}")
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("区间总投入", f"${final_cost:,.0f}")
            m2.metric(f"累计持仓", f"{final_qty:.4f}")
            m3.metric("持仓均价", f"${final_avg:,.2f}")
            m4.metric("实时价对比", f"{(final_p-final_avg)/final_avg*100:+.2f}%", delta_color="inverse")
            m5.metric("最终/实时市值", f"${final_val:,.0f}", f"{final_roi:+.2f}%")

            # 图表绘图 (Hover 保持本金市值显示)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df.index, y=df['Market_Value'], name="市值", fill='tonexty', 
                line=dict(color='#FF8C00', width=2),
                hovertemplate="<b>日期: %{x}</b><br>累计投入: $%{customdata[1]:,.0f}<br>账户市值: $%{y:,.0f}<br>盈亏比: %{customdata[2]:+.2f}%<extra></extra>",
                customdata=df[['Price', 'Cum_Cost', 'ROI_Pct']].values
            ))
            fig.add_trace(go.Scatter(x=df.index, y=df['Cum_Cost'], name="本金线", line=dict(color='gray', dash='dash')))
            fig.update_layout(template="plotly_white", hovermode="x unified", height=600)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("无法加载数据，请检查网络连接或尝试缩短日期区间。")

except Exception as e:
    st.error(f"❌ 程序遇到未知错误: {e}")
