import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# 1. 网页基础配置
st.set_page_config(page_title="加密货币多资产回测工具", layout="wide")
st.title("🧡 多资产定投全景分析 (精准对齐版)")

# --- UI 样式优化：确保数字显示不全时自动缩放 ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: max(14px, 1.6vw) !important; white-space: nowrap; }
    [data-testid="stMetricLabel"] { font-size: 0.9vw !important; }
    </style>
    """, unsafe_allow_html=True)

# 2. 从 Secrets 读取 API Key
cmc_api_key = st.secrets.get("CMC_API_KEY")

# 3. 侧边栏：多资产切换设置
with st.sidebar:
    st.header("⚙️ 资产与策略")
    # 增加 BNB
    coin = st.selectbox("选择切换币种", ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA"])
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

# --- 数据抓取：带币种隔离的缓存 ---
@st.cache_data(ttl=300)
def get_crypto_data(coin_sym, start):
    symbol = f"{coin_sym}-USD"
    # 获取全量日线数据
    df = yf.download(symbol, start=start, progress=False)
    if df.empty: return None
    
    # 精准提取当前币种的收盘价，防止多级索引混淆
    if isinstance(df.columns, pd.MultiIndex):
        temp = df.xs('Close', axis=1, level=0)[symbol]
    else:
        temp = df['Close']
    
    res = temp.to_frame(name='Price')
    res.index = res.index + timedelta(hours=8) # 对齐北京时间 8:00
    return res.dropna()

def get_realtime_price(symbol, api_key):
    if not api_key: return None
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': api_key}
    try:
        response = requests.get(url, headers=headers, params={'symbol': symbol, 'convert': 'USD'})
        return response.json()['data'][symbol]['quote']['USD']['price']
    except: return None

# --- 执行计算逻辑 ---
try:
    df = get_crypto_data(coin, start_date)
    
    if df is not None:
        # A. 标记该币种的定投触发日
        if frequency == "每天":
            df['Is_DCA'] = True
        elif frequency == "每周":
            df['Is_DCA'] = df.index.weekday == target_day
        elif frequency == "每月":
            df['Is_DCA'] = df.index.day == target_day
        
        # B. 核心财务计算
        # 仅在定投日产生支出和购入币数
        df['Cost_Step'] = df['Is_DCA'].apply(lambda x: amount if x else 0)
        df['Qty_Step'] = df.apply(lambda row: row['Cost_Step'] / row['Price'] if row['Is_DCA'] else 0, axis=1)
        
        # 累计数据
        df['Cum_Cost'] = df['Cost_Step'].cumsum()
        df['Cum_Qty'] = df['Qty_Step'].cumsum()
        
        # 计算该币种此时此刻的持仓均价
        df['Avg_Price'] = (df['Cum_Cost'] / df['Cum_Qty']).fillna(0)
        # 当前市值与盈亏
        df['Market_Value'] = df['Cum_Qty'] * df['Price']
        df['ROI_Pct'] = ((df['Price'] - df['Avg_Price']) / df['Avg_Price'] * 100).fillna(0)

        # 获取 CMC 实时价 (若失败则用最后一天日线价)
        live_price = get_realtime_price(coin, cmc_api_key) or df['Price'].iloc[-1]
        
        # C. 顶部五个核心指标
        final_cost = df['Cum_Cost'].iloc[-1]
        final_qty = df['Cum_Qty'].iloc[-1]
        final_avg = final_cost / final_qty if final_qty > 0 else 0
        final_value = final_qty * live_price
        final_roi = ((final_value - final_cost) / final_cost * 100) if final_cost > 0 else 0
        diff_vs_avg = ((live_price - final_avg) / final_avg * 100) if final_avg > 0 else 0

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("累计总投入", f"${final_cost:,.0f}")
        m2.metric(f"累计持仓 {coin}", f"{final_qty:.4f}")
        m3.metric(f"{coin} 持仓均价", f"${final_avg:,.2f}")
        m4.metric("实时价 vs 均价", f"{diff_vs_avg:+.2f}%", delta_color="inverse")
        m5.metric("实时账户市值", f"${final_value:,.0f}", f"{final_roi:+.2f}%")

        if cmc_api_key:
            st.success(f"✅ 已连接 CMC：{coin} 实时价格 ${live_price:,.2f} 已精准同步")

        # D. 专业 Plotly 图表
        fig = go.Figure()
        
        # 市值填充线 (橙色)
        fig.add_trace(go.Scatter(
            x=df.index, y=df['Market_Value'], name=f"{coin} 市值", 
            fill='tonexty', line=dict(color='#FF8C00', width=2.5),
            fillcolor='rgba(255, 140, 0, 0.15)',
            hovertemplate = (
                "<b>日期: %{x}</b><br>" +
                f"当时 {coin} 价格: " + "$%{customdata[0]:,.2f}<br>" +
                "当前持仓均价: $%{customdata[1]:,.2f}<br>" +
                "<b>当前实时盈亏: %{customdata[2]:+.2f}%</b>" +
                "<extra></extra>"
            ),
            customdata=df[['Price', 'Avg_Price', 'ROI_Pct']].values
        ))
        
        # 本金投入线 (灰色虚线)
        fig.add_trace(go.Scatter(
            x=df.index, y=df['Cum_Cost'], name="累计投入本金", 
            line=dict(color='#666666', dash='dash', width=2),
            hoverinfo='skip'
        ))

        # BTC 减半大事件标注 (仅在选择 BTC 时显示)
        if coin == "BTC":
            halvings = ['2020-04-11', '2024-04-20']
            for h in halvings:
                h_dt = pd.to_datetime(h) + timedelta(hours=8)
                if h_dt >= df.index.min() and h_dt <= df.index.max():
                    fig.add_vline(x=h_dt.timestamp() * 1000, line_dash="dot", line_color="red", 
                                 annotation_text="BTC 减半", annotation_position="top left")

        fig.update_layout(
            title=f"{coin} 资产增长与定投效率分析",
            xaxis_title="北京时间 (08:00 对齐)",
            yaxis_title="价值 (USD)",
            hovermode="x unified",
            template="plotly_white",
            height=600
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📂 查看详细定投账单"):
            # 仅展示两位小数
            st.dataframe(df[['Price', 'Avg_Price', 'Cum_Qty', 'ROI_Pct', 'Market_Value']].style.format("{:.2f}"))

except Exception as e:
    st.error(f"❌ 运行异常：请确认币种选择正确或日期范围有效。错误详情：{e}")
