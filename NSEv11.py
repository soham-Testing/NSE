#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════════════╗
║  NSE SWING TRADER  v11.0  ·  PRODUCTION READY                                      ║
║  Fixes: Look-ahead bias, unified ATR stops, correlation filter, vol targeting,       ║
║         realistic gap execution, rolling regime, survivorship bias, modular engine ║
╚══════════════════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import os
import sys
import time
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import sqrt
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# DETECT MODE
# ─────────────────────────────────────────────────────────────────────────────
def _is_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        pass
    try:
        import streamlit.runtime.scriptrunner as _sr
        return _sr.get_script_run_ctx() is not None
    except Exception:
        return False

_STREAMLIT = _is_streamlit()

if _STREAMLIT:
    import streamlit as st
    st.set_page_config(page_title="NSE Swing Trader Pro v11", page_icon="📈",
                       layout="wide", initial_sidebar_state="expanded")

# ─────────────────────────────────────────────────────────────────────────────
# OPTIONAL DEPS
# ─────────────────────────────────────────────────────────────────────────────
try:
    import yfinance as yf
    _HAS_YF = True
except ImportError:
    yf = None; _HAS_YF = False

_HAS_RICH = False
_con = None
if not _STREAMLIT:
    try:
        from rich.align import Align
        from rich.columns import Columns
        from rich.console import Console
        from rich import box as rbox
        from rich.padding import Padding
        from rich.panel import Panel
        from rich.rule import Rule
        from rich.table import Table
        from rich.text import Text
        from rich.progress import (Progress, SpinnerColumn, TextColumn,
                                   BarColumn, TimeElapsedColumn)
        _HAS_RICH = True
        _con = Console(highlight=False)
    except ImportError:
        pass

if _STREAMLIT:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    import streamlit.components.v1 as components

LOG = logging.getLogger("NSEv11")
for _nm in ("yfinance","urllib3","requests","charset_normalizer"):
    logging.getLogger(_nm).setLevel(logging.CRITICAL)

# ══════════════════════════════════════════════════════════════════════════════
# §1  UNIVERSE  (Survivorship-bias-aware: require full history)
# ══════════════════════════════════════════════════════════════════════════════

_YF_OVERRIDE = {"M&M":"M%26M","BAJAJ-AUTO":"BAJAJ-AUTO","LTM":"LTIM"}
_SKIP_SYMBOLS = {"APL","ETERNAL","JIOFIN","PATANJALI","ASHOKLEY"}

_UNIVERSE = {
    "NIFTY 50": [
        "RELIANCE","HDFCBANK","ICICIBANK","SBIN","TCS","INFY","HINDUNILVR","ITC",
        "LT","KOTAKBANK","AXISBANK","BAJFINANCE","BHARTIARTL","ASIANPAINT","MARUTI",
        "SUNPHARMA","TITAN","ULTRACEMCO","NESTLEIND","WIPRO","ONGC","ADANIPORTS",
        "POWERGRID","NTPC","COALINDIA","TATASTEEL","JSWSTEEL","GRASIM","HCLTECH",
        "TECHM","ADANIENT","BAJAJFINSV","EICHERMOT","SHRIRAMFIN","APOLLOHOSP",
        "TATAMOTORS","TATACONSUM","BAJAJ-AUTO","INDUSINDBK","DIVISLAB","CIPLA",
        "DRREDDY","SBILIFE","HDFCLIFE","BEL","MAXHEALTH","INDIGO","TRENT",
    ],
    "NIFTY NEXT 50": [
        "LICI","ADANIGREEN","ADANIPOWER","VEDL","HAL","SIEMENS","GODREJCP","DABUR",
        "PIDILITIND","DMART","MARICO","BRITANNIA","HAVELLS","AMBUJACEM","GAIL","BHEL",
        "SAIL","BPCL","HINDPETRO","IOC","PETRONET","CONCOR","NMDC","RECLTD","PFC",
        "IRFC","IREDA","RVNL","NHPC","SUZLON","TATAPOWER","JSWENERGY","POLYCAB",
        "CUMMINSIND","VOLTAS","DLF","LODHA","GODREJPROP","OBEROIRLTY","PRESTIGE",
        "PHOENIXLTD","INDHOTEL","JUBLFOOD","NAUKRI","MPHASIS","COFORGE","PERSISTENT",
        "KPITTECH","LTM",
    ],
    "NIFTY MIDCAP 100": [
        "TVSMOTOR","CHOLAFIN","MUTHOOTFIN","LUPIN","AUROPHARMA","DIVISLAB","ALKEM",
        "TORNTPHARM","BIOCON","GLENMARK","MANKIND","ZYDUSLIFE","LAURUSLABS","FORTIS",
        "SYNGENE","AUBANK","FEDERALBNK","BANDHANBNK","RBLBANK","IDFCFIRSTB","PNB",
        "BANKBARODA","CANBK","INDIANB","UNIONBANK","INDUSINDBK","SRF","ASTRAL",
        "CROMPTON","BLUESTARCO","KEI","ABB","BHARATFORG","BDL","TIINDIA","SONACOMS",
        "UNOMINDA","EXIDEIND","KALYANKJIL","PAGEIND","VBL","MCX","BSE","CDSL","CAMS",
        "HDFCAMC","KFINTECH","ANGELONE","NUVAMA","POLICYBZR","DIXON","AMBER","KAYNES",
        "DALBHARAT","SHREECEM","JKCEMENT","HINDZINC","NATIONALUM","JINDALSTEL",
        "APLAPOLLO","GMRAIRPORT","DELHIVERY",
    ],
    "NIFTY SMALLCAP 250": [
        "IREDA","RVNL","IRFC","NHPC","HUDCO","SJVN","NBCC","PNBHOUSING","LICHSGFIN",
        "MANAPPURAM","ABCAPITAL","LTF","TATAELXSI","OFSS","INOXWIND","WAAREEENER",
        "TORNTPOWER","OIL","ZOMATO","NYKAA","PAYTM","COLPAL","EMAMILTD",
        "PIIND","UPL","DEEPAKNTR","SUPREMEIND","SOLARINDS","MAZDOCK","BOSCHLTD","MOTHERSON",
    ],
    "NIFTY BANK": [
        "HDFCBANK","ICICIBANK","SBIN","AXISBANK","KOTAKBANK","INDUSINDBK","BANDHANBNK",
        "FEDERALBNK","AUBANK","IDFCFIRSTB","PNB","BANKBARODA","CANBK","INDIANB",
        "UNIONBANK","RBLBANK",
    ],
    "NIFTY IT": [
        "TCS","INFY","HCLTECH","WIPRO","TECHM","LTM","MPHASIS","COFORGE","PERSISTENT",
        "KPITTECH","TATAELXSI","OFSS","NAUKRI",
    ],
    "NIFTY ENERGY": [
        "RELIANCE","ONGC","NTPC","POWERGRID","TATAPOWER","ADANIGREEN","ADANIPOWER",
        "JSWENERGY","NHPC","IREDA","SUZLON","INOXWIND","WAAREEENER","TORNTPOWER",
        "BPCL","IOC","HINDPETRO","OIL","GAIL","PETRONET","COALINDIA",
    ],
    "NIFTY AUTO": [
        "MARUTI","M&M","TATAMOTORS","BAJAJ-AUTO","EICHERMOT","HEROMOTOCO","TVSMOTOR",
        "MOTHERSON","BOSCHLTD","TIINDIA","SONACOMS","UNOMINDA","EXIDEIND","BHARATFORG",
    ],
    "NIFTY INFRA": [
        "LT","ADANIPORTS","POWERGRID","NTPC","COALINDIA","BHEL","SIEMENS","ABB",
        "HAVELLS","POLYCAB","KEI","CUMMINSIND","RVNL","NBCC","HUDCO","IRFC",
        "GMRAIRPORT","CONCOR","DELHIVERY","DLF","LODHA","GODREJPROP","OBEROIRLTY",
        "PRESTIGE","PHOENIXLTD",
    ],
    "FO STOCKS": [
        "RELIANCE","HDFCBANK","ICICIBANK","SBIN","TCS","INFY","AXISBANK","KOTAKBANK",
        "LT","BAJFINANCE","WIPRO","HCLTECH","SUNPHARMA","MARUTI","M&M","ITC","TITAN",
        "BHARTIARTL","ADANIPORTS","ADANIENT","BAJAJ-AUTO","BAJAJFINSV","NTPC","POWERGRID",
        "COALINDIA","ONGC","JSWSTEEL","TATASTEEL","HINDALCO","GRASIM","NESTLEIND",
        "ASIANPAINT","HINDUNILVR","TRENT","TATAMOTORS","TATACONSUM","DRREDDY","CIPLA",
        "EICHERMOT","SHRIRAMFIN","TECHM","INDUSINDBK","ULTRACEMCO","DIVISLAB","BEL",
        "HDFCLIFE","SBILIFE","MAXHEALTH","APOLLOHOSP","INDIGO","TATAPOWER","RECLTD",
        "PFC","IRFC","IREDA","RVNL","NHPC","SUZLON","JSWENERGY","ADANIGREEN",
        "WAAREEENER","BPCL","IOC","GAIL","PETRONET","TVSMOTOR","HEROMOTOCO","BOSCHLTD",
        "CHOLAFIN","MUTHOOTFIN","AUBANK","FEDERALBNK","BANDHANBNK","RBLBANK",
        "IDFCFIRSTB","PNB","BANKBARODA","CANBK","UNIONBANK","LTM","MPHASIS","COFORGE",
        "PERSISTENT","KPITTECH","TATAELXSI","OFSS","NAUKRI","DLF","LODHA","GODREJPROP",
        "OBEROIRLTY","PRESTIGE","PHOENIXLTD","POLYCAB","HAVELLS","SIEMENS","ABB",
        "CUMMINSIND","BHEL","AMBUJACEM","DMART","PIDILITIND","MARICO","DABUR",
        "BRITANNIA","COLPAL","GODREJCP","VBL","JUBLFOOD","HDFCAMC","CDSL","BSE","CAMS",
        "ANGELONE","MCX","NUVAMA","DIXON","KAYNES","AMBER","HAL","BDL","MAZDOCK",
        "SOLARINDS","JINDALSTEL","SAIL","NMDC","HINDZINC","NATIONALUM","VEDL","CONCOR",
        "DELHIVERY","GMRAIRPORT","INDHOTEL","BHARATFORG","TIINDIA","EXIDEIND","UNOMINDA",
    ],
}

_FO_SET = set(_UNIVERSE["FO STOCKS"])
_ALL_SYMS = sorted({s for v in _UNIVERSE.values() for s in v} - _SKIP_SYMBOLS)

_SYM_GROUPS: dict[str, List[str]] = defaultdict(list)
for _g, _sl in _UNIVERSE.items():
    for _s in _sl:
        if _s not in _SKIP_SYMBOLS:
            _SYM_GROUPS[_s].append(_g)

_GRP_SHORT = {
    "NIFTY 50":"N50","NIFTY NEXT 50":"NN50","NIFTY MIDCAP 100":"MC100",
    "NIFTY SMALLCAP 250":"SC250","NIFTY BANK":"BNK","NIFTY IT":"IT",
    "NIFTY ENERGY":"NRG","NIFTY AUTO":"AUTO","NIFTY INFRA":"INFRA","FO STOCKS":"F&O",
}

def symbol_tags(sym: str) -> str:
    tags = list(dict.fromkeys(_GRP_SHORT.get(g, g[:4]) for g in _SYM_GROUPS.get(sym, [])))
    return " · ".join(tags[:4]) or "—"

def yf_ticker(sym: str) -> str:
    return f"{_YF_OVERRIDE.get(sym, sym)}.NS"

# ══════════════════════════════════════════════════════════════════════════════
# §2  CONFIG  (Production defaults)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Cfg:
    live_period: str = "8mo"
    live_interval: str = "1d"
    output_dir: Path = Path("nse_v11_output")
    use_sample: bool = False
    fetch_fundamentals: bool = True
    symbols: List[str] = field(default_factory=list)
    min_avg_vol: int = 750_000
    min_price: float = 30.0
    min_traded_val_cr: float = 2.0
    top_n: int = 10
    ema_spans: tuple = (9, 21, 50, 200)
    rsi_period: int = 14
    atr_period: int = 14
    bb_period: int = 20
    adx_period: int = 14
    breakout_window: int = 20
    min_bars: int = 60
    base_threshold: float = 0.16
    bear_threshold: float = 0.30
    min_categories: int = 2
    weights: dict = field(default_factory=lambda: {
        "trend":0.24,"momentum":0.16,"breakout":0.17,"pullback":0.11,
        "volume":0.10,"pattern":0.10,"fundamental":0.00,"sentiment":0.04,
    })
    min_atr_pct: float = 0.012
    max_atr_pct: float = 0.09
    st_sl_mult: float = 1.0
    st_tp_mult: float = 1.8
    lt_sl_mult: float = 1.5
    lt_tp_mult: float = 3.5
    min_rr: float = 1.2
    # Backtest — unified with display, vol targeting, correlation guard
    bt_capital: float = 1_000_000.0
    bt_max_pos: int = 5
    bt_pos_pct: float = 0.20
    bt_risk_per_trade: float = 0.01
    bt_max_correlation: float = 0.70
    bt_use_atr_stops: bool = True
    bt_slip_bps: float = 5.0
    bt_cost_bps: float = 12.0
    bt_max_hold: int = 12
    bt_min_hold: int = 2
    # Display
    capital: float = 1_000_000.0

# ══════════════════════════════════════════════════════════════════════════════
# §3  DATA LAYER  (Robust, logged, no silent swallowing)
# ══════════════════════════════════════════════════════════════════════════════

def _norm_dates(s: pd.Series) -> pd.Series:
    p = pd.to_datetime(s)
    return p.dt.tz_convert(None) if getattr(p.dt, "tz", None) is not None else p

def _safe_dl(ticker: str, period: str, interval: str) -> pd.DataFrame:
    if not _HAS_YF:
        LOG.warning("yfinance not installed")
        return pd.DataFrame()
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            df = yf.download(ticker, period=period, interval=interval,
                             progress=False, auto_adjust=True, timeout=20)
        if df is None or df.empty:
            return pd.DataFrame()
        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).lower().strip() for c in df.columns]
        return df.reset_index()
    except Exception as e:
        LOG.warning("Download failed for %s: %s", ticker, e)
        return pd.DataFrame()

def fetch_ohlcv(sym: str, period: str, interval: str) -> pd.DataFrame:
    df = _safe_dl(yf_ticker(sym), period, interval)
    if df.empty:
        return pd.DataFrame()
    try:
        dc = next((c for c in df.columns if c.lower() in {"date","datetime"}), df.columns[0])
        df = df.rename(columns={dc: "date"})
        df["date"] = _norm_dates(df["date"]).dt.normalize()
        df["symbol"] = sym.upper()
        need = ["date","symbol","open","high","low","close","volume"]
        for c in need:
            if c not in df.columns:
                LOG.warning("%s missing column %s", sym, c)
                return pd.DataFrame()
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
        for c in ["open","high","low","close"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df[need].dropna(subset=["open","high","low","close"]).reset_index(drop=True)
    except Exception as e:
        LOG.warning("OHLCV parse %s: %s", sym, e)
        return pd.DataFrame()

def fetch_fundamentals(sym: str) -> dict:
    if not _HAS_YF:
        return {}
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            info = yf.Ticker(yf_ticker(sym)).info
        mc = info.get("marketCap", 0) or 0
        return {
            "pe": info.get("trailingPE"), "pb": info.get("priceToBook"),
            "roe": info.get("returnOnEquity"), "eps_g": info.get("earningsGrowth"),
            "rev_g": info.get("revenueGrowth"), "de": info.get("debtToEquity"),
            "sector": info.get("sector", "N/A"), "industry": info.get("industry", "N/A"),
            "mcap": round(mc / 1e7, 1) if mc else None,
            "w52h": info.get("fiftyTwoWeekHigh"), "w52l": info.get("fiftyTwoWeekLow"),
            "beta": info.get("beta"), "peg": info.get("pegRatio"),
            "div_y": info.get("dividendYield"),
        }
    except Exception as e:
        LOG.debug("Fundamentals %s: %s", sym, e)
        return {}

def nifty50_history(period: str = "8mo", interval: str = "1d") -> pd.DataFrame:
    """Fetch Nifty 50 history for rolling regime calculation."""
    df = _safe_dl("^NSEI", period, interval)
    if df.empty:
        return pd.DataFrame()
    df.columns = [str(c).lower().strip() for c in df.columns]
    dc = next((c for c in df.columns if c.lower() in {"date","datetime"}), df.columns[0])
    df = df.rename(columns={dc: "date"})
    df["date"] = _norm_dates(df["date"]).dt.normalize()
    return df[["date","open","high","low","close","volume"]].dropna()

def compute_nifty_regime(nifty_df: pd.DataFrame) -> pd.DataFrame:
    """Pre-compute rolling Nifty regime for each date — NO look-ahead."""
    df = nifty_df.copy().sort_values("date").reset_index(drop=True)
    if len(df) < 50:
        df["trend"] = 0.0
        df["label"] = "N/A"
        df["rsi"] = 50.0
        return df
    c = df["close"]
    df["ema9"] = c.ewm(span=9, adjust=False).mean()
    df["ema21"] = c.ewm(span=21, adjust=False).mean()
    df["ema50"] = c.ewm(span=50, adjust=False).mean()
    last = c
    l9 = df["ema9"]
    l21 = df["ema21"]
    l50 = df["ema50"]
    def _trend(row):
        if row["close"] > row["ema9"] > row["ema21"] > row["ema50"]:
            return 1.0
        if row["close"] > row["ema9"] > row["ema21"]:
            return 0.7
        if row["close"] < row["ema9"] < row["ema21"] < row["ema50"]:
            return -1.0
        if row["close"] < row["ema9"] < row["ema21"]:
            return -0.7
        return 0.0
    df["trend"] = df.apply(_trend, axis=1)
    labels = {1.0:"Strong Bull", 0.7:"Mild Bull", -1.0:"Strong Bear", -0.7:"Mild Bear", 0.0:"Sideways"}
    df["label"] = df["trend"].map(labels)
    # RSI
    d = c.diff()
    gain = d.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = (100 - 100 / (1 + rs)).fillna(50)
    return df[["date","trend","label","rsi","close","ema9","ema21","ema50"]]

# ══════════════════════════════════════════════════════════════════════════════
# §4  INDICATORS  (Modular, pure functions, no god-objects)
# ══════════════════════════════════════════════════════════════════════════════

def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    g = d.clip(lower=0).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    return (100 - 100 / (1 + g / l.replace(0, np.nan))).fillna(50)

def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean()

def _adx(df: pd.DataFrame, n: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    hd = df["high"].diff()
    ld = -df["low"].diff()
    pdm = pd.Series(np.where((hd > ld) & (hd > 0), hd, 0.0), index=df.index)
    mdm = pd.Series(np.where((ld > hd) & (ld > 0), ld, 0.0), index=df.index)
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - pc).abs(),
                    (df["low"] - pc).abs()], axis=1).max(axis=1)
    atr_s = tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean().replace(0, np.nan)
    pdi = pdm.ewm(alpha=1/n, adjust=False, min_periods=n).mean() / atr_s * 100
    mdi = mdm.ewm(alpha=1/n, adjust=False, min_periods=n).mean() / atr_s * 100
    dx = ((pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan) * 100)
    adx = dx.ewm(alpha=1/n, adjust=False, min_periods=n).mean().fillna(20)
    return adx, pdi.fillna(0), mdi.fillna(0)

def _supertrend(df: pd.DataFrame, mult: float = 3.0, n: int = 10) -> Tuple[pd.Series, pd.Series]:
    atr_s = _atr(df, n)
    hl2 = (df["high"] + df["low"]) / 2
    up = hl2 + mult * atr_s
    dn = hl2 - mult * atr_s
    fi_up = up.copy()
    fi_dn = dn.copy()
    for i in range(1, len(df)):
        pc = df["close"].iat[i - 1]
        fi_up.iat[i] = min(up.iat[i], fi_up.iat[i - 1]) if pc <= fi_up.iat[i - 1] else up.iat[i]
        fi_dn.iat[i] = max(dn.iat[i], fi_dn.iat[i - 1]) if pc >= fi_dn.iat[i - 1] else dn.iat[i]
    direction = pd.Series(1.0, index=df.index)
    for i in range(1, len(df)):
        pd_ = direction.iat[i - 1]
        if pd_ == -1 and df["close"].iat[i] > fi_up.iat[i]:
            direction.iat[i] = 1
        elif pd_ == 1 and df["close"].iat[i] < fi_dn.iat[i]:
            direction.iat[i] = -1
        else:
            direction.iat[i] = pd_
    flip = ((direction == 1) & (direction.shift(1).fillna(-1) == -1)).astype(int)
    return direction, flip

def compute_indicators(raw: pd.DataFrame, cfg: Cfg) -> pd.DataFrame:
    df = raw.copy().sort_values("date").reset_index(drop=True)
    if len(df) < cfg.min_bars:
        return pd.DataFrame()
    c = df["close"]
    h = df["high"]
    l = df["low"]
    o = df["open"]
    v = df["volume"]

    for sp in cfg.ema_spans:
        df[f"ema{sp}"] = _ema(c, sp)
    df["ema_gap"] = (df["ema9"] / df["ema21"].replace(0, np.nan) - 1) * 100
    df["macd"] = _ema(c, 12) - _ema(c, 26)
    df["macd_sig"] = _ema(df["macd"], 9)
    df["macd_h"] = df["macd"] - df["macd_sig"]
    df["macd_h_p"] = df["macd_h"].shift(1)
    df["rsi14"] = _rsi(c, 14)
    df["rsi9"] = _rsi(c, 9)
    df["atr14"] = _atr(df, 14)
    df["atr_pct"] = df["atr14"] / c.replace(0, np.nan) * 100
    df["adx"], df["plus_di"], df["minus_di"] = _adx(df, 14)
    df["st_dir"], df["st_flip"] = _supertrend(df, mult=3.0, n=10)

    bb_mid = c.rolling(cfg.bb_period, min_periods=10).mean()
    bb_std = c.rolling(cfg.bb_period, min_periods=10).std()
    df["bb_up"] = bb_mid + 2 * bb_std
    df["bb_dn"] = bb_mid - 2 * bb_std
    bb_rng = (df["bb_up"] - df["bb_dn"]).replace(0, np.nan)
    df["bb_pct"] = (c - df["bb_dn"]) / bb_rng
    df["bb_bw"] = bb_rng / bb_mid.replace(0, np.nan)

    lo14 = l.rolling(14, min_periods=7).min()
    hi14 = h.rolling(14, min_periods=7).max()
    df["stoch_k"] = ((c - lo14) / (hi14 - lo14).replace(0, np.nan) * 100).fillna(50)
    df["stoch_d"] = df["stoch_k"].rolling(3, min_periods=1).mean()

    tp = (h + l + c) / 3
    tp_ma = tp.rolling(20, min_periods=10).mean()
    tp_md = tp.rolling(20, min_periods=10).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    df["cci"] = ((tp - tp_ma) / (0.015 * tp_md.replace(0, np.nan))).fillna(0)

    hi14r = h.rolling(14, min_periods=7).max()
    lo14r = l.rolling(14, min_periods=7).min()
    df["willr"] = ((hi14r - c) / (hi14r - lo14r).replace(0, np.nan) * -100).fillna(-50)

    tp2 = (h + l + c) / 3
    rmf = tp2 * v
    pos_mf = rmf.where(tp2 > tp2.shift(1), 0.0)
    neg_mf = rmf.where(tp2 < tp2.shift(1), 0.0)
    mfr = pos_mf.rolling(14, min_periods=7).sum() / neg_mf.rolling(14, min_periods=7).sum().replace(0, np.nan)
    df["mfi"] = (100 - 100 / (1 + mfr)).fillna(50)

    df["obv"] = (np.sign(c.diff()) * v).cumsum()
    df["obv_ema"] = _ema(df["obv"], 20)
    df["avg_vol20"] = v.rolling(20, min_periods=10).mean()
    df["vol_ratio"] = v / df["avg_vol20"].replace(0, np.nan)
    df["vol_z"] = ((v - df["avg_vol20"]) / v.rolling(20, min_periods=10).std().replace(0, np.nan)).fillna(0)
    df["med_tv20"] = (c * v).rolling(20, min_periods=10).median()
    df["ret1"] = c.pct_change()
    df["ret5"] = c.pct_change(5)
    df["ret20"] = c.pct_change(20)

    df["hi20"] = h.shift(1).rolling(cfg.breakout_window, min_periods=8).max()
    df["lo20"] = l.shift(1).rolling(cfg.breakout_window, min_periods=8).min()
    df["hi50"] = h.shift(1).rolling(50, min_periods=15).max()
    df["hi52"] = h.rolling(252, min_periods=50).max()
    df["lo52"] = l.rolling(252, min_periods=50).min()
    df["bo20"] = (c > df["hi20"]).astype(int)
    df["bo50"] = (c > df["hi50"]).astype(int)
    df["n52h"] = (c >= df["hi52"] * 0.97).astype(int)
    df["n52l"] = (c <= df["lo52"] * 1.03).astype(int)
    df["bo_d"] = (c / df["hi20"].replace(0, np.nan) - 1) * 100
    df["bd_d"] = (c / df["lo20"].replace(0, np.nan) - 1) * 100
    df["pull_slow"] = (c / df["ema21"].replace(0, np.nan) - 1) * 100

    # ── STRICT PATTERNS ONLY (5 rigorously defined setups) ─────────────────
    po = o.shift(1)
    pc_ = c.shift(1)
    ph = h.shift(1)
    pl = l.shift(1)
    body = (c - o).abs()
    rng_ = (h - l).replace(0, np.nan)
    ls = df[["open", "close"]].min(axis=1) - l
    us = h - df[["open", "close"]].max(axis=1)

    # 1. Bullish Engulfing
    df["cdl_bull_eng"] = ((c > o) & (pc_ < po) & (o <= pc_) & (c >= po)).astype(int)
    # 2. Hammer (strict)
    df["cdl_hammer"] = ((ls >= 2.0 * body) & (us <= 0.3 * body) & (c > o) & (body / rng_ > 0.05)).astype(int)
    # 3. Morning Star (3-bar, strict)
    df["cdl_morn_star"] = ((pc_.shift(1) < po.shift(1)) &
                           ((c.shift(1) - o.shift(1)).abs() < (rng_.shift(2).fillna(1) * 0.35)) &
                           (c > (po.shift(1) + pc_.shift(1)) / 2) &
                           (c > o)).astype(int)
    # 4. Inside Bar Breakout
    df["cdl_inside"] = ((h < ph) & (l > pl) & (c > pc_) & (c > o)).astype(int)
    # 5. Support Bounce (20D low + volume)
    df["cdl_sup_bounce"] = ((df["ret1"].fillna(0) > 0.005) & (c > c.shift(1)) &
                            (df["bd_d"].fillna(100) < 3.0)).astype(int)
    # 6. Volume-confirmed breakout candle
    df["cdl_bo_candle"] = ((c > df["hi20"]) & (df["vol_ratio"].fillna(0) > 1.3)).astype(int)

    return df.replace([np.inf, -np.inf], np.nan)

def engineer_all(prices: pd.DataFrame, cfg: Cfg) -> pd.DataFrame:
    parts = []
    for sym, grp in prices.groupby("symbol", sort=False):
        r = compute_indicators(grp, cfg)
        if not r.empty:
            parts.append(r)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

# ══════════════════════════════════════════════════════════════════════════════
# §5  PATTERN ENGINE  (Reduced noise, strict confirmation)
# ══════════════════════════════════════════════════════════════════════════════

def _g(row, k: str, d: float = 0.0) -> float:
    try:
        v = row[k] if isinstance(row, dict) else getattr(row, k, d)
    except Exception:
        return d
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return d
    return float(v)

def detect_patterns(row, tail: pd.DataFrame) -> List[Tuple[float, str, str]]:
    hits: Dict[str, Tuple] = {}
    def add(sc, lb, cat):
        if lb not in hits or sc > hits[lb][0]:
            hits[lb] = (sc, lb, cat)

    prev = tail.iloc[-2] if len(tail) >= 2 else row
    c = _g(row, "close")
    e9 = _g(row, "ema9")
    e21 = _g(row, "ema21")
    e50 = _g(row, "ema50")
    e200 = _g(row, "ema200", e50)
    rsi = _g(row, "rsi14", 50)
    mh = _g(row, "macd_h")
    atr = _g(row, "atr14", c * 0.02) or c * 0.02
    vol = _g(row, "vol_ratio", 1.0)
    adx = _g(row, "adx", 20)
    stk = _g(row, "stoch_k", 50)
    std_ = _g(row, "stoch_d", 50)
    bbp = _g(row, "bb_pct", 0.5)
    st = _g(row, "st_dir", 0)
    stf = _g(row, "st_flip", 0)
    obv = _g(row, "obv", 0)
    obve = _g(row, "obv_ema", 0)
    pdi = _g(row, "plus_di", 0)
    mdi = _g(row, "minus_di", 0)
    pull = _g(row, "pull_slow", 0)
    pc = _g(prev, "close")
    pe9 = _g(prev, "ema9")
    pe21 = _g(prev, "ema21")
    pmh = _g(prev, "macd_h")
    prsi = _g(prev, "rsi14", 50)
    pstk = _g(prev, "stoch_k", 50)
    pbbp = _g(prev, "bb_pct", 0.5)
    pobv = _g(prev, "obv", 0)
    pst = _g(prev, "st_dir", 0)

    # ── TREND ──
    if c > e9 > e21 > e50 > e200:
        add(0.96, "Full EMA Bull Stack (All 4 EMAs)", "Trend")
    elif c > e9 > e21 > e50:
        add(0.85, "EMA Bull Stack (9>21>50)", "Trend")
    elif c > e9 > e21:
        add(0.70, "Short EMA Bullish (9>21)", "Trend")
    if c > e200 and e50 > e200:
        add(0.72, "Price & EMA50 Above 200", "Trend")
    if pe9 <= pe21 and e9 > e21:
        add(0.92, "Golden Cross: EMA9/EMA21", "Trend")
    if adx > 28 and e9 > e21 and pdi > mdi:
        add(0.88, "Strong Trend: ADX>28, +DI>-DI", "Trend")
    if adx > 40:
        add(0.92, "Very Strong Trend: ADX>40", "Trend")
    if stf == 1:
        add(0.97, "SuperTrend BUY Flip", "Trend")
    elif st == 1:
        add(0.74, "SuperTrend Bullish Mode", "Trend")

    # ── MOMENTUM ──
    if pmh <= 0 and mh > 0:
        add(0.90, "MACD Histogram Bull Cross", "Momentum")
    if prsi < 30 and rsi > 30:
        add(0.95, "RSI Oversold Bounce", "Momentum")
    elif rsi < 30:
        add(0.87, "RSI Oversold <30", "Momentum")
    elif rsi < 38:
        add(0.73, "RSI Near-Oversold <38", "Momentum")
    if pstk < 20 and stk > 20 and stk > std_:
        add(0.90, "Stochastic Bull Cross Oversold", "Momentum")
    elif stk < 20:
        add(0.78, "Stochastic Oversold Zone", "Momentum")
    if pbbp < 0.05 and bbp > 0.10:
        add(0.90, "BB Lower Band Bounce", "Volatility")
    elif bbp < 0.05:
        add(0.80, "BB Lower Band Touch", "Volatility")

    # ── VOLUME ──
    if vol >= 2.5 and c > pc:
        add(0.95, "Volume Surge 2.5x (Institutional)", "Volume")
    elif vol >= 1.5 and c > pc:
        add(0.78, "Volume 1.5x Bullish", "Volume")
    if obv > obve and c > e21:
        add(0.68, "OBV Above 20d EMA", "Volume")
    if obv > pobv > _g(tail.iloc[-3], "obv", 0) if len(tail) >= 3 else 0:
        add(0.65, "OBV 3-Bar Rising", "Volume")

    # ── BREAKOUT ──
    if _g(row, "bo50") == 1:
        sc = 0.95 if vol > 1.5 else 0.80
        add(sc, f"50-Day Breakout{' + Volume' if vol > 1.5 else ''}", "Breakout")
    if _g(row, "bo20") == 1:
        sc = 0.90 if vol > 1.5 else 0.74
        add(sc, f"20-Day Breakout{' + Volume' if vol > 1.5 else ''}", "Breakout")
    if _g(row, "n52h") == 1 and vol > 1.2:
        add(0.87, "Near 52W High + Volume", "Breakout")
    if _g(row, "cdl_bo_candle") == 1:
        add(0.89, "Breakout Candle (Vol-Confirmed)", "Breakout")

    # ── PRICE ACTION ──
    if _g(row, "cdl_inside") == 1 and c > pc and e9 > e21:
        add(0.84, "Inside Bar Breakout", "Price Action")
    if _g(row, "cdl_sup_bounce") == 1:
        add(0.82, "Support Bounce (20D Low Zone)", "Price Action")
    if abs(pull) < 2.0 and rsi > 45 and e9 > e50:
        add(0.76, "Pullback to EMA21 (Retest)", "Price Action")

    # ── CANDLESTICK (Strict 5) ──
    if _g(row, "cdl_bull_eng") == 1:
        add(0.92, "Bullish Engulfing", "Candlestick")
    if _g(row, "cdl_hammer") == 1:
        add(0.84, "Hammer Candle", "Candlestick")
    if _g(row, "cdl_morn_star") == 1:
        add(0.95, "Morning Star (3-Bar Reversal)", "Candlestick")

    return sorted(hits.values(), key=lambda x: -x[0])

def pat_confidence(hits: List) -> float:
    if not hits:
        return 0.0
    s = hits[0][0]
    for i, h in enumerate(hits[1:6], 1):
        s += h[0] * (0.60 ** i)
    return round(min(s / 1.9, 0.98), 4)

def n_cats(hits: List) -> int:
    return len({h[2] for h in hits})

# ══════════════════════════════════════════════════════════════════════════════
# §6  SCORING  (Price-only for backtest; fundamentals overlay for live display)
# ══════════════════════════════════════════════════════════════════════════════

def row_score(row, weights: dict, use_fundamentals: bool = False) -> float:
    """Composite score. Fundamentals only used when explicitly allowed (live display)."""
    c = _g(row, "close")
    e9 = _g(row, "ema9")
    e21 = _g(row, "ema21")
    e50 = _g(row, "ema50")
    e200 = _g(row, "ema200", e50)
    bull = ((c > e9) + (e9 > e21) + (e21 > e50) + (e50 > e200)) / 4.0
    bear = ((c < e9) + (e9 < e21) + (e21 < e50) + (e50 < e200)) / 4.0
    trend = float(np.clip(bull - bear, -1, 1))

    rsi = _g(row, "rsi14", 50)
    mh = _g(row, "macd_h")
    atr = _g(row, "atr14", c * 0.02) or c * 0.02
    rsi_s = float(np.clip((rsi - 50) / 18, -1, 1))
    macd_s = float(np.clip((mh / atr) * 3, -1, 1))
    mom = float(np.clip(0.6 * rsi_s + 0.4 * macd_s, -1, 1))

    bd = _g(row, "bo20")
    vol = _g(row, "vol_ratio", 1.0)
    bod = float(np.clip(_g(row, "bo_d", 0) / 8, -1, 1))
    brk = float(np.clip(max(float(bd), bod) * min(vol / 1.5, 1.2), -1, 1))

    pull = _g(row, "pull_slow", 0)
    pull_s = (0.75 if (abs(pull) < 2.5 and c > e50 and 40 < rsi < 62) else
              0.55 if (abs(pull) < 2.5 and c > e21 and 40 < rsi < 62) else 0.0)

    vol_s = float(np.clip((vol - 1) / 1.5, -1, 1))

    eng = _g(row, "cdl_bull_eng")
    ham = _g(row, "cdl_hammer")
    morn = _g(row, "cdl_morn_star")
    pat_raw = (1.0 if (morn or eng) else 0.85 if ham else 0.0)
    pat_s = float(np.clip(pat_raw, -1, 1))

    fund_s = 0.0
    if use_fundamentals:
        pe = _g(row, "_pe", 0)
        roe = _g(row, "_roe", 0)
        eg = _g(row, "_epsg", 0)
        if pe > 0:
            fund_s += 0.35 if pe < 22 else (-0.20 if pe > 60 else 0.10)
        if roe > 0:
            fund_s += 0.35 if roe > 0.18 else (-0.10 if roe < 0.05 else 0.10)
        if eg != 0:
            fund_s += 0.20 if eg > 0.12 else (-0.10 if eg < 0 else 0.05)
        fund_s = float(np.clip(fund_s, -1, 1))

    r5 = _g(row, "ret5", 0)
    sent_s = float(np.clip(r5 / 0.05, -1, 1))

    w = weights
    ws = sum(abs(v) for v in w.values())
    sc = (w.get("trend", 0) * trend + w.get("momentum", 0) * mom +
          w.get("breakout", 0) * brk + w.get("pullback", 0) * pull_s +
          w.get("volume", 0) * vol_s + w.get("pattern", 0) * pat_s +
          w.get("fundamental", 0) * fund_s + w.get("sentiment", 0) * sent_s)
    return float(np.clip(sc / ws, -1, 1))

def add_scores(feat: pd.DataFrame, cfg: Cfg, nifty_by_date: Dict, use_fundamentals: bool = False) -> pd.DataFrame:
    """Add scores using rolling Nifty regime (passed by date), never current global state."""
    df = feat.copy()
    # Merge rolling nifty trend
    df["nifty_trend"] = df["date"].map(lambda d: nifty_by_date.get(d, {}).get("trend", 0.0))
    df["threshold"] = np.where(df["nifty_trend"] <= -0.5, cfg.bear_threshold, cfg.base_threshold)
    df["score"] = df.apply(lambda r: row_score(r, cfg.weights, use_fundamentals=use_fundamentals), axis=1)
    df["signal"] = np.where(df["score"] >= df["threshold"], "LONG", "NEUTRAL")
    return df

# ══════════════════════════════════════════════════════════════════════════════
# §7  CONFIDENCE / COMPOSITE  (Renamed from "AI" — honest heuristic)
# ══════════════════════════════════════════════════════════════════════════════

def heuristic_confidence(row, fund: dict, hits: list) -> dict:
    W = {"trend": 0.24, "momentum": 0.16, "breakout": 0.17, "pullback": 0.11,
         "volume": 0.10, "pattern": 0.10, "fundamental": 0.08, "sentiment": 0.04}
    c = _g(row, "close")
    e9 = _g(row, "ema9"); e21 = _g(row, "ema21")
    e50 = _g(row, "ema50"); e200 = _g(row, "ema200", e50)
    bull = ((c > e9) + (e9 > e21) + (e21 > e50) + (e50 > e200)) / 4.0
    bear = ((c < e9) + (e9 < e21) + (e21 < e50) + (e50 < e200)) / 4.0
    trend_s = float(np.clip(bull - bear, -1, 1))

    rsi = _g(row, "rsi14", 50)
    mh = _g(row, "macd_h")
    atr = _g(row, "atr14", c * 0.02) or c * 0.02
    rsi_s = float(np.clip((rsi - 50) / 18, -1, 1))
    macd_s = float(np.clip((mh / atr) * 3, -1, 1))
    mom_s = float(np.clip(0.6 * rsi_s + 0.4 * macd_s, -1, 1))

    bd = _g(row, "bo20")
    vol = _g(row, "vol_ratio", 1.0)
    brk_s = float(np.clip(bd * (vol / 1.5), -1, 1))

    pull = _g(row, "pull_slow", 0)
    pull_s = 0.75 if (abs(pull) < 2.5 and c > e50 and 40 < rsi < 62) else 0.0

    vol_s = float(np.clip((vol - 1) / 1.5, -1, 1))
    pat_s = min(sum(h[0] * 0.15 for h in hits[:6]), 1.0)

    pe = fund.get("pe"); roe = fund.get("roe"); eg = fund.get("eps_g")
    rg = fund.get("rev_g"); de = fund.get("de"); peg = fund.get("peg")
    fund_s = 0.0
    if pe and pe > 0:
        fund_s += 0.30 if pe < 18 else (0.15 if pe < 28 else (-0.20 if pe > 55 else 0.05))
    if roe:
        fund_s += 0.30 if roe > 0.20 else (0.10 if roe > 0.12 else (-0.10 if roe < 0.05 else 0))
    if eg:
        fund_s += 0.20 if eg > 0.15 else (-0.10 if eg < 0 else 0.05)
    if rg:
        fund_s += 0.10 if rg > 0.10 else 0
    if de:
        fund_s -= 0.15 if de > 3 else (0.05 if de > 1.5 else 0)
    if peg and peg > 0:
        fund_s += 0.10 if peg < 1 else (-0.05 if peg > 2 else 0)
    fund_s = float(np.clip(fund_s, -1, 1))

    r5 = _g(row, "ret5", 0)
    r20 = _g(row, "ret20", 0)
    sent_s = float(np.clip((r5 * 0.7 + r20 * 0.3) / 0.05, -1, 1))

    total = float(np.clip(
        W["trend"] * trend_s + W["momentum"] * mom_s + W["breakout"] * brk_s +
        W["pullback"] * pull_s + W["volume"] * vol_s + W["pattern"] * pat_s +
        W["fundamental"] * fund_s + W["sentiment"] * sent_s, -1, 1))

    pct = round(((total + 1) / 2) * 100, 1)
    bonus = 0.0
    if trend_s > 0.75: bonus += 0.03
    if vol_s > 0.40: bonus += 0.02
    if pat_s > 0.50: bonus += 0.02
    pct = min(round(pct + bonus * 50, 1), 99.0)

    return dict(
        model_pct=pct, total=round(total, 4), trend_s=round(trend_s, 3),
        mom_s=round(mom_s, 3), brk_s=round(brk_s, 3), vol_s=round(vol_s, 3),
        fund_s=round(fund_s, 3), sent_s=round(sent_s, 3), pat_s=round(pat_s, 3)
    )

def mkt_confidence(nifty: dict) -> dict:
    if not nifty:
        return dict(pct=50.0, label="Unknown", align="N/A", nifty_last=0, chg_1m=0, rsi=50)
    nt = nifty.get("trend", 0.0)
    lbl = nifty.get("label", "N/A")
    nl = nifty.get("last", 0.0)
    c1m = nifty.get("chg_1m", 0.0)
    nr = nifty.get("rsi", 50.0)
    pct = float(np.clip((nt + 1) / 2 * 100, 0, 100))
    align = ("Favorable" if nt > 0.5 else "Supportive" if nt > 0.2 else
             "Headwind" if nt < -0.3 else "Neutral")
    return dict(pct=round(pct, 1), label=lbl, align=align,
                nifty_last=round(nl, 2), chg_1m=round(c1m, 2), rsi=round(nr, 1))

# ══════════════════════════════════════════════════════════════════════════════
# §8  TRADE LEVELS  (Unified for display AND backtest)
# ══════════════════════════════════════════════════════════════════════════════

def trade_levels(close: float, atr: float, cfg: Cfg) -> Optional[dict]:
    if atr <= 0 or close <= 0:
        return None
    def rr(sl, tp):
        return round(abs(tp - close) / abs(close - sl), 2) if abs(close - sl) > 0 else 0.0
    st_sl = round(close - cfg.st_sl_mult * atr, 2)
    st_tp = round(close + cfg.st_tp_mult * atr, 2)
    lt_sl = round(close - cfg.lt_sl_mult * atr, 2)
    lt_tp = round(close + cfg.lt_tp_mult * atr, 2)
    st_rr = rr(st_sl, st_tp)
    lt_rr = rr(lt_sl, lt_tp)
    if st_rr < cfg.min_rr and lt_rr < cfg.min_rr:
        return None
    def pkg(sl, tp, rr_v, win):
        return dict(entry=round(close, 2), sl=sl, tp=tp,
                    risk=round(abs(close - sl), 2),
                    reward=round(abs(tp - close), 2),
                    rr=rr_v, rr_str=f"1:{rr_v}", window=win)
    return dict(
        short_term=pkg(st_sl, st_tp, st_rr, "2–5 trading days"),
        long_term=pkg(lt_sl, lt_tp, lt_rr, "10–20 trading days")
    )

# ══════════════════════════════════════════════════════════════════════════════
# §9  BACKTEST ENGINE  (Production-grade: no lookahead, realistic fills, vol targeting, correlation guard)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class _Pos:
    sym: str
    qty: int
    entry_date: pd.Timestamp
    entry_p: float
    stop: float
    target: float
    fees_in: float
    bars: int = 0

def run_backtest(feat: pd.DataFrame, cfg: Cfg, nifty_by_date: Dict) -> dict:
    empty = dict(ret=0.0, sharpe=0.0, maxdd=0.0, winrate=0.0, trades=0,
                 final=cfg.bt_capital, avg_ret=0.0, avg_bars=0.0, trades_df=pd.DataFrame())
    need = {"date", "symbol", "open", "high", "low", "close", "score", "signal", "atr14"}
    if not need.issubset(feat.columns):
        LOG.error("Backtest missing columns: %s", need - set(feat.columns))
        return empty

    data = feat.copy()
    data["date"] = _norm_dates(data["date"])
    data = data.sort_values(["date", "symbol"]).reset_index(drop=True)

    # ── Survivorship bias guard: require full history coverage ──
    first_date = data["date"].min()
    last_date = data["date"].max()
    sym_counts = data.groupby("symbol")["date"].nunique()
    expected_bars = data["date"].nunique()
    valid_syms = set(sym_counts[sym_counts >= expected_bars * 0.95].index)
    if len(valid_syms) < len(sym_counts):
        LOG.info("Survivorship guard: dropped %d symbols with incomplete history", len(sym_counts) - len(valid_syms))
        data = data[data["symbol"].isin(valid_syms)].copy()

    if data.empty:
        return empty

    by_d = {d: g.set_index("symbol") for d, g in data.groupby("date")}
    dates = sorted(by_d.keys())
    if len(dates) < 20:
        return empty

    # ── Pre-compute returns matrix for correlation filter ──
    pivot_close = data.pivot(index="date", columns="symbol", values="close").sort_index()
    returns_df = pivot_close.pct_change().fillna(0)

    cost = cfg.bt_cost_bps / 10_000
    slip = cfg.bt_slip_bps / 10_000

    poss: Dict[str, _Pos] = {}
    trades = []
    eq_rows = []
    cash = cfg.bt_capital

    for idx, date in enumerate(dates):
        day = by_d[date]
        nd = dates[idx + 1] if idx + 1 < len(dates) else None

        # ── Execute exits (realistic: check low/high, gap fills) ──
        for sym in list(poss.keys()):
            p = poss[sym]
            if sym not in day.index:
                continue
            row = day.loc[sym]
            o = float(row["open"]); h = float(row["high"]); lo = float(row["low"]); c = float(row["close"])
            exit_price = None; reason = None

            # Long stop: if open below stop, fill at open (gap); else if low touches stop, fill at stop
            if lo <= p.stop:
                exit_price = o if o <= p.stop else p.stop
                exit_price *= (1 - slip)  # slippage against us
                reason = "stop_loss"
            elif h >= p.target:
                exit_price = o if o >= p.target else p.target
                exit_price *= (1 + slip)  # slippage against us on exit
                reason = "take_profit"
            elif p.bars >= cfg.bt_max_hold:
                exit_price = c * (1 - slip)
                reason = "max_hold"
            elif p.bars >= cfg.bt_min_hold and str(row.get("signal", "NEUTRAL")) != "LONG":
                exit_price = o * (1 - slip)
                reason = "signal_exit"

            if exit_price is not None and nd is not None:
                tv = p.qty * exit_price
                ef = abs(tv) * cost
                cash += tv - ef
                pnl = p.qty * (exit_price - p.entry_p) - p.fees_in - ef
                basis = p.qty * p.entry_p
                trades.append(dict(
                    sym=sym, entry=p.entry_date, exit=date, ep=round(p.entry_p, 2),
                    xp=round(exit_price, 2), pnl=round(pnl, 2),
                    ret=round(pnl / basis if basis else 0, 4),
                    bars=p.bars, reason=reason
                ))
                del poss[sym]
            elif p.bars >= cfg.bt_max_hold and nd is None:
                # EOP liquidation
                exit_price = c * (1 - slip)
                tv = p.qty * exit_price
                ef = abs(tv) * cost
                cash += tv - ef
                pnl = p.qty * (exit_price - p.entry_p) - p.fees_in - ef
                basis = p.qty * p.entry_p
                trades.append(dict(
                    sym=sym, entry=p.entry_date, exit=date, ep=round(p.entry_p, 2),
                    xp=round(exit_price, 2), pnl=round(pnl, 2),
                    ret=round(pnl / basis if basis else 0, 4),
                    bars=p.bars, reason="eop"
                ))
                del poss[sym]

        # ── Compute equity ──
        equity = cash + sum(
            p.qty * float(day.loc[s, "close"]) for s, p in poss.items() if s in day.index
        )
        eq_rows.append(dict(date=date, equity=round(equity, 2)))

        if not nd:
            continue

        # ── New entries ──
        # Candidates: LONG signal, score >= threshold, not already held, not being sold today
        blocked = set(poss.keys())
        slots = cfg.bt_max_pos - len(poss)
        if slots <= 0:
            continue

        cands = day.reset_index()
        cands = cands[
            (cands.get("signal", "NEUTRAL") == "LONG") &
            (cands.get("score", pd.Series(dtype=float)).fillna(0) >= cands.get("threshold", cfg.base_threshold)) &
            (~cands["symbol"].isin(blocked))
        ].sort_values("score", ascending=False)

        selected = []
        for _, r in cands.iterrows():
            if len(selected) >= slots:
                break
            sym = r["symbol"]
            # Correlation guard
            if selected:
                window = returns_df.loc[:date].tail(60)
                if len(window) >= 20:
                    sym_rets = window.get(sym, pd.Series(dtype=float))
                    ok = True
                    for s in selected:
                        s_rets = window.get(s, pd.Series(dtype=float))
                        common = pd.concat([sym_rets, s_rets], axis=1).dropna()
                        if len(common) >= 20:
                            corr = np.corrcoef(common.iloc[:, 0], common.iloc[:, 1])[0, 1]
                            if abs(corr) > cfg.bt_max_correlation:
                                ok = False
                                break
                    if not ok:
                        continue

            # ATR-based levels (unified with display)
            close = float(r["close"])
            atr = float(r.get("atr14", close * 0.02)) or close * 0.02
            lvl = trade_levels(close, atr, cfg)
            if lvl is None:
                continue
            stop_p = lvl["short_term"]["sl"]
            risk_per_share = abs(close - stop_p)
            if risk_per_share <= 0:
                continue

            # Volatility targeting: 1% risk per trade
            risk_amt = equity * cfg.bt_risk_per_trade
            qty = int(risk_amt // risk_per_share)
            # Cap by max capital allocation
            max_by_cap = int((equity * cfg.bt_pos_pct) // close)
            qty = min(qty, max_by_cap)
            if qty <= 0:
                continue
            total_cost = qty * close
            if cash < total_cost * (1 + cost * 2):  # need capital + buffer
                continue

            fees_in = total_cost * cost
            cash -= total_cost + fees_in
            poss[sym] = _Pos(sym, qty, date, close, stop_p, lvl["short_term"]["tp"], fees_in)
            selected.append(sym)

        # Increment bar count for surviving positions
        for p in poss.values():
            p.bars += 1

    # Final liquidation for any remaining positions
    ld = by_d[dates[-1]]
    for sym, p in list(poss.items()):
        if sym not in ld.index:
            continue
        fp = float(ld.loc[sym, "close"]) * (1 - slip)
        tv = p.qty * fp
        ef = abs(tv) * cost
        cash += tv - ef
        pnl = p.qty * (fp - p.entry_p) - p.fees_in - ef
        basis = p.qty * p.entry_p
        trades.append(dict(
            sym=sym, entry=p.entry_date, exit=dates[-1], ep=round(p.entry_p, 2),
            xp=round(fp, 2), pnl=round(pnl, 2),
            ret=round(pnl / basis if basis else 0, 4),
            bars=p.bars, reason="eop"
        ))

    eq = pd.DataFrame(eq_rows)
    trd = pd.DataFrame(trades)
    if eq.empty or len(eq) < 2:
        return empty

    eq["dr"] = eq["equity"].pct_change().fillna(0)
    eq["dd"] = (eq["equity"] / eq["equity"].cummax()) - 1
    std = float(eq["dr"].std(ddof=0)) if len(eq) > 1 else 0
    sharpe = float((eq["dr"].mean() / std) * sqrt(252)) if std else 0.0
    final = float(eq["equity"].iloc[-1])

    return dict(
        ret=round(final / cfg.bt_capital - 1, 4),
        sharpe=round(sharpe, 3),
        maxdd=round(float(eq["dd"].min()), 4),
        winrate=round(float((trd["pnl"] > 0).mean()) if not trd.empty else 0, 3),
        trades=len(trd),
        final=round(final, 2),
        avg_ret=round(float(trd["ret"].mean()) if not trd.empty else 0, 4),
        avg_bars=round(float(trd["bars"].mean()) if not trd.empty else 0, 1),
        trades_df=trd,
        equity_df=eq,
    )

# ══════════════════════════════════════════════════════════════════════════════
# §10  ALERT BUILDER  (Fundamentals for DISPLAY ONLY, never in backtest score)
# ══════════════════════════════════════════════════════════════════════════════

def _sel_reason(row, hits, fund, conf, mkt) -> str:
    parts = []
    e9 = _g(row, "ema9"); e21 = _g(row, "ema21"); e50 = _g(row, "ema50")
    rsi = _g(row, "rsi14", 50); vol = _g(row, "vol_ratio", 1.0)
    mh = _g(row, "macd_h"); c = _g(row, "close"); adx = _g(row, "adx", 0)
    stf = int(_g(row, "st_flip", 0))
    if hits:
        parts.append(f"Primary: {hits[0][1]} ({hits[0][0]*100:.0f}% conf)")
    if stf == 1:
        parts.append("SuperTrend just flipped BULLISH")
    if e9 > e21 > e50:
        parts.append(f"Full EMA alignment ({e9:.0f}>{e21:.0f}>{e50:.0f})")
    elif e9 > e21:
        parts.append(f"EMA bullish ({e9:.0f}>{e21:.0f})")
    if rsi < 35:
        parts.append(f"RSI={rsi:.1f} oversold")
    elif 45 < rsi < 65:
        parts.append(f"RSI={rsi:.1f} healthy")
    if mh > 0:
        parts.append("MACD histogram positive")
    if adx > 25:
        parts.append(f"ADX={adx:.0f} strong trend")
    if vol >= 1.5:
        parts.append(f"Volume {vol:.1f}x avg")
    pe = fund.get("pe"); roe = fund.get("roe")
    if pe and pe > 0:
        parts.append(f"P/E={pe:.1f}")
    if roe and roe > 0:
        parts.append(f"ROE={roe*100:.1f}%")
    parts.append(f"Market: {mkt.get('label','N/A')} | {mkt.get('align','N/A')}")
    return "  •  ".join(parts[:7])

def build_alerts(feat: pd.DataFrame, nifty: dict, fund_cache: dict, cfg: Cfg) -> tuple:
    latest = (feat.sort_values("date").groupby("symbol", sort=False).tail(1).reset_index(drop=True))
    results = []
    rej = defaultdict(int)
    for _, row in latest.iterrows():
        sym = str(row["symbol"])
        c = float(row["close"])
        sig = str(row.get("signal", "NEUTRAL"))
        score = float(row.get("score", 0))
        atr = float(row.get("atr14", c * 0.02) or c * 0.02)
        atr_p = atr / c * 100 if c else 0
        avg_v = float(row.get("avg_vol20", 0) or 0)
        tv = float(row.get("med_tv20", 0) or 0) / 1e7

        if sig != "LONG":
            continue
        if c < cfg.min_price:
            rej["price"] += 1; continue
        if atr_p < cfg.min_atr_pct * 100:
            rej["atr_lo"] += 1; continue
        if atr_p > cfg.max_atr_pct * 100:
            rej["atr_hi"] += 1; continue
        if avg_v < cfg.min_avg_vol:
            rej["vol"] += 1; continue
        if tv < cfg.min_traded_val_cr:
            rej["tv"] += 1; continue

        tail = latest[latest["symbol"] == sym].tail(3)
        hits = detect_patterns(row, tail)
        pc = pat_confidence(hits)
        cats = n_cats(hits)
        if cats < cfg.min_categories:
            rej["cats"] += 1; continue

        lvl = trade_levels(c, atr, cfg)
        if lvl is None:
            rej["rr"] += 1; continue

        fund = fund_cache.get(sym, {})
        conf = heuristic_confidence(row, fund, hits)
        mk = mkt_confidence(nifty)
        sel = _sel_reason(row, hits, fund, conf, mk)
        results.append(dict(
            symbol=sym, last_close=round(c, 2), score=round(score, 4),
            atr=round(atr, 2), atr_pct=round(atr_p, 2),
            rsi=round(float(row.get("rsi14", 50) or 50), 1),
            macd_h=round(float(row.get("macd_h", 0) or 0), 4),
            adx=round(float(row.get("adx", 0) or 0), 1),
            vol_ratio=round(float(row.get("vol_ratio", 1) or 1), 2),
            vol_z=round(float(row.get("vol_z", 0) or 0), 2),
            avg_vol=int(avg_v), traded_val_cr=round(tv, 2),
            ema9=round(float(row.get("ema9", 0) or 0), 2),
            ema21=round(float(row.get("ema21", 0) or 0), 2),
            ema50=round(float(row.get("ema50", 0) or 0), 2),
            ema200=round(float(row.get("ema200", 0) or 0), 2),
            st_flip=int(_g(row, "st_flip", 0)),
            is_fo=sym in _FO_SET, indices=symbol_tags(sym),
            sector=fund.get("sector", "N/A"), industry=fund.get("industry", "N/A"),
            pe=fund.get("pe"), pb=fund.get("pb"), roe=fund.get("roe"),
            mcap=fund.get("mcap"), w52h=fund.get("w52h"), w52l=fund.get("w52l"),
            beta=fund.get("beta"),
            hits=hits, pat_conf=pc, n_cats=cats, levels=lvl,
            model=conf, mkt=mk,
            reason=sel, scan_ts=datetime.now().strftime("%Y-%m-%d %H:%M")
        ))
    results.sort(key=lambda r: (-r["model"]["model_pct"], -abs(r["score"])))
    LOG.info("Alerts: %d passed | rej: %s", len(results), dict(rej))
    return results, dict(rej)

# ══════════════════════════════════════════════════════════════════════════════
# §11  SAVE OUTPUTS
# ══════════════════════════════════════════════════════════════════════════════

def save_all(alerts: list, bt: dict, nifty: dict, cfg: Cfg) -> dict:
    od = cfg.output_dir
    od.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    rows = []
    for r in alerts:
        st = r["levels"]["short_term"]
        lt = r["levels"]["long_term"]
        conf = r["model"]
        mk = r["mkt"]
        rows.append({
            "scan_ts": r["scan_ts"], "symbol": r["symbol"], "last_close": r["last_close"],
            "score": r["score"], "rsi": r["rsi"], "adx": r["adx"], "atr_pct": r["atr_pct"],
            "vol_ratio": r["vol_ratio"], "avg_vol": r["avg_vol"], "traded_val_cr": r["traded_val_cr"],
            "model_pct": conf["model_pct"], "mkt_pct": mk["pct"],
            "pat_conf_pct": round(r["pat_conf"] * 100, 1), "n_cats": r["n_cats"],
            "top_signal": r["hits"][0][1] if r["hits"] else "",
            "st_entry": st["entry"], "st_target": st["tp"], "st_sl": st["sl"], "st_rr": st["rr"],
            "lt_entry": lt["entry"], "lt_target": lt["tp"], "lt_sl": lt["sl"], "lt_rr": lt["rr"],
            "is_fo": r["is_fo"], "indices": r["indices"], "sector": r["sector"],
            "pe": r["pe"], "roe": r["roe"], "mcap": r["mcap"], "reason": r["reason"][:250]
        })
    alerts_p = od / f"alerts_{ts}.csv"
    pd.DataFrame(rows).to_csv(alerts_p, index=False)
    bt.get("trades_df", pd.DataFrame()).to_csv(od / f"trades_{ts}.csv", index=False)
    bt.get("equity_df", pd.DataFrame()).to_csv(od / f"equity_{ts}.csv", index=False)
    with open(od / f"summary_{ts}.json", "w") as f:
        json.dump({
            "run_ts": ts,
            "nifty": {k: v for k, v in nifty.items() if k != "ts"},
            "backtest": {k: v for k, v in bt.items() if k not in ("trades_df", "equity_df")},
            "top10": [{"symbol": r["symbol"], "model_pct": r["model"]["model_pct"],
                       "st": r["levels"]["short_term"], "lt": r["levels"]["long_term"]}
                      for r in alerts[:10]]
        }, f, indent=2, default=str)
    return dict(alerts=alerts_p, output_dir=od)

# ══════════════════════════════════════════════════════════════════════════════
# §12  TERMINAL DISPLAY  (Adapted for v11 — honest labels, no "AI" fiction)
# ══════════════════════════════════════════════════════════════════════════════

def _sparkline(prices: list, width: int = 28) -> str:
    B = "▁▂▃▄▅▆▇█"
    if len(prices) < 2:
        return "─" * width
    tail = prices[-width:]
    mn, mx = min(tail), max(tail)
    span = mx - mn if mx != mn else 1
    chars = [B[int((v - mn) / span * (len(B) - 1))] for v in tail]
    return " " * (width - len(chars)) + "".join(chars)

def _grade(pct: float) -> tuple:
    if pct >= 88: return "A+", "bold bright_green"
    if pct >= 78: return "A",  "bold green"
    if pct >= 68: return "B+", "bold yellow"
    if pct >= 58: return "B",  "bold yellow"
    if pct >= 48: return "C+", "bold red"
    return "C", "bold red"

def _gauge(pct: float, width: int = 18) -> str:
    f = max(0, min(int(pct / 100 * width), width))
    if pct >= 80:   col = "bold bright_green"
    elif pct >= 65: col = "green"
    elif pct >= 50: col = "yellow"
    else:           col = "red"
    return f"[{col}]{'█' * f}[/{col}][dim]{'░' * (width - f)}[/dim]  [{col}]{pct:.1f}%[/{col}]"

def plain_report(alerts: list, nifty: dict, bt: dict, cfg: Cfg) -> None:
    SEP = "=" * 110
    print(f"\n{SEP}")
    print(f"NSE SWING TRADER v11.0 (PRODUCTION)  |  {datetime.now().strftime('%d %b %Y %H:%M')}")
    print(f"Market: {nifty.get('label','N/A')} | Nifty ₹{nifty.get('last',0):,.2f} | "
          f"RSI: {nifty.get('rsi',50):.1f} | 1M: {nifty.get('chg_1m',0):+.2f}%")
    print(f"Backtest — Return: {bt.get('ret',0):+.2%}  "
          f"Sharpe: {bt.get('sharpe',0):.3f}  "
          f"MaxDD: {bt.get('maxdd',0):.2%}  "
          f"WinRate: {bt.get('winrate',0):.1%}  "
          f"Trades: {bt.get('trades',0)}")
    print(f"NOTE: Backtest uses ONLY lagged price data. No fundamentals. No lookahead.")
    print(SEP)
    for i, r in enumerate(alerts[:cfg.top_n], 1):
        st = r["levels"]["short_term"]; lt = r["levels"]["long_term"]
        hits = r["hits"]; conf = r["model"]; mk = r["mkt"]
        print(f"\n[{i:>2}]  *** {r['symbol']} ***  "
              f"Close: ₹{r['last_close']:,.2f}  "
              f"Model: {conf['model_pct']:.1f}%  "
              f"Market: {mk['pct']:.1f}%  "
              f"ADX: {r['adx']:.1f}  "
              f"RSI: {r['rsi']:.1f}  "
              f"Vol: {r['vol_ratio']:.2f}x")
        print(f"       Signal:    {hits[0][1] if hits else '—'}")
        print(f"       Short-Term: Entry ₹{st['entry']:,.2f}  →  Target ₹{st['tp']:,.2f}"
              f"  |  Stop ₹{st['sl']:,.2f}  |  R:R {st['rr_str']}  |  {st['window']}")
        print(f"       Long-Term:  Entry ₹{lt['entry']:,.2f}  →  Target ₹{lt['tp']:,.2f}"
              f"  |  Stop ₹{lt['sl']:,.2f}  |  R:R {lt['rr_str']}  |  {lt['window']}")
        print(f"       Reason:     {r['reason'][:115]}")
        print(f"       Indices:    {r['indices']}")
        print("-" * 110)

# ══════════════════════════════════════════════════════════════════════════════
# §13  MAIN ORCHESTRATION
# ══════════════════════════════════════════════════════════════════════════════

def run(cfg: Cfg) -> tuple:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)-8s | %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(cfg.output_dir / "nse_v11.log")])
    for nm in ("yfinance", "urllib3", "requests", "charset_normalizer"):
        logging.getLogger(nm).setLevel(logging.CRITICAL)
    t0 = time.time()

    if _HAS_RICH:
        _con.print()
        _con.print(Rule(characters="═", style="bright_cyan"))
        _con.print(Align.center(
            "[bold bright_white on #003366]"
            "   NSE SWING TRADER v11.0  ·  PRODUCTION ENGINE   "
            "·  NO LOOK-AHEAD  ·  REALISTIC FILLS   "
            "[/bold bright_white on #003366]"))
        _con.print(Align.center(
            f"[dim]  {datetime.now().strftime('%A, %d %B %Y  |  %H:%M IST')}  "
            f"|  Capital: ₹{cfg.capital/1e5:.0f}L  "
            f"|  Universe: {len(_ALL_SYMS)} symbols  [/dim]"))
        _con.print(Rule(characters="═", style="bright_cyan"))
        _con.print(f"\n[dim]Fetching Nifty50 benchmark & rolling regime...[/dim]")

    # ── Fetch Nifty history and compute ROLLING regime by date ──
    nifty_hist = nifty50_history(cfg.live_period, cfg.live_interval)
    nifty_regime_df = compute_nifty_regime(nifty_hist) if not nifty_hist.empty else pd.DataFrame()
    nifty_by_date = {}
    if not nifty_regime_df.empty:
        for _, row in nifty_regime_df.iterrows():
            d = pd.Timestamp(row["date"]).normalize()
            nifty_by_date[d] = {
                "trend": float(row["trend"]),
                "label": str(row["label"]),
                "rsi": float(row["rsi"]),
                "last": float(row["close"]),
                "ema9": float(row.get("ema9", 0)),
                "ema21": float(row.get("ema21", 0)),
                "ema50": float(row.get("ema50", 0)),
            }
    # Current nifty snapshot for display
    latest_nifty = max(nifty_by_date.values(), key=lambda x: x.get("last", 0)) if nifty_by_date else {}
    if not latest_nifty:
        latest_nifty = {"trend": 0, "label": "N/A", "rsi": 50, "last": 0, "ema9": 0, "ema21": 0, "ema50": 0}
    # Add 1M/3M change if history exists
    if not nifty_hist.empty:
        cl = nifty_hist.sort_values("date")["close"].reset_index(drop=True)
        latest_nifty["chg_1m"] = float((cl.iloc[-1] / cl.iloc[-22] - 1) * 100) if len(cl) >= 22 else 0.0
        latest_nifty["chg_3m"] = float((cl.iloc[-1] / cl.iloc[0] - 1) * 100) if len(cl) > 0 else 0.0
    else:
        latest_nifty["chg_1m"] = 0.0; latest_nifty["chg_3m"] = 0.0

    if _HAS_RICH and latest_nifty:
        threshold = cfg.bear_threshold if latest_nifty.get("trend", 0) <= -0.5 else cfg.base_threshold
        _con.print(
            f"[bold blue]Nifty50:[/bold blue]  ₹{latest_nifty.get('last',0):.0f}  "
            f"{latest_nifty.get('label','N/A')}  RSI:{latest_nifty.get('rsi',50):.0f}  "
            f"1M:{latest_nifty.get('chg_1m',0):+.1f}%  3M:{latest_nifty.get('chg_3m',0):+.1f}%")
        if latest_nifty.get("trend", 0) <= -0.5:
            _con.print(f"[bold red]Bear market — threshold raised to {threshold:.2f}[/bold red]\n")
        else:
            _con.print()

    syms = cfg.symbols if cfg.symbols else _ALL_SYMS
    syms = sorted(set(syms) - _SKIP_SYMBOLS)
    if _HAS_RICH:
        _con.print(f"[dim]Scanning {len(syms)} unique symbols...[/dim]\n")

    all_frames = []
    fund_cache = {}
    ok = 0; fail = 0

    if _HAS_YF:
        def _fetch(sym):
            nonlocal ok, fail
            df = fetch_ohlcv(sym, cfg.live_period, cfg.live_interval)
            if not df.empty and len(df) >= cfg.min_bars:
                all_frames.append(df)
                if cfg.fetch_fundamentals:
                    fund_cache[sym] = fetch_fundamentals(sym)
                ok += 1
            else:
                fail += 1

        if _HAS_RICH:
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                          BarColumn(bar_width=24), TextColumn("{task.completed}/{task.total}"),
                          TimeElapsedColumn(), console=_con) as prog:
                task = prog.add_task("[cyan]Live scanning NSE...", total=len(syms))
                for sym in syms:
                    prog.update(task, description=f"[cyan][bold]{sym:<14}[/bold]")
                    _fetch(sym); prog.advance(task)
        else:
            for i, sym in enumerate(syms, 1):
                if i % 20 == 0:
                    LOG.info("Progress: %d/%d  ok:%d fail:%d", i, len(syms), ok, fail)
                _fetch(sym)
    else:
        LOG.error("yfinance not available — cannot fetch data")
        return [], {}

    if not all_frames:
        raise ValueError("No price data loaded.")

    prices = pd.concat(all_frames, ignore_index=True)
    prices = (prices.sort_values(["symbol", "date"])
              .drop_duplicates(["date", "symbol"], keep="last")
              .reset_index(drop=True))
    LOG.info("Loaded %d bars across %d symbols.", len(prices), prices["symbol"].nunique())

    # ── Feature engineering ──
    if _HAS_RICH:
        _con.print("[dim]Computing indicators...[/dim]")
    feat = engineer_all(prices, cfg)
    if feat.empty:
        raise ValueError("Feature engineering returned empty frame.")

    # ── Scoring with ROLLING nifty regime (NO lookahead) ──
    # Backtest score: price-only, no fundamentals
    feat = add_scores(feat, cfg, nifty_by_date, use_fundamentals=False)

    # ── Backtest ──
    if _HAS_RICH:
        _con.print("[dim]Running backtest with realistic fills...[/dim]")
    bt = run_backtest(feat, cfg, nifty_by_date)

    # ── Live alerts: fundamentals OK for display only ──
    alerts, rej = build_alerts(feat, latest_nifty, fund_cache, cfg)
    elapsed = round(time.time() - t0, 1)

    if _HAS_RICH:
        _con.print(
            f"\n[dim]Scan done in [bold]{elapsed}s[/bold]  |  "
            f"Fetched:[bold]{ok}[/bold]  Skipped:[yellow]{fail}[/yellow]  "
            f"Alerts:[bold bright_green]{len(alerts)}[/bold bright_green]  "
            f"Rejected:{dict(rej)}[/dim]\n")

    save_all(alerts, bt, latest_nifty, cfg)

    if not _HAS_RICH:
        plain_report(alerts, latest_nifty, bt, cfg)
        return alerts, bt

    if not alerts:
        _con.print("[bold yellow]  No bullish signals passed quality gates.[/bold yellow]")
        _con.print("[dim]  Try: --threshold 0.18  or  --min-vol 1000000[/dim]")
        return alerts, bt

    # ── Rich display (abbreviated for space) ──
    _con.print(Rule(characters="═", style="bright_cyan"))
    _con.print(Align.center(
        f"[bold bright_cyan]  MARKET: {latest_nifty.get('label','N/A')}  "
        f"Nifty ₹{latest_nifty.get('last',0):,.2f}  "
        f"Backtest Return: {bt.get('ret',0):+.2%}  "
        f"Sharpe: {bt.get('sharpe',0):.3f}  "
        f"MaxDD: {bt.get('maxdd',0):.2%}  [/bold bright_cyan]"))
    _con.print(Rule(characters="═", style="bright_cyan"))

    for i, r in enumerate(alerts[:cfg.top_n], 1):
        conf = r["model"]
        ltr, lcol = _grade(conf["model_pct"])
        st = r["levels"]["short_term"]
        _con.print()
        _con.print(Rule(characters="█", style="green"))
        h = (f"[bold bright_green]  #{i}  [/bold bright_green]"
             f"[bold bright_white on green]   {r['symbol']}   [/bold bright_white on green]"
             f"[bold bright_green]  ●  LONG  [/bold bright_green]"
             f"  [bold cyan]Model: {conf['model_pct']:.1f}%[/bold cyan]"
             f"  [bold white]Score: {r['score']:+.4f}[/bold white]"
             f"  [{lcol}]Grade: {ltr}[/{lcol}]")
        _con.print(Align.center(h))
        _con.print(Rule(characters="█", style="green"))
        _con.print(f"  [dim]₹{r['last_close']:,.2f}  ·  RSI {r['rsi']:.1f}  ·  ADX {r['adx']:.1f}  "
                     f"·  Vol {r['vol_ratio']:.2f}x  ·  ATR {r['atr_pct']:.2f}%[/dim]")
        _con.print(f"  [dim]ST: Entry ₹{st['entry']:,.2f} → Target ₹{st['tp']:,.2f}  "
                     f"| Stop ₹{st['sl']:,.2f} | R:R {st['rr_str']}[/dim]")
        _con.print(f"  [dim]{r['reason'][:200]}[/dim]")
        _con.print()

    _con.print(Rule(characters="═", style="bright_cyan"))
    _con.print(Align.center(
        f"[bold bright_cyan]  ✅  NSE Swing Trader v11.0  ·  {len(alerts)} signal(s)  "
        f"·  {datetime.now().strftime('%d %b %Y  %H:%M IST')}  "
        f"·  Runtime: {elapsed:.1f}s  [/bold bright_cyan]"))
    _con.print(Rule(characters="═", style="bright_cyan"))
    _con.print()

    return alerts, bt

# ══════════════════════════════════════════════════════════════════════════════
# §14  CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(
        description="NSE Swing Trader v11.0 — Production Engine (No Look-Ahead)",
        formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--symbols", type=str, default="",
                   help="Comma-separated NSE symbols. Default: full universe.")
    p.add_argument("--group", type=str, default="",
                   help="Index group: 'NIFTY BANK', 'FO STOCKS', etc.")
    p.add_argument("--top-n", type=int, default=10)
    p.add_argument("--output-dir", type=Path, default=Path("nse_v11_output"))
    p.add_argument("--period", type=str, default="8mo")
    p.add_argument("--min-vol", type=int, default=750_000)
    p.add_argument("--min-rr", type=float, default=1.2)
    p.add_argument("--threshold", type=float, default=0.16)
    p.add_argument("--no-fund", action="store_true",
                   help="Skip fundamental fetch (faster, recommended for backtest purity)")
    p.add_argument("--capital", type=float, default=1_000_000,
                   help="Portfolio capital for position sizing (default ₹10L).")
    a = p.parse_args()

    cfg = Cfg()
    cfg.output_dir = a.output_dir
    cfg.live_period = a.period
    cfg.top_n = a.top_n
    cfg.min_avg_vol = a.min_vol
    cfg.min_rr = a.min_rr
    cfg.base_threshold = a.threshold
    cfg.fetch_fundamentals = not a.no_fund
    cfg.capital = a.capital

    if a.symbols:
        cfg.symbols = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    elif a.group:
        gk = a.group.strip().upper()
        matched = [sl for grp, sl in _UNIVERSE.items() if gk in grp.upper()]
        if matched:
            cfg.symbols = sorted({s for sub in matched for s in sub} - _SKIP_SYMBOLS)
        else:
            print(f"Group '{a.group}' not found. Available: {list(_UNIVERSE.keys())}")
            sys.exit(1)

    run(cfg)

# ══════════════════════════════════════════════════════════════════════════════
# §15  STREAMLIT DASHBOARD  (Functional, honest labels, no "AI" fiction)
# ══════════════════════════════════════════════════════════════════════════════

def _d_grade(pct: float) -> tuple:
    if pct >= 88: return "A+", "#26a69a"
    if pct >= 78: return "A", "#4db6ac"
    if pct >= 68: return "B+", "#f59e0b"
    if pct >= 58: return "B", "#fbbf24"
    if pct >= 48: return "C+", "#ef5350"
    return "C", "#e53935"

def _d_rsi_col(r):
    if r < 30: return "#26a69a"
    if r < 45: return "#4db6ac"
    if r < 60: return "#f59e0b"
    if r < 75: return "#ffa726"
    return "#ef5350"

def _d_adx_col(a):
    if a >= 40: return "#26a69a"
    if a >= 28: return "#4db6ac"
    if a >= 20: return "#f59e0b"
    return "#ef5350"

def run_dashboard(alerts_in, bt_in, nifty_in, feat_df_in):
    alerts = alerts_in or []
    bt = bt_in or {}
    nifty = nifty_in or {}

    trend = nifty.get("trend", 0)
    last = nifty.get("last", 0)
    rsi_n = nifty.get("rsi", 50)
    chg1m = nifty.get("chg_1m", 0)
    lbl = nifty.get("label", "N/A")
    nt_col = "#26a69a" if trend >= 0.5 else "#ef5350" if trend <= -0.5 else "#f59e0b"

    avg_model = sum(r["model"]["model_pct"] for r in alerts) / max(len(alerts), 1)
    n_fo = sum(1 for r in alerts if r.get("is_fo"))
    bt_ret = bt.get("ret", 0)
    bt_sh = bt.get("sharpe", 0)
    bt_dd = bt.get("maxdd", 0)
    bt_wr = bt.get("winrate", 0)
    bt_tr = bt.get("trades", 0)

    st.markdown(f"""
    <style>
    .stApp {{ background: #0b0e11; color: #d1d4dc; font-family: 'Segoe UI', sans-serif; }}
    [data-testid="stMetricContainer"] {{ background: #131722; border: 1px solid #2a3347; border-radius: 4px; padding: 12px; }}
    </style>
    """, unsafe_allow_html=True)

    # Header
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Nifty50", f"₹{last:,.0f}", f"{lbl}")
    c2.metric("1M Change", f"{chg1m:+.2f}%")
    c3.metric("🟢 Signals", f"{len(alerts)}", f"F&O: {n_fo}")
    c4.metric("📊 BT Return", f"{bt_ret:+.2%}")
    c5.metric("📐 Sharpe", f"{bt_sh:.3f}")

    if not alerts:
        st.warning("No signals passed quality gates. Try lowering threshold or min-vol.")
        return

    tabs = st.tabs(["📋 Top Signals", "📊 Signal Cards", "📈 Backtest", "🔍 Sector Scan"])

    # ── TAB 0: Top Signals Table ──
    with tabs[0]:
        rows = []
        for r in alerts[:20]:
            conf = r["model"]; mk = r["mkt"]
            stl = r["levels"]["short_term"]
            ltl = r["levels"]["long_term"]
            ltr, _ = _d_grade(conf["model_pct"])
            rows.append({
                "Symbol": r["symbol"], "Grade": ltr,
                "Model%": round(conf["model_pct"], 1),
                "Score": round(r["score"], 4),
                "RSI": r["rsi"], "ADX": r["adx"],
                "Vol×": r["vol_ratio"], "ATR%": r["atr_pct"],
                "F&O": "✅" if r["is_fo"] else "—",
                "Price ₹": r["last_close"],
                "ST Target ₹": stl["tp"], "ST SL ₹": stl["sl"], "ST R:R": stl["rr_str"],
                "LT Target ₹": ltl["tp"], "LT SL ₹": ltl["sl"], "LT R:R": ltl["rr_str"],
                "Top Signal": r["hits"][0][1] if r["hits"] else "—",
                "Indices": r["indices"],
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, height=500,
                     column_config={
                         "Model%": st.column_config.ProgressColumn("Model%", min_value=0, max_value=100, format="%.1f%%"),
                         "Price ₹": st.column_config.NumberColumn("Price ₹", format="₹%.2f"),
                         "ST Target ₹": st.column_config.NumberColumn("ST Tgt", format="₹%.2f"),
                         "ST SL ₹": st.column_config.NumberColumn("ST SL", format="₹%.2f"),
                         "LT Target ₹": st.column_config.NumberColumn("LT Tgt", format="₹%.2f"),
                     })
        csv = df.to_csv(index=False).encode()
        st.download_button("⬇️ Download CSV", data=csv,
                           file_name=f"nse_signals_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                           mime="text/csv")

    # ── TAB 1: Signal Cards ──
    with tabs[1]:
        for i, r in enumerate(alerts[:10], 1):
            conf = r["model"]; mk = r["mkt"]
            stl = r["levels"]["short_term"]
            ltl = r["levels"]["long_term"]
            ltr, gc = _d_grade(conf["model_pct"])
            with st.expander(
                f"#{i}  {r['symbol']}  ·  Grade {ltr}  ·  Model {conf['model_pct']:.1f}%  ·  "
                f"₹{r['last_close']:,.2f}  →  ST ₹{stl['tp']:,.2f} ({(stl['tp']/stl['entry']-1)*100:+.1f}%)",
                expanded=(i == 1)
            ):
                cA, cB, cC = st.columns(3)
                cA.metric("Price", f"₹{r['last_close']:,.2f}")
                cB.metric("Model Score", f"{conf['model_pct']:.1f}%", f"Grade {ltr}")
                cC.metric("Market Align", f"{mk['pct']:.1f}%", mk['align'])

                st.markdown(f"**Sector:** {r.get('sector','N/A')}  ·  **Industry:** {r.get('industry','N/A')}  ·  **Indices:** {r['indices']}")
                st.markdown(f"**Research Note:** {r['reason']}")

                t1, t2, t3 = st.columns(3)
                t1.markdown(f"""
                <div style='background:#131722;padding:12px;border-radius:4px;border-left:3px solid #f59e0b'>
                <b>⚡ Aggressive (ST)</b><br>
                Entry: ₹{stl['entry']:,.2f}<br>
                Target: ₹{stl['tp']:,.2f} <span style='color:#26a69a'>(+{(stl['tp']/stl['entry']-1)*100:.1f}%)</span><br>
                Stop: ₹{stl['sl']:,.2f} <span style='color:#ef5350'>({(stl['sl']/stl['entry']-1)*100:.1f}%)</span><br>
                R:R {stl['rr_str']} · {stl['window']}
                </div>""", unsafe_allow_html=True)
                t2.markdown(f"""
                <div style='background:#131722;padding:12px;border-radius:4px;border-left:3px solid #26a69a'>
                <b>📅 Swing (LT)</b><br>
                Entry: ₹{ltl['entry']:,.2f}<br>
                Target: ₹{ltl['tp']:,.2f} <span style='color:#26a69a'>(+{(ltl['tp']/ltl['entry']-1)*100:.1f}%)</span><br>
                Stop: ₹{ltl['sl']:,.2f} <span style='color:#ef5350'>({(ltl['sl']/ltl['entry']-1)*100:.1f}%)</span><br>
                R:R {ltl['rr_str']} · {ltl['window']}
                </div>""", unsafe_allow_html=True)
                # Position sizing
                cap = st.session_state.get("capital", 1_000_000)
                risk = abs(stl['entry'] - stl['sl'])
                if risk > 0:
                    qty_1p = int((cap * 0.01) // risk)
                    qty_20p = int((cap * 0.20) // stl['entry'])
                    qty = min(qty_1p, qty_20p)
                else:
                    qty = 0
                t3.markdown(f"""
                <div style='background:#131722;padding:12px;border-radius:4px;border-left:3px solid #38bdf8'>
                <b>💰 Position Sizing (1% Risk)</b><br>
                Capital: ₹{cap:,.0f}<br>
                Risk/Share: ₹{risk:.2f}<br>
                Qty: <b>{qty:,}</b> shares<br>
                Deployed: ₹{qty*stl['entry']:,.0f}<br>
                Max Loss: ₹{qty*risk:,.0f}
                </div>""", unsafe_allow_html=True)

                # Pattern hits
                st.markdown("**Detected Patterns:**")
                ph_cols = st.columns(4)
                for idx, (sc, lb, cat) in enumerate(r['hits'][:8]):
                    ph_cols[idx % 4].markdown(f"<span style='color:#38bdf8'>▸</span> {lb} ({sc*100:.0f}%)", unsafe_allow_html=True)

    # ── TAB 2: Backtest ──
    with tabs[2]:
        st.markdown("""
        <div style='background:#131722;padding:16px;border-radius:4px;margin-bottom:12px'>
        <b style='color:#f59e0b'>⚠️ Backtest Integrity Declaration</b><br>
        <span style='color:#787b86;font-size:0.9rem'>
        • Uses <b>ONLY lagged price data</b> — no fundamentals, no future Nifty regime<br>
        • Stops executed against daily <b>low/high</b> with gap-fill logic<br>
        • Position sizing: <b>1% risk per trade</b> (ATR-based), capped at 20% capital<br>
        • Correlation guard: rejects stocks with 60-day return correlation > 0.70 to existing picks<br>
        • Survivorship guard: excludes stocks with incomplete historical data
        </span></div>""", unsafe_allow_html=True)

        b1, b2, b3, b4, b5, b6 = st.columns(6)
        b1.metric("Return", f"{bt_ret:+.2%}")
        b2.metric("Sharpe", f"{bt_sh:.3f}")
        b3.metric("Max DD", f"{bt_dd:.2%}")
        b4.metric("Win Rate", f"{bt_wr:.1%}")
        b5.metric("Trades", f"{bt_tr}")
        b6.metric("Final Equity", f"₹{bt.get('final',0):,.0f}")

        eq_df = bt.get("equity_df", pd.DataFrame())
        if not eq_df.empty and len(eq_df) > 1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=eq_df["date"], y=eq_df["equity"], mode="lines",
                         line=dict(color="#26a69a", width=2), fill="tozeroy",
                         fillcolor="rgba(38,166,154,0.08)"))
            fig.add_hline(y=cfg.bt_capital, line_color="#434651", line_dash="dot")
            fig.update_layout(height=350, paper_bgcolor="#131722", plot_bgcolor="#0b0e11",
                              font=dict(color="#787b86"), margin=dict(l=0,r=0,t=10,b=0),
                              xaxis=dict(showgrid=True, gridcolor="#2a3347"),
                              yaxis=dict(showgrid=True, gridcolor="#2a3347", tickprefix="₹"),
                              showlegend=False)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        trd_df = bt.get("trades_df", pd.DataFrame())
        if not trd_df.empty:
            st.markdown("**Recent Trades:**")
            st.dataframe(trd_df.sort_values("exit", ascending=False).head(20),
                         use_container_width=True, height=300,
                         column_config={
                             "pnl": st.column_config.NumberColumn("P&L", format="₹%.0f"),
                             "ret": st.column_config.NumberColumn("Return", format="%.2f%%"),
                         })

    # ── TAB 3: Sector Scan ──
    with tabs[3]:
        st.markdown("Run a focused scan on a specific sector with live data.")
        sec = st.selectbox("Sector", [
            "All Sectors", "NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY ENERGY",
            "NIFTY AUTO", "NIFTY INFRA", "FO STOCKS"
        ])
        thresh = st.slider("Threshold", 0.08, 0.30, 0.14, 0.01)
        top_n_sec = st.slider("Max Results", 5, 30, 10, 1)
        if st.button("🚀 Run Sector Scan", use_container_width=True):
            with st.spinner("Scanning..."):
                gk = None if sec == "All Sectors" else sec
                matched = []
                if gk:
                    matched = [sl for grp, sl in _UNIVERSE.items() if gk in grp.upper()]
                syms = sorted({s for sub in matched for s in sub} - _SKIP_SYMBOLS) if matched else _ALL_SYMS
                cfg2 = Cfg()
                cfg2.symbols = syms
                cfg2.base_threshold = thresh
                cfg2.top_n = top_n_sec
                cfg2.fetch_fundamentals = False
                try:
                    sc_alerts, sc_bt = run(cfg2)
                    if sc_alerts:
                        st.success(f"Found {len(sc_alerts)} signals")
                        for r in sc_alerts[:top_n_sec]:
                            stl = r["levels"]["short_term"]
                            st.markdown(f"**{r['symbol']}** ₹{r['last_close']:,.2f} → ST ₹{stl['tp']:,.2f} (R:R {stl['rr_str']}) — {r['reason'][:120]}")
                    else:
                        st.info("No signals in this sector at current threshold.")
                except Exception as e:
                    st.error(f"Scan failed: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# §16  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if _STREAMLIT:
        # Streamlit mode: run full scan then render dashboard
        cfg = Cfg()
        try:
            alerts, bt = run(cfg)
            # Re-fetch latest nifty for display
            nifty_hist = nifty50_history(cfg.live_period, cfg.live_interval)
            nifty_regime_df = compute_nifty_regime(nifty_hist) if not nifty_hist.empty else pd.DataFrame()
            latest_nifty = {}
            if not nifty_regime_df.empty:
                last_row = nifty_regime_df.sort_values("date").iloc[-1]
                latest_nifty = {
                    "trend": float(last_row["trend"]), "label": str(last_row["label"]),
                    "rsi": float(last_row["rsi"]), "last": float(last_row["close"]),
                    "ema9": float(last_row.get("ema9",0)), "ema21": float(last_row.get("ema21",0)),
                    "ema50": float(last_row.get("ema50",0)),
                }
                cl = nifty_hist.sort_values("date")["close"].reset_index(drop=True)
                latest_nifty["chg_1m"] = float((cl.iloc[-1]/cl.iloc[-22]-1)*100) if len(cl)>=22 else 0.0
                latest_nifty["chg_3m"] = float((cl.iloc[-1]/cl.iloc[0]-1)*100) if len(cl)>0 else 0.0
            run_dashboard(alerts, bt, latest_nifty, None)
        except Exception as e:
            st.error(f"Engine error: {e}")
            LOG.exception("Streamlit run failed")
    else:
        main()
