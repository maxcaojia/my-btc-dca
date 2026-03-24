import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# 1. 网页基础配置
st.set_page_config(page_title="AHR999 全動態回測系統", layout="wide")

# --- UI 样式補丁 ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: max(14px, 1.6vw) !important; white-space: nowrap; color: #FF8C00; }
    div[data-baseweb="datepicker"], div[data-baseweb="popover"] { z-index: 999999 !important; }
    section[data-testid="stSidebar"] > div { padding-bottom: 300px !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🧡 AHR999 全動態歷史探測器")

# 2. 侧边栏：核心交互
with st.sidebar:
    st.header("📅 1. 自定義回測區間")
    # 這裡現在完全由你決定，不再死板
    start_date = st.date_input("回測開始日期", value=datetime(2020, 1, 1))
    end_date = st.date_input("回測截止日期", value=datetime.now().date())
    
    st.header("🎯 2. AHR999 門檻設置")
    target_ahr = st.slider("自定義探測閾值 (顯示低於此值的日子)", 0.1, 3.0, 0.45, step=0.01)

    st.header("⚙️ 3. 策略參數")
    amount = st.number_input("每期定投金額 ($)", min_value=1, value=100)
    frequency = st.selectbox("定投頻率", ["每天", "每周", "每月"], index=0)

    if st.button("🔄 刷新並重新計算"):
        st.cache_data.clear()
        st.rerun()

# --- 核心算法：幾何平均對齊 ---
def calculate_ahr999_dynamic(df):
    # 幾何平均計算 (200日)
    df['Log_Price'] = np.log(df['Price'])
    df['Geo_MA200'] = np.exp(df['Log_Price'].rolling(window=200).mean())
    # 九神擬合線
    genesis = pd.to_datetime('2009-01-03')
    df['Days_Since'] = (df.index - genesis).days
    df['Fit_Price'] = 10**(5.84 * np.log10(df['Days_Since']) - 17.01)
    # AHR999 計算
    df['AHR999'] = ((df['Price'] / df['Fit_Price']) * (df['Price'] / df['Geo_MA200'])).round(2)
    return df

@st.cache_data(ttl=600)
def fetch_data(start, end):
    symbol = "BTC-USD"
    # 為了確保起始日的 MA200 準確，自動向前追溯 400 天
    f_start = start - timedelta(days=400)
    try:
        data = yf.download(symbol, start=f_start, end=end + timedelta(days=1), progress=False)
        if data.empty: return None
        # 數據提取與 UTC+8 對齊
        df = data.xs('Close', axis=1, level=0)[symbol].to_frame(name='Price') if isinstance(data.columns, pd.MultiIndex) else data[['Close']].rename(columns={'Close': 'Price'})
        df.index = df.index + timedelta(hours=8)
        df = calculate_ahr999_dynamic(df)
        # 精準切回用戶選定的時間段
        return df[df.index >= pd.to_datetime(start)]
    except: return None

# --- 執行引擎 ---
try:
    df_raw = fetch_data(start_date, end_date)
    
    if df_raw is not None:
        # 1. 篩選邏輯：完全響應 slider 的數值
        df_filtered = df_raw[df_raw['AHR999'] < target_ahr].copy()
        
        # 2. 頂部看板
        m1, m2, m3 = st.columns(3)
        m1.metric("當前區間最新指數", f"{df_raw.iloc[-1]['AHR999']:.2f}")
        m2.metric(f"符合閾值 ({target_ahr}) 天數", f"{len(df_filtered)} 天")
        m3.metric("該狀態下平均幣價", f"${df_filtered['Price'].mean():,.2f}" if not df_filtered.empty else "N/A")

        # 3. 趨勢圖表 (藍色實線)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_raw.index, y=df_raw['AHR999'], name="AHR999指數", line=dict(color='blue', width=2)))
        fig.add_hline(y=target_ahr, line_dash="dash", line_color="red", annotation_text=f"你的探測線:{target_ahr}")
        fig.update_layout(template="plotly_white", title="AHR999 歷史走勢", yaxis=dict(title="指數值", range=[0, 3]))
        st.plotly_chart(fig, use_container_width=True)

        # 4. 全量數據表 (移除 tail 限制)
        st.subheader(f"📋 數據明細：AHR999 < {target_ahr:.2f} (全區間追蹤)")
        if not df_filtered.empty:
            # 這裡會顯示該區間內所有的符合條件的數據，不再被截斷
            st.dataframe(df_filtered[['Price', 'AHR999', 'Geo_MA200', 'Fit_Price']].style.format({
                "Price": "${:,.2f}", "AHR999": "{:.2f}", "Geo_MA200": "${:,.2f}", "Fit_Price": "${:,.2f}"
            }), height=400) # 設置高度以便滾動查看
            
            # 增加下載按鈕
            csv = df_filtered.to_csv().encode('utf-8')
            st.download_button(
                label="📥 下載符合條件的 CSV 數據",
                data=csv,
                file_name=f"ahr999_under_{target_ahr}_{start_date}.csv",
                mime='text/csv',
            )
        else:
            st.warning(f"在您選擇的區間 {start_date} 至 {end_date} 內，沒有指數低於 {target_ahr:.2f} 的記錄。")

except Exception as e:
    st.error(f"❌ 分析出錯：{e}")
