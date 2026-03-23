import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# 1. 网页基础配置
st.set_page_config(page_title="CMC 区间定投回测", layout="wide")

# --- UI 样式优化 ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.6vw !important; color: #FF8C00; }
    .stSuccess { background-color: rgba(255, 140, 0, 0.1) !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("💎 CMC 实时联动：任意区间定投回测终端")

# 2. 从后台获取你的 API Key
cmc_api_key = st.secrets.get("CMC_API_KEY")

# 3. 侧边栏：区间与策略配置
with st.sidebar:
    st.header("📅 时间区间设置")
    # 让你可以自由选择开始和结束
    start_date = st.date_input("定投开始日期", value=datetime(2024, 3, 15))
    end_date = st.date_input("定投截止日期", value=datetime(2025, 4, 15))
    
    if start_date >= end_date:
        st.error("错误：开始日期必须早于截止日期")
        st.stop()

    st.header("⚙️ 资产与频率")
    coin = st.selectbox("同步币种", ["BTC", "ETH", "SOL", "BNB", "XRP"])
    amount = st.number_input("每期定投金额 ($)", min_value=1, value=100)
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月"], index=0)
    
    target_day = 0
    if frequency == "每周":
        weekday_map = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6}
        selected_day = st.selectbox("选择周定投日", list(weekday_map.keys()))
        target_day = weekday_map[selected_day]
    elif frequency == "每月":
        target_day = st.slider("选择月定投日期", 1, 28, 1)

# --- 函数：CMC 实时报价 ---
def get_cmc_price(symbol, api_key):
    if not api_key: return None
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': api_key}
    try:
        r = requests.get(url, headers=headers, params={'symbol': symbol, 'convert': 'USD'})
        return r.json()['data'][symbol]['quote']['USD']['price']
    except: return None

# --- 执行引擎 ---
try:
    with st.spinner(f'正在分析 {start_date} 至 {end_date} 的数据...'):
        # 抓取数据（稍微多抓一点以确保包含边界）
        symbol = f"{coin}-USD"
        df_raw = yf.download(symbol, start=start_date, end=end_date + timedelta(days=1), progress=False)
        
        if df_raw.empty:
            st.error("该区间内无有效行情数据。")
        else:
            # 数据清洗
            if isinstance(df_raw.columns, pd.MultiIndex):
                df = df_raw.xs('Close', axis=1, level=0)[symbol].to_frame(name='Price')
            else:
                df = df_raw[['Close']].rename(columns={'Close': 'Price'})
            
            df.index = df.index + timedelta(hours=8) # 北京时间对齐

            # A. 标记定投触发
            if frequency == "每天":
                df['Is_DCA'] = True
            elif frequency == "每周":
                df['Is_DCA'] = df.index.weekday == target_day
            else:
                df['Is_DCA'] = df.index.day == target_day

            # B. 核心财务计算
            df['Cost_Step'] = df['Is_DCA'].apply(lambda x: amount if x else 0)
            df['Qty_Step'] = df.apply(lambda r: r['Cost_Step']/r['Price'] if r['Is_DCA'] else 0, axis=1)
            
            df['Total_Cost'] = df['Cost_Step'].cumsum()
            df['Total_Qty'] = df['Qty_Step'].cumsum()
            df['Avg_Price'] = (df['Total_Cost'] / df['Total_Qty']).fillna(0)
            df['Portfolio_Value'] = df['Total_Qty'] * df['Price']
            df['ROI_Pct'] = (((df['Price'] - df['Avg_Price']) / df['Avg_Price']) * 100).fillna(0).round(2)

            # C. 实时数据对接（仅当截止日期是今天或以后时才显示实时价）
            is_to_now = end_date >= datetime.now().date()
            live_p = get_cmc_price(coin, cmc_api_key) if is_to_now else None
            
            # 最终回测点数据
            f_price = live_p if (live_p and is_to_now) else df['Price'].iloc[-1]
            f_cost = df['Total_Cost'].iloc[-1]
            f_qty = df['Total_Qty'].iloc[-1]
            f_avg = f_cost / f_qty if f_qty > 0 else 0
            f_val = f_qty * f_price
            f_roi = ((f_val - f_cost) / f_cost * 100) if f_cost > 0 else 0

            # D. 指标渲染
            st.info(f"📅 回测区间：{start_date} 至 {end_date} (共计定投 {len(df[df['Is_DCA']])} 期)")
            
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("区间总投入", f"${f_cost:,.0f}")
            m2.metric(f"累计持仓 {coin}", f"{f_qty:.4f}")
            m3.metric("区间持仓均价", f"${f_avg:,.2f}")
            m4.metric("区间盈亏率", f"{f_roi:+.2f}%")
            m5.metric("截止日市值", f"${f_val:,.0f}")

            # E. 绘图
            fig = go.Figure()
            # 市值增长
            fig.add_trace(go.Scatter(
                x=df.index, y=df['Portfolio_Value'], name="账户市值", 
                fill='tonexty', line=dict(color='#FF8C00', width=2),
                hovertemplate="日期: %{x}<br>当时币价: $%{customdata[0]:,.2f}<br>盈亏比: %{customdata[1]:+.2f}%<extra></extra>",
                customdata=df[['Price', 'ROI_Pct']].values
            ))
            # 本金线
            fig.add_trace(go.Scatter(x=df.index, y=df['Total_Cost'], name="本金线", line=dict(color='gray', dash='dash')))
            
            fig.update_layout(
                title=f"{coin} 区间定投表现分析",
                template="plotly_white", 
                hovermode="x unified", 
                height=550
            )
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("📂 查看定投详细日志"):
                st.dataframe(df[df['Is_DCA']][['Price', 'Total_Cost', 'Total_Qty', 'Avg_Price']].style.format("{:.2f}"))

except Exception as e:
    st.error(f"分析出错：{e}")
