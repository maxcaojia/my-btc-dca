import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import time

# 1. 网页基础配置
st.set_page_config(page_title="AHR999 實時定投終端", layout="wide")

# --- UI 样式优化补丁 ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: max(14px, 1.6vw) !important; white-space: nowrap; color: #FF8C00; }
    div[data-baseweb="datepicker"], div[data-baseweb="popover"] { z-index: 999999 !important; }
    section[data-testid="stSidebar"] > div { padding-bottom: 300px !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🧡 AHR999 定投全景分析 (實時戰況版)")

# 2. 从后台获取 API Key
cmc_api_key = st.secrets.get("CMC_API_KEY")

# 3. 侧边栏
with st.sidebar:
    st.header("📅 1. 区间设置")
    start_date = st.date_input("定投开始日期", value=datetime(2020, 1, 1))
    end_date = st.date_input("定投截止日期", value=datetime.now().date())
    
    st.header("🎯 2. AHR999 探测参数")
    target_ahr = st.slider("自定义探测线 (统计低于此值的日子)", 0.1, 3.0, 0.45, step=0.01)

    st.header("⚙️ 3. 资产与策略")
    coin = st.selectbox("选择切换币种", ["BTC", "ETH", "SOL", "BNB"], index=0)
    amount = st.number_input("每期定投金额 ($)", min_value=1, value=100)
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月"], index=0)
    
    if st.button("🔄 强制刷新数据"):
        st.cache_data.clear()
        st.rerun()

# --- 核心算法：几何平均 AHR999 ---
def calculate_ahr999_core(df):
    df['Log_Price'] = np.log(df['Price'])
    df['Geo_MA200'] = np.exp(df['Log_Price'].rolling(window=200).mean())
    genesis = pd.to_datetime('2009-01-03')
    df['Days_Passed'] = (df.index - genesis).days
    df['Fit_Price'] = 10**(5.84 * np.log10(df['Days_Passed']) - 17.01)
    df['AHR999'] = ((df['Price'] / df['Fit_Price']) * (df['Price'] / df['Geo_MA200'])).round(2)
    return df

@st.cache_data(ttl=600)
def fetch_data_stable(coin_sym, start, end, retries=3):
    symbol = f"{coin_sym}-USD"
    f_start = start - timedelta(days=400)
    for i in range(retries):
        try:
            data = yf.download(symbol, start=f_start, end=end + timedelta(days=1), progress=False, timeout=15)
            if not data.empty:
                df = data.xs('Close', axis=1, level=0)[symbol].to_frame(name='Price') if isinstance(data.columns, pd.MultiIndex) else data[['Close']].rename(columns={'Close': 'Price'})
                df.index = df.index + timedelta(hours=8) # 北京时间 08:00
                df = calculate_ahr999_core(df)
                return df[df.index >= pd.to_datetime(start)]
        except Exception:
            if i < retries - 1: time.sleep(1); continue
    return None

# --- 执行主逻辑 ---
try:
    with st.spinner('📡 正在同步全球實時數據...'):
        df_all = fetch_data_stable(coin, start_date, end_date)
    
    if df_all is not None:
        # 1. 财务回测计算
        if frequency == "每天": df_all['Is_DCA'] = True
        elif frequency == "每周": df_all['Is_DCA'] = df_all.index.weekday == 0
        else: df_all['Is_DCA'] = df_all.index.day == 1

        df_all['Cost_In'] = df_all['Is_DCA'].apply(lambda x: amount if x else 0)
        df_all['Qty_In'] = df_all.apply(lambda r: r['Cost_In'] / r['Price'] if r['Is_DCA'] else 0, axis=1)
        df_all['Cum_Cost'] = df_all['Cost_In'].cumsum()
        df_all['Cum_Qty'] = df_all['Qty_In'].cumsum()
        df_all['Market_Value'] = df_all['Cum_Qty'] * df_all['Price']
        df_all['ROI_Pct'] = (((df_all['Market_Value'] - df_all['Cum_Cost']) / df_all['Cum_Cost']) * 100).fillna(0).round(2)

        # 2. 指标展示
        latest = df_all.iloc[-1]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("當前 AHR999", f"{latest['AHR999']:.2f}")
        m2.metric("累計投入", f"${latest['Cum_Cost']:,.0f}")
        m3.metric("當前市值", f"${latest['Market_Value']:,.0f}")
        m4.metric("總盈虧比", f"{latest['ROI_Pct']:+.2f}%")

        # 3. 增强版图表 (包含实时币价、市值、盈亏)
        fig = go.Figure()
        
        # 账户市值 (主曲线)
        fig.add_trace(go.Scatter(
            x=df_all.index, y=df_all['Market_Value'], name="市值", fill='tonexty', 
            line=dict(color='#FF8C00', width=2), fillcolor='rgba(255, 140, 0, 0.15)',
            # 核心改进：悬停显示所有实时关键信息
            hovertemplate=(
                "<b>📅 日期: %{x}</b><br>" +
                "🪙 實時幣價: $%{customdata[0]:,.2f}<br>" +
                "💰 累計投入: $%{customdata[1]:,.0f}<br>" +
                "📈 當前市值: $%{y:,.0f}<br>" +
                "<b>📊 盈虧程度: %{customdata[2]:+.2f}%</b><br>" +
                "📐 AHR999: %{customdata[3]:.2f}" +
                "<extra></extra>"
            ),
            # 传递：币价, 累计本金, 盈亏比, AHR999
            customdata=df_all[['Price', 'Cum_Cost', 'ROI_Pct', 'AHR999']].values
        ))
        
        # AHR999 (蓝色实线)
        fig.add_trace(go.Scatter(
            x=df_all.index, y=df_all['AHR999'], name="AHR999指數", 
            line=dict(color='blue', width=2.5, dash='solid'), 
            yaxis="y2",
            hoverinfo='skip' # 避免悬停框重叠，数据已整合进市值悬停
        ))
        
        # 本金线
        fig.add_trace(go.Scatter(
            x=df_all.index, y=df_all['Cum_Cost'], name="投入本金", 
            line=dict(color='#666666', dash='dash', width=2),
            hoverinfo='skip'
        ))
        
        # 探测阈值线
        fig.add_hline(y=target_ahr, line_dash="dash", line_color="red", annotation_text=f"探測:{target_ahr}", yref="y2")

        fig.update_layout(
            template="plotly_white", hovermode="x unified", height=600,
            yaxis=dict(title="價值 (USD)"),
            yaxis2=dict(title="AHR999", overlaying="y", side="right", range=[0, 3.5]),
            legend=dict(orientation="h", y=1.05)
        )
        st.plotly_chart(fig, use_container_width=True)

        # 4. 底部统计表格
        hit_df = df_all[df_all['AHR999'] < target_ahr].copy()
        st.subheader(f"📋 AHR999 < {target_ahr:.2f} 歷史記錄")
        st.dataframe(hit_df[['Price', 'AHR999', 'Cum_Cost', 'Market_Value', 'ROI_Pct']].style.format({
            "Price": "${:,.2f}", "AHR999": "{:.2f}", "Cum_Cost": "${:,.0f}", 
            "Market_Value": "${:,.0f}", "ROI_Pct": "{:+.2f}%"
        }), height=400)

except Exception as e:
    st.error(f"❌ 程序運行異常: {e}")
