
from fastapi import APIRouter, Request, Query

from fastapi.responses import HTMLResponse

from exchange.database import db

from exchange.utility import settings

from datetime import datetime, timedelta



router = APIRouter(prefix="/dashboard", tags=["report"])



def check_auth(request: Request):

    return request.cookies.get("dashboard_auth") == settings.PASSWORD



def get_login_page():

    return """<!DOCTYPE html>

<html>

<head>

    <meta charset="UTF-8">

    <title>Login</title>

    <style>

        body { font-family: -apple-system, sans-serif; background: #0f0f0f; color: #e0e0e0; display: flex; justify-content: center; align-items: center; height: 100vh; }

        .login-box { background: #1a1a1a; padding: 40px; border-radius: 10px; width: 300px; }

        input { width: 100%; padding: 12px; margin-bottom: 15px; border: 1px solid #333; border-radius: 5px; background: #252525; color: #fff; }

        button { width: 100%; padding: 12px; background: #4dabf7; border: none; border-radius: 5px; color: #fff; cursor: pointer; }

    </style>

</head>

<body>

    <div class="login-box">

        <h2 style="text-align:center;margin-bottom:20px">🔐 Login</h2>

        <form method="post" action="/dashboard/login">

            <input type="password" name="password" placeholder="비밀번호" required>

            <button type="submit">로그인</button>

        </form>

    </div>

</body>

</html>"""



@router.get("/report", response_class=HTMLResponse)

async def report_page(

    request: Request,

    start: str = None,

    end: str = None

):

    if not check_auth(request):

        return HTMLResponse(content=get_login_page())

    

    today = datetime.now().strftime('%Y-%m-%d')

    

    # 기본값: 최근 30일

    if not start:

        start = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    if not end:

        end = today

    

    # 프리셋 기간 계산

    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    year_ago = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    

    # 선택 기간 통계

    period_stats = db.get_stats_by_period(start + ' 00:00:00', end + ' 23:59:59')

    

    # 기간별 프리셋 통계

    today_stats = db.get_stats_by_period(today + ' 00:00:00', today + ' 23:59:59')

    week_stats = db.get_stats_by_period(week_ago + ' 00:00:00', today + ' 23:59:59')

    month_stats = db.get_stats_by_period(month_ago + ' 00:00:00', today + ' 23:59:59')

    

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

    

    period_s = format_stats(period_stats)

    today_s = format_stats(today_stats)

    week_s = format_stats(week_stats)

    month_s = format_stats(month_stats)

    

    # 종목별 테이블

    symbol_rows = ""

    if symbol_stats:

        for s in symbol_stats:

            wr = round(s['wins'] / s['total_trades'] * 100, 1) if s['total_trades'] > 0 else 0

            pnl_color = "#40c057" if (s['total_pnl'] or 0) >= 0 else "#fa5252"

            symbol_rows += f"<tr><td>{s['symbol']}</td><td>{s['total_trades']}</td><td>{wr}%</td><td style='color:{pnl_color}'>{s['total_pnl'] or 0:.2f}</td><td>{s['avg_pnl_percent'] or 0:.2f}%</td></tr>"

    else:

        symbol_rows = '<tr><td colspan="5" style="text-align:center">거래 내역 없음</td></tr>'

    

    # 차트 데이터

    chart_labels = [d['date'] for d in daily_pnl] if daily_pnl else []

    chart_data = [d['daily_pnl'] for d in daily_pnl] if daily_pnl else []

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

        .nav a {{ color: #4dabf7; text-decoration: none; margin-right: 15px; }}

        .section {{ margin-bottom: 30px; }}

        .section-title {{ font-size: 18px; margin-bottom: 15px; color: #fff; }}

        .date-picker {{ background: #1a1a1a; padding: 20px; border-radius: 10px; margin-bottom: 20px; display: flex; gap: 15px; align-items: center; flex-wrap: wrap; }}

        .date-picker input {{ padding: 10px; border: 1px solid #333; border-radius: 5px; background: #252525; color: #fff; }}

        .date-picker button {{ padding: 10px 20px; background: #4dabf7; border: none; border-radius: 5px; color: #fff; cursor: pointer; }}

        .date-picker button:hover {{ background: #339af0; }}

        .presets {{ display: flex; gap: 10px; }}

        .presets a {{ padding: 8px 15px; background: #252525; border-radius: 5px; color: #888; text-decoration: none; font-size: 12px; }}

        .presets a:hover, .presets a.active {{ background: #4dabf7; color: #fff; }}

        .result-card {{ background: #1a1a1a; padding: 25px; border-radius: 10px; margin-bottom: 20px; border: 2px solid #4dabf7; }}

        .result-card h3 {{ color: #4dabf7; margin-bottom: 15px; }}

        .result-card .pnl {{ font-size: 36px; font-weight: bold; margin-bottom: 10px; }}

        .result-card .details {{ display: flex; gap: 30px; color: #888; }}

        .period-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; }}

        .period-card {{ background: #1a1a1a; padding: 20px; border-radius: 10px; }}

        .period-card h3 {{ color: #888; margin-bottom: 10px; font-size: 12px; }}

        .period-card .pnl {{ font-size: 24px; font-weight: bold; }}

        .period-card .details {{ color: #666; font-size: 11px; margin-top: 8px; }}

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

        </div>

    </div>

    

    <div class="section">

        <div class="date-picker">

            <form method="get" style="display:flex;gap:10px;align-items:center;">

                <label>시작:</label>

                <input type="date" name="start" value="{start}">

                <label>종료:</label>

                <input type="date" name="end" value="{end}">

                <button type="submit">조회</button>

            </form>

            <div class="presets">

                <a href="/dashboard/report?start={today}&end={today}">오늘</a>

                <a href="/dashboard/report?start={week_ago}&end={today}">7일</a>

                <a href="/dashboard/report?start={month_ago}&end={today}">30일</a>

                <a href="/dashboard/report?start={year_ago}&end={today}">1년</a>

                <a href="/dashboard/report?start=2020-01-01&end={today}">전체</a>

            </div>

        </div>

        

        <div class="result-card">

            <h3>📅 {start} ~ {end}</h3>

            <div class="pnl" style="color:{'#40c057' if period_s['pnl'] >= 0 else '#fa5252'}">{period_s['pnl']:.2f} USDT</div>

            <div class="details">

                <span>거래: {period_s['trades']}회</span>

                <span>승률: {period_s['win_rate']}% ({period_s['wins']}W / {period_s['losses']}L)</span>

                <span>평균: {period_s['avg_pnl']:.2f}%</span>

            </div>

        </div>

    </div>

    

    <div class="section">

        <h2 class="section-title">⏱️ 빠른 비교</h2>

        <div class="period-grid">

            <div class="period-card">

                <h3>오늘</h3>

                <div class="pnl" style="color:{'#40c057' if today_s['pnl'] >= 0 else '#fa5252'}">{today_s['pnl']:.2f}</div>

                <div class="details">{today_s['trades']}회 | {today_s['win_rate']}%</div>

            </div>

            <div class="period-card">

                <h3>7일</h3>

                <div class="pnl" style="color:{'#40c057' if week_s['pnl'] >= 0 else '#fa5252'}">{week_s['pnl']:.2f}</div>

                <div class="details">{week_s['trades']}회 | {week_s['win_rate']}%</div>

            </div>

            <div class="period-card">

                <h3>30일</h3>

                <div class="pnl" style="color:{'#40c057' if month_s['pnl'] >= 0 else '#fa5252'}">{month_s['pnl']:.2f}</div>

                <div class="details">{month_s['trades']}회 | {month_s['win_rate']}%</div>

            </div>

        </div>

    </div>

    

    <div class="section">

        <h2 class="section-title">📈 일별 손익 (30일)</h2>

        <div class="card">

            <canvas id="dailyChart" height="100"></canvas>

        </div>

    </div>

    

    <div class="section">

        <h2 class="section-title">💰 종목별 성과</h2>

        <table>

            <thead><tr><th>종목</th><th>거래</th><th>승률</th><th>손익</th><th>평균</th></tr></thead>

            <tbody>{symbol_rows}</tbody>

        </table>

    </div>

    

    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

    <script>

        new Chart(document.getElementById('dailyChart').getContext('2d'), {{

            type: 'bar',

            data: {{

                labels: {chart_labels},

                datasets: [

                    {{ label: '일별', data: {chart_data}, backgroundColor: {chart_data}.map(v => v >= 0 ? 'rgba(64,192,87,0.8)' : 'rgba(250,82,82,0.8)'), yAxisID: 'y' }},

                    {{ label: '누적', data: {cumulative}, type: 'line', borderColor: '#4dabf7', backgroundColor: 'transparent', yAxisID: 'y1' }}

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

