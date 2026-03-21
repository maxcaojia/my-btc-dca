import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time

# 1. 网页基础配置
st.set_page_config(page_title="Crypto 定投回测", layout="wide")
st.title("💰 BTC/Altcoin 定投分析工具 (纯净版)")

# 2. 侧边栏
with st.sidebar:
    st.header("⚙️ 策略配置")
    coin = st.selectbox("选择币种", ["BTC", "ETH", "BNB", "SOL", "ADA", "XRP", "NVDA", "AAPL"])
    symbol = f"{coin}-USD" if coin not in ["NVDA", "AAPL"] else coin
    
    # 默认日期 2015 年
    start_date = st.date_input("开始定投日期", value=datetime(2015, 1, 1))
    amount = st.number_input("每次投入金额 ($)", min_value=1, value=100)
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月初"], index=1)
    freq_map = {"每天": "D", "每周": "W", "每月初": "MS"}

# 3. 稳固的数据抓取 (彻底破解索引问题)
@st.cache_data(ttl=600) # 缩短缓存时间到10分钟，保证数据更“新”
def get_clean_data(symbol, start):
    for _ in range(3):
        try:
            # 获取数据
            df = yf.download(symbol, start=start, progress=False)
            if df.empty: continue
            
            # --- 核心修复：完全无视表头结构，只按位置拿数据 ---
            # 无论 yfinance 返回几层表头，我们只想要 'Close' 这一列
            if 'Close' in df.columns:
                # 如果是多级索引，'Close' 后面会跟币种名，我们只取第一列 Close
                if isinstance(df.columns, pd.MultiIndex):
                    temp = df['Close'].iloc[:, 0]
                else:
                    temp = df['Close']
                
                clean_df = temp.to_frame(name='Close')
                clean_df.index.name = 'Date'
                return clean_df.dropna()
        except Exception:
            time.sleep(1)
    return None

# 4. 运算与显示
try:
    data = get_clean_data(symbol, start_date)
    
    if data is None or len(data) < 2:
        st.error("📡 数据同步中或雅虎限流，请稍后刷新。")
    else:
        # 重采样：取每个周期的第一个价格
        dca = data['Close'].resample(freq_map[frequency]).first().to_frame()
        dca = dca.dropna()

        # 计算定投逻辑
        dca['Cost'] = [amount * (i + 1) for i in range(len(dca))]
        dca['Qty'] = amount / dca['Close']
        dca['Total_Qty'] = dca['Qty'].cumsum()
        dca['Value'] = dca['Total_Qty'] * dca['Close']
        
        # 核心指标
        f_cost = dca['Cost'].iloc[-1]
        f_val = dca['Value'].iloc[-1]
        avg_p = f_cost / dca['Total_Qty'].iloc[-1]
        curr_p = dca['Close'].iloc[-1] # 这就是最新价格
        roi = (f_val - f_cost) / f_cost * 100

        # UI 显示：回归四个指标卡片
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("累计投入", f"${f_cost:,.0f}")
        c2.metric("持仓均价", f"${avg_p:,.2f}")
        c3.metric("当前市值", f"${f_val:,.0f}", f"{roi:.2f}%")
        c4.metric("最新价格", f"${curr_p:,.2f}")

        # 可视化图表
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Value'], name="账户市值", 
                                 fill='tonexty', line=dict(color='#F3BA2F', width=2)))
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Cost'], name="投入本金", 
                                 line=dict(color='gray', dash='dash')))
        
        fig.update_layout(
            title=f"{coin} 定投回报分析 ({start_date} 至今)",
            xaxis_title="年份",
            yaxis_title="金额 (USD)",
            hovermode="x unified",
            template="plotly_white" # 换回亮色模式，看起来更清爽
        )
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.warning(f"数据加载中... ({e})")
