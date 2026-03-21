import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# 1. 网页配置
st.set_page_config(page_title="实时定投模拟器", layout="wide")
st.title("🏹 实时联动：BTC/Altcoin 定投分析")

# 2. 侧边栏
with st.sidebar:
    st.header("⚙️ 策略设置")
    coin = st.selectbox("选择币种", ["BTC", "ETH", "BNB", "SOL", "NVDA"])
    symbol = f"{coin}-USD" if coin != "NVDA" else coin
    start_date = st.date_input("开始日期", value=datetime(2020, 1, 1))
    amount = st.number_input("定投金额 ($)", min_value=1, value=100)
    frequency = st.selectbox("频率", ["每天", "每周", "每月初"], index=1)
    freq_map = {"每天": "D", "每周": "W", "每月初": "MS"}

@st.cache_data(ttl=300) # 缓存缩短至5分钟，确保价格足够新
def get_realtime_data(symbol, start):
    df = yf.download(symbol, start=start, progress=False)
    if df.empty: return None
    # 兼容处理多级索引
    if isinstance(df.columns, pd.MultiIndex):
        temp = df['Close'].iloc[:, 0]
    else:
        temp = df['Close']
    return temp.to_frame(name='Close').dropna()

try:
    data = get_realtime_data(symbol, start_date)
    
    if data is not None:
        # --- 核心改进：实时价格追加逻辑 ---
        # A. 提取历史周期点数据
        dca = data['Close'].resample(freq_map[frequency]).first().to_frame()
        
        # B. 获取此时此刻的最新价格
        latest_price = data['Close'].iloc[-1]
        latest_date = data.index[-1]
        
        # C. 检查最后一笔是否是“今天”的实时价
        # 如果历史周期点里不包含今天，就强行把今天这一笔加上去
        if latest_date not in dca.index:
            last_row = pd.DataFrame({'Close': [latest_price]}, index=[latest_date])
            dca = pd.concat([dca, last_row])
        
        dca = dca.sort_index().dropna()

        # 核心计算
        dca['Cost'] = [amount * (i + 1) for i in range(len(dca))]
        dca['Qty'] = amount / dca['Close']
        dca['Total_Qty'] = dca['Qty'].cumsum()
        dca['Value'] = dca['Total_Qty'] * dca['Close']
        
        # 数据看板
        f_cost = dca['Cost'].iloc[-1]
        f_val = dca['Value'].iloc[-1]
        avg_p = f_cost / dca['Total_Qty'].iloc[-1]
        curr_p = latest_price # 强制显示最新的实时价
        roi = (f_val - f_cost) / f_cost * 100

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("累计投入", f"${f_cost:,.0f}")
        c2.metric("持仓均价", f"${avg_p:,.2f}")
        c3.metric("当前总市值", f"${f_val:,.0f}", f"{roi:.2f}%")
        c4.metric("最新实时价", f"${curr_p:,.2f}")

        # 图表显示
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Value'], name="账户市值", fill='tonexty', line=dict(color='#F3BA2F')))
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Cost'], name="投入本金", line=dict(color='gray', dash='dash')))
        fig.update_layout(title=f"{coin} 定投实时分析图", hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"数据更新中... {e}")
