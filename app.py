import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# 1. 网页基础配置
st.set_page_config(page_title="AHR999 專業對齊版", layout="wide")

# --- UI 样式：解决日历遮挡与层级问题 ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: max(14px, 1.6vw) !important; white-space: nowrap; color: #FF8C00; }
    div[data-baseweb="datepicker"], div[data-baseweb="popover"] { z-index: 999999 !important; }
    section[data-testid="stSidebar"] > div { padding-bottom: 300px !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🧡 AHR999 深度對齊終端 (UTC+8 08:00 同步)")

# 2. 从后台获取 API Key
cmc_api_key = st.secrets.get("CMC_API_KEY")

# 3. 侧边栏：区间与策略控制
with st.sidebar:
    st.header("📅 1. 区间设置")
    start_date = st.date_input("定投开始日期", value=datetime(2023, 1, 1))
    end_date = st.date_input("定投截止日期", value=datetime.now().date())
    
    st.header("🎯 2. AHR999 探测参数")
    target_ahr = st.slider("自定义探测线", 0.1, 2.0, 0.45, step=0.01)

    st.header("⚙️ 3. 资产配置")
    coin = "BTC" # AHR999 核心建议只看 BTC
    amount = st.number_input("每期定投金额 ($)", min_value=1, value=100)
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月"], index=0)

    if st.button("🔄 强制重置数据"):
        st.cache_data.clear()
        st.rerun()

# --- 核心：几何平均 AHR999 算法 (對齊 CoinGlass) ---
def calculate_ahr999_final(df):
    # 200日几何平均 (Geometric Mean)
    # 计算逻辑：对价格取对数 -> 求均值 -> 指数还原
    df['Log_Price'] = np.log(df['Price'])
    df['Geo_MA200'] = np.exp(df['Log_Price'].rolling(window=200).mean())
    
    # 币龄拟合线 (九神公式)
    genesis = pd.to_datetime('2009-01-03')
    df['Days_Passed'] = (df.index - genesis).days
    df['Fit_Price'] = 10**(5.84 * np.log10(df['Days_Passed']) - 17.01)
    
    # AHR999 计算
    df['AHR999_Raw'] = (df['Price'] / df['Fit_Price']) * (df['Price'] / df['Geo_MA200'])
    df['AHR999'] = df['AHR999_Raw'].round(2)
    return df

@st.cache_data(ttl=600)
def fetch_and_sync(start, end):
    symbol = "BTC-USD"
    # 为了均线稳定，向前追溯 400 天
    f_start = start - timedelta(days=400)
    try:
        data = yf.download(symbol, start=f_start, end=end + timedelta(days=1), progress=False, timeout=20)
        if data.empty: return None
        # 提取收盘价
        df = data.xs('Close', axis=1, level=0)[symbol].to_frame(name='Price') if isinstance(data.columns, pd.MultiIndex) else data[['Close']].rename(columns={'Close': 'Price'})
        # 核心对齐：保持 08:00 结算逻辑
        df.index = df.index + timedelta(hours=8)
        df = calculate_ahr999_final(df)
        return df[df.index >= pd.to_datetime(start)]
    except: return None

# --- 执行主逻辑 ---
try:
    df = fetch_and_sync(start_date, end_date)
    
    if df is not None:
        # 1. 财务计算
        if frequency == "每天": df['Is_DCA'] = True
        elif frequency == "每周": df['Is_DCA'] = df.index.weekday == 0
        else: df['Is_DCA'] = df.index.day == 1

        df['Cost_In'] = df['Is_DCA'].apply(lambda x: amount if x else 0)
        df['Qty_In'] = df.apply(lambda r: r['Cost_In'] / r['Price'] if r['Is_DCA'] else 0, axis=1)
        df['Cum_Cost'] = df['Cost_In'].cumsum()
        df['Cum_Qty'] = df['Qty_In'].cumsum()
        df['Portfolio_Value'] = df['Cum_Qty'] * df['Price']
        df['Avg_Price'] = (df['Cum_Cost'] / df['Cum_Qty']).fillna(0)
        df['ROI_Pct'] = (((df['Portfolio_Value'] - df['Cum_Cost']) / df['Cum_Cost']) * 100).fillna(0).round(2)

        # 2. 指标显示
        latest = df.iloc[-1]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("當前 AHR999", f"{latest['AHR999']:.2f}")
        m2.metric("200日幾何成本", f"${latest['Geo_MA200']:,.2f}")
        m3.metric("總投入本金", f"${latest['Cum_Cost']:,.0f}")
        m4.metric("全段盈虧比", f"{latest['ROI_Pct']:+.2f}%")

        # 3. 增强版图表 (蓝色实线 + 悬停显示)
        fig = go.Figure()
        
        # 市值面积 (层级底)
        fig.add_trace(go.Scatter(
            x=df.index, y=df['Portfolio_Value'], name="账户价值", fill='tonexty', 
            line=dict(color='#FF8C00', width=2),
            fillcolor='rgba(255, 140, 0, 0.1)',
            hovertemplate="日期: %{x}<br>AHR999: %{customdata:.2f}<br>市值: $%{y:,.0f}<extra></extra>",
            customdata=df['AHR999']
        ))
        
        # AHR999 (蓝色实线)
        fig.add_trace(go.Scatter(
            x=df.index, y=df['AHR999'], name="AHR999指數", 
            line=dict(color='blue', width=2, dash='solid'), # <-- 蓝色实线
            yaxis="y2"
        ))

        # 探测虚线
        fig.add_hline(y=target_ahr, line_dash="dash", line_color="red", annotation_text=f"探测线:{target_ahr}", yref="y2")

        fig.update_layout(
            template="plotly_white", hovermode="x unified", height=600,
            yaxis=dict(title="价值 (USD)"),
            yaxis2=dict(title="AHR999", overlaying="y", side="right", range=[0, 3]),
            legend=dict(orientation="h", y=1.05)
        )
        st.plotly_chart(fig, use_container_width=True)

        # 4. 详细明细表格
        st.subheader("📋 AHR999 分段數據明细")
        st.dataframe(df[['Price', 'AHR999', 'Geo_MA200', 'Fit_Price']].tail(15).style.format({
            "Price": "${:,.2f}", "AHR999": "{:.2f}", "Geo_MA200": "${:,.2f}", "Fit_Price": "${:,.2f}"
        }))

except Exception as e:
    st.error(f"❌ 系统暂时不可用，请点击刷新按钮: {e}")
