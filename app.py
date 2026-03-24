import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import time

# 1. 网页基础配置
st.set_page_config(page_title="AHR999 策略深度回测", layout="wide")

st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: max(14px, 1.6vw) !important; white-space: nowrap; color: #FF8C00; }
    div[data-baseweb="datepicker"], div[data-baseweb="popover"] { z-index: 999999 !important; }
    section[data-testid="stSidebar"] > div { padding-bottom: 300px !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("CRYPTO定投 全景分析")

# 2. 侧边栏：区间与策略配置
with st.sidebar:
    st.header("📅 时间区间设置")
    start_date = st.date_input("开始日期", value=datetime(2023, 1, 1))
    end_date = st.date_input("截止日期", value=datetime.now().date())
    
    st.header("⚙️ 定投配置")
    coin = st.selectbox("选择资产 (建议BTC)", ["BTC", "ETH", "SOL", "BNB"], index=0)
    amount = st.number_input("每期定投金额 ($)", min_value=1, value=100)
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月"], index=0)

    if st.button("🔄 强制重置数据"):
        st.cache_data.clear()
        st.rerun()

# --- AHR999 核心算法 ---
def get_ahr999_metrics(df):
    # 200日均线
    df['MA200'] = df['Price'].rolling(window=200).mean()
    # 币龄拟合线
    genesis = pd.to_datetime('2009-01-03')
    df['Days'] = (df.index - genesis).days
    df['Fit'] = 10**(5.84 * np.log10(df['Days']) - 17.01)
    # AHR999 计算
    df['AHR999'] = ((df['Price'] / df['Fit']) * (df['Price'] / df['MA200'])).round(2)
    return df

@st.cache_data(ttl=600)
def fetch_and_calc(coin_sym, start, end):
    symbol = f"{coin_sym}-USD"
    # 为了 MA200 准确，必须向前追溯
    f_start = start - timedelta(days=350)
    try:
        data = yf.download(symbol, start=f_start, end=end + timedelta(days=1), progress=False, timeout=20)
        if data.empty: return None
        df = data.xs('Close', axis=1, level=0)[symbol].to_frame(name='Price') if isinstance(data.columns, pd.MultiIndex) else data[['Close']].rename(columns={'Close': 'Price'})
        df.index = df.index + timedelta(hours=8)
        df = get_ahr999_metrics(df)
        return df[df.index >= pd.to_datetime(start)]
    except: return None

# --- 执行主逻辑 ---
try:
    df = fetch_and_calc(coin, start_date, end_date)
    
    if df is not None:
        # 定投逻辑
        if frequency == "每天": df['Is_DCA'] = True
        elif frequency == "每周": df['Is_DCA'] = df.index.weekday == 0
        else: df['Is_DCA'] = df.index.day == 1

        df['Cost_In'] = df['Is_DCA'].apply(lambda x: amount if x else 0)
        df['Qty_In'] = df.apply(lambda r: r['Cost_In'] / r['Price'] if r['Is_DCA'] else 0, axis=1)
        df['Cum_Cost'] = df['Cost_In'].cumsum()
        df['Cum_Qty'] = df['Qty_In'].cumsum()
        df['Portfolio_Value'] = df['Cum_Qty'] * df['Price']
        df['ROI_Pct'] = (((df['Portfolio_Value'] - df['Cum_Cost']) / df['Cum_Cost']) * 100).fillna(0).round(2)

        # --- AHR999 区间统计深度分析 ---
        # 定义区间
        bins = [0, 0.45, 1.2, 5.0, 100]
        labels = ['抄底区(<0.45)', '定投区(0.45-1.2)', '持有区(1.2-5.0)', '风险区(>5.0)']
        df['AHR_Zone'] = pd.cut(df['AHR999'], bins=bins, labels=labels)

        # 聚合统计
        zone_stats = df.groupby('AHR_Zone', observed=True).agg({
            'Price': ['count', 'mean'],
            'Cost_In': 'sum',
            'AHR999': ['min', 'max', 'mean']
        })
        zone_stats.columns = ['持续天数', '平均币价', '累计投入本金', '区间最小值', '区间最大值', '平均指数']
        
        # 指标展示
        latest = df.iloc[-1]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("当前 AHR999", f"{latest['AHR999']:.2f}")
        m2.metric("累计投入", f"${latest['Cum_Cost']:,.0f}")
        m3.metric("当前价值", f"${latest['Portfolio_Value']:,.0f}")
        m4.metric("总盈亏比", f"{latest['ROI_Pct']:+.2f}%")

        # --- 绘图 ---
        fig = go.Figure()
        # 市值线
        fig.add_trace(go.Scatter(
            x=df.index, y=df['Portfolio_Value'], name="账户价值", fill='tonexty', line=dict(color='#FF8C00', width=2),
            hovertemplate="日期: %{x}<br>AHR999: %{customdata:.2f}<br>市值: $%{y:,.0f}<extra></extra>",
            customdata=df['AHR999']
        ))
        # AHR999 副轴
        fig.add_trace(go.Scatter(x=df.index, y=df['AHR999'], name="AHR999指数", line=dict(color='blue', width=1, dash='dot'), yaxis="y2"))
        
        fig.update_layout(
            template="plotly_white", hovermode="x unified", height=500,
            yaxis=dict(title="价值 (USD)"),
            yaxis2=dict(title="AHR999", overlaying="y", side="right", range=[0, 3]),
            legend=dict(orientation="h", y=1.1)
        )
        st.plotly_chart(fig, use_container_width=True)

        # --- 重点：AHR999 区间表现明细 ---
        st.subheader("📋 AHR999 分段投入明细")
        st.write("根据您选择的时间区间，不同 AHR999 阶段的持仓贡献如下：")
        st.table(zone_stats.style.format({
            '平均币价': '${:,.2f}',
            '累计投入本金': '${:,.0f}',
            '区间最小值': '{:.2f}',
            '区间最大值': '{:.2f}',
            '平均指数': '{:.2f}'
        }))

        with st.expander("📂 下载完整原始数据表"):
            st.dataframe(df[['Price', 'AHR999', 'AHR_Zone', 'Cum_Cost', 'ROI_Pct']])

    else:
        st.error("数据加载失败，请检查网络或点击刷新。")

except Exception as e:
    st.error(f"分析出错: {e}")
