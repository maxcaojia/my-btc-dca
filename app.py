import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time

# 1. 网页配置
st.set_page_config(page_title="Crypto 定投终极版", layout="wide")
st.title("🛡️ 稳定版：BTC/Altcoin 定投回测工具")

# 2. 侧边栏
with st.sidebar:
    st.header("⚙️ 策略设置")
    coin = st.selectbox("选择币种", ["BTC", "ETH", "BNB", "SOL", "ADA", "XRP", "NVDA", "AAPL"])
    symbol = f"{coin}-USD" if coin not in ["NVDA", "AAPL"] else coin
    
    # 默认日期回溯到 2015 年
    start_date = st.date_input("开始定投日期", value=datetime(2015, 1, 1))
    amount = st.number_input("每次投入金额 ($)", min_value=1, value=100)
    frequency = st.selectbox("定投频率", ["每天", "每周", "每月初"], index=1)
    freq_map = {"每天": "D", "每周": "W", "每月初": "MS"}

# 3. 增强版数据抓取（带重试和多层索引破解）
@st.cache_data(ttl=3600) # 缓存 1 小时，减少对雅虎的请求压力
def get_safe_data(symbol, start):
    # 尝试最多 3 次请求
    for _ in range(3):
        try:
            df = yf.download(symbol, start=start, progress=False, auto_adjust=True)
            if not df.empty:
                # 关键修复：强制处理多级索引 (MultiIndex)
                if isinstance(df.columns, pd.MultiIndex):
                    # 只提取 'Close' 这一层级的数据
                    df_final = df['Close'].iloc[:, 0].to_frame(name='Close')
                else:
                    df_final = df[['Close']]
                return df_final
        except Exception:
            time.sleep(1) # 失败了等一秒再试
            continue
    return None

# 4. 逻辑处理
try:
    data = get_safe_data(symbol, start_date)
    
    if data is None or len(data) < 2:
        st.error("⚠️ 数据源连接不稳定（雅虎限流）。请尝试点击右上角 'Rerun' 或稍后刷新。")
        st.info("提示：如果选的日期太早（币还没出生），也会看到这个错误。")
    else:
        # 清洗数据并按频率重采样
        dca = data['Close'].resample(freq_map[frequency]).first().to_frame()
        dca = dca.dropna()

        # 计算核心指标
        dca['Cumulative_Cost'] = [amount * (i + 1) for i in range(len(dca))]
        dca['Bought_Qty'] = amount / dca['Close']
        dca['Total_Qty'] = dca['Bought_Qty'].cumsum()
        dca['Portfolio_Value'] = dca['Total_Qty'] * dca['Close']
        
        f_cost = dca['Cumulative_Cost'].iloc[-1]
        f_val = dca['Portfolio_Value'].iloc[-1]
        avg_p = f_cost / dca['Total_Qty'].iloc[-1]
        curr_p = dca['Close'].iloc[-1]
        roi = (f_val - f_cost) / f_cost * 100

        # UI 显示
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("累计投入", f"${f_cost:,.0f}")
        c2.metric("持仓均价", f"${avg_p:,.2f}")
        c3.metric("当前市值", f"${f_val:,.0f}", f"{roi:.2f}%")
        c4.metric("最新币价", f"${curr_p:,.2f}")

        # 绘图
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Cumulative_Cost'], name="本金", line=dict(color='gray', dash='dash')))
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Portfolio_Value'], name="市值", fill='tonexty', line=dict(color='#F3BA2F')))
        fig.update_layout(hovermode="x unified", title=f"{coin} 定投回报分析")
        st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.warning(f"正在等待数据同步... 如果长时间不动请尝试刷新。详情: {e}")
