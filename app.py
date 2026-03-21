import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# 1. 网页配置
st.set_page_config(page_title="定投实时精准回测", layout="wide")
st.title("🎯 定投实时价差与均价分析 (全周期对齐版)")

# 2. 侧边栏设置
with st.sidebar:
    st.header("⚙️ 策略设置")
    coin = st.selectbox("选择币种", ["BTC", "ETH", "BNB", "SOL", "NVDA", "AAPL"])
    symbol = f"{coin}-USD" if coin not in ["NVDA", "AAPL"] else coin
    start_date = st.date_input("开始定投日期", value=datetime(2020, 1, 1))
    amount = st.number_input("每期定投金额 ($)", min_value=1, value=100)
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月初"], index=2) # 默认选每月
    freq_map = {"每天": "D", "每周": "W", "每月初": "MS"}

@st.cache_data(ttl=60) 
def get_final_data(symbol, start):
    df = yf.download(symbol, start=start, progress=False)
    if df.empty: return None
    if isinstance(df.columns, pd.MultiIndex):
        temp = df['Close'].iloc[:, 0]
    else:
        temp = df['Close']
    return temp.to_frame(name='Close').dropna()

try:
    raw = get_final_data(symbol, start_date)
    
    if raw is not None:
        # --- 步骤 A: 提取历史定投点 (不含今天) ---
        # 我们只计算已经过去的、完整的周期点
        dca_history = raw['Close'].resample(freq_map[frequency]).first().to_frame()
        
        # 获取真正的实时价格和日期
        latest_price = raw['Close'].iloc[-1]
        latest_date = raw.index[-1]

        # 如果最新的日期还没到下一个定投周期，我们要确保不重复扣款
        # 排除掉还没发生的未来扣款点，只保留历史
        dca_history = dca_history[dca_history.index < latest_date]
        
        # --- 步骤 B: 计算历史扣款结果 ---
        dca_history['Cost'] = [amount * (i + 1) for i in range(len(dca_history))]
        dca_history['Qty'] = amount / dca_history['Close']
        dca_history['Total_Qty'] = dca_history['Qty'].cumsum()
        dca_history['Value'] = dca_history['Total_Qty'] * dca_history['Close']
        
        # 获取截止到最后一笔定投时的状态
        total_invested = dca_history['Cost'].iloc[-1]
        total_qty_held = dca_history['Total_Qty'].iloc[-1]
        my_avg_price = total_invested / total_qty_held  # 真实持仓均价
        
        # --- 步骤 C: 计算实时参考数据 ---
        # 实时市值 = 已有的币 * 此时此刻的价格
        current_market_value = total_qty_held * latest_price
        # 实时总收益率 (基于已投入本金)
        total_roi = (current_market_value - total_invested) / total_invested * 100
        # 实时价与均价的差价百分比
        price_diff_pct = (latest_price - my_avg_price) / my_avg_price * 100

        # 3. UI 显示：精准指标卡片
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("累计投入本金", f"${total_invested:,.0f}")
        c2.metric("我的持仓均价", f"${my_avg_price:,.2f}")
        
        # 核心参考指标：实时价格 vs 你的成本
        diff_color = "normal" if price_diff_pct > 0 else "inverse"
        c3.metric(f"实时价 vs 均价", f"{price_diff_pct:+.2f}%", 
                  help="正数表示当前价格高于你的成本，负数表示当前处于折价状态")
        
        c4.metric("实时账户市值", f"${current_market_value:,.0f}", f"{total_roi:.2f}%")

        st.info(f"📊 实时参考价: **${latest_price:,.2f}** | 上次定投时间: {dca_history.index[-1].strftime('%Y-%m-%d')}")

        # 4. 可视化图表
        fig = go.Figure()
        # 市值填充线
        fig.add_trace(go.Scatter(x=dca_history.index, y=dca_history['Portfolio_Value'], 
                                 name="历史市值", fill='tonexty', line=dict(color='#F3BA2F')))
        # 本金阶梯线
        fig.add_trace(go.Scatter(x=dca_history.index, y=dca_history['Cost'], 
                                 name="投入本金", line=dict(color='gray', dash='dash')))
        
        # 增加一个醒目的“今天实时点”
        fig.add_trace(go.Scatter(x=[latest_date], y=[current_market_value], 
                                 mode='markers', name="当前实时位置",
                                 marker=dict(color='red', size=15, symbol='star')))
        
        fig.update_layout(title=f"{coin} 定投实时对齐分析 ({frequency})", 
                          hovermode="x unified", template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"数据对齐中，请稍候... ({e})")
