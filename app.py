import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# 1. 网页基础设置
st.set_page_config(page_title="Crypto 定投全历史回测", layout="wide")
st.title("📈 BTC/Altcoin 定投全历史回测工具")
st.markdown("---")

# 2. 侧边栏交互设置
with st.sidebar:
    st.header("⚙️ 策略设置")
    coin = st.selectbox("选择币种", ["BTC", "ETH", "BNB", "SOL", "ADA", "XRP", "NVDA", "AAPL"])
    symbol = f"{coin}-USD" if coin not in ["NVDA", "AAPL"] else coin
    
    # 默认日期设为 2015 年，方便回测大周期
    start_date = st.date_input("开始定投日期", value=datetime(2015, 1, 1))
    amount = st.number_input("每次投入金额 ($)", min_value=1, value=100)
    
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月初"], index=1)
    freq_map = {"每天": "D", "每周": "W", "每月初": "MS"}

# 3. 稳健的数据抓取逻辑
@st.cache_data(ttl=3600)
def get_historical_data(symbol, start):
    try:
        # 下载数据
        df = yf.download(symbol, start=start, progress=False)
        if df.empty:
            return None
        
        # 核心修复：处理多级索引和列名问题
        # 不管它返回几层，直接找名为 'Close' 的第一列
        if isinstance(df.columns, pd.MultiIndex):
            # 如果是多级索引，取第一级为 'Close' 的那一列
            df_close = df['Close'].iloc[:, 0]
        else:
            df_close = df['Close']
            
        return df_close.to_frame(name='Close')
    except Exception as e:
        st.error(f"连接数据源失败: {e}")
        return None

# 4. 执行测算
try:
    data = get_historical_data(symbol, start_date)
    
    if data is None or len(data) < 2:
        st.warning(f"⚠️ 没找到 {coin} 在该时段的数据。小贴士：很多代币（如 SOL/BNB）在 2017 年前尚未诞生。")
    else:
        # 按照频率重采样
        dca = data['Close'].resample(freq_map[frequency]).first().to_frame()
        dca = dca.dropna() # 剔除空值

        # 定投核心算法
        dca['Cumulative_Cost'] = [amount * (i + 1) for i in range(len(dca))]
        dca['Bought_Qty'] = amount / dca['Close']
        dca['Total_Qty'] = dca['Bought_Qty'].cumsum()
        dca['Portfolio_Value'] = dca['Total_Qty'] * dca['Close']
        
        # 核心指标看板
        final_cost = dca['Cumulative_Cost'].iloc[-1]
        final_value = dca['Portfolio_Value'].iloc[-1]
        avg_price = final_cost / dca['Total_Qty'].iloc[-1]
        current_price = dca['Close'].iloc[-1]
        roi = (final_value - final_cost) / final_cost * 100

        # UI 显示：四个指标卡片
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("累计投入 (Cost)", f"${final_cost:,.0f}")
        col2.metric("持仓均价 (Avg)", f"${avg_price:,.2f}")
        col3.metric("当前价值 (Value)", f"${final_value:,.0f}", f"{roi:.2f}%")
        col4.metric("最新价格 (Price)", f"${current_price:,.2f}")

        # 5. 可视化图表
        fig = go.Figure()
        # 投入本金线
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Cumulative_Cost'], 
                                 name="投入本金", line=dict(color='gray', dash='dash')))
        # 账户市值曲线
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Portfolio_Value'], 
                                 name="账户市值", fill='tonexty', line=dict(color='#F3BA2F', width=3)))
        
        fig.update_layout(
            title=f"{coin} 定投增长曲线 ({start_date} 至今)",
            xaxis_title="年份",
            yaxis_title="金额 (USD)",
            hovermode="x unified",
            legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
        )
        st.plotly_chart(fig, use_container_width=True)

        # 底部详情
        with st.expander("📂 查看定投数据详情表"):
            st.dataframe(dca.style.format("{:.2f}"), use_container_width=True)

except Exception as e:
    st.error(f"程序计算时发生预料外的错误: {e}")
