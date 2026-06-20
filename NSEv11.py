#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════════════╗
║  NSE SWING TRADER  v13.0  ·  THREE-HORIZON INTELLIGENCE ENGINE                    ║
║  Short (2–7D) · Mid (1–3M) · Long (6–12M+)                                       ║
║  Verdict: BUY / AVOID / WATCH / WAIT  ·  Strategy Attribution Analytics            ║
║  Production: No lookahead, realistic fills, vol targeting, correlation guard       ║
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
from typing import Optional, Dict, List, Tuple, Any, Set

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

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
    st.set_page_config(page_title="NSE Three-Horizon Trader v13", page_icon="📈",
                       layout="wide", initial_sidebar_state="expanded")

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
        from rich.console import Console
        from rich import box as rbox
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
    import streamlit.components.v1 as components

LOG = logging.getLogger("NSEv13")
for _nm in ("yfinance","urllib3","requests","charset_normalizer"):
    logging.getLogger(_nm).setLevel(logging.CRITICAL)

# ══════════════════════════════════════════════════════════════════════════════
# §1  UNIVERSE
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
# §2  CONFIG  (Three Horizon Configs)
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class HorizonCfg:
    name: str = "swing"
    label: str = "Swing (2–7 Days)"
    ema_fast: int = 9
    ema_slow: int = 21
    ema_trend: int = 50
    atr_sl_mult: float = 0.8
    atr_tp_mult: float = 1.5
    max_hold: int = 7
    min_hold: int = 2
    threshold: float = 0.20
    weights: dict = field(default_factory=lambda: {
        "momentum":0.30,"volume":0.25,"breakout":0.20,"pattern":0.15,"trend":0.10
    })
    min_rr: float = 1.0
    description: str = "Fast momentum, volume surge, tight stops"

@dataclass
class Cfg:
    live_period: str = "8mo"
    live_interval: str = "1d"
    output_dir: Path = Path("nse_v13_output")
    fetch_fundamentals: bool = True
    symbols: List[str] = field(default_factory=list)
    min_avg_vol: int = 500_000
    min_price: float = 30.0
    min_traded_val_cr: float = 2.0
    top_n: int = 12
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
    # Backtest
    bt_capital: float = 1_000_000.0
    bt_max_pos: int = 5
    bt_pos_pct: float = 0.20
    bt_risk_per_trade: float = 0.01
    bt_max_correlation: float = 0.70
    bt_slip_bps: float = 5.0
    bt_cost_bps: float = 12.0
    bt_max_hold: int = 12
    bt_min_hold: int = 2
    # Display
    capital: float = 1_000_000.0
    # Three horizons
    short_cfg: HorizonCfg = field(default_factory=lambda: HorizonCfg(
        name="short", label="Short Term (2–7 Days)",
        ema_fast=9, ema_slow=21, ema_trend=50,
        atr_sl_mult=0.8, atr_tp_mult=1.5, max_hold=7, min_hold=2,
        threshold=0.22,
        weights={"momentum":0.30,"volume":0.25,"breakout":0.20,"pattern":0.15,"trend":0.10},
        min_rr=1.0,
        description="Fast momentum plays. Tight 0.8× ATR stops. 2–7 day holds."
    ))
    mid_cfg: HorizonCfg = field(default_factory=lambda: HorizonCfg(
        name="mid", label="Mid Term (1–3 Months)",
        ema_fast=21, ema_slow=50, ema_trend=200,
        atr_sl_mult=1.5, atr_tp_mult=2.5, max_hold=45, min_hold=10,
        threshold=0.18,
        weights={"trend":0.30,"breakout":0.25,"pullback":0.20,"volume":0.15,"momentum":0.10},
        min_rr=1.5,
        description="Trend continuation & breakouts. 1.5× ATR stops. 1–3 month holds."
    ))
    long_cfg: HorizonCfg = field(default_factory=lambda: HorizonCfg(
        name="long", label="Long Term (6–12+ Months)",
        ema_fast=50, ema_slow=200, ema_trend=200,
        atr_sl_mult=2.5, atr_tp_mult=5.0, max_hold=252, min_hold=60,
        threshold=0.14,
        weights={"trend":0.35,"fundamental":0.25,"volume":0.15,"breakout":0.15,"momentum":0.10},
        min_rr=2.0,
        description="Major trend & fundamental plays. Wide 2.5× ATR stops. 6–12 month holds."
    ))

# ══════════════════════════════════════════════════════════════════════════════
# §3  DATA LAYER
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
        for c in ["open","high","low","close","volume"]:
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
            "pe": info.get("trailingPE"), "forward_pe": info.get("forwardPE"),
            "pb": info.get("priceToBook"), "roe": info.get("returnOnEquity"),
            "eps_g": info.get("earningsGrowth"), "rev_g": info.get("revenueGrowth"),
            "de": info.get("debtToEquity"), "sector": info.get("sector","N/A"),
            "industry": info.get("industry","N/A"),
            "mcap": round(mc/1e7,1) if mc else None,
            "mcap_raw": mc,
            "w52h": info.get("fiftyTwoWeekHigh"), "w52l": info.get("fiftyTwoWeekLow"),
            "beta": info.get("beta"), "peg": info.get("pegRatio"),
            "div_y": info.get("dividendYield"),
            "profit_m": info.get("profitMargins"),
            "oper_m": info.get("operatingMargins"),
            "curr_r": info.get("currentRatio"),
            "target_p": info.get("targetMeanPrice"),
            "recommendation": str(info.get("recommendationKey") or "").lower(),
            "num_analysts": info.get("numberOfAnalystOpinions",0),
            "short_ratio": info.get("shortRatio"),
            "float_shares": info.get("floatShares"),
            "shares_outstanding": info.get("sharesOutstanding"),
        }
    except Exception as e:
        LOG.debug("Fundamentals %s: %s", sym, e)
        return {}

def nifty50_history(period: str = "8mo", interval: str = "1d") -> pd.DataFrame:
    df = _safe_dl("^NSEI", period, interval)
    if df.empty:
        return pd.DataFrame()
    df.columns = [str(c).lower().strip() for c in df.columns]
    dc = next((c for c in df.columns if c.lower() in {"date","datetime"}), df.columns[0])
    df = df.rename(columns={dc: "date"})
    df["date"] = _norm_dates(df["date"]).dt.normalize()
    return df[["date","open","high","low","close","volume"]].dropna()

def compute_nifty_regime(nifty_df: pd.DataFrame) -> pd.DataFrame:
    df = nifty_df.copy().sort_values("date").reset_index(drop=True)
    if len(df) < 50:
        df["trend"] = 0.0; df["label"] = "N/A"; df["rsi"] = 50.0
        return df
    c = df["close"]
    df["ema9"] = c.ewm(span=9, adjust=False).mean()
    df["ema21"] = c.ewm(span=21, adjust=False).mean()
    df["ema50"] = c.ewm(span=50, adjust=False).mean()
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
    labels = {1.0:"Strong Bull",0.7:"Mild Bull",-1.0:"Strong Bear",-0.7:"Mild Bear",0.0:"Sideways"}
    df["label"] = df["trend"].map(labels)
    d = c.diff()
    g = d.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rs = g / l.replace(0, np.nan)
    df["rsi"] = (100 - 100/(1+rs)).fillna(50)
    return df[["date","trend","label","rsi","close","ema9","ema21","ema50"]]

# ══════════════════════════════════════════════════════════════════════════════
# §4  INDICATORS  (Modular pure functions)
# ══════════════════════════════════════════════════════════════════════════════
def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def _rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    g = d.clip(lower=0).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    return (100 - 100/(1+g/l.replace(0,np.nan))).fillna(50)

def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"]-df["low"], (df["high"]-pc).abs(), (df["low"]-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean()

def _adx(df: pd.DataFrame, n: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    hd = df["high"].diff(); ld = -df["low"].diff()
    pdm = pd.Series(np.where((hd>ld)&(hd>0), hd, 0.0), index=df.index)
    mdm = pd.Series(np.where((ld>hd)&(ld>0), ld, 0.0), index=df.index)
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"]-df["low"], (df["high"]-pc).abs(), (df["low"]-pc).abs()], axis=1).max(axis=1)
    atr_s = tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean().replace(0, np.nan)
    pdi = pdm.ewm(alpha=1/n, adjust=False, min_periods=n).mean()/atr_s*100
    mdi = mdm.ewm(alpha=1/n, adjust=False, min_periods=n).mean()/atr_s*100
    dx = ((pdi-mdi).abs()/(pdi+mdi).replace(0,np.nan)*100)
    adx = dx.ewm(alpha=1/n, adjust=False, min_periods=n).mean().fillna(20)
    return adx, pdi.fillna(0), mdi.fillna(0)

def _supertrend(df: pd.DataFrame, mult: float = 3.0, n: int = 10) -> Tuple[pd.Series, pd.Series]:
    atr_s = _atr(df, n); hl2 = (df["high"]+df["low"])/2
    up = hl2 + mult*atr_s; dn = hl2 - mult*atr_s
    fi_up = up.copy(); fi_dn = dn.copy()
    for i in range(1, len(df)):
        pc = df["close"].iat[i-1]
        fi_up.iat[i] = min(up.iat[i], fi_up.iat[i-1]) if pc <= fi_up.iat[i-1] else up.iat[i]
        fi_dn.iat[i] = max(dn.iat[i], fi_dn.iat[i-1]) if pc >= fi_dn.iat[i-1] else dn.iat[i]
    direction = pd.Series(1.0, index=df.index)
    for i in range(1, len(df)):
        pd_ = direction.iat[i-1]
        if pd_ == -1 and df["close"].iat[i] > fi_up.iat[i]: direction.iat[i] = 1
        elif pd_ == 1 and df["close"].iat[i] < fi_dn.iat[i]: direction.iat[i] = -1
        else: direction.iat[i] = pd_
    flip = ((direction==1)&(direction.shift(1).fillna(-1)==-1)).astype(int)
    return direction, flip

def compute_indicators(raw: pd.DataFrame, cfg: Cfg) -> pd.DataFrame:
    df = raw.copy().sort_values("date").reset_index(drop=True)
    if len(df) < cfg.min_bars: return pd.DataFrame()
    c, h, l, o, v = df["close"], df["high"], df["low"], df["open"], df["volume"]
    for sp in cfg.ema_spans: df[f"ema{sp}"] = _ema(c, sp)
    df["ema_gap"] = (df["ema9"]/df["ema21"].replace(0,np.nan)-1)*100
    df["macd"] = _ema(c,12) - _ema(c,26)
    df["macd_sig"] = _ema(df["macd"],9)
    df["macd_h"] = df["macd"] - df["macd_sig"]
    df["macd_h_p"] = df["macd_h"].shift(1)
    df["rsi14"] = _rsi(c,14); df["rsi9"] = _rsi(c,9)
    df["atr14"] = _atr(df,14)
    df["atr_pct"] = df["atr14"]/c.replace(0,np.nan)*100
    df["adx"], df["plus_di"], df["minus_di"] = _adx(df,14)
    df["st_dir"], df["st_flip"] = _supertrend(df, mult=3.0, n=10)
    bb_mid = c.rolling(cfg.bb_period, min_periods=10).mean()
    bb_std = c.rolling(cfg.bb_period, min_periods=10).std()
    df["bb_up"] = bb_mid + 2*bb_std; df["bb_dn"] = bb_mid - 2*bb_std
    bb_rng = (df["bb_up"]-df["bb_dn"]).replace(0,np.nan)
    df["bb_pct"] = (c-df["bb_dn"])/bb_rng; df["bb_bw"] = bb_rng/bb_mid.replace(0,np.nan)
    lo14 = l.rolling(14, min_periods=7).min(); hi14 = h.rolling(14, min_periods=7).max()
    df["stoch_k"] = ((c-lo14)/(hi14-lo14).replace(0,np.nan)*100).fillna(50)
    df["stoch_d"] = df["stoch_k"].rolling(3, min_periods=1).mean()
    tp = (h+l+c)/3; tp_ma = tp.rolling(20, min_periods=10).mean()
    tp_md = tp.rolling(20, min_periods=10).apply(lambda x: np.mean(np.abs(x-x.mean())), raw=True)
    df["cci"] = ((tp-tp_ma)/(0.015*tp_md.replace(0,np.nan))).fillna(0)
    hi14r = h.rolling(14, min_periods=7).max(); lo14r = l.rolling(14, min_periods=7).min()
    df["willr"] = ((hi14r-c)/(hi14r-lo14r).replace(0,np.nan)*-100).fillna(-50)
    tp2 = (h+l+c)/3; rmf = tp2*v
    pos_mf = rmf.where(tp2>tp2.shift(1),0.0); neg_mf = rmf.where(tp2<tp2.shift(1),0.0)
    mfr = pos_mf.rolling(14, min_periods=7).sum()/neg_mf.rolling(14, min_periods=7).sum().replace(0,np.nan)
    df["mfi"] = (100-100/(1+mfr)).fillna(50)
    df["obv"] = (np.sign(c.diff())*v).cumsum(); df["obv_ema"] = _ema(df["obv"],20)
    df["avg_vol20"] = v.rolling(20, min_periods=10).mean()
    df["vol_ratio"] = v/df["avg_vol20"].replace(0,np.nan)
    df["vol_z"] = ((v-df["avg_vol20"])/v.rolling(20, min_periods=10).std().replace(0,np.nan)).fillna(0)
    df["med_tv20"] = (c*v).rolling(20, min_periods=10).median()
    df["ret1"] = c.pct_change(); df["ret5"] = c.pct_change(5); df["ret20"] = c.pct_change(20)
    df["ret60"] = c.pct_change(60)
    df["hi20"] = h.shift(1).rolling(cfg.breakout_window, min_periods=8).max()
    df["lo20"] = l.shift(1).rolling(cfg.breakout_window, min_periods=8).min()
    df["hi50"] = h.shift(1).rolling(50, min_periods=15).max()
    df["hi52"] = h.rolling(252, min_periods=50).max(); df["lo52"] = l.rolling(252, min_periods=50).min()
    df["bo20"] = (c>df["hi20"]).astype(int); df["bo50"] = (c>df["hi50"]).astype(int)
    df["n52h"] = (c>=df["hi52"]*0.97).astype(int); df["n52l"] = (c<=df["lo52"]*1.03).astype(int)
    df["bo_d"] = (c/df["hi20"].replace(0,np.nan)-1)*100; df["bd_d"] = (c/df["lo20"].replace(0,np.nan)-1)*100
    df["pull_slow"] = (c/df["ema21"].replace(0,np.nan)-1)*100
    df["pull_mid"] = (c/df["ema50"].replace(0,np.nan)-1)*100
    df["pull_long"] = (c/df["ema200"].replace(0,np.nan)-1)*100
    # Strict patterns
    po=o.shift(1); pc_=c.shift(1); ph=h.shift(1); pl=l.shift(1)
    body=(c-o).abs(); rng_=(h-l).replace(0,np.nan)
    ls=df[["open","close"]].min(axis=1)-l; us=h-df[["open","close"]].max(axis=1)
    df["cdl_bull_eng"] = ((c>o)&(pc_<po)&(o<=pc_)&(c>=po)).astype(int)
    df["cdl_hammer"] = ((ls>=2.0*body)&(us<=0.3*body)&(c>o)&(body/rng_>0.05)).astype(int)
    df["cdl_morn_star"] = ((pc_.shift(1)<po.shift(1))&
                           ((c.shift(1)-o.shift(1)).abs()<(rng_.shift(2).fillna(1)*0.35))&
                           (c>(po.shift(1)+pc_.shift(1))/2)&(c>o)).astype(int)
    df["cdl_inside"] = ((h<ph)&(l>pl)&(c>pc_)&(c>o)).astype(int)
    df["cdl_sup_bounce"] = ((df["ret1"].fillna(0)>0.005)&(c>c.shift(1))&(df["bd_d"].fillna(100)<3.0)).astype(int)
    df["cdl_bo_candle"] = ((c>df["hi20"])&(df["vol_ratio"].fillna(0)>1.3)).astype(int)
    return df.replace([np.inf,-np.inf],np.nan)

def engineer_all(prices: pd.DataFrame, cfg: Cfg) -> pd.DataFrame:
    parts=[]
    for sym,grp in prices.groupby("symbol",sort=False):
        r=compute_indicators(grp,cfg)
        if not r.empty: parts.append(r)
    return pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()

# ══════════════════════════════════════════════════════════════════════════════
# §5  THREE-HORIZON SCORING & VERDICT ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def _g(row, k: str, d: float = 0.0) -> float:
    try:
        v = row[k] if isinstance(row, dict) else getattr(row, k, d)
    except Exception:
        return d
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return d
    return float(v)

def score_horizon(row, hcfg: HorizonCfg, fund: dict = None) -> Tuple[float, List[Tuple[float,str,str]], dict]:
    """Score a stock for a specific horizon. Returns (score, hits, factor_scores)."""
    c = _g(row, "close")
    e_fast = _g(row, f"ema{hcfg.ema_fast}")
    e_slow = _g(row, f"ema{hcfg.ema_slow}")
    e_trend = _g(row, f"ema{hcfg.ema_trend}", e_slow)
    rsi = _g(row, "rsi14", 50)
    mh = _g(row, "macd_h")
    atr = _g(row, "atr14", c*0.02) or c*0.02
    vol = _g(row, "vol_ratio", 1.0)
    adx = _g(row, "adx", 20)
    st = _g(row, "st_dir", 0)
    stf = _g(row, "st_flip", 0)
    bbp = _g(row, "bb_pct", 0.5)
    bo20 = _g(row, "bo20", 0)
    bo50 = _g(row, "bo50", 0)
    ret5 = _g(row, "ret5", 0)
    ret20 = _g(row, "ret20", 0)
    ret60 = _g(row, "ret60", 0)
    pull = _g(row, "pull_slow", 0)
    pull_mid = _g(row, "pull_mid", 0)

    hits = []
    factors = {"trend":0.0, "momentum":0.0, "breakout":0.0, "pullback":0.0, 
               "volume":0.0, "pattern":0.0, "fundamental":0.0, "sentiment":0.0}

    # TREND
    if c > e_fast > e_slow > e_trend:
        factors["trend"] = 1.0
        hits.append((0.95, f"Full EMA Stack ({hcfg.ema_fast}>{hcfg.ema_slow}>{hcfg.ema_trend})", "Trend"))
    elif c > e_fast > e_slow:
        factors["trend"] = 0.7
        hits.append((0.80, f"EMA Bullish ({hcfg.ema_fast}>{hcfg.ema_slow})", "Trend"))
    elif c > e_slow:
        factors["trend"] = 0.3
        hits.append((0.50, f"Price above EMA{hcfg.ema_slow}", "Trend"))
    elif c < e_fast < e_slow < e_trend:
        factors["trend"] = -1.0

    if adx > 30 and c > e_fast:
        factors["trend"] = min(1.0, factors["trend"] + 0.2)
        hits.append((0.75, f"ADX {adx:.0f} — Strong Trend", "Trend"))

    if stf == 1:
        factors["trend"] = 1.0
        hits.append((0.98, "SuperTrend BUY Flip", "Trend"))
    elif st == 1:
        factors["trend"] = max(factors["trend"], 0.6)
        hits.append((0.65, "SuperTrend Bullish", "Trend"))

    # MOMENTUM
    if rsi < 30:
        factors["momentum"] = 0.9
        hits.append((0.90, f"RSI {rsi:.1f} — Oversold Bounce", "Momentum"))
    elif rsi < 40:
        factors["momentum"] = 0.6
        hits.append((0.70, f"RSI {rsi:.1f} — Near Oversold", "Momentum"))
    elif 45 < rsi < 65:
        factors["momentum"] = 0.4
        hits.append((0.50, f"RSI {rsi:.1f} — Healthy Momentum", "Momentum"))
    elif rsi > 75:
        factors["momentum"] = -0.5
        hits.append((0.30, f"RSI {rsi:.1f} — Overbought Caution", "Momentum"))

    if mh > 0 and _g(row, "macd_h_p", 0) <= 0:
        factors["momentum"] = max(factors["momentum"], 0.8)
        hits.append((0.85, "MACD Histogram Bull Cross", "Momentum"))
    elif mh > 0:
        factors["momentum"] = max(factors["momentum"], 0.4)
        hits.append((0.55, "MACD Positive", "Momentum"))

    # BREAKOUT
    if bo50 == 1 and vol > 1.5:
        factors["breakout"] = 0.9
        hits.append((0.90, "50-Day Breakout + Volume", "Breakout"))
    elif bo20 == 1 and vol > 1.3:
        factors["breakout"] = 0.8
        hits.append((0.80, "20-Day Breakout + Volume", "Breakout"))
    elif bo20 == 1:
        factors["breakout"] = 0.5
        hits.append((0.60, "20-Day Breakout", "Breakout"))

    if _g(row, "n52h", 0) == 1 and vol > 1.2:
        factors["breakout"] = max(factors["breakout"], 0.85)
        hits.append((0.85, "Near 52-Week High + Volume", "Breakout"))

    # PULLBACK
    if abs(pull) < 2.5 and c > e_slow and 40 < rsi < 62:
        factors["pullback"] = 0.75
        hits.append((0.75, "Pullback to EMA — Clean Retest", "Pullback"))
    elif abs(pull_mid) < 3.0 and c > e_trend and 40 < rsi < 65:
        factors["pullback"] = 0.55
        hits.append((0.60, "Pullback to Slow EMA", "Pullback"))

    # VOLUME
    if vol >= 2.5 and ret5 > 0:
        factors["volume"] = 0.95
        hits.append((0.95, f"Volume Surge {vol:.1f}x + Up Day", "Volume"))
    elif vol >= 1.5 and ret5 > 0:
        factors["volume"] = 0.7
        hits.append((0.75, f"Volume {vol:.1f}x — Institutional", "Volume"))
    elif vol >= 1.2 and ret5 > 0:
        factors["volume"] = 0.4
        hits.append((0.55, f"Volume {vol:.1f}x — Above Average", "Volume"))

    # PATTERN
    eng = _g(row, "cdl_bull_eng", 0)
    ham = _g(row, "cdl_hammer", 0)
    morn = _g(row, "cdl_morn_star", 0)
    inside = _g(row, "cdl_inside", 0)
    sup_bounce = _g(row, "cdl_sup_bounce", 0)
    bo_candle = _g(row, "cdl_bo_candle", 0)

    if morn == 1:
        factors["pattern"] = 1.0
        hits.append((0.95, "Morning Star (3-Bar Reversal)", "Pattern"))
    elif eng == 1 and vol > 1.2:
        factors["pattern"] = 0.9
        hits.append((0.90, "Bullish Engulfing + Volume", "Pattern"))
    elif eng == 1:
        factors["pattern"] = 0.7
        hits.append((0.80, "Bullish Engulfing", "Pattern"))
    elif ham == 1:
        factors["pattern"] = 0.75
        hits.append((0.75, "Hammer Candle", "Pattern"))
    elif inside == 1 and c > _g(row, "close", c):
        factors["pattern"] = 0.6
        hits.append((0.70, "Inside Bar Breakout", "Pattern"))
    elif sup_bounce == 1:
        factors["pattern"] = 0.65
        hits.append((0.65, "Support Bounce (20D Low)", "Pattern"))
    elif bo_candle == 1:
        factors["pattern"] = 0.7
        hits.append((0.70, "Breakout Candle (Vol-Confirmed)", "Pattern"))

    # FUNDAMENTAL (for long term only)
    if fund and hcfg.name == "long":
        pe = fund.get("pe")
        roe = fund.get("roe")
        eps_g = fund.get("eps_g")
        if pe and 0 < pe < 25:
            factors["fundamental"] = 0.5
            hits.append((0.60, f"P/E {pe:.1f} — Value + Growth", "Fundamental"))
        elif pe and 0 < pe < 35:
            factors["fundamental"] = 0.3
        if roe and roe > 0.20:
            factors["fundamental"] = max(factors["fundamental"], 0.6)
            hits.append((0.65, f"ROE {roe*100:.1f}% — Quality", "Fundamental"))
        elif roe and roe > 0.15:
            factors["fundamental"] = max(factors["fundamental"], 0.4)
        if eps_g and eps_g > 0.20:
            factors["fundamental"] = max(factors["fundamental"], 0.5)
            hits.append((0.55, f"EPS Growth {eps_g*100:.1f}%", "Fundamental"))

    # SENTIMENT
    if ret5 > 0.03 and ret20 > 0.05:
        factors["sentiment"] = 0.6
        hits.append((0.60, "Strong 5D + 20D Momentum", "Sentiment"))
    elif ret5 > 0.01 and ret20 > 0.03:
        factors["sentiment"] = 0.4
        hits.append((0.50, "Building Momentum", "Sentiment"))
    elif ret60 < -0.15:
        factors["sentiment"] = -0.3
        hits.append((0.30, "Weak 60D Trend — Caution", "Sentiment"))

    # Weighted score
    w = hcfg.weights
    total = sum(factors[k] * w.get(k, 0) for k in factors)
    weight_sum = sum(abs(w.get(k, 0)) for k in w)
    score = float(np.clip(total / weight_sum if weight_sum else 0, -1, 1))

    hits.sort(key=lambda x: -x[0])
    return score, hits, factors

def horizon_trade_levels(close: float, atr: float, hcfg: HorizonCfg) -> Optional[dict]:
    if atr <= 0 or close <= 0: return None
    def rr(sl, tp): return round(abs(tp-close) / abs(close-sl), 2) if abs(close-sl) > 0 else 0.0
    sl = round(close - hcfg.atr_sl_mult * atr, 2)
    tp = round(close + hcfg.atr_tp_mult * atr, 2)
    rr_val = rr(sl, tp)
    if rr_val < hcfg.min_rr: return None
    return dict(
        entry=round(close, 2), sl=sl, tp=tp,
        risk=round(abs(close-sl), 2), reward=round(abs(tp-close), 2),
        rr=rr_val, rr_str=f"1:{rr_val}",
        window=hcfg.label.split("(")[1].replace(")","") if "(" in hcfg.label else hcfg.label,
        atr_mult_sl=hcfg.atr_sl_mult, atr_mult_tp=hcfg.atr_tp_mult
    )

def generate_verdict(row, score: float, hits: List, factors: dict, hcfg: HorizonCfg, 
                     fund: dict = None, nifty_trend: float = 0) -> dict:
    """Generate BUY / AVOID / WATCH / WAIT verdict with detailed rationale."""
    c = _g(row, "close")
    rsi = _g(row, "rsi14", 50)
    adx = _g(row, "adx", 20)
    vol = _g(row, "vol_ratio", 1.0)
    atr_pct = _g(row, "atr_pct", 2.0)
    e9 = _g(row, "ema9"); e21 = _g(row, "ema21"); e50 = _g(row, "ema50")
    ret5 = _g(row, "ret5", 0); ret20 = _g(row, "ret20", 0)

    why_buy = []
    why_avoid = []
    why_wait = []

    # WHY BUY
    if score >= hcfg.threshold:
        why_buy.append(f"✅ Score {score:+.3f} exceeds threshold {hcfg.threshold}")
    if factors.get("trend", 0) > 0.5:
        why_buy.append("✅ Strong trend alignment — EMAs stacked bullishly")
    if factors.get("momentum", 0) > 0.5:
        why_buy.append("✅ Momentum building — RSI/MACD turning positive")
    if factors.get("breakout", 0) > 0.5:
        why_buy.append("✅ Breakout confirmed — price above key resistance with volume")
    if factors.get("volume", 0) > 0.5:
        why_buy.append(f"✅ Volume surge {vol:.1f}x — institutional participation")
    if factors.get("pattern", 0) > 0.5:
        why_buy.append("✅ Bullish candlestick pattern confirmed")
    if factors.get("fundamental", 0) > 0.3:
        why_buy.append("✅ Strong fundamentals — quality + growth at reasonable price")
    if nifty_trend > 0.3:
        why_buy.append("✅ Market tailwind — Nifty in bullish regime")

    # WHY AVOID
    if score < hcfg.threshold - 0.1:
        why_avoid.append(f"❌ Score {score:+.3f} too weak — below threshold {hcfg.threshold}")
    if rsi > 75:
        why_avoid.append(f"❌ RSI {rsi:.1f} overbought — high pullback risk")
    if adx < 15 and score < 0.1:
        why_avoid.append("❌ ADX < 15 — no trend, chop likely")
    if atr_pct > 6.0 and hcfg.name == "short":
        why_avoid.append(f"❌ ATR {atr_pct:.1f}% too volatile for short-term swing")
    if ret20 < -0.10 and hcfg.name in ("short", "mid"):
        why_avoid.append("❌ Down 10%+ in 20 days — counter-trend for short/mid term")
    if nifty_trend < -0.5:
        why_avoid.append("❌ Bear market — headwind for long positions")
    if vol < 0.8 and score > 0:
        why_avoid.append("❌ Volume below average — low conviction, liquidity risk")
    if fund and fund.get("de", 0) and fund["de"] > 3.0:
        why_avoid.append("❌ High debt/equity > 3.0 — balance sheet risk")

    # WHY WAIT
    if 0.05 < score < hcfg.threshold:
        why_wait.append(f"⏳ Score {score:+.3f} close to threshold — monitor for confirmation")
    if 35 < rsi < 45:
        why_wait.append(f"⏳ RSI {rsi:.1f} neutral — wait for momentum confirmation")
    if e9 > e21 and c < e9:
        why_wait.append("⏳ Price below fast EMA — wait for reclaim")
    if vol < 1.0 and factors.get("breakout", 0) > 0.3:
        why_wait.append("⏳ Breakout lacks volume confirmation — wait for volume spike")
    if ret5 > 0.05 and hcfg.name == "short":
        why_wait.append("⏳ Already up 5% in 5 days — wait for pullback entry")
    if hcfg.name == "long" and (not fund or not fund.get("pe")):
        why_wait.append("⏳ Fundamental data incomplete — verify before investing")
    if nifty_trend > -0.3 and nifty_trend < 0.2:
        why_wait.append("⏳ Market sideways — better entries may come")

    # Determine verdict
    if score >= hcfg.threshold and len(why_buy) >= 2 and len(why_avoid) < 2:
        verdict = "BUY"
        confidence = min(95, int(50 + score * 100 + len(why_buy) * 5))
    elif len(why_avoid) >= 3 or score < hcfg.threshold - 0.15:
        verdict = "AVOID"
        confidence = min(95, int(50 + (1 - abs(score)) * 50 + len(why_avoid) * 5))
    elif len(why_wait) >= 2 and score > 0:
        verdict = "WAIT"
        confidence = min(80, int(40 + score * 80))
    else:
        verdict = "WATCH"
        confidence = min(70, int(30 + abs(score) * 70))

    return {
        "verdict": verdict,
        "confidence": confidence,
        "score": round(score, 4),
        "threshold": hcfg.threshold,
        "why_buy": why_buy,
        "why_avoid": why_avoid,
        "why_wait": why_wait,
        "factors": {k: round(v, 3) for k, v in factors.items()},
        "primary_signals": [h[1] for h in hits[:3]],
        "all_hits": hits,
    }

# ══════════════════════════════════════════════════════════════════════════════
# §6  BACKTEST ENGINE  (With strategy attribution tracking)
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class _Pos:
    sym:str; qty:int; entry_date:pd.Timestamp; entry_p:float; stop:float; target:float
    fees_in:float; horizon:str; signals:List[str]; bars:int=0

def run_backtest(feat:pd.DataFrame, cfg:Cfg, nifty_by_date:Dict, horizon:str="mid")->dict:
    hcfg = getattr(cfg, f"{horizon}_cfg", cfg.mid_cfg)
    empty=dict(ret=0.0,sharpe=0.0,maxdd=0.0,winrate=0.0,trades=0,
               final=cfg.bt_capital,avg_ret=0.0,avg_bars=0.0,
               trades_df=pd.DataFrame(),equity_df=pd.DataFrame(),
               strategy_attribution=defaultdict(lambda: {"wins":0,"losses":0,"pnl":0.0}))
    need={"date","symbol","open","high","low","close","score","signal","atr14"}
    if not need.issubset(feat.columns):
        LOG.error("Backtest missing columns: %s", need-set(feat.columns))
        return empty
    data=feat.copy(); data["date"]=_norm_dates(data["date"])
    data=data.sort_values(["date","symbol"]).reset_index(drop=True)
    # Survivorship guard
    expected_bars=data["date"].nunique()
    sym_counts=data.groupby("symbol")["date"].nunique()
    valid_syms=set(sym_counts[sym_counts>=expected_bars*0.95].index)
    if len(valid_syms)<len(sym_counts):
        data=data[data["symbol"].isin(valid_syms)].copy()
    if data.empty: return empty
    by_d={d:g.set_index("symbol") for d,g in data.groupby("date")}
    dates=sorted(by_d.keys())
    if len(dates)<20: return empty
    pivot_close=data.pivot(index="date",columns="symbol",values="close").sort_index()
    returns_df=pivot_close.pct_change().fillna(0)
    cost=cfg.bt_cost_bps/10_000; slip=cfg.bt_slip_bps/10_000
    poss:Dict[str,_Pos]={}; trades=[]; eq_rows=[]; cash=cfg.bt_capital
    # Strategy attribution tracker
    strat_attr=defaultdict(lambda:{"wins":0,"losses":0,"pnl":0.0,"trades":0})

    for idx,date in enumerate(dates):
        day=by_d[date]; nd=dates[idx+1] if idx+1<len(dates) else None
        # Exits
        for sym in list(poss.keys()):
            p=poss[sym]
            if sym not in day.index: continue
            row=day.loc[sym]
            o=float(row["open"]); h=float(row["high"]); lo=float(row["low"]); c=float(row["close"])
            exit_price=None; reason=None
            if lo<=p.stop:
                exit_price=o if o<=p.stop else p.stop
                exit_price*=(1-slip); reason="stop_loss"
            elif h>=p.target:
                exit_price=o if o>=p.target else p.target
                exit_price*=(1+slip); reason="take_profit"
            elif p.bars>=hcfg.max_hold:
                exit_price=c*(1-slip); reason="max_hold"
            elif p.bars>=hcfg.min_hold and str(row.get("signal","NEUTRAL"))!="LONG":
                exit_price=o*(1-slip); reason="signal_exit"
            if exit_price is not None and nd is not None:
                tv=p.qty*exit_price; ef=abs(tv)*cost; cash+=tv-ef
                pnl=p.qty*(exit_price-p.entry_p)-p.fees_in-ef
                basis=p.qty*p.entry_p
                ret=pnl/basis if basis else 0
                trades.append(dict(sym=sym,entry=p.entry_date,exit=date,ep=round(p.entry_p,2),
                                   xp=round(exit_price,2),pnl=round(pnl,2),ret=round(ret,4),
                                   bars=p.bars,reason=reason,horizon=horizon,signals=p.signals))
                # Attribution
                for sig in p.signals:
                    strat_attr[sig]["trades"]+=1
                    strat_attr[sig]["pnl"]+=pnl
                    if pnl>0: strat_attr[sig]["wins"]+=1
                    else: strat_attr[sig]["losses"]+=1
                del poss[sym]
            elif p.bars>=hcfg.max_hold and nd is None:
                exit_price=c*(1-slip); tv=p.qty*exit_price; ef=abs(tv)*cost; cash+=tv-ef
                pnl=p.qty*(exit_price-p.entry_p)-p.fees_in-ef; basis=p.qty*p.entry_p
                ret=pnl/basis if basis else 0
                trades.append(dict(sym=sym,entry=p.entry_date,exit=date,ep=round(p.entry_p,2),
                                   xp=round(exit_price,2),pnl=round(pnl,2),ret=round(ret,4),
                                   bars=p.bars,reason="eop",horizon=horizon,signals=p.signals))
                for sig in p.signals:
                    strat_attr[sig]["trades"]+=1; strat_attr[sig]["pnl"]+=pnl
                    if pnl>0: strat_attr[sig]["wins"]+=1
                    else: strat_attr[sig]["losses"]+=1
                del poss[sym]
        # Equity
        equity=cash+sum(p.qty*float(day.loc[s,"close"]) for s,p in poss.items() if s in day.index)
        eq_rows.append(dict(date=date,equity=round(equity,2)))
        if not nd: continue
        # Entries
        blocked=set(poss.keys()); slots=cfg.bt_max_pos-len(poss)
        if slots<=0: continue
        cands=day.reset_index()
        cands=cands[(cands.get("signal","NEUTRAL")=="LONG")&
                    (cands.get("score",pd.Series(dtype=float)).fillna(0)>=cands.get("threshold",hcfg.threshold))&
                    (~cands["symbol"].isin(blocked))].sort_values("score",ascending=False)
        selected=[]
        for _,r in cands.iterrows():
            if len(selected)>=slots: break
            sym=r["symbol"]
            # Correlation guard
            if selected:
                window=returns_df.loc[:date].tail(60)
                if len(window)>=20:
                    sym_rets=window.get(sym,pd.Series(dtype=float)); ok=True
                    for s in selected:
                        s_rets=window.get(s,pd.Series(dtype=float))
                        common=pd.concat([sym_rets,s_rets],axis=1).dropna()
                        if len(common)>=20:
                            corr=np.corrcoef(common.iloc[:,0],common.iloc[:,1])[0,1]
                            if abs(corr)>cfg.bt_max_correlation: ok=False; break
                    if not ok: continue
            close=float(r["close"]); atr=float(r.get("atr14",close*0.02)) or close*0.02
            lvl=horizon_trade_levels(close,atr,hcfg)
            if lvl is None: continue
            stop_p=lvl["sl"]; risk_per_share=abs(close-stop_p)
            if risk_per_share<=0: continue
            risk_amt=equity*cfg.bt_risk_per_trade
            qty=int(risk_amt//risk_per_share)
            max_by_cap=int((equity*cfg.bt_pos_pct)//close)
            qty=min(qty,max_by_cap)
            if qty<=0: continue
            total_cost=qty*close
            if cash<total_cost*(1+cost*2): continue
            fees_in=total_cost*cost; cash-=total_cost+fees_in
            # Extract signals from row for attribution
            sigs=[]
            for col in ["cdl_bull_eng","cdl_hammer","cdl_morn_star","cdl_inside","cdl_sup_bounce","cdl_bo_candle"]:
                if r.get(col,0)==1: sigs.append(col)
            if r.get("st_flip",0)==1: sigs.append("supertrend_flip")
            if r.get("bo20",0)==1: sigs.append("breakout_20d")
            if r.get("bo50",0)==1: sigs.append("breakout_50d")
            poss[sym]=_Pos(sym,qty,date,close,stop_p,lvl["tp"],fees_in,horizon,sigs)
            selected.append(sym)
        for p in poss.values(): p.bars+=1
    # Final liquidation
    ld=by_d[dates[-1]]
    for sym,p in list(poss.items()):
        if sym not in ld.index: continue
        fp=float(ld.loc[sym,"close"])*(1-slip); tv=p.qty*fp; ef=abs(tv)*cost; cash+=tv-ef
        pnl=p.qty*(fp-p.entry_p)-p.fees_in-ef; basis=p.qty*p.entry_p
        ret=pnl/basis if basis else 0
        trades.append(dict(sym=sym,entry=p.entry_date,exit=dates[-1],ep=round(p.entry_p,2),
                           xp=round(fp,2),pnl=round(pnl,2),ret=round(ret,4),
                           bars=p.bars,reason="eop",horizon=horizon,signals=p.signals))
        for sig in p.signals:
            strat_attr[sig]["trades"]+=1; strat_attr[sig]["pnl"]+=pnl
            if pnl>0: strat_attr[sig]["wins"]+=1
            else: strat_attr[sig]["losses"]+=1
    eq=pd.DataFrame(eq_rows); trd=pd.DataFrame(trades)
    if eq.empty or len(eq)<2: return empty
    eq["dr"]=eq["equity"].pct_change().fillna(0); eq["dd"]=(eq["equity"]/eq["equity"].cummax())-1
    std=float(eq["dr"].std(ddof=0)) if len(eq)>1 else 0
    sharpe=float((eq["dr"].mean()/std)*sqrt(252)) if std else 0.0
    final=float(eq["equity"].iloc[-1])
    # Process attribution
    attr_summary={}
    for sig,vals in strat_attr.items():
        if vals["trades"]>0:
            attr_summary[sig]={
                "trades":vals["trades"],"wins":vals["wins"],"losses":vals["losses"],
                "winrate":round(vals["wins"]/vals["trades"],3),
                "total_pnl":round(vals["pnl"],2),
                "avg_pnl":round(vals["pnl"]/vals["trades"],2),
                "status":"HOT" if vals["wins"]>vals["losses"] and vals["pnl"]>0 else "COLD" if vals["losses"]>vals["wins"] else "NEUTRAL"
            }
    return dict(ret=round(final/cfg.bt_capital-1,4),sharpe=round(sharpe,3),
                maxdd=round(float(eq["dd"].min()),4),
                winrate=round(float((trd["pnl"]>0).mean()) if not trd.empty else 0,3),
                trades=len(trd),final=round(final,2),
                avg_ret=round(float(trd["ret"].mean()) if not trd.empty else 0,4),
                avg_bars=round(float(trd["bars"].mean()) if not trd.empty else 0,1),
                trades_df=trd,equity_df=eq,strategy_attribution=attr_summary)

# ══════════════════════════════════════════════════════════════════════════════
# §7  THREE-HORIZON ALERT BUILDER
# ══════════════════════════════════════════════════════════════════════════════
def build_three_horizon_alerts(feat:pd.DataFrame, nifty:dict, fund_cache:dict, cfg:Cfg)->Dict[str,List]:
    latest=(feat.sort_values("date").groupby("symbol",sort=False).tail(1).reset_index(drop=True))
    results={"short":[],"mid":[],"long":[]}
    rej=defaultdict(lambda:defaultdict(int))
    nifty_trend=nifty.get("trend",0.0)

    for _,row in latest.iterrows():
        sym=str(row["symbol"]); c=float(row["close"])
        atr=float(row.get("atr14",c*0.02)) or c*0.02; atr_p=atr/c*100 if c else 0
        avg_v=float(row.get("avg_vol20",0) or 0); tv=float(row.get("med_tv20",0) or 0)/1e7

        # Universal filters
        if c<cfg.min_price: continue
        if avg_v<cfg.min_avg_vol: continue
        if tv<cfg.min_traded_val_cr: continue

        fund=fund_cache.get(sym,{})

        for hname in ["short","mid","long"]:
            hcfg=getattr(cfg, f"{hname}_cfg")
            score,hits,factors=score_horizon(row,hcfg,fund)

            # ATR filter per horizon
            if hname=="short" and atr_p>5.0: rej[hname]["atr_high"]+=1; continue
            if hname=="mid" and atr_p>4.0: rej[hname]["atr_high"]+=1; continue
            if hname=="long" and atr_p<1.0: rej[hname]["atr_low"]+=1; continue

            if score<hcfg.threshold: rej[hname]["score"]+=1; continue

            lvl=horizon_trade_levels(c,atr,hcfg)
            if lvl is None: rej[hname]["rr"]+=1; continue

            verdict=generate_verdict(row,score,hits,factors,hcfg,fund,nifty_trend)
            if verdict["verdict"] in ("AVOID",): rej[hname]["verdict_avoid"]+=1; continue

            # Require at least 2 positive signals for BUY
            if verdict["verdict"]=="BUY" and len(verdict["why_buy"])<2:
                verdict["verdict"]="WATCH"
                verdict["why_wait"].append("⏳ Need 2+ confirmation signals for BUY")

            results[hname].append(dict(
                symbol=sym,last_close=round(c,2),score=round(score,4),
                atr=round(atr,2),atr_pct=round(atr_p,2),
                rsi=round(float(row.get("rsi14",50) or 50),1),
                adx=round(float(row.get("adx",0) or 0),1),
                vol_ratio=round(float(row.get("vol_ratio",1) or 1),2),
                avg_vol=int(avg_v),traded_val_cr=round(tv,2),
                ema9=round(float(row.get("ema9",0) or 0),2),
                ema21=round(float(row.get("ema21",0) or 0),2),
                ema50=round(float(row.get("ema50",0) or 0),2),
                ema200=round(float(row.get("ema200",0) or 0),2),
                st_flip=int(_g(row,"st_flip",0)),
                is_fo=sym in _FO_SET,indices=symbol_tags(sym),
                sector=fund.get("sector","N/A"),industry=fund.get("industry","N/A"),
                pe=fund.get("pe"),pb=fund.get("pb"),roe=fund.get("roe"),
                mcap=fund.get("mcap"),w52h=fund.get("w52h"),w52l=fund.get("w52l"),
                beta=fund.get("beta"),peg=fund.get("peg"),
                levels=lvl,verdict=verdict,horizon=hname,
                scan_ts=datetime.now().strftime("%Y-%m-%d %H:%M")))

    for hname in results:
        results[hname].sort(key=lambda r:(-r["verdict"]["confidence"] if r["verdict"]["verdict"]=="BUY" else 0,
                                          -r["score"]))
        # Put BUY first, then WATCH, then WAIT, then AVOID
        buy=[r for r in results[hname] if r["verdict"]["verdict"]=="BUY"]
        watch=[r for r in results[hname] if r["verdict"]["verdict"]=="WATCH"]
        wait=[r for r in results[hname] if r["verdict"]["verdict"]=="WAIT"]
        avoid=[r for r in results[hname] if r["verdict"]["verdict"]=="AVOID"]
        results[hname]=buy+watch+wait+avoid
        LOG.info("%s horizon: %d BUY, %d WATCH, %d WAIT, %d AVOID | rej: %s",
                 hname.upper(),len(buy),len(watch),len(wait),len(avoid),dict(rej[hname]))

    return results,dict(rej)

# ══════════════════════════════════════════════════════════════════════════════
# §8  SAVE OUTPUTS
# ══════════════════════════════════════════════════════════════════════════════
def save_all(results:dict, bt:dict, nifty:dict, cfg:Cfg)->dict:
    od=cfg.output_dir; od.mkdir(parents=True, exist_ok=True)
    ts=datetime.now().strftime("%Y%m%d_%H%M")

    for hname in ["short","mid","long"]:
        alerts=results.get(hname,[])
        if not alerts: continue
        rows=[]
        for r in alerts:
            v=r["verdict"]; l=r["levels"]
            rows.append({
                "scan_ts":r["scan_ts"],"symbol":r["symbol"],"horizon":hname,
                "verdict":v["verdict"],"confidence":v["confidence"],"score":r["score"],
                "price":r["last_close"],"rsi":r["rsi"],"adx":r["adx"],"atr_pct":r["atr_pct"],
                "vol_ratio":r["vol_ratio"],"entry":l["entry"],"target":l["tp"],"stop":l["sl"],
                "rr":l["rr_str"],"window":l["window"],
                "why_buy":" | ".join(v["why_buy"][:5]),
                "why_avoid":" | ".join(v["why_avoid"][:3]),
                "why_wait":" | ".join(v["why_wait"][:3]),
                "primary_signals":" | ".join(v["primary_signals"]),
                "sector":r["sector"],"indices":r["indices"],"is_fo":r["is_fo"],
            })
        pd.DataFrame(rows).to_csv(od/f"{hname}_alerts_{ts}.csv",index=False)

    bt.get("trades_df",pd.DataFrame()).to_csv(od/f"trades_{ts}.csv",index=False)
    bt.get("equity_df",pd.DataFrame()).to_csv(od/f"equity_{ts}.csv",index=False)

    with open(od/f"summary_{ts}.json","w") as f:
        json.dump({
            "run_ts":ts,"nifty":{k:v for k,v in nifty.items() if k!="ts"},
            "backtest":{k:v for k,v in bt.items() if k not in ("trades_df","equity_df","strategy_attribution")},
            "strategy_attribution":bt.get("strategy_attribution",{}),
            "top_signals":{h:[{"symbol":r["symbol"],"verdict":r["verdict"]["verdict"],
                              "confidence":r["verdict"]["confidence"],"score":r["score"],
                              "entry":r["levels"]["entry"],"target":r["levels"]["tp"],
                              "stop":r["levels"]["sl"],"rr":r["levels"]["rr_str"]}
                             for r in results.get(h,[])[:10]] for h in ["short","mid","long"]}
        },f,indent=2,default=str)
    return dict(output_dir=od)

# ══════════════════════════════════════════════════════════════════════════════
# §9  TERMINAL DISPLAY
# ══════════════════════════════════════════════════════════════════════════════
def plain_report(results:dict, nifty:dict, bt:dict, cfg:Cfg)->None:
    SEP="="*120
    print(f"\n{SEP}")
    print(f"NSE THREE-HORIZON TRADER v13.0 | {datetime.now().strftime('%d %b %Y %H:%M')}")
    print(f"Market: {nifty.get('label','N/A')} | Nifty ₹{nifty.get('last',0):,.2f}")
    print(f"Backtest — Return: {bt.get('ret',0):+.2%} | Sharpe: {bt.get('sharpe',0):.3f} | MaxDD: {bt.get('maxdd',0):.2%}")
    print(f"NOTE: Three separate engines. No lookahead. Realistic fills. 1% risk per trade.")
    print(SEP)

    for hname in ["short","mid","long"]:
        hcfg=getattr(cfg, f"{hname}_cfg")
        alerts=results.get(hname,[])
        print(f"\n{'═'*60}")
        print(f"  {hcfg.label.upper()}")
        print(f"  {hcfg.description}")
        print(f"{'═'*60}")

        for i,r in enumerate(alerts[:cfg.top_n],1):
            v=r["verdict"]; l=r["levels"]
            emoji={"BUY":"🟢","WATCH":"🟡","WAIT":"🟠","AVOID":"🔴"}.get(v["verdict"],"⚪")
            print(f"\n  {emoji} [{i:>2}] {r['symbol']} | {v['verdict']} (Confidence: {v['confidence']}%)")
            print(f"       Price: ₹{r['last_close']:,.2f} | Score: {r['score']:+.4f} | RSI: {r['rsi']:.1f} | ADX: {r['adx']:.1f} | Vol: {r['vol_ratio']:.2f}x")
            print(f"       Entry: ₹{l['entry']:,.2f} | Target: ₹{l['tp']:,.2f} | Stop: ₹{l['sl']:,.2f} | R:R {l['rr_str']} | {l['window']}")
            if v["why_buy"]:
                print(f"       ✅ BUY: {' | '.join(v['why_buy'][:3])}")
            if v["why_avoid"]:
                print(f"       ❌ AVOID: {' | '.join(v['why_avoid'][:2])}")
            if v["why_wait"]:
                print(f"       ⏳ WAIT: {' | '.join(v['why_wait'][:2])}")
            print(f"       Signals: {' | '.join(v['primary_signals'][:3])}")

        if not alerts:
            print(f"  No signals passed quality gates for this horizon.")

    # Strategy attribution
    attr=bt.get("strategy_attribution",{})
    if attr:
        print(f"\n{'═'*60}")
        print(f"  STRATEGY ATTRIBUTION (What's Working / What's Not)")
        print(f"{'═'*60}")
        sorted_attr=sorted(attr.items(),key=lambda x:-x[1].get("total_pnl",0))
        for sig,vals in sorted_attr[:10]:
            status=vals.get("status","NEUTRAL")
            emoji="🔥" if status=="HOT" else "❄️" if status=="COLD" else "➖"
            print(f"  {emoji} {sig:<25} | WinRate: {vals['winrate']:.1%} | Trades: {vals['trades']} | P&L: ₹{vals['total_pnl']:,.0f} | Avg: ₹{vals['avg_pnl']:,.0f} | {status}")
    print(f"\n{SEP}")

# ══════════════════════════════════════════════════════════════════════════════
# §10  MAIN ORCHESTRATION
# ══════════════════════════════════════════════════════════════════════════════
def run(cfg:Cfg)->tuple:
    cfg.output_dir.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)-8s | %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  logging.FileHandler(cfg.output_dir/"nse_v13.log")])
    for nm in ("yfinance","urllib3","requests","charset_normalizer"):
        logging.getLogger(nm).setLevel(logging.CRITICAL)
    t0=time.time()

    if _HAS_RICH:
        _con.print()
        _con.print(Rule(characters="═", style="bright_cyan"))
        _con.print(Align.center(
            "[bold bright_white on #003366]"
            "   NSE THREE-HORIZON TRADER v13.0   "
            "·  SHORT · MID · LONG  ·  VERDICT ENGINE   "
            "[/bold bright_white on #003366]"))
        _con.print(Align.center(
            f"[dim]  {datetime.now().strftime('%A, %d %B %Y  |  %H:%M IST')}  "
            f"|  Capital: ₹{cfg.capital/1e5:.0f}L  "
            f"|  Universe: {len(_ALL_SYMS)} symbols  [/dim]"))
        _con.print(Rule(characters="═", style="bright_cyan"))
        _con.print(f"\n[dim]Fetching Nifty50 benchmark & rolling regime...[/dim]")

    # Nifty rolling regime
    nifty_hist=nifty50_history(cfg.live_period, cfg.live_interval)
    nifty_regime_df=compute_nifty_regime(nifty_hist) if not nifty_hist.empty else pd.DataFrame()
    nifty_by_date={}
    if not nifty_regime_df.empty:
        for _,row in nifty_regime_df.iterrows():
            d=pd.Timestamp(row["date"]).normalize()
            nifty_by_date[d]={"trend":float(row["trend"]),"label":str(row["label"]),
                              "rsi":float(row["rsi"]),"last":float(row["close"]),
                              "ema9":float(row.get("ema9",0)),"ema21":float(row.get("ema21",0)),
                              "ema50":float(row.get("ema50",0))}
    latest_nifty=max(nifty_by_date.values(),key=lambda x:x.get("last",0)) if nifty_by_date else {}
    if not latest_nifty:
        latest_nifty={"trend":0,"label":"N/A","rsi":50,"last":0,"ema9":0,"ema21":0,"ema50":0}
    if not nifty_hist.empty:
        cl=nifty_hist.sort_values("date")["close"].reset_index(drop=True)
        latest_nifty["chg_1m"]=float((cl.iloc[-1]/cl.iloc[-22]-1)*100) if len(cl)>=22 else 0.0
        latest_nifty["chg_3m"]=float((cl.iloc[-1]/cl.iloc[0]-1)*100) if len(cl)>0 else 0.0
    else:
        latest_nifty["chg_1m"]=0.0; latest_nifty["chg_3m"]=0.0

    if _HAS_RICH and latest_nifty:
        threshold=cfg.bear_threshold if latest_nifty.get("trend",0)<=-0.5 else cfg.base_threshold
        _con.print(f"[bold blue]Nifty50:[/bold blue] ₹{latest_nifty.get('last',0):.0f} "
                   f"{latest_nifty.get('label','N/A')} RSI:{latest_nifty.get('rsi',50):.0f} "
                   f"1M:{latest_nifty.get('chg_1m',0):+.1f}% 3M:{latest_nifty.get('chg_3m',0):+.1f}%")

    # Fetch data
    syms=cfg.symbols if cfg.symbols else _ALL_SYMS
    syms=sorted(set(syms)-_SKIP_SYMBOLS)
    if _HAS_RICH: _con.print(f"[dim]Fetching {len(syms)} symbols...[/dim]\n")
    all_frames=[]; fund_cache={}; ok=0; fail=0

    if _HAS_YF:
        def _fetch(sym):
            nonlocal ok,fail
            df=fetch_ohlcv(sym,cfg.live_period,cfg.live_interval)
            if not df.empty and len(df)>=cfg.min_bars:
                all_frames.append(df)
                if cfg.fetch_fundamentals: fund_cache[sym]=fetch_fundamentals(sym)
                ok+=1
            else: fail+=1
        if _HAS_RICH:
            with Progress(SpinnerColumn(),TextColumn("[progress.description]{task.description}"),
                          BarColumn(bar_width=24),TextColumn("{task.completed}/{task.total}"),
                          TimeElapsedColumn(),console=_con) as prog:
                task=prog.add_task("[cyan]Fetching NSE data...",total=len(syms))
                for sym in syms:
                    prog.update(task,description=f"[cyan][bold]{sym:<14}[/bold]")
                    _fetch(sym); prog.advance(task)
        else:
            for i,sym in enumerate(syms,1):
                if i%20==0: LOG.info("Progress: %d/%d ok:%d fail:%d",i,len(syms),ok,fail)
                _fetch(sym)
    else:
        LOG.error("yfinance not available"); return {}, {}, latest_nifty

    if not all_frames: raise ValueError("No price data loaded.")
    prices=pd.concat(all_frames,ignore_index=True)
    prices=(prices.sort_values(["symbol","date"]).drop_duplicates(["date","symbol"],keep="last").reset_index(drop=True))
    LOG.info("Loaded %d bars across %d symbols.",len(prices),prices["symbol"].nunique())

    # Feature engineering
    if _HAS_RICH: _con.print("[dim]Computing indicators...[/dim]")
    feat=engineer_all(prices,cfg)
    if feat.empty: raise ValueError("Feature engineering returned empty frame.")

    # Score with rolling regime
    feat=add_scores(feat,cfg,nifty_by_date,use_fundamentals=False)

    # Backtest (mid-term as default)
    if _HAS_RICH: _con.print("[dim]Running backtest with realistic fills...[/dim]")
    bt=run_backtest(feat,cfg,nifty_by_date,horizon="mid")

    # Three-horizon alerts
    if _HAS_RICH: _con.print("[dim]Building three-horizon verdicts...[/dim]")
    results,rej=build_three_horizon_alerts(feat,latest_nifty,fund_cache,cfg)
    elapsed=round(time.time()-t0,1)

    if _HAS_RICH:
        total_signals=sum(len(v) for v in results.values())
        _con.print(f"\n[dim]Done in {elapsed}s | Fetched:{ok} Failed:{fail} | Signals:{total_signals}[/dim]\n")

    save_all(results,bt,latest_nifty,cfg)

    if not _HAS_RICH:
        plain_report(results,latest_nifty,bt,cfg)
        return results,bt,latest_nifty

    if _HAS_RICH:
        for hname in ["short","mid","long"]:
            hcfg=getattr(cfg, f"{hname}_cfg")
            alerts=results.get(hname,[])
            _con.print(Rule(characters="═", style="bright_cyan"))
            _con.print(Align.center(f"[bold bright_cyan] {hcfg.label.upper()} [/bold bright_cyan]"))
            _con.print(Rule(characters="═", style="bright_cyan"))
            if not alerts:
                _con.print("[dim]  No signals passed quality gates.[/dim]")
                continue
            for i,r in enumerate(alerts[:cfg.top_n],1):
                v=r["verdict"]; l=r["levels"]
                col={"BUY":"bold bright_green","WATCH":"bold yellow","WAIT":"bold orange3","AVOID":"bold red"}.get(v["verdict"],"dim")
                _con.print(f"  [{col}]{v['verdict']:<6}[/{col}] #{i} {r['symbol']:<12} ₹{r['last_close']:>8,.2f}  "
                           f"Score:{r['score']:+.3f}  Conf:{v['confidence']}%  "
                           f"Entry:₹{l['entry']:,.2f}→₹{l['tp']:,.2f}  SL:₹{l['sl']:,.2f}  {l['rr_str']}")
                if v["why_buy"]:
                    _con.print(f"       [green]✓ {' | '.join(v['why_buy'][:2])}[/green]")
                if v["why_avoid"]:
                    _con.print(f"       [red]✗ {' | '.join(v['why_avoid'][:2])}[/red]")

        # Attribution
        attr=bt.get("strategy_attribution",{})
        if attr:
            _con.print(Rule(characters="═", style="bright_magenta"))
            _con.print(Align.center("[bold bright_magenta] STRATEGY ATTRIBUTION [/bold bright_magenta]"))
            _con.print(Rule(characters="═", style="bright_magenta"))
            sorted_attr=sorted(attr.items(),key=lambda x:-x[1].get("total_pnl",0))
            for sig,vals in sorted_attr[:10]:
                status=vals.get("status","NEUTRAL")
                col="bright_green" if status=="HOT" else "red" if status=="COLD" else "yellow"
                _con.print(f"  [{col}]{status:<6}[/{col}] {sig:<25} WR:{vals['winrate']:.1%}  "
                           f"Trades:{vals['trades']}  P&L:₹{vals['total_pnl']:>10,.0f}  Avg:₹{vals['avg_pnl']:>8,.0f}")

        _con.print(Rule(characters="═", style="bright_cyan"))
        _con.print(Align.center(
            f"[bold bright_cyan] ✅ v13.0 | {sum(len(v) for v in results.values())} signals | "
            f"{datetime.now().strftime('%d %b %Y %H:%M IST')} | {elapsed:.1f}s [/bold bright_cyan]"))
        _con.print(Rule(characters="═", style="bright_cyan"))
        _con.print()

    return results,bt,latest_nifty

# ══════════════════════════════════════════════════════════════════════════════
# §11  CLI
# ══════════════════════════════════════════════════════════════════════════════
def main():
    p=argparse.ArgumentParser(
        description="NSE Three-Horizon Trader v13.0 — Short/Mid/Long with Verdicts",
        formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--symbols", type=str, default="", help="Comma-separated NSE symbols")
    p.add_argument("--group", type=str, default="", help="Index group")
    p.add_argument("--top-n", type=int, default=12)
    p.add_argument("--output-dir", type=Path, default=Path("nse_v13_output"))
    p.add_argument("--period", type=str, default="8mo")
    p.add_argument("--min-vol", type=int, default=500_000)
    p.add_argument("--threshold", type=float, default=0.16)
    p.add_argument("--no-fund", action="store_true", help="Skip fundamentals")
    p.add_argument("--capital", type=float, default=1_000_000)
    a=p.parse_args()

    cfg=Cfg()
    cfg.output_dir=a.output_dir; cfg.live_period=a.period; cfg.top_n=a.top_n
    cfg.min_avg_vol=a.min_vol; cfg.base_threshold=a.threshold
    cfg.fetch_fundamentals=not a.no_fund; cfg.capital=a.capital

    if a.symbols:
        cfg.symbols=[s.strip().upper() for s in a.symbols.split(",") if s.strip()]
    elif a.group:
        gk=a.group.strip().upper()
        matched=[sl for grp,sl in _UNIVERSE.items() if gk in grp.upper()]
        if matched:
            cfg.symbols=sorted({s for sub in matched for s in sub}-_SKIP_SYMBOLS)
        else:
            print(f"Group '{a.group}' not found. Available: {list(_UNIVERSE.keys())}")
            sys.exit(1)
    run(cfg)

# ══════════════════════════════════════════════════════════════════════════════
# §12  STREAMLIT DASHBOARD  (Rich, detailed, three-horizon, verdicts, attribution)
# ══════════════════════════════════════════════════════════════════════════════

def _verdict_color(v: str) -> str:
    return {"BUY":"#26a69a","WATCH":"#f59e0b","WAIT":"#f97316","AVOID":"#ef5350"}.get(v,"#787b86")

def _verdict_bg(v: str) -> str:
    return {"BUY":"#26a69a15","WATCH":"#f59e0b15","WAIT":"#f9731615","AVOID":"#ef535015"}.get(v,"#787b8615")

def _verdict_emoji(v: str) -> str:
    return {"BUY":"🟢","WATCH":"🟡","WAIT":"🟠","AVOID":"🔴"}.get(v,"⚪")

def run_dashboard(results: dict, bt: dict, nifty: dict):
    alerts_short = results.get("short", [])
    alerts_mid = results.get("mid", [])
    alerts_long = results.get("long", [])

    trend = nifty.get("trend", 0)
    last = nifty.get("last", 0)
    rsi_n = nifty.get("rsi", 50)
    chg1m = nifty.get("chg_1m", 0)
    lbl = nifty.get("label", "N/A")

    bt_ret = bt.get("ret", 0)
    bt_sh = bt.get("sharpe", 0)
    bt_dd = bt.get("maxdd", 0)
    bt_wr = bt.get("winrate", 0)
    bt_tr = bt.get("trades", 0)

    st.markdown("""
    <style>
    .stApp { background: #0b0e11; color: #d1d4dc; font-family: 'Segoe UI', sans-serif; }
    [data-testid="stMetricContainer"] { background: #131722; border: 1px solid #2a3347; border-radius: 4px; padding: 12px; }
    .verdict-card { border-radius: 6px; padding: 16px; margin-bottom: 12px; border-left: 4px solid; }
    .signal-pill { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 0.68rem; font-weight: 600; margin: 2px; }
    </style>
    """, unsafe_allow_html=True)

    # Header
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Nifty50", f"₹{last:,.0f}", f"{lbl}")
    c2.metric("1M Change", f"{chg1m:+.2f}%")
    c3.metric("🟢 Signals", f"{len(alerts_short)+len(alerts_mid)+len(alerts_long)}")
    c4.metric("📊 BT Return", f"{bt_ret:+.2%}")
    c5.metric("📐 Sharpe", f"{bt_sh:.3f}")

    tabs = st.tabs([
        "⚡ Short Term (2–7 Days)",
        "📅 Mid Term (1–3 Months)",
        "🏛️ Long Term (6–12+ Months)",
        "📊 Strategy Attribution",
        "📈 Backtest Integrity",
    ])

    # ══════════════════════════════════════════════════════════════════════
    # TAB 0 — SHORT TERM
    # ══════════════════════════════════════════════════════════════════════
    with tabs[0]:
        _render_horizon_tab(alerts_short, "short", cfg)

    # ══════════════════════════════════════════════════════════════════════
    # TAB 1 — MID TERM
    # ══════════════════════════════════════════════════════════════════════
    with tabs[1]:
        _render_horizon_tab(alerts_mid, "mid", cfg)

    # ══════════════════════════════════════════════════════════════════════
    # TAB 2 — LONG TERM
    # ══════════════════════════════════════════════════════════════════════
    with tabs[2]:
        _render_horizon_tab(alerts_long, "long", cfg)

    # ══════════════════════════════════════════════════════════════════════
    # TAB 3 — STRATEGY ATTRIBUTION
    # ══════════════════════════════════════════════════════════════════════
    with tabs[3]:
        st.markdown("""
        <div style='background:#131722;padding:16px 20px;border-left:4px solid #a855f7;border-radius:6px;margin-bottom:16px'>
          <div style='font-family:Syne,sans-serif;font-weight:800;font-size:1.2rem;color:#a855f7'>
            📊 STRATEGY ATTRIBUTION — What's Working vs What's Not
          </div>
          <div style='font-size:.76rem;color:#787b86;margin-top:4px'>
            Tracks which signal types generated winning vs losing trades in the backtest.
            HOT = making money. COLD = losing money. Adjust your weights accordingly.
          </div>
        </div>""", unsafe_allow_html=True)

        attr = bt.get("strategy_attribution", {})
        if not attr:
            st.info("Run a backtest to see strategy attribution data.")
        else:
            sorted_attr = sorted(attr.items(), key=lambda x: -x[1].get("total_pnl", 0))

            # Summary metrics
            hot_count = sum(1 for _, v in sorted_attr if v.get("status") == "HOT")
            cold_count = sum(1 for _, v in sorted_attr if v.get("status") == "COLD")
            total_pnl = sum(v.get("total_pnl", 0) for _, v in sorted_attr)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("🔥 HOT Strategies", f"{hot_count}")
            m2.metric("❄️ COLD Strategies", f"{cold_count}")
            m3.metric("Total Trades", f"{sum(v.get('trades',0) for _,v in sorted_attr)}")
            m4.metric("Net P&L", f"₹{total_pnl:,.0f}")

            # Attribution table
            attr_rows = []
            for sig, vals in sorted_attr:
                attr_rows.append({
                    "Signal Type": sig.replace("_", " ").title(),
                    "Status": vals.get("status", "NEUTRAL"),
                    "Trades": vals.get("trades", 0),
                    "Wins": vals.get("wins", 0),
                    "Losses": vals.get("losses", 0),
                    "Win Rate": f"{vals.get('winrate',0):.1%}",
                    "Total P&L ₹": vals.get("total_pnl", 0),
                    "Avg P&L ₹": vals.get("avg_pnl", 0),
                })

            attr_df = pd.DataFrame(attr_rows)
            st.dataframe(attr_df, use_container_width=True, height=400,
                        column_config={
                            "Total P&L ₹": st.column_config.NumberColumn("Total P&L", format="₹%.0f"),
                            "Avg P&L ₹": st.column_config.NumberColumn("Avg P&L", format="₹%.0f"),
                        })

            # Visual bars
            st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
            for sig, vals in sorted_attr[:15]:
                status = vals.get("status", "NEUTRAL")
                color = "#26a69a" if status == "HOT" else "#ef5350" if status == "COLD" else "#f59e0b"
                emoji = "🔥" if status == "HOT" else "❄️" if status == "COLD" else "➖"
                pnl = vals.get("total_pnl", 0)
                max_pnl = max(abs(v.get("total_pnl", 0)) for _, v in sorted_attr) if sorted_attr else 1
                bar_width = min(abs(pnl) / max_pnl * 300, 300) if max_pnl > 0 else 0
                bar_color = "#26a69a" if pnl > 0 else "#ef5350"

                st.markdown(f"""
                <div style='display:flex;align-items:center;gap:12px;margin-bottom:8px;padding:8px 12px;background:#131722;border-radius:4px'>
                  <div style='width:30px;text-align:center;font-size:1.2rem'>{emoji}</div>
                  <div style='width:180px;font-size:.85rem;color:#d1d4dc;font-weight:600'>{sig.replace("_"," ").title()}</div>
                  <div style='width:60px;font-size:.75rem;color:{color};font-weight:700'>{status}</div>
                  <div style='flex:1;height:8px;background:#1c2030;border-radius:4px;overflow:hidden'>
                    <div style='width:{bar_width}px;height:100%;background:{bar_color};border-radius:4px'></div>
                  </div>
                  <div style='width:100px;text-align:right;font-size:.8rem;color:{bar_color};font-weight:700'>₹{pnl:,.0f}</div>
                  <div style='width:60px;text-align:right;font-size:.75rem;color:#787b86'>{vals.get('winrate',0):.0%} WR</div>
                </div>
                """, unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    # TAB 4 — BACKTEST INTEGRITY
    # ══════════════════════════════════════════════════════════════════════
    with tabs[4]:
        st.markdown("""
        <div style='background:#131722;padding:16px 20px;border-left:4px solid #f59e0b;border-radius:6px;margin-bottom:16px'>
          <div style='font-family:Syne,sans-serif;font-weight:800;font-size:1.2rem;color:#f59e0b'>
            📈 BACKTEST INTEGRITY DECLARATION
          </div>
          <div style='font-size:.76rem;color:#787b86;margin-top:4px;line-height:1.7'>
            • <b style='color:#d1d4dc'>No look-ahead bias</b> — fundamentals banned from historical scoring<br>
            • <b style='color:#d1d4dc'>Realistic fills</b> — stops execute against daily low/high, not close<br>
            • <b style='color:#d1d4dc'>1% risk per trade</b> — volatility-targeted sizing, not fixed allocation<br>
            • <b style='color:#d1d4dc'>Correlation guard</b> — blocks >0.70 correlated picks<br>
            • <b style='color:#d1d4dc'>Survivorship filter</b> — excludes stocks with incomplete history<br>
            • <b style='color:#d1d4dc'>Strategy attribution</b> — tracks which signals actually make money
          </div>
        </div>""", unsafe_allow_html=True)

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
                         line=dict(color="#26a69a", width=2), fill="tozeroy", fillcolor="rgba(38,166,154,0.08)"))
            fig.add_hline(y=1_000_000, line_color="#434651", line_dash="dot")
            fig.update_layout(height=350, paper_bgcolor="#131722", plot_bgcolor="#0b0e11",
                              font=dict(color="#787b86"), margin=dict(l=0, r=0, t=10, b=0),
                              xaxis=dict(showgrid=True, gridcolor="#2a3347"),
                              yaxis=dict(showgrid=True, gridcolor="#2a3347", tickprefix="₹"), showlegend=False)
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


def _render_horizon_tab(alerts: List[dict], horizon: str, cfg: Cfg):
    """Render a single horizon tab with rich verdict cards."""
    hcfg = getattr(cfg, f"{horizon}_cfg", cfg.mid_cfg)

    st.markdown(f"""
    <div style='background:linear-gradient(135deg,{_verdict_bg("BUY")},#0b0e11);padding:14px 20px;border-left:4px solid {_verdict_color("BUY")};border-radius:6px;margin-bottom:16px'>
      <div style='font-family:Syne,sans-serif;font-weight:800;font-size:1.2rem;color:#d1d4dc'>
        {hcfg.label}
      </div>
      <div style='font-size:.76rem;color:#787b86;margin-top:4px'>
        {hcfg.description} | Threshold: {hcfg.threshold} | ATR SL: {hcfg.atr_sl_mult}× | ATR TP: {hcfg.atr_tp_mult}×
      </div>
    </div>""", unsafe_allow_html=True)

    if not alerts:
        st.warning(f"No {horizon}-term signals passed quality gates. Try lowering threshold or min-vol.")
        return

    # Summary table
    rows = []
    for r in alerts[:20]:
        v = r["verdict"]; l = r["levels"]
        rows.append({
            "Symbol": r["symbol"], "Verdict": v["verdict"], "Conf": v["confidence"],
            "Score": round(r["score"], 4), "RSI": r["rsi"], "ADX": r["adx"],
            "Vol×": r["vol_ratio"], "ATR%": r["atr_pct"], "F&O": "✅" if r["is_fo"] else "—",
            "Price ₹": r["last_close"], "Entry ₹": l["entry"], "Target ₹": l["tp"],
            "Stop ₹": l["sl"], "R:R": l["rr_str"], "Window": l["window"],
            "Top Signal": " | ".join(v["primary_signals"][:2]),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, height=400,
                 column_config={
                     "Conf": st.column_config.ProgressColumn("Conf", min_value=0, max_value=100, format="%.0f%%"),
                     "Price ₹": st.column_config.NumberColumn("Price", format="₹%.2f"),
                     "Entry ₹": st.column_config.NumberColumn("Entry", format="₹%.2f"),
                     "Target ₹": st.column_config.NumberColumn("Target", format="₹%.2f"),
                     "Stop ₹": st.column_config.NumberColumn("Stop", format="₹%.2f"),
                 })

    csv = df.to_csv(index=False).encode()
    st.download_button(f"⬇️ Download {horizon.title()} CSV", data=csv,
                       file_name=f"{horizon}_signals_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                       mime="text/csv")

    st.markdown("<hr style='border-color:#2a3347;margin:16px 0'>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-family:Syne,sans-serif;font-weight:700;font-size:1rem;color:#38bdf8;margin-bottom:12px'>📋 DETAILED VERDICT CARDS — {horizon.upper()} TERM</div>", unsafe_allow_html=True)

    # Verdict cards
    for i, r in enumerate(alerts[:cfg.top_n], 1):
        v = r["verdict"]; l = r["levels"]
        vc = _verdict_color(v["verdict"])
        vbg = _verdict_bg(v["verdict"])
        ve = _verdict_emoji(v["verdict"])

        with st.expander(
            f"{ve} #{i} {r['symbol']} | {v['verdict']} ({v['confidence']}%) | ₹{r['last_close']:,.2f} → ₹{l['tp']:,.2f} | R:R {l['rr_str']}",
            expanded=(i == 1 and v["verdict"] == "BUY")
        ):
            # Top row: verdict + price + metrics
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("Verdict", v["verdict"], f"{v['confidence']}% confidence")
            c2.metric("Price", f"₹{r['last_close']:,.2f}")
            c3.metric("RSI", f"{r['rsi']:.1f}")
            c4.metric("ADX", f"{r['adx']:.1f}")
            c5.metric("Vol", f"{r['vol_ratio']:.2f}×")
            c6.metric("ATR%", f"{r['atr_pct']:.2f}%")

            # Trade plan
            st.markdown(f"""
            <div style='background:{vbg};border-left:4px solid {vc};border-radius:6px;padding:14px 18px;margin:12px 0'>
              <div style='font-family:Syne,sans-serif;font-weight:700;font-size:1rem;color:{vc};margin-bottom:10px'>
                📐 TRADE PLAN — {v['verdict']}
              </div>
              <div style='display:grid;grid-template-columns:repeat(4,1fr);gap:12px;font-size:.85rem'>
                <div style='background:#131722;padding:10px;border-radius:4px;text-align:center'>
                  <div style='color:#787b86;font-size:.7rem'>ENTRY</div>
                  <div style='color:#38bdf8;font-weight:700;font-size:1.1rem'>₹{l['entry']:,.2f}</div>
                </div>
                <div style='background:#131722;padding:10px;border-radius:4px;text-align:center'>
                  <div style='color:#787b86;font-size:.7rem'>TARGET</div>
                  <div style='color:#26a69a;font-weight:700;font-size:1.1rem'>₹{l['tp']:,.2f}</div>
                  <div style='color:#26a69a;font-size:.75rem'>+{(l['tp']/l['entry']-1)*100:.1f}%</div>
                </div>
                <div style='background:#131722;padding:10px;border-radius:4px;text-align:center'>
                  <div style='color:#787b86;font-size:.7rem'>STOP LOSS</div>
                  <div style='color:#ef5350;font-weight:700;font-size:1.1rem'>₹{l['sl']:,.2f}</div>
                  <div style='color:#ef5350;font-size:.75rem'>{(l['sl']/l['entry']-1)*100:.1f}%</div>
                </div>
                <div style='background:#131722;padding:10px;border-radius:4px;text-align:center'>
                  <div style='color:#787b86;font-size:.7rem'>RISK:REWARD</div>
                  <div style='color:#d1d4dc;font-weight:700;font-size:1.1rem'>{l['rr_str']}</div>
                  <div style='color:#787b86;font-size:.75rem'>{l['window']}</div>
                </div>
              </div>
            </div>""", unsafe_allow_html=True)

            # Position sizing
            cap = st.session_state.get("capital", 1_000_000)
            risk = abs(l['entry'] - l['sl'])
            if risk > 0:
                qty_1p = int((cap * 0.01) // risk)
                qty_20p = int((cap * 0.20) // l['entry'])
                qty = min(qty_1p, qty_20p)
            else:
                qty = 0

            st.markdown(f"""
            <div style='background:#1c2030;padding:10px 14px;border-radius:4px;margin:10px 0'>
              <div style='color:#f59e0b;font-weight:700;font-size:.85rem;margin-bottom:6px'>💰 POSITION SIZING (1% Risk Rule)</div>
              <div style='display:flex;gap:16px;font-size:.8rem;color:#d1d4dc'>
                <div><b>Capital:</b> ₹{cap:,.0f}</div>
                <div><b>Risk/Share:</b> ₹{risk:.2f}</div>
                <div><b>Qty:</b> <span style='color:#38bdf8;font-weight:700'>{qty:,}</span> shares</div>
                <div><b>Deployed:</b> ₹{qty*l['entry']:,.0f}</div>
                <div><b>Max Loss:</b> <span style='color:#ef5350'>₹{qty*risk:,.0f}</span></div>
              </div>
            </div>""", unsafe_allow_html=True)

            # Verdict rationale
            col_buy, col_avoid, col_wait = st.columns(3)

            with col_buy:
                if v["why_buy"]:
                    st.markdown(f"""
                    <div style='background:#26a69a15;padding:10px 12px;border-radius:4px;border-left:3px solid #26a69a;height:100%'>
                      <div style='color:#26a69a;font-weight:700;font-size:.85rem;margin-bottom:6px'>✅ WHY BUY</div>
                      <div style='font-size:.78rem;color:#d1d4dc;line-height:1.7'>
                      {'<br>'.join(f'<span style="color:#26a69a">▸</span> {b}' for b in v['why_buy'][:5])}
                      </div>
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown("<div style='color:#434651;font-size:.78rem;padding:10px'>No strong buy signals</div>", unsafe_allow_html=True)

            with col_avoid:
                if v["why_avoid"]:
                    st.markdown(f"""
                    <div style='background:#ef535015;padding:10px 12px;border-radius:4px;border-left:3px solid #ef5350;height:100%'>
                      <div style='color:#ef5350;font-weight:700;font-size:.85rem;margin-bottom:6px'>❌ WHY AVOID</div>
                      <div style='font-size:.78rem;color:#d1d4dc;line-height:1.7'>
                      {'<br>'.join(f'<span style="color:#ef5350">▸</span> {a}' for a in v['why_avoid'][:5])}
                      </div>
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown("<div style='color:#434651;font-size:.78rem;padding:10px'>No major red flags</div>", unsafe_allow_html=True)

            with col_wait:
                if v["why_wait"]:
                    st.markdown(f"""
                    <div style='background:#f59e0b15;padding:10px 12px;border-radius:4px;border-left:3px solid #f59e0b;height:100%'>
                      <div style='color:#f59e0b;font-weight:700;font-size:.85rem;margin-bottom:6px'>⏳ WHY WAIT</div>
                      <div style='font-size:.78rem;color:#d1d4dc;line-height:1.7'>
                      {'<br>'.join(f'<span style="color:#f59e0b">▸</span> {w}' for w in v['why_wait'][:5])}
                      </div>
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown("<div style='color:#434651;font-size:.78rem;padding:10px'>No pending conditions</div>", unsafe_allow_html=True)

            # Factor breakdown
            st.markdown("<div style='margin-top:10px'></div>", unsafe_allow_html=True)
            factors = v.get("factors", {})
            if factors:
                fcols = st.columns(4)
                factor_items = list(factors.items())
                for idx, (fname, fval) in enumerate(factor_items):
                    fcol = "#26a69a" if fval > 0.3 else "#f59e0b" if fval > 0 else "#ef5350"
                    fcols[idx % 4].markdown(f"""
                    <div style='background:#131722;padding:8px 10px;border-radius:3px;margin-bottom:4px'>
                      <div style='display:flex;justify-content:space-between;align-items:center'>
                        <span style='font-size:.75rem;color:#787b86'>{fname.title()}</span>
                        <span style='font-size:.8rem;color:{fcol};font-weight:700'>{fval:+.2f}</span>
                      </div>
                      <div style='height:3px;background:#1c2030;border-radius:2px;margin-top:4px;overflow:hidden'>
                        <div style='width:{min(abs(fval)*100,100):.0f}%;height:100%;background:{fcol};border-radius:2px'></div>
                      </div>
                    </div>""", unsafe_allow_html=True)

            # Primary signals
            st.markdown(f"""
            <div style='margin-top:8px;font-size:.75rem;color:#787b86'>
              <b style='color:#38bdf8'>Primary Signals:</b> {' · '.join(v['primary_signals'][:3])}
            </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# §13  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if _STREAMLIT:
        cfg = Cfg()
        try:
            results, bt, nifty = run(cfg)
            run_dashboard(results, bt, nifty)
        except Exception as e:
            st.error(f"Engine error: {e}")
            LOG.exception("Streamlit run failed")
    else:
        main()
