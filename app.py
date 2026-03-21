import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time

# 1. 网页基础配置
st.set_page_config(page_title="Crypto 定投大师", layout="wide")
st.title("📊 Crypto 定投回测与实时盈亏分析")

# 2. 侧边栏
with st.sidebar:
    st.header("⚙️ 策略配置")
    coin = st.selectbox("选择币种", ["BTC", "ETH", "BNB", "SOL", "ADA", "XRP", "NVDA", "AAPL"])
    symbol = f"{coin}-USD" if coin not in ["NVDA", "AAPL"] else coin
    
    # 默认日期提前到 2015 年，方便回测
    start_date = st.date_input("开始日期", value=datetime(2015, 1, 1))
    amount = st.number_input("每次投入金额 ($)", min_value=1, value=100)
    frequency = st.selectbox("频率", ["每天", "每周", "每月初"], index=1)
    freq_map = {"每天": "D", "每周": "W", "每月初": "MS"}

# 3. 增强版数据抓取 (防限流、防格式报错)
@st.cache_data(ttl=3600)
def get_data_ultimate(symbol, start):
    for _ in range(3):
        try:
            df = yf.download(symbol, start=start, progress=False, auto_adjust=False)
            if df.empty: continue
            
            # 暴力破解多层表头
            if isinstance(df.columns, pd.MultiIndex):
                df_close = df.xs('Close', axis=1, level=0)
                if isinstance(df_close, pd.DataFrame):
                    df_close = df_close.iloc[:, 0]
            else:
                df_close = df['Close']
            
            res = df_close.to_frame(name='Close')
            res.index.name = 'Date'
            return res.dropna()
        except Exception:
            time.sleep(1)
    return None

# 4. 核心逻辑运算
try:
    data = get_data_ultimate(symbol, start_date)
    
    if data is None or len(data) < 2:
        st.error("📡 数据源连接失败。请尝试修改侧边栏参数或点击右上角 Rerun。")
    else:
        # 重采样
        dca = data['Close'].resample(freq_map[frequency]).first().to_frame()
        dca = dca.dropna()

        # 定投计算
        dca['Cost'] = [amount * (i + 1) for i in range(len(dca))]
        dca['Qty'] = amount / dca['Close']
        dca['Total_Qty'] = dca['Qty'].cumsum()
        dca['Value'] = dca['Total_Qty'] * dca['Close']
        
        # --- 新增指标：计算回撤 ---
        # 记录账户历史最高市值
        dca['Peak'] = dca['Value'].cummax()
        # 计算回撤百分比
        dca['Drawdown'] = (dca['Value'] - dca['Peak']) / dca['Peak'] * 100
        max_dd = dca['Drawdown'].min()

        # 核心看板数据
        f_cost = dca['Cost'].iloc[-1]
        f_val = dca['Value'].iloc[-1]
        avg_p = f_cost / dca['Total_Qty'].iloc[-1]
        curr_p = dca['Close'].iloc[-1]
        total_roi = (f_val - f_cost) / f_cost * 100

        # UI 显示：五个指标卡片
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("累计投入", f"${f_cost:,.0f}")
        m2.metric("持仓均价", f"${avg_p:,.2f}")
        m3.metric("当前价值", f"${f_val:,.0f}", f"{total_roi:.2f}%")
        m4.metric("当前币价", f"${curr_p:,.2f}")
        m5.metric("最大回撤", f"{max_dd:.2f}%", delta_color="inverse")

        # 5. 可视化图表 (双坐标轴或多线图)
        fig = go.Figure()
        # 市值线
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Value'], name="账户市值", 
                                 fill='tonexty', line=dict(color='#F3BA2F', width=3)))
        # 本金线
        fig.add_trace(go.Scatter(x=dca.index, y=dca['Cost'], name="投入本金", 
                                 line=dict(color='white', dash='dash')))
        
        fig.update_layout(
            title=f"{coin} 定投增长曲线 (数据更新至最新)",
            xaxis_title="年份",
            yaxis_title="金额 (USD)",
            hovermode="x unified",
            template="plotly_dark" # 深色模式更专业
        )
        st.plotly_chart(fig, use_container_width=True)

        # 6. 新增回撤分布图 (让用户心里有数)
        fig_dd = go.Figure()
        fig_dd.add_trace(go.Scatter(x=dca.index, y=dca['Drawdown'], name="账户回撤 %", 
                                    fill='tozeroy', line=dict(color='red')))
        fig_dd.update_layout(
            title="定投过程中的账户缩水情况 (心理承受压力测试)",
            xaxis_title="日期",
            yaxis_title="亏损百分比 %",
            template="plotly_dark"
        )
        st.plotly_chart(fig_dd, use_container_width=True)

        with st.expander("📂 查看详细定投账单"):
            st.dataframe(dca[['Close', 'Cost', 'Total_Qty', 'Value', 'Drawdown']].style.format("{:.2f}"))

except Exception as e:
    st.warning(f"🔄 正在初始化或尝试连接数据源... ({e})")
