
from fastapi import APIRouter, Request, Form

from fastapi.responses import HTMLResponse, RedirectResponse

from exchange.database import db

from exchange.utility import settings

from exchange import get_bot

from datetime import datetime



router = APIRouter(prefix="/dashboard", tags=["dashboard"])



def check_auth(request: Request):

    return request.cookies.get("dashboard_auth") == settings.PASSWORD



def get_login_page():

    return """<!DOCTYPE html>

<html>

<head>

    <meta charset="UTF-8">

    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>POA Dashboard Login</title>

    <style>

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body { font-family: -apple-system, sans-serif; background: #0f0f0f; color: #e0e0e0; display: flex; justify-content: center; align-items: center; height: 100vh; }

        .login-box { background: #1a1a1a; padding: 40px; border-radius: 10px; width: 300px; }

        h2 { margin-bottom: 20px; text-align: center; }

        input { width: 100%; padding: 12px; margin-bottom: 15px; border: 1px solid #333; border-radius: 5px; background: #252525; color: #fff; }

        button { width: 100%; padding: 12px; background: #4dabf7; border: none; border-radius: 5px; color: #fff; cursor: pointer; font-size: 16px; }

        button:hover { background: #339af0; }

    </style>

</head>

<body>

    <div class="login-box">

        <h2>🔐 POA Dashboard</h2>

        <form method="post" action="/dashboard/login">

            <input type="password" name="password" placeholder="비밀번호" required>

            <button type="submit">로그인</button>

        </form>

    </div>

</body>

</html>"""



def calculate_mdd(trades):

    if not trades:

        return 0

    cumulative = 0

    peak = 0

    mdd = 0

    for t in reversed(list(trades)):

        pnl = t['pnl'] or 0

        cumulative += pnl

        if cumulative > peak:

            peak = cumulative

        drawdown = peak - cumulative

        if drawdown > mdd:

            mdd = drawdown

    return round(mdd, 2)



def get_equity_curve(trades):

    if not trades:

        return []

    curve = []

    cumulative = 0

    for t in reversed(list(trades)):

        pnl = t['pnl'] or 0

        cumulative += pnl

        curve.append({

            'date': t['created_at'][:10],

            'pnl': round(cumulative, 2)

        })

    return curve



def get_exchange_positions():

    try:

        bot = get_bot("BITGET")

        positions = bot.client.fetch_positions()

        active = []

        for p in positions:

            if float(p['contracts']) > 0:

                active.append({

                    'symbol': p['symbol'],

                    'side': 'buy' if p['side'] == 'long' else 'sell',

                    'amount': float(p['contracts']),

                    'entry_price': float(p['entryPrice']) if p['entryPrice'] else 0,

                    'unrealized_pnl': float(p['unrealizedPnl']) if p['unrealizedPnl'] else 0,

                    'leverage': int(p['leverage']) if p['leverage'] else 1

                })

        return active

    except Exception as e:

        return []



def check_position_sync():

    db_positions = db.get_active_positions()

    exchange_positions = get_exchange_positions()

    

    db_symbols = {p['symbol'] for p in db_positions} if db_positions else set()

    ex_symbols = {p['symbol'] for p in exchange_positions}

    

    issues = []

    

    for p in exchange_positions:

        if p['symbol'] not in db_symbols:

            issues.append({

                'type': 'missing_in_db',

                'symbol': p['symbol'],

                'message': f"거래소에 {p['symbol']} 포지션 있으나 DB에 없음"

            })

    

    if db_positions:

        for p in db_positions:

            if p['symbol'] not in ex_symbols:

                issues.append({

                    'type': 'missing_in_exchange',

                    'symbol': p['symbol'],

                    'message': f"DB에 {p['symbol']} 포지션 있으나 거래소에 없음"

                })

    

    return issues, exchange_positions



@router.get("/", response_class=HTMLResponse)

async def dashboard_home(request: Request):

    if not check_auth(request):

        return HTMLResponse(content=get_login_page())

    

    stats = db.get_strategy_stats()

    positions = db.get_active_positions()

    trades = db.get_all_trades(limit=100)

    

    sync_issues, exchange_positions = check_position_sync()

    

    total_pnl = sum(s['total_pnl'] or 0 for s in stats) if stats else 0

    total_trades = sum(s['total_trades'] or 0 for s in stats) if stats else 0

    total_wins = sum(s['wins'] or 0 for s in stats) if stats else 0

    win_rate = round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0

    mdd = calculate_mdd(trades)

    

    equity_curve = get_equity_curve(trades)

    chart_labels = [p['date'] for p in equity_curve]

    chart_data = [p['pnl'] for p in equity_curve]

    

    sync_alert = ""

    if sync_issues:

        issue_list = "".join([f"<li style='color:#fa5252'>{i['message']}</li>" for i in sync_issues])

        sync_alert = f"""

        <div class="section">

            <h2 class="section-title">⚠️ 포지션 불일치 감지</h2>

            <div class="card" style="border: 1px solid #fa5252;">

                <ul style="list-style: none;">{issue_list}</ul>

            </div>

        </div>"""

    

    exchange_position_rows = ""

    if exchange_positions:

        total_unrealized = sum(p['unrealized_pnl'] for p in exchange_positions)

        for p in exchange_positions:

            side_text = "롱" if p['side'] == 'buy' else "숏"

            pnl_color = "#40c057" if p['unrealized_pnl'] >= 0 else "#fa5252"

            exchange_position_rows += f"<tr><td>{p['symbol']}</td><td>{side_text}</td><td>{p['amount']}</td><td>{p['entry_price']}</td><td>{p['leverage']}x</td><td style='color:{pnl_color}'>{p['unrealized_pnl']:.2f}</td></tr>"

    else:

        exchange_position_rows = '<tr><td colspan="6" style="text-align:center">열린 포지션 없음</td></tr>'

        total_unrealized = 0

    

    strategy_cards = ""

    if stats:

        for s in stats:

            wr = round(s['wins'] / s['total_trades'] * 100, 1) if s['total_trades'] > 0 else 0

            pnl_color = "#40c057" if (s['total_pnl'] or 0) >= 0 else "#fa5252"

            strategy_trades = db.get_all_trades(strategy=s['strategy'], limit=100)

            s_mdd = calculate_mdd(strategy_trades)

            strategy_cards += f"""

            <div class="card">

                <h3>{s['strategy']}</h3>

                <div class="stat-row"><span>총 거래</span><span>{s['total_trades']}회</span></div>

                <div class="stat-row"><span>승률</span><span>{wr}% ({s['wins']}W / {s['losses']}L)</span></div>

                <div class="stat-row"><span>총 손익</span><span style="color: {pnl_color}">{s['total_pnl'] or 0:.2f} USDT</span></div>

                <div class="stat-row"><span>평균 수익률</span><span>{s['avg_pnl_percent'] or 0:.2f}%</span></div>

                <div class="stat-row"><span>MDD</span><span style="color: #fa5252">{s_mdd:.2f} USDT</span></div>

            </div>"""

    else:

        strategy_cards = '<div class="card"><p>아직 거래 기록이 없습니다.</p></div>'

    

    position_rows = ""

    if positions:

        for p in positions:

            side_text = "롱" if p['side'] == 'buy' else "숏"

            position_rows += f"<tr><td>{p['strategy']}</td><td>{p['symbol']}</td><td>{side_text}</td><td>{p['amount']}</td><td>{p['entry_price']}</td><td>{p['leverage']}x</td></tr>"

    else:

        position_rows = '<tr><td colspan="6" style="text-align:center">열린 포지션 없음</td></tr>'

    

    trade_rows = ""

    if trades:

        for t in list(trades)[:20]:

            pnl_color = "#40c057" if (t['pnl'] or 0) >= 0 else "#fa5252"

            try:

                entry_p = t['entry_price'] if 'entry_price' in t.keys() and t['entry_price'] else '-'

            except:

                entry_p = '-'

            try:

                exit_p = t['price'] if t['price'] else '-'

            except:

                exit_p = '-'

            try:

                fee = t['fee'] if 'fee' in t.keys() and t['fee'] else 0

            except:

                fee = 0

            try:

                holding = t['holding_seconds'] if 'holding_seconds' in t.keys() and t['holding_seconds'] else 0

            except:

                holding = 0

            h_hours = holding // 3600

            h_mins = (holding % 3600) // 60

            h_str = f"{h_hours}h {h_mins}m" if h_hours > 0 else f"{h_mins}m"

            trade_rows += f"<tr><td>{t['strategy']}</td><td>{t['symbol']}</td><td>{t['side']}</td><td>{entry_p}</td><td>{exit_p}</td><td style='color:{pnl_color}'>{t['pnl'] or 0:.2f}</td><td style='color:{pnl_color}'>{t['pnl_percent'] or 0:.2f}%</td><td>{fee:.4f}</td><td>{h_str}</td><td>{t['created_at'][:16]}</td></tr>"

    else:

        trade_rows = '<tr><td colspan="6" style="text-align:center">거래 내역 없음</td></tr>'

    

    chart_section = ""

    if equity_curve:

        chart_section = f"""

    <div class="section">

        <h2 class="section-title">📈 누적 손익 차트</h2>

        <div class="card" style="padding: 20px;">

            <canvas id="equityChart" height="100"></canvas>

        </div>

    </div>

    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

    <script>

        const ctx = document.getElementById('equityChart').getContext('2d');

        new Chart(ctx, {{

            type: 'line',

            data: {{

                labels: {chart_labels},

                datasets: [{{

                    label: '누적 손익 (USDT)',

                    data: {chart_data},

                    borderColor: {chart_data[-1] if chart_data else 0} >= 0 ? '#40c057' : '#fa5252',

                    backgroundColor: 'rgba(64, 192, 87, 0.1)',

                    fill: true,

                    tension: 0.3

                }}]

            }},

            options: {{

                responsive: true,

                plugins: {{

                    legend: {{ display: false }}

                }},

                scales: {{

                    x: {{ grid: {{ color: '#333' }}, ticks: {{ color: '#888' }} }},

                    y: {{ grid: {{ color: '#333' }}, ticks: {{ color: '#888' }} }}

                }}

            }}

        }});

    </script>"""

    

    html = f"""<!DOCTYPE html>

<html>

<head>

    <meta charset="UTF-8">

    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>POA Dashboard</title>

    <style>

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{ font-family: -apple-system, sans-serif; background: #0f0f0f; color: #e0e0e0; padding: 20px; }}

        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px solid #333; }}

        h1 {{ color: #fff; font-size: 24px; }}

        .logout {{ color: #888; text-decoration: none; font-size: 14px; }}

        .logout:hover {{ color: #fff; }}

        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 15px; margin-bottom: 30px; }}

        .summary-card {{ background: #1a1a1a; padding: 20px; border-radius: 10px; text-align: center; }}

        .summary-card .value {{ font-size: 24px; font-weight: bold; margin-bottom: 5px; }}

        .summary-card .label {{ color: #888; font-size: 12px; }}

        .section {{ margin-bottom: 30px; }}

        .section-title {{ font-size: 18px; margin-bottom: 15px; color: #fff; }}

        .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 15px; }}

        .card {{ background: #1a1a1a; padding: 20px; border-radius: 10px; }}

        .card h3 {{ margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid #333; color: #4dabf7; }}

        .stat-row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #222; }}

        table {{ width: 100%; border-collapse: collapse; background: #1a1a1a; border-radius: 10px; overflow: hidden; }}

        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #333; }}

        th {{ background: #252525; color: #888; }}

    </style>

</head>

<body>

    <div class="header">

        <h1>📊 POA Dashboard</h1></div><div class="nav"><a href="/dashboard/report" style="color:#4dabf7;text-decoration:none;margin-right:20px;">📈 리포트</a>

        <div><span style="color:#888; margin-right:20px">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span><a href="/dashboard/logout" class="logout">로그아웃</a></div>

    </div>

    <div class="summary">

        <div class="summary-card"><div class="value" style="color:{'#40c057' if total_pnl >= 0 else '#fa5252'}">{total_pnl:.2f}</div><div class="label">총 손익 (USDT)</div></div>

        <div class="summary-card"><div class="value">{total_trades}</div><div class="label">총 거래 수</div></div>

        <div class="summary-card"><div class="value">{win_rate}%</div><div class="label">승률</div></div>

        <div class="summary-card"><div class="value" style="color:#fa5252">{mdd:.2f}</div><div class="label">MDD (USDT)</div></div>

        <div class="summary-card"><div class="value" style="color:{'#40c057' if total_unrealized >= 0 else '#fa5252'}">{total_unrealized:.2f}</div><div class="label">미실현 손익</div></div>

    </div>

    {sync_alert}

    {chart_section}

    <div class="section"><h2 class="section-title">💹 거래소 실시간 포지션</h2>

        <table><thead><tr><th>심볼</th><th>방향</th><th>수량</th><th>진입가</th><th>레버리지</th><th>미실현 손익</th></tr></thead><tbody>{exchange_position_rows}</tbody></table>

    </div>

    <div class="section"><h2 class="section-title">📊 전략별 성과</h2><div class="cards">{strategy_cards}</div></div>

    <div class="section"><h2 class="section-title">🔓 DB 포지션</h2>

        <table><thead><tr><th>전략</th><th>심볼</th><th>방향</th><th>수량</th><th>진입가</th><th>레버리지</th></tr></thead><tbody>{position_rows}</tbody></table>

    </div>

    <div class="section"><h2 class="section-title">📋 최근 거래</h2>

        <table><thead><tr><th>전략</th><th>심볼</th><th>방향</th><th>진입가</th><th>종료가</th><th>손익</th><th>수익률</th><th>수수료</th><th>보유</th><th>시간</th></tr></thead><tbody>{trade_rows}</tbody></table>

    </div>

    <script>setTimeout(() => location.reload(), 30000);</script>

</body>

</html>"""

    return HTMLResponse(content=html)



@router.post("/login")

async def login(password: str = Form(...)):

    if password == settings.PASSWORD:

        response = RedirectResponse(url="/dashboard/", status_code=302)

        response.set_cookie(key="dashboard_auth", value=settings.PASSWORD, httponly=True, max_age=86400)

        return response

    return HTMLResponse(content=get_login_page() + "<script>alert('비밀번호가 틀렸습니다.')</script>")



@router.get("/logout")

async def logout():

    response = RedirectResponse(url="/dashboard/", status_code=302)

    response.delete_cookie(key="dashboard_auth")

    return response



@router.get("/api/stats")

async def get_stats(request: Request):

    if not check_auth(request):

        return {"error": "unauthorized"}

    stats = db.get_strategy_stats()

    return {"stats": [dict(s) for s in stats] if stats else []}



@router.get("/api/positions")

async def get_positions(request: Request):

    if not check_auth(request):

        return {"error": "unauthorized"}

    positions = db.get_active_positions()

    return {"positions": [dict(p) for p in positions] if positions else []}



@router.get("/api/exchange-positions")

async def get_exchange_pos(request: Request):

    if not check_auth(request):

        return {"error": "unauthorized"}

    return {"positions": get_exchange_positions()}



@router.get("/api/trades")

async def get_trades(request: Request, limit: int = 100):

    if not check_auth(request):

        return {"error": "unauthorized"}

    trades = db.get_all_trades(limit=limit)

    return {"trades": [dict(t) for t in trades] if trades else []}




@router.get("/api/recovery-status")

async def get_recovery_status(request: Request):

    if not check_auth(request):

        return {"error": "unauthorized"}

    from exchange.recovery_engine import recovery_engine

    return recovery_engine.get_status()



@router.post("/api/recovery-check")

async def trigger_recovery_check(request: Request):

    if not check_auth(request):

        return {"error": "unauthorized"}

    from exchange.recovery_engine import recovery_engine

    recovery_engine.check_and_recover()

    return {"result": "checked", "issues": recovery_engine.issues_found}




@router.get("/report", response_class=HTMLResponse)

async def report_page(request: Request):

    if not check_auth(request):

        return HTMLResponse(content=get_login_page())

    

    from datetime import datetime, timedelta

    

    # 기간 계산

    today = datetime.now().strftime('%Y-%m-%d')

    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    

    # 기간별 통계

    today_stats = db.get_stats_by_period(today + ' 00:00:00', today + ' 23:59:59')

    week_stats = db.get_stats_by_period(week_ago + ' 00:00:00', today + ' 23:59:59')

    month_stats = db.get_stats_by_period(month_ago + ' 00:00:00', today + ' 23:59:59')

    all_stats = db.get_strategy_stats()

    

    # 종목별 통계

    symbol_stats = db.get_stats_by_symbol()

    

    # 일별 손익

    daily_pnl = db.get_daily_pnl(30)

    

    def format_stats(s):

        if not s:

            return {'trades': 0, 'wins': 0, 'losses': 0, 'pnl': 0, 'win_rate': 0, 'avg_pnl': 0}

        trades = s['total_trades'] or 0

        wins = s['wins'] or 0

        return {

            'trades': trades,

            'wins': wins,

            'losses': s['losses'] or 0,

            'pnl': s['total_pnl'] or 0,

            'win_rate': round(wins / trades * 100, 1) if trades > 0 else 0,

            'avg_pnl': s['avg_pnl_percent'] or 0

        }

    

    today_s = format_stats(today_stats)

    week_s = format_stats(week_stats)

    month_s = format_stats(month_stats)

    

    # 전체 통계

    total_pnl = sum(s['total_pnl'] or 0 for s in all_stats) if all_stats else 0

    total_trades = sum(s['total_trades'] or 0 for s in all_stats) if all_stats else 0

    total_wins = sum(s['wins'] or 0 for s in all_stats) if all_stats else 0

    all_s = {

        'trades': total_trades,

        'wins': total_wins,

        'losses': total_trades - total_wins,

        'pnl': round(total_pnl, 2),

        'win_rate': round(total_wins / total_trades * 100, 1) if total_trades > 0 else 0,

        'avg_pnl': 0

    }

    

    # 종목별 테이블

    symbol_rows = ""

    if symbol_stats:

        for s in symbol_stats:

            wr = round(s['wins'] / s['total_trades'] * 100, 1) if s['total_trades'] > 0 else 0

            pnl_color = "#40c057" if (s['total_pnl'] or 0) >= 0 else "#fa5252"

            symbol_rows += f"<tr><td>{s['symbol']}</td><td>{s['total_trades']}</td><td>{wr}%</td><td style='color:{pnl_color}'>{s['total_pnl'] or 0:.2f}</td><td>{s['avg_pnl_percent'] or 0:.2f}%</td></tr>"

    else:

        symbol_rows = '<tr><td colspan="5" style="text-align:center">거래 내역 없음</td></tr>'

    

    # 일별 차트 데이터

    chart_labels = [d['date'] for d in daily_pnl] if daily_pnl else []

    chart_data = [d['daily_pnl'] for d in daily_pnl] if daily_pnl else []

    

    # 누적 계산

    cumulative = []

    total = 0

    for d in chart_data:

        total += d

        cumulative.append(round(total, 2))

    

    html = f"""<!DOCTYPE html>

<html>

<head>

    <meta charset="UTF-8">

    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <title>POA Report</title>

    <style>

        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

        body {{ font-family: -apple-system, sans-serif; background: #0f0f0f; color: #e0e0e0; padding: 20px; }}

        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px solid #333; }}

        h1 {{ color: #fff; font-size: 24px; }}

        .nav {{ display: flex; gap: 15px; }}

        .nav a {{ color: #4dabf7; text-decoration: none; }}

        .nav a:hover {{ color: #fff; }}

        .section {{ margin-bottom: 30px; }}

        .section-title {{ font-size: 18px; margin-bottom: 15px; color: #fff; }}

        .period-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 30px; }}

        .period-card {{ background: #1a1a1a; padding: 20px; border-radius: 10px; }}

        .period-card h3 {{ color: #4dabf7; margin-bottom: 15px; font-size: 14px; }}

        .period-card .pnl {{ font-size: 28px; font-weight: bold; margin-bottom: 10px; }}

        .period-card .details {{ color: #888; font-size: 12px; }}

        .period-card .details span {{ display: block; margin: 5px 0; }}

        table {{ width: 100%; border-collapse: collapse; background: #1a1a1a; border-radius: 10px; overflow: hidden; }}

        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #333; }}

        th {{ background: #252525; color: #888; }}

        .card {{ background: #1a1a1a; padding: 20px; border-radius: 10px; }}

    </style>

</head>

<body>

    <div class="header">

        <h1>📊 성과 리포트</h1>

        <div class="nav">

            <a href="/dashboard/">← 대시보드</a>

            <span style="color:#888">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</span>

        </div>

    </div>

    

    <div class="section">

        <h2 class="section-title">📅 기간별 성과</h2>

        <div class="period-grid">

            <div class="period-card">

                <h3>오늘</h3>

                <div class="pnl" style="color:{'#40c057' if today_s['pnl'] >= 0 else '#fa5252'}">{today_s['pnl']:.2f} USDT</div>

                <div class="details">

                    <span>거래: {today_s['trades']}회</span>

                    <span>승률: {today_s['win_rate']}% ({today_s['wins']}W / {today_s['losses']}L)</span>

                </div>

            </div>

            <div class="period-card">

                <h3>이번 주 (7일)</h3>

                <div class="pnl" style="color:{'#40c057' if week_s['pnl'] >= 0 else '#fa5252'}">{week_s['pnl']:.2f} USDT</div>

                <div class="details">

                    <span>거래: {week_s['trades']}회</span>

                    <span>승률: {week_s['win_rate']}% ({week_s['wins']}W / {week_s['losses']}L)</span>

                </div>

            </div>

            <div class="period-card">

                <h3>이번 달 (30일)</h3>

                <div class="pnl" style="color:{'#40c057' if month_s['pnl'] >= 0 else '#fa5252'}">{month_s['pnl']:.2f} USDT</div>

                <div class="details">

                    <span>거래: {month_s['trades']}회</span>

                    <span>승률: {month_s['win_rate']}% ({month_s['wins']}W / {month_s['losses']}L)</span>

                </div>

            </div>

            <div class="period-card">

                <h3>전체</h3>

                <div class="pnl" style="color:{'#40c057' if all_s['pnl'] >= 0 else '#fa5252'}">{all_s['pnl']:.2f} USDT</div>

                <div class="details">

                    <span>거래: {all_s['trades']}회</span>

                    <span>승률: {all_s['win_rate']}% ({all_s['wins']}W / {all_s['losses']}L)</span>

                </div>

            </div>

        </div>

    </div>

    

    <div class="section">

        <h2 class="section-title">📈 일별 손익 추이 (30일)</h2>

        <div class="card" style="padding: 20px;">

            <canvas id="dailyChart" height="100"></canvas>

        </div>

    </div>

    

    <div class="section">

        <h2 class="section-title">💰 종목별 성과</h2>

        <table>

            <thead>

                <tr><th>종목</th><th>거래 수</th><th>승률</th><th>총 손익</th><th>평균 수익률</th></tr>

            </thead>

            <tbody>{symbol_rows}</tbody>

        </table>

    </div>

    

    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

    <script>

        const ctx = document.getElementById('dailyChart').getContext('2d');

        new Chart(ctx, {{

            type: 'bar',

            data: {{

                labels: {chart_labels},

                datasets: [

                    {{

                        label: '일별 손익',

                        data: {chart_data},

                        backgroundColor: {chart_data}.map(v => v >= 0 ? 'rgba(64, 192, 87, 0.8)' : 'rgba(250, 82, 82, 0.8)'),

                        yAxisID: 'y'

                    }},

                    {{

                        label: '누적 손익',

                        data: {cumulative},

                        type: 'line',

                        borderColor: '#4dabf7',

                        backgroundColor: 'transparent',

                        yAxisID: 'y1'

                    }}

                ]

            }},

            options: {{

                responsive: true,

                scales: {{

                    x: {{ grid: {{ color: '#333' }}, ticks: {{ color: '#888' }} }},

                    y: {{ position: 'left', grid: {{ color: '#333' }}, ticks: {{ color: '#888' }} }},

                    y1: {{ position: 'right', grid: {{ display: false }}, ticks: {{ color: '#4dabf7' }} }}

                }}

            }}

        }});

    </script>

</body>

</html>"""

    return HTMLResponse(content=html)

