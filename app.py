import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# 1. 网页配置
st.set_page_config(page_title="專業定投分析工具", layout="wide")
st.title("🧡 定投全景分析：BTC 減半事件聯動版")

# --- UI 优化补丁 (确保五卡片数字清晰) ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] {
        font-size: max(14px, 1.6vw) !important;
        white-space: nowrap;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.9vw !important;
    }
    </style>
    """, unsafe_allow_html=True)
# -------------------------------------

# 2. API Key 获取 (Secrets)
cmc_api_key = st.secrets.get("CMC_API_KEY") if "CMC_API_KEY" in st.secrets else None

# 3. 侧边栏设置
with st.sidebar:
    st.header("⚙️ 策略设置")
    coin = st.selectbox("选择币种", ["BTC", "ETH", "BNB", "SOL", "XRP"])
    start_date = st.date_input("开始定投日期", value=datetime(2020, 1, 1))
    amount = st.number_input("每期定投金额 ($)", min_value=1, value=100)
    
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月"], index=2)
    
    # 自由选择日逻辑
    target_day = 0
    if frequency == "每周":
        weekday_map = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6}
        selected_day = st.selectbox("选择每周定投日", list(weekday_map.keys()))
        target_day = weekday_map[selected_day]
    elif frequency == "每月":
        target_day = st.slider("选择每月定投号数", 1, 28, 1)

# --- 函数：数据抓取与 CMC 实时价 ---
def get_cmc_price(symbol, api_key):
    if not api_key: return None
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': api_key}
    try:
        response = requests.get(url, headers=headers, params={'symbol': symbol, 'convert': 'USD'})
        return response.json()['data'][symbol]['quote']['USD']['price']
    except: return None

@st.cache_data(ttl=300)
def get_aligned_data(coin_sym, start):
    symbol = f"{coin_sym}-USD"
    df = yf.download(symbol, start=start, progress=False)
    if df.empty: return None
    if isinstance(df.columns, pd.MultiIndex):
        temp = df['Close'].iloc[:, 0]
    else:
        temp = df['Close']
    res = temp.to_frame(name='Close')
    res.index = res.index + timedelta(hours=8)
    return res.dropna()

try:
    hist_raw = get_aligned_data(coin, start_date)
    
    if hist_raw is not None:
        # --- 精准定投筛选 ---
        if frequency == "每天":
            dca = hist_raw.copy()
        elif frequency == "每周":
            dca = hist_raw[hist_raw.index.weekday == target_day].copy()
        elif frequency == "每月":
            dca = hist_raw[hist_raw.index.day == target_day].copy()
        
        # 排除未发生今天
        now_bj = datetime.now() + timedelta(hours=8)
        dca = dca[dca.index < now_bj].dropna()
        
        # 获取 CMC 实时价
        realtime_p = get_cmc_price(coin, cmc_api_key)
        if realtime_p is None:
            realtime_p = hist_raw['Close'].iloc[-1]
            st.caption("⚠️ 使用备用实时行情")
        else:
            st.success(f"✅ CMC 实时价已对齐 (北京时间): ${realtime_p:,.2f}")

        # --- 指标计算 ---
        total_invested = len(dca) * amount
        qty_held = (amount / dca['Close']).sum()
        my_avg_price = total_invested / qty_held
        current_val = qty_held * realtime_p
        total_roi = (current_val - total_invested) / total_invested * 100
        price_diff_pct = (realtime_p - my_avg_price) / my_avg_price * 100

        # --- UI 卡片 (5个) ---
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("累计投入", f"${total_invested:,.0f}")
        m2.metric(f"持仓 {coin}", f"{qty_held:.4f}")
        m3.metric("持仓均价", f"${my_avg_price:,.2f}")
        m4.metric("实时价 vs 均价", f"{price_diff_pct:+.2f}%", delta_color="inverse")
        m5.metric("实时市值", f"${current_val:,.0f}", f"{total_roi:.2f}%")

        # --- 图表增强：包含 Hover 盈亏比和 BTC 减半标注 ---
        dca['Cumulative_Qty'] = qty_held
        dca['Portfolio_Value'] = qty_held * dca['Close']
        dca['Cumulative_Cost'] = [amount * (i+1) for i in range(len(dca))]
        
        # 计算每一天的实时盈亏比百分比
        dca['ROI_at_Time'] = (dca['Portfolio_Value'] - dca['Cumulative_Cost']) / dca['Cumulative_Cost'] * 100

        fig = go.Figure()

        # 1. 账户市值 (橙色填充线)
        fig.add_trace(go.Scatter(
            x=dca.index, 
            y=dca['Portfolio_Value'], 
            name="账户市值", 
            fill='tonexty', 
            line=dict(color='#FF8C00', width=3),
            fillcolor='rgba(255, 140, 0, 0.2)',
            hovertemplate = (
                "<b>日期: %{x}</b><br>" +
                "当时币价: $%{customdata[0]:,.2f}<br>" +
                "累计投入: $%{customdata[1]:,.0f}<br>" +
                "当前市值: $%{y:,.0f}<br>" +
                "<b>实时盈亏: %{customdata[2]:+.2f}%</b>" +
                "<extra></extra>"
            ),
            customdata=dca[['Close', 'Cumulative_Cost', 'ROI_at_Time']].values
        ))

        # 2. 投入本金线 (灰色虚线)
        fig.add_trace(go.Scatter(
            x=dca.index, 
            y=dca['Cumulative_Cost'], 
            name="投入本金", 
            line=dict(color='gray', dash='dash', width=2),
            hoverinfo='skip'
        ))
        
        # --- 新增：BTC 减半标注 (Halving Events) ---
        # 减半日期对齐北京时间 8:00
        halving_dates = ['2020-04-11', '2024-04-20', '2028-03-27'] 
        
        for hd in halving_dates:
            hd_bj = pd.to_datetime(hd) + timedelta(hours=8)
            # 只在当前图表日期范围内标注
            if hd_bj >= dca.index.min() and hd_bj <= dca.index.max():
                fig.add_vline(
                    x=hd_bj.timestamp() * 1000, 
                    line_dash="dot", 
                    line_color="red", 
                    annotation_text="BTC 減半", 
                    annotation_position="top left",
                    annotation_font=dict(color="red", size=14)
                )

        # 3. 布局优化
        fig.update_layout(
            title=f"{coin} 定投增长细节与 BTC 減半事件",
            xaxis_title="日期 (北京时间 8:00)",
            yaxis_title="金额 (USD)",
            hovermode="x unified",
            template="plotly_white",
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
        )
        
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📂 查看详细定投账单 (北京时间 8:00)"):
            st.dataframe(dca[['Close', 'Cumulative_Cost', 'ROI_at_Time', 'Portfolio_Value']].style.format("{:.2f}"))

except Exception as e:
    st.error(f"分析出错: {e}")
