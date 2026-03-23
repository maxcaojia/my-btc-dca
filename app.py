import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# 1. 网页配置
st.set_page_config(page_title="CRYPTO定投", layout="wide")

# --- UI 优化 ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: max(14px, 1.8vw) !important; white-space: nowrap; color: #FF8C00; }
    </style>
    """, unsafe_allow_html=True)

st.title("🧡 CRYPTO定投")

# 2. 获取 API Key
cmc_api_key = st.secrets.get("CMC_API_KEY")

# 3. 侧边栏
with st.sidebar:
    st.header("⚙️ 资产与策略")
    coin = st.selectbox("选择切换币种", ["BTC", "ETH", "SOL", "BNB", "XRP"])
    start_date = st.date_input("开始定投日期", value=datetime(2020, 1, 1))
    amount = st.number_input("每期定投金额 ($)", min_value=1, value=100)
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月"], index=2)
    
    target_day = 0
    if frequency == "每周":
        weekday_map = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6}
        selected_day = st.selectbox("选择周定投日", list(weekday_map.keys()))
        target_day = weekday_map[selected_day]
    elif frequency == "每月":
        target_day = st.slider("选择月定投日期 (1-28号)", 1, 28, 1)

# --- 核心逻辑 ---
try:
    with st.spinner(f'正在从全球市场抓取 {coin} 数据...'):
        symbol = f"{coin}-USD"
        # 抓取数据
        df_raw = yf.download(symbol, start=start_date, progress=False)
        
        if df_raw.empty:
            st.error("❌ 无法获取历史数据，请尝试更换开始日期或刷新页面。")
        else:
            # 提取价格
            if isinstance(df_raw.columns, pd.MultiIndex):
                df = df_raw.xs('Close', axis=1, level=0)[symbol].to_frame(name='Price')
            else:
                df = df_raw[['Close']].rename(columns={'Close': 'Price'})
            
            df.index = df.index + timedelta(hours=8) # 北京时间对齐

            # 定投标记
            if frequency == "每天":
                df['Is_DCA'] = True
            elif frequency == "每周":
                df['Is_DCA'] = df.index.weekday == target_day
            else: # 每月
                df['Is_DCA'] = df.index.day == target_day

            # 财务计算
            df['Cost_Step'] = df['Is_DCA'].apply(lambda x: amount if x else 0)
            df['Qty_Step'] = df.apply(lambda row: row['Cost_Step'] / row['Price'] if row['Is_DCA'] else 0, axis=1)
            df['Cum_Cost'] = df['Cost_Step'].cumsum()
            df['Cum_Qty'] = df['Qty_Step'].cumsum()
            df['Avg_Price'] = (df['Cum_Cost'] / df['Cum_Qty']).fillna(0)
            df['Market_Value'] = df['Cum_Qty'] * df['Price']
            df['ROI_Pct'] = (((df['Price'] - df['Avg_Price']) / df['Avg_Price']) * 100).fillna(0).round(2)

            # 实时价 (CMC)
            live_p = df['Price'].iloc[-1]
            if cmc_api_key:
                try:
                    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
                    r = requests.get(url, headers={'X-CMC_PRO_API_KEY': cmc_api_key}, params={'symbol': coin, 'convert': 'USD'})
                    live_p = r.json()['data'][coin]['quote']['USD']['price']
                except:
                    pass

            # 指标渲染
            f_cost = df['Cum_Cost'].iloc[-1]
            f_qty = df['Cum_Qty'].iloc[-1]
            f_avg = f_cost / f_qty if f_qty > 0 else 0
            f_val = f_qty * live_p
            f_roi = ((f_val - f_cost) / f_cost * 100) if f_cost > 0 else 0

            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("累计投入", f"${f_cost:,.0f}")
            m2.metric(f"持仓 {coin}", f"{f_qty:.4f}")
            m3.metric("均价", f"${f_avg:,.2f}")
            m4.metric("实时盈亏比", f"{f_roi:+.2f}%", delta_color="normal")
            m5.metric("当前总市值", f"${f_val:,.0f}")

            # 绘图
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df.index, y=df['Market_Value'], name="总市值", fill='tonexty', line=dict(color='#FF8C00')))
            fig.add_trace(go.Scatter(x=df.index, y=df['Cum_Cost'], name="本金线", line=dict(color='gray', dash='dash')))
            fig.update_layout(template="plotly_white", hovermode="x unified", height=500)
            st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.warning(f"💡 提示：正在同步数据中... ({str(e)})")
