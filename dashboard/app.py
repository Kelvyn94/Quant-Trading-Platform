import os
import sys
import dash
from dash import dcc, html, Input, Output
import plotly.graph_objs as go
import sqlite3
import pandas as pd
import importlib
from functools import wraps
import time
import ast
import numpy as np
from datetime import datetime, timedelta
from dash import State  # add if not already imported
import math

# Try to use Flask-Caching; fall back to a simple in-memory cache if not installed
Cache = None
try:
    flask_caching = importlib.import_module('flask_caching')
    Cache = flask_caching.Cache
except Exception:
    Cache = None
    print("Warning: Flask-Caching not installed — using in-memory fallback cache.", file=sys.stderr)

# --------------------------------------
# Load Data From SQLite Database (pick best table)
# --------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(BASE_DIR, 'database', 'trading.db')

if not os.path.exists(DB_PATH):
    print(f"ERROR: database not found at {DB_PATH}", file=sys.stderr)
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]

candidates = ['prices', 'gold_1d', 'gold_4h', 'gold_1h', 'gold_30m', 'gold_15m', 'gold_5m', 'gold_1m']
available = [t for t in candidates if t in tables]
if not available:
    print("ERROR: no known price tables found in DB. Available:", tables, file=sys.stderr)
    conn.close()
    sys.exit(1)

best_table = None
best_count = -1
for t in available:
    try:
        c.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = c.fetchone()[0]
    except Exception:
        cnt = 0
    if cnt > best_count:
        best_count = cnt
        best_table = t

# --- inspect schema and build proper aliased SELECT while connection is still open ---
c.execute(f"PRAGMA table_info({best_table})")
schema = c.fetchall()
actual_cols = [row[1] for row in schema]
print("DB columns:", actual_cols)

def _normalize(col):
    # handle tuple-like string column names written by pandas/yfinance
    if isinstance(col, tuple):
        parts = [str(p).strip() for p in col if str(p).strip() != ""]
        return (parts[0].lower() if parts else "_".join(map(str, col))).lower()
    if isinstance(col, str):
        try:
            v = ast.literal_eval(col)
            if isinstance(v, tuple):
                parts = [str(p).strip() for p in v if str(p).strip() != ""]
                if parts:
                    return parts[0].lower()
                return "_".join(map(str, v)).lower()
        except Exception:
            pass
        return col.lower()
    return str(col).lower()

normalized = {actual: _normalize(actual) for actual in actual_cols}
print("Normalized mapping:", normalized)

def find_actual_for(needle):
    needle = needle.lower()
    for actual, norm in normalized.items():
        if norm == needle or needle in norm:
            return actual
    return None

date_actual = find_actual_for('date') or find_actual_for('datetime') or find_actual_for('time')
open_actual = find_actual_for('open')
high_actual = find_actual_for('high')
low_actual = find_actual_for('low')
close_actual = find_actual_for('close')
volume_actual = find_actual_for('volume')

missing = [name for name, val in (('date', date_actual), ('open', open_actual), ('high', high_actual), ('low', low_actual), ('close', close_actual)) if val is None]
if missing:
    print(f"ERROR: missing required columns {missing} in table '{best_table}'. DB cols: {actual_cols}", file=sys.stderr)
    conn.close()
    sys.exit(1)

# Build SELECT with AS aliases so pandas returns canonical column names
select_cols = [
    f'"{date_actual}" AS date',
    f'"{open_actual}" AS open',
    f'"{high_actual}" AS high',
    f'"{low_actual}" AS low',
    f'"{close_actual}" AS close'
]
if volume_actual:
    select_cols.append(f'"{volume_actual}" AS volume')

q = f"SELECT {', '.join(select_cols)} FROM {best_table}"
df_prices = pd.read_sql_query(q, conn, parse_dates=['date'])
conn.close()

print(f"Loaded {len(df_prices)} rows from table {best_table} (aliased columns)")

# canonicalize and cleanup
df_prices.columns = [c.lower() for c in df_prices.columns]
df_prices.dropna(subset=['date', 'open', 'close'], inplace=True)
df_prices.sort_values('date', inplace=True)
print("After cleanup rows:", len(df_prices))

# simple downsample aggregator for OHLC data (vectorized grouping)
def downsample_ohlc(df, max_points=1000):
    if df is None or df.empty:
        return df
    n = len(df)
    if n <= max_points:
        return df.reset_index(drop=True)
    # assign each row to a bucket [0..max_points-1]
    idx = np.arange(n)
    buckets = (idx * max_points) // n
    df = df.reset_index(drop=True)
    df['__bucket'] = buckets
    agg = df.groupby('__bucket').agg({
        'date': 'first',
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        # include volume if present
        **({'volume': 'sum'} if 'volume' in df.columns else {})
    }).reset_index(drop=True)
    return agg

# default initial window: last 7 days (adjust per timeframe)
max_points = 1200
default_days = 7
latest = df_prices['date'].max()
earliest = df_prices['date'].min()
default_start = (latest - timedelta(days=default_days)).date()
default_end = latest.date()

# --------------------------------------
# DASH APP INITIALIZATION
# --------------------------------------
app = dash.Dash(__name__)
app.title = "Gold Market Dashboard"

# configure cache (filesystem or simple; adjust as needed)
if Cache is not None:
    cache = Cache(app.server, config={'CACHE_TYPE': 'filesystem', 'CACHE_DIR': os.path.join(BASE_DIR, 'cache'), 'CACHE_DEFAULT_TIMEOUT': 300})
    memoize_decorator = cache.memoize
else:
    # simple in-memory memoize decorator (works for hashable args)
    _mem_cache = {}
    def memoize_decorator(timeout=None):
        def decorator(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                key = (fn.__name__, args, tuple(sorted(kwargs.items())))
                if key in _mem_cache:
                    return _mem_cache[key]
                val = fn(*args, **kwargs)
                _mem_cache[key] = val
                return val
            return wrapped
        return decorator

def _query_db(table, start=None, end=None, limit=None):
    """
    Query using the actual DB columns (aliased to canonical names).
    Uses the already-detected actual column names (date_actual, open_actual, etc.).
    """
    conn = sqlite3.connect(DB_PATH)
    params = {}

    # build SELECT with actual column names aliased to canonical names
    select_cols = [
        f'"{date_actual}" AS date',
        f'"{open_actual}" AS open',
        f'"{high_actual}" AS high',
        f'"{low_actual}" AS low',
        f'"{close_actual}" AS close'
    ]
    if volume_actual:
        select_cols.append(f'"{volume_actual}" AS volume')

    table_quoted = f'"{table}"'
    q = f"SELECT {', '.join(select_cols)} FROM {table_quoted} "

    where = []
    if start:
        where.append(f'"{date_actual}" >= :start')
        params['start'] = start
    if end:
        where.append(f'"{date_actual}" <= :end')
        params['end'] = end
    if where:
        q += "WHERE " + " AND ".join(where) + " "

    # Order by the aliased date column (alias 'date' is valid in ORDER BY)
    q += "ORDER BY date DESC "
    if limit:
        q += "LIMIT :limit"
        params['limit'] = int(limit)

    df = pd.read_sql_query(q, conn, params=params, parse_dates=['date'])
    conn.close()
    # return chronological order
    return df.iloc[::-1].reset_index(drop=True)

@memoize_decorator()  # cache by args (uses Flask-Caching if installed)
def get_data_cached(table, start, end, limit):
    return _query_db(table, start, end, limit)

# initial small load for chart (last N rows)
initial_df = _query_db(best_table, limit=2000)
# canonicalize columns as before (lowercase/date parsing/open/high/low/close) ...
df_prices = initial_df  # use only this small slice for startup

# --------------------------------------
# LAYOUT
# --------------------------------------
app.layout = html.Div(
    style={'font-family': 'Arial', 'margin': '20px'},
    children=[
        html.H1("Gold Market Dashboard", style={'text-align': 'center'}),

        html.Div(
            style={'display': 'flex', 'justifyContent': 'center', 'gap': '16px', 'marginBottom': '12px'},
            children=[
                html.Div([
                    html.Label("Visible date range"),
                    dcc.DatePickerRange(
                        id='date-range',
                        min_date_allowed=earliest,
                        max_date_allowed=latest,
                        start_date=default_start,
                        end_date=default_end,
                        display_format='YYYY-MM-DD'
                    )
                ]),
                html.Div([
                    html.Label("Points (max)"),
                    dcc.Slider(
                        id='max-points-slider',
                        min=200, max=4000, step=100, value=max_points,
                        marks={200: '200', 1000: '1000', 2000: '2000'}
                    )
                ], style={'width': '320px', 'paddingTop': '18px'})
            ]
        ),

        dcc.Loading(
            id='loading-graph',
            type='default',
            children=dcc.Graph(id='gold_chart', config={'displayModeBar': True})
        ),

        # small store for initial slice (keeps startup fast)
        dcc.Store(
            id='df_prices_store',
            data=df_prices.assign(date=df_prices['date'].dt.strftime('%Y-%m-%d %H:%M:%S')).to_dict('records')
        )
    ]
)

# ---------- New: indicator detection helpers ----------
def detect_swings(df, left=2, right=2):
    """Return list of swings: dicts with idx, date, value, type ('high'|'low')."""
    swings = []
    n = len(df)
    for i in range(left, n - right):
        window = df['high'].iloc[i - left:i + right + 1]
        if df['high'].iat[i] == window.max():
            swings.append({'idx': i, 'date': df['date'].iat[i], 'value': df['high'].iat[i], 'type': 'high'})
        windowl = df['low'].iloc[i - left:i + right + 1]
        if df['low'].iat[i] == windowl.min():
            swings.append({'idx': i, 'date': df['date'].iat[i], 'value': df['low'].iat[i], 'type': 'low'})
    # sort by idx
    swings.sort(key=lambda s: s['idx'])
    return swings

def detect_bos_choch(swings):
    """
    Simple BOS/CHoCH detection:
    - Bullish BOS: a swing high > previous swing high.
    - Bearish BOS: a swing low < previous swing low.
    - CHoCH when direction flips (bull -> bear or bear -> bull).
    Returns list of events with type 'BOS'/'CHoCH' and side 'bull'/'bear'.
    """
    events = []
    last_high = None
    last_low = None
    last_dir = None
    for s in swings:
        if s['type'] == 'high':
            if last_high is None or s['value'] > last_high:
                # bullish BOS (for highs)
                events.append({'type': 'BOS', 'side': 'bull', 'idx': s['idx'], 'date': s['date'], 'value': s['value']})
                last_dir = 'bull'
            last_high = s['value'] if (last_high is None or s['value'] > last_high) else last_high
        elif s['type'] == 'low':
            if last_low is None or s['value'] < last_low:
                # bearish BOS (for lows)
                events.append({'type': 'BOS', 'side': 'bear', 'idx': s['idx'], 'date': s['date'], 'value': s['value']})
                last_dir = 'bear'
            last_low = s['value'] if (last_low is None or s['value'] < last_low) else last_low
        # detect CHoCH when direction flips compared to previous BOS
        if len(events) >= 2:
            if events[-1]['side'] != events[-2]['side']:
                events.append({'type': 'CHoCH', 'side': events[-1]['side'], 'idx': events[-1]['idx'], 'date': events[-1]['date'], 'value': events[-1]['value']})
    return events

def detect_fvg(df):
    """
    Simple 3-candle FVG detection:
    If candle i high < candle i+2 low -> bullish FVG between high_i and low_i+2
    If candle i low > candle i+2 high -> bearish FVG between low_i and high_i+2
    Returns list of dicts with left_dt,right_dt,top,bottom,side.
    """
    fgvs = []
    for i in range(len(df) - 2):
        c1 = df.iloc[i]
        c3 = df.iloc[i + 2]
        # bullish gap (upward imbalance)
        if c1['high'] < c3['low']:
            fgvs.append({
                'side': 'bull',
                'left': c1['date'],
                'right': c3['date'],
                'top': c3['low'],
                'bottom': c1['high']
            })
        # bearish gap (downward imbalance)
        if c1['low'] > c3['high']:
            fgvs.append({
                'side': 'bear',
                'left': c1['date'],
                'right': c3['date'],
                'top': c1['low'],
                'bottom': c3['high']
            })
    return fgvs

def quarterly_lines(start_date, end_date):
    """Return list of quarter start datetimes between start_date and end_date."""
    lines = []
    s = pd.to_datetime(start_date).replace(day=1)
    # set to first day of that quarter
    q = ((s.month - 1) // 3) * 3 + 1
    s = s.replace(month=q, day=1)
    while s <= pd.to_datetime(end_date):
        lines.append(s)
        s = (s + pd.DateOffset(months=3)).replace(day=1)
    return lines

# --------------------------------------
# CALLBACK to load windowed data + downsample
# --------------------------------------
@app.callback(
    Output('gold_chart', 'figure'),
    Input('date-range', 'start_date'),
    Input('date-range', 'end_date'),
    Input('max-points-slider', 'value'),
    Input('gold_chart', 'relayoutData')  # capture user zoom/pan
)
def update_chart(start_date, end_date, max_points_value, relayout):
    # debug prints to console
    print("update_chart called", {"start_date": start_date, "end_date": end_date, "max_points": max_points_value, "relayout": bool(relayout)})

    # determine requested x-range: prefer relayout zoom if present
    start_iso = None
    end_iso = None
    if relayout and isinstance(relayout, dict):
        xr0 = relayout.get('xaxis.range[0]') or (relayout.get('xaxis.range') and relayout.get('xaxis.range')[0])
        xr1 = relayout.get('xaxis.range[1]') or (relayout.get('xaxis.range') and relayout.get('xaxis.range')[1])
        if xr0 and xr1:
            start_iso = pd.to_datetime(xr0).strftime('%Y-%m-%d %H:%M:%S')
            end_iso = pd.to_datetime(xr1).strftime('%Y-%m-%d %H:%M:%S')

    if start_iso is None:
        if start_date is None:
            start_date = default_start.isoformat()
        start_iso = pd.to_datetime(start_date).strftime('%Y-%m-%d %H:%M:%S')
    if end_iso is None:
        if end_date is None:
            end_date = default_end.isoformat()
        end_iso = pd.to_datetime(end_date).strftime('%Y-%m-%d %H:%M:%S')

    print("Querying DB for range:", start_iso, "->", end_iso)
    df = get_data_cached(best_table, start_iso, end_iso, None)

    # debug info
    if df is None:
        print("get_data_cached returned None")
    else:
        print("Fetched rows:", len(df))
        print("DTypes:", df.dtypes.to_dict())
        print("Head:\n", df.head(5).to_string(index=False))

    if df is None or df.empty:
        # return friendly message on chart instead of blank
        return {
            'data': [],
            'layout': go.Layout(
                title=f"No data for {start_iso} → {end_iso}",
                annotations=[{
                    'text': "No data in selected range — try expanding the date range or pick another timeframe.",
                    'xref': 'paper', 'yref': 'paper',
                    'x': 0.5, 'y': 0.5, 'showarrow': False,
                    'font': {'size': 14}
                }],
                template='plotly_dark',
                height=700
            )
        }

    # ensure date column is datetime
    try:
        df['date'] = pd.to_datetime(df['date'])
    except Exception as e:
        print("Failed to parse df['date'] to datetime:", e)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')

    # downsample
    ds = downsample_ohlc(df, max_points=int(max_points_value))

    # ensure downsample date dtype
    try:
        ds['date'] = pd.to_datetime(ds['date'])
    except Exception:
        pass

    # compute y-range
    try:
        y_min = float(ds['low'].min())
        y_max = float(ds['high'].max())
        margin = max((y_max - y_min) * 0.02, 0.0001 * abs(y_max)) if y_max > y_min else max(0.5, 0.01 * abs(y_max))
        y_range = [y_min - margin, y_max + margin]
        yaxis_props = dict(range=y_range, autorange=False)
    except Exception:
        yaxis_props = dict(autorange=True)

    fig = {
        'data': [
            go.Candlestick(
                x=ds['date'],
                open=ds['open'],
                high=ds['high'],
                low=ds['low'],
                close=ds['close'],
                name=best_table
            )
        ],
        'layout': go.Layout(
            title=f"Gold — {best_table} ({start_iso} → {end_iso})",
            xaxis=dict(type='date', rangeslider=dict(visible=False)),
            yaxis=yaxis_props,
            template='plotly_dark',
            height=700
        )
    }

    # keep existing structural overlays (FVG/BOS/CHoCH/quarters) but guard for errors
    try:
        raw_df = df
        swings = detect_swings(raw_df, left=2, right=2)
        events = detect_bos_choch(swings)
        fgvs = detect_fvg(raw_df)

        shapes = []
        annotations = []
        for f in fgvs:
            color = 'rgba(0,200,0,0.18)' if f['side'] == 'bull' else 'rgba(200,0,0,0.18)'
            shapes.append({'type': 'rect','xref': 'x','yref': 'y','x0': f['left'],'x1': f['right'],'y0': f['bottom'],'y1': f['top'],'fillcolor': color,'line': {'width': 0},'layer': 'below'})
        for e in events:
            col = 'lime' if e['side'] == 'bull' else 'red'
            txt = e['type']
            annotations.append({'x': e['date'],'y': e['value'],'xref': 'x','yref': 'y','text': txt,'showarrow': True,'arrowhead': 2,'ax': 0,'ay': -30 if e['side']=='bull' else 30,'font': {'color': col, 'size': 10},'arrowcolor': col})
        q_lines = quarterly_lines(start_iso, end_iso)
        for qd in q_lines:
            shapes.append({'type': 'line','xref': 'x','x0': qd,'x1': qd,'yref': 'paper','y0': 0,'y1': 1,'line': {'color': 'rgba(200,200,200,0.12)', 'width': 1, 'dash': 'dash'},'layer': 'above'})
            annotations.append({'x': qd,'y': 1.02,'xref': 'x','yref': 'paper','text': f"Q{((qd.month-1)//3)+1} {qd.year}",'showarrow': False,'font': {'size': 9, 'color': 'rgba(200,200,200,0.8)'}})
        fig['layout']['shapes'] = fig['layout'].get('shapes', []) + shapes
        fig['layout']['annotations'] = fig['layout'].get('annotations', []) + annotations
    except Exception as ex:
        print("Overlay generation failed:", ex)

    return fig

# --------------------------------------
# RUN SERVER (unchanged)
# --------------------------------------
if __name__ == "__main__":
    app.run(debug=True)