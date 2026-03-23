import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests

# 1. 网页基础配置
st.set_page_config(page_title="CRYPTO定投專業分析", layout="wide")

# --- UI 样式优化：确保数字显示清晰且自动缩放 ---
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: max(14px, 1.6vw) !important; white-space: nowrap; color: #FF8C00; }
    [data-testid="stMetricLabel"] { font-size: 0.9vw !important; }
    .stSuccess { background-color: rgba(255, 140, 0, 0.1) !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("🧡 CRYPTO定投全景分析 (專業版)")

# 2. 从后台获取 API Key
cmc_api_key = st.secrets.get("CMC_API_KEY")

# 3. 侧边栏：区间与策略配置
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

# --- 函数：CMC 实时报价 ---
def get_cmc_price(symbol, api_key):
    if not api_key: return None
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': api_key}
    try:
        r = requests.get(url, headers=headers, params={'symbol': symbol, 'convert': 'USD'})
        return r.json()['data'][symbol]['quote']['USD']['price']
    except: return None

# --- 函数：清洗数据 ---
@st.cache_data(ttl=300)
def get_crypto_data(coin_sym, start, end):
    symbol = f"{coin_sym}-USD"
    # 多抓一天确保包含结束日
    df_raw = yf.download(symbol, start=start, end=end + timedelta(days=1), progress=False)
    if df_raw.empty: return None
    
    if isinstance(df_raw.columns, pd.MultiIndex):
        temp = df_raw.xs('Close', axis=1, level=0)[symbol]
    else:
        temp = df_raw['Close']
    
    res = temp.to_frame(name='Price')
    res.index = res.index + timedelta(hours=8) # 北京时间 08:00
    return res.dropna()

# --- 核心逻辑执行 ---
try:
    with st.spinner(f'正在同步 {coin} 数据...'):
        df = get_crypto_data(coin, start_date, end_date)
        
        if df is not None:
            # A. 标记定投日
            if frequency == "每天":
                df['Is_DCA'] = True
            elif frequency == "每周":
                df['Is_DCA'] = df.index.weekday == target_day
            else:
                df['Is_DCA'] = df.index.day == target_day

            # B. 财务计算
            df['Cost_Step'] = df['Is_DCA'].apply(lambda x: amount if x else 0)
            df['Qty_Step'] = df.apply(lambda row: row['Cost_Step'] / row['Price'] if row['Is_DCA'] else 0, axis=1)
            
            df['Cum_Cost'] = df['Cost_Step'].cumsum()
            df['Cum_Qty'] = df['Qty_Step'].cumsum()
            df['Avg_Price'] = (df['Cum_Cost'] / df['Cum_Qty']).fillna(0)
            df['Market_Value'] = df['Cum_Qty'] * df['Price']
            # 盈亏百分比：保留两位小数
            df['ROI_Pct'] = (((df['Price'] - df['Avg_Price']) / df['Avg_Price']) * 100).fillna(0).round(2)

            # C. 实时数据对齐
            # 只有当截止日期是今天或未来，才调用 CMC 实时价
            is_to_now = end_date >= datetime.now().date()
            live_p = get_cmc_price(coin, cmc_api_key) if is_to_now else None
            
            final_p = live_p if (live_p and is_to_now) else df['Price'].iloc[-1]
            final_cost = df['Cum_Cost'].iloc[-1]
            final_qty = df['Cum_Qty'].iloc[-1]
            final_avg = final_cost / final_qty if final_qty > 0 else 0
            final_val = final_qty * final_p
            final_roi = ((final_val - final_cost) / final_cost * 100) if final_cost > 0 else 0

            # D. 渲染顶部指标
            st.info(f"📊 区间统计：{start_date} 至 {end_date} | 共计定投 {len(df[df['Is_DCA']])} 期")
            
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("区间总投入", f"${final_cost:,.0f}")
            m2.metric(f"累计持仓 {coin}", f"{final_qty:.4f}")
            m3.metric("持仓均价", f"${final_avg:,.2f}")
            m4.metric("实时价 vs 均价", f"{(final_p-final_avg)/final_avg*100:+.2f}%", delta_color="inverse")
            m5.metric("截止市值/实时市值", f"${final_val:,.0f}", f"{final_roi:+.2f}%")

            if live_p and is_to_now:
                st.success(f"✅ CMC 實時數據已掛載：{coin} 現價 ${live_p:,.2f}")

            # E. 增强版 Plotly 图表
            fig = go.Figure()

            # 1. 账户市值 (主曲线：橙色填充)
            fig.add_trace(go.Scatter(
                x=df.index, 
                y=df['Market_Value'], 
                name="账户市值", 
                fill='tonexty', 
                line=dict(color='#FF8C00', width=2.5),
                fillcolor='rgba(255, 140, 0, 0.15)',
                # 悬停显示：包含币价、累计本金、市值、盈亏比
                hovertemplate=(
                    "<b>📅 日期: %{x}</b><br>" +
                    f"🪙 当时 {coin} 价格: " + "$%{customdata[0]:,.2f}<br>" +
                    "💰 累计投入本金: $%{customdata[1]:,.0f}<br>" +
                    "📈 账户当前市值: $%{y:,.0f}<br>" +
                    "<b>📊 实时盈亏比例: %{customdata[2]:+.2f}%</b>" +
                    "<extra></extra>"
                ),
                customdata=df[['Price', 'Cum_Cost', 'ROI_Pct']].values
            ))

            # 2. 投入本金线 (灰色虚线)
            fig.add_trace(go.Scatter(
                x=df.index, y=df['Cum_Cost'], name="累计本金线", 
                line=dict(color='#666666', dash='dash', width=2),
                hoverinfo='skip'
            ))
            
            # 3. BTC 减半标注
            if coin == "BTC":
                for h in ['2020-04-11', '2024-04-20']:
                    h_dt = pd.to_datetime(h) + timedelta(hours=8)
                    if h_dt >= df.index.min() and h_dt <= df.index.max():
                        fig.add_vline(x=h_dt.timestamp() * 1000, line_dash="dot", line_color="red", 
                                     annotation_text="BTC 减半", annotation_position="top left")

            # 4. 图表布局
            fig.update_layout(
                title=f"<b>{coin} 资产增长细节分析 (区间回测)</b>",
                xaxis_title="日期 (北京时间 08:00)",
                yaxis_title="价值 (USD)",
                hovermode="x unified",
                template="plotly_white",
                height=600,
                legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
            )
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("📂 查看详细定投账单"):
                st.dataframe(df[['Price', 'Avg_Price', 'Cum_Qty', 'ROI_Pct', 'Market_Value']].style.format("{:.2f}"))

except Exception as e:
    st.error(f"❌ 运行异常：{e}")
