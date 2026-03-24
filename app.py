import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import time

# 1. 网页基础配置
st.set_page_config(page_title="AHR999 自定義探測器", layout="wide")

st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: max(14px, 1.6vw) !important; white-space: nowrap; color: #FF8C00; }
    div[data-baseweb="datepicker"], div[data-baseweb="popover"] { z-index: 999999 !important; }
    section[data-testid="stSidebar"] > div { padding-bottom: 300px !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🧡 AHR999 自定義參數回測終端")

# 2. 侧边栏：核心控制
with st.sidebar:
    st.header("📅 1. 区间设置")
    start_date = st.date_input("开始日期", value=datetime(2020, 1, 1))
    end_date = st.date_input("截止日期", value=datetime.now().date())
    
    st.header("🎯 2. AHR999 探測參數")
    # --- 新增：用户自定义阈值 ---
    target_ahr = st.slider("自定义 AHR999 警戒线", 0.1, 5.0, 0.45, step=0.01)
    st.caption(f"当前统计所有 AHR999 < {target_ahr:.2f} 的历史时刻")

    st.header("⚙️ 3. 资产配置")
    coin = st.selectbox("选择资产", ["BTC", "ETH", "SOL", "BNB"], index=0)
    amount = st.number_input("每期定投金额 ($)", min_value=1, value=100)
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月"], index=0)

    if st.button("🔄 刷新全部数据"):
        st.cache_data.clear()
        st.rerun()

# --- AHR999 计算函数 ---
def calculate_ahr_full(df):
    df['MA200'] = df['Price'].rolling(window=200).mean()
    genesis = pd.to_datetime('2009-01-03')
    df['Days'] = (df.index - genesis).days
    df['Fit'] = 10**(5.84 * np.log10(df['Days']) - 17.01)
    df['AHR999'] = ((df['Price'] / df['Fit']) * (df['Price'] / df['MA200'])).round(2)
    return df

@st.cache_data(ttl=600)
def fetch_and_calc(coin_sym, start, end):
    symbol = f"{coin_sym}-USD"
    f_start = start - timedelta(days=350) # 预留均线计算空间
    try:
        data = yf.download(symbol, start=f_start, end=end + timedelta(days=1), progress=False, timeout=20)
        if data.empty: return None
        df = data.xs('Close', axis=1, level=0)[symbol].to_frame(name='Price') if isinstance(data.columns, pd.MultiIndex) else data[['Close']].rename(columns={'Close': 'Price'})
        df.index = df.index + timedelta(hours=8)
        df = calculate_ahr_full(df)
        return df[df.index >= pd.to_datetime(start)]
    except: return None

# --- 执行主逻辑 ---
try:
    df = fetch_and_calc(coin, start_date, end_date)
    
    if df is not None:
        # 1. 基础定投计算
        if frequency == "每天": df['Is_DCA'] = True
        elif frequency == "每周": df['Is_DCA'] = df.index.weekday == 0
        else: df['Is_DCA'] = df.index.day == 1

        df['Cost_In'] = df['Is_DCA'].apply(lambda x: amount if x else 0)
        df['Qty_In'] = df.apply(lambda r: r['Cost_In'] / r['Price'] if r['Is_DCA'] else 0, axis=1)
        df['Cum_Cost'] = df['Cost_In'].cumsum()
        df['Cum_Qty'] = df['Qty_Step'] = df['Qty_In'].cumsum()
        df['Portfolio_Value'] = df['Cum_Qty'] * df['Price']
        df['ROI_Pct'] = (((df['Portfolio_Value'] - df['Cum_Cost']) / df['Cum_Cost']) * 100).fillna(0).round(2)

        # 2. --- 核心：动态探测统计 ---
        # 筛选低于用户设定阈值的日子
        hit_df = df[df['AHR999'] < target_ahr].copy()
        
        # 3. 顶部指标展示
        latest = df.iloc[-1]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("最新 AHR999", f"{latest['AHR999']:.2f}")
        m2.metric(f"指数 < {target_ahr:.2f} 天数", f"{len(hit_df)}天")
        m3.metric("区间平均买入价", f"${hit_df['Price'].mean():,.2f}" if not hit_df.empty else "N/A")
        m4.metric("全段总盈亏", f"{latest['ROI_Pct']:+.2f}%")

        # 4. 图表渲染 (增加阈值参考线)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df.index, y=df['Portfolio_Value'], name="市值", fill='tonexty', line=dict(color='#FF8C00', width=2),
            hovertemplate="日期: %{x}<br>AHR999: %{customdata:.2f}<extra></extra>",
            customdata=df['AHR999']
        ))
        fig.add_trace(go.Scatter(x=df.index, y=df['AHR999'], name="AHR999指数", line=dict(color='blue', width=1, dash='dot'), yaxis="y2"))
        
        # 增加动态参考线
        fig.add_hline(y=target_ahr, line_dash="dash", line_color="red", annotation_text=f"你的探測線({target_ahr})", yref="y2")

        fig.update_layout(
            template="plotly_white", hovermode="x unified", height=500,
            yaxis2=dict(title="AHR999", overlaying="y", side="right", range=[0, 3])
        )
        st.plotly_chart(fig, use_container_width=True)

        # --- 5. 动态探测结果明细 ---
        st.subheader(f"📋 AHR999 < {target_ahr:.2f} 时的详细统计")
        if not hit_df.empty:
            stats_data = {
                "指标项目": ["出现天数", "期间平均币价", "期间最低币价", "期间最高币价", "期间平均指数值", "指数最低点"],
                "数值详情": [
                    f"{len(hit_df)} 天",
                    f"${hit_df['Price'].mean():,.2f}",
                    f"${hit_df['Price'].min():,.2f}",
                    f"${hit_df['Price'].max():,.2f}",
                    f"{hit_df['AHR999'].mean():.2f}",
                    f"{hit_df['AHR999'].min():.2f}"
                ]
            }
            st.table(pd.DataFrame(stats_data))
            
            with st.expander("📂 查看这些“黄金时刻”的日期明细"):
                st.dataframe(hit_df[['Price', 'AHR999', 'ROI_Pct']].style.format({"Price": "${:,.2f}", "AHR999": "{:.2f}", "ROI_Pct": "{:+.2f}%"}))
        else:
            st.warning(f"在该时间段内，AHR999 从未低于 {target_ahr:.2f}。请尝试调高阈值或扩大日期范围。")

except Exception as e:
    st.error(f"分析出错: {e}")
