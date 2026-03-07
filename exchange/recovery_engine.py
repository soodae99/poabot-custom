
import threading

import time

from datetime import datetime, timedelta

from exchange.database import db

from exchange import get_bot

from exchange.utility import log_message, log_error_message



class RecoveryEngine:

    def __init__(self, check_interval=60, auto_recover=True):

        self.check_interval = check_interval

        self.auto_recover = auto_recover

        self.running = False

        self.thread = None

        self.last_check = None

        self.issues_found = []

        self.synced_trades = self._load_synced_trades()

    

    def _load_synced_trades(self):

        try:

            existing = db.fetch_all("SELECT exit_time FROM trades WHERE strategy='비트겟직접' ORDER BY created_at DESC LIMIT 100", {})

            if existing:

                return set(e['exit_time'] for e in existing if e['exit_time'])

        except:

            pass

        return set()

    

    def start(self):

        if self.running:

            return

        self.running = True

        self.thread = threading.Thread(target=self._run_loop, daemon=True)

        self.thread.start()

        log_message(f"[리커버리 엔진] 시작됨 (주기: {self.check_interval}초, 자동복구: {self.auto_recover})")

    

    def stop(self):

        self.running = False

        if self.thread:

            self.thread.join(timeout=5)

    

    def _run_loop(self):

        while self.running:

            try:

                self.check_and_recover()

                self.sync_recent_trades()

            except Exception as e:

                log_error_message(f"리커버리 엔진 에러: {str(e)[:100]}", "Recovery Engine")

            time.sleep(self.check_interval)

    

    def check_and_recover(self):

        self.last_check = datetime.now()

        self.issues_found = []

        

        try:

            exchange_positions = self._get_exchange_positions()

            db_positions = db.get_active_positions()

            issues = self._compare_positions(exchange_positions, db_positions)

            

            if issues:

                self.issues_found = issues

                self._handle_issues(issues)

        except Exception as e:

            log_error_message(f"포지션 체크 실패: {str(e)[:100]}", "Recovery Engine")

    

    def _get_exchange_positions(self):

        try:

            bot = get_bot("BITGET")

            positions = bot.client.fetch_positions()

            active = {}

            for p in positions:

                contracts = float(p.get('contracts', 0))

                if contracts > 0:

                    symbol = p['symbol']

                    active[symbol] = {

                        'symbol': symbol,

                        'side': 'buy' if p['side'] == 'long' else 'sell',

                        'amount': contracts,

                        'entry_price': float(p['entryPrice']) if p['entryPrice'] else 0,

                    }

            return active

        except Exception as e:

            return {}

    

    def _compare_positions(self, exchange_pos, db_pos):

        issues = []

        db_by_symbol = {}

        if db_pos:

            for p in db_pos:

                db_by_symbol[p['symbol']] = dict(p)

        

        for symbol, ex_pos in exchange_pos.items():

            if symbol not in db_by_symbol:

                issues.append({

                    'type': 'missing_in_db',

                    'symbol': symbol,

                    'exchange_side': ex_pos['side'],

                    'exchange_amount': ex_pos['amount'],

                    'entry_price': ex_pos['entry_price'],

                    'message': f"거래소에 {symbol} 포지션 있으나 DB에 없음"

                })

        

        for symbol, db_p in db_by_symbol.items():

            if symbol not in exchange_pos:

                issues.append({

                    'type': 'missing_in_exchange',

                    'symbol': symbol,

                    'db_data': db_p,

                    'message': f"DB에 {symbol} 포지션 있으나 거래소에 없음"

                })

        

        return issues

    

    def _handle_issues(self, issues):

        for issue in issues:

            if issue['type'] == 'missing_in_exchange' and self.auto_recover:

                self._auto_close_position(issue)

            elif issue['type'] == 'missing_in_db' and self.auto_recover:

                self._auto_add_position(issue)

            else:

                self._send_alert(issue)

    

    def _auto_add_position(self, issue):

        try:

            symbol = issue['symbol']

            side = issue.get('exchange_side', 'buy')

            amount = issue.get('exchange_amount', 0)

            entry_price = issue.get('entry_price', 0)

            

            db.excute("""

                INSERT INTO positions (strategy, exchange, symbol, side, amount, entry_price, leverage, created_at)

                VALUES (:strategy, :exchange, :symbol, :side, :amount, :entry_price, :leverage, :created_at)

            """, {

                'strategy': '수동거래',

                'exchange': 'BITGET',

                'symbol': symbol,

                'side': side,

                'amount': amount,

                'entry_price': entry_price,

                'leverage': 1,

                'created_at': datetime.now().isoformat()

            })

            

            log_message(f"✅ [자동 추가] {symbol} 포지션 DB에 등록")

            

        except Exception as e:

            log_error_message(f"자동 추가 실패: {str(e)}", "Recovery Engine")

    

    def _auto_close_position(self, issue):

        try:

            db_data = issue.get('db_data', {})

            symbol = issue['symbol']

            strategy = db_data.get('strategy', 'unknown')

            entry_price = db_data.get('entry_price', 0)

            entry_time = db_data.get('created_at', '')

            side = db_data.get('side', 'buy')

            amount = db_data.get('amount', 0)

            leverage = db_data.get('leverage', 1) or 1

            

            bot = get_bot("BITGET")

            trades = bot.client.fetch_my_trades(symbol, limit=20)

            

            exit_price = None

            exit_time = None

            total_fee = 0

            

            for trade in reversed(trades):

                trade_side = trade.get('side', '')

                if (side == 'buy' and trade_side == 'sell') or (side == 'sell' and trade_side == 'buy'):

                    exit_price = float(trade.get('price', 0))

                    exit_time = trade.get('datetime', datetime.now().isoformat())

                    fee_info = trade.get('fee', {})

                    if fee_info:

                        total_fee = float(fee_info.get('cost', 0))

                    break

            

            if not exit_price:

                ticker = bot.client.fetch_ticker(symbol)

                exit_price = float(ticker.get('last', 0))

            

            if not exit_time:

                exit_time = datetime.now().isoformat()

            

            holding_seconds = 0

            try:

                if entry_time:

                    entry_dt = datetime.fromisoformat(entry_time.split('+')[0].split('Z')[0])

                    exit_dt = datetime.fromisoformat(exit_time.split('+')[0].split('Z')[0])

                    holding_seconds = int((exit_dt - entry_dt).total_seconds())

            except:

                pass

            

            if side == 'buy':

                pnl = (exit_price - entry_price) * amount

                pnl_percent = ((exit_price - entry_price) / entry_price) * 100 * leverage if entry_price > 0 else 0

            else:

                pnl = (entry_price - exit_price) * amount

                pnl_percent = ((entry_price - exit_price) / entry_price) * 100 * leverage if entry_price > 0 else 0

            

            is_win = 1 if pnl > 0 else 0

            

            db.save_trade({

                'strategy': strategy,

                'exchange': 'BITGET',

                'symbol': symbol,

                'side': 'close_' + side,

                'amount': amount,

                'price': exit_price,

                'entry_price': entry_price,

                'exit_price': exit_price,

                'entry_time': entry_time,

                'exit_time': exit_time,

                'leverage': leverage,

                'pnl': round(pnl, 4),

                'pnl_percent': round(pnl_percent, 2),

                'is_win': is_win,

                'fee': round(total_fee, 6),

                'holding_seconds': holding_seconds

            })

            

            db.excute("DELETE FROM positions WHERE symbol = :symbol AND strategy = :strategy", 

                     {"symbol": symbol, "strategy": strategy})

            

            hours = holding_seconds // 3600

            minutes = (holding_seconds % 3600) // 60

            holding_str = f"{hours}시간 {minutes}분" if hours > 0 else f"{minutes}분"

            

            pnl_emoji = "🟢" if pnl >= 0 else "🔴"

            log_message(f"{pnl_emoji} [{strategy}] {symbol} 종료 - 손익: {pnl:.4f} USDT ({pnl_percent:.2f}%) | 보유: {holding_str}")

            

        except Exception as e:

            log_error_message(f"자동 정리 실패: {str(e)}", "Recovery Engine")

    

    def sync_recent_trades(self):

        try:

            bot = get_bot("BITGET")

            symbols = ['XRP/USDT:USDT', 'BTC/USDT:USDT', 'ETH/USDT:USDT']

            

            for symbol in symbols:

                try:

                    trades = bot.client.fetch_my_trades(symbol, limit=20)

                    self._process_trades(trades, symbol)

                except:

                    pass

        except:

            pass

    

    def _process_trades(self, trades, symbol):

        if not trades:

            return

        

        now = datetime.now()

        cutoff = now - timedelta(minutes=5)

        

        entries = []

        exits = []

        

        for t in trades:

            trade_id = t.get('id', '')

            if trade_id in self.synced_trades:

                continue

            

            trade_time_str = t.get('datetime', '')

            try:

                trade_time = datetime.fromisoformat(trade_time_str.replace('Z', '+00:00').split('+')[0])

                if trade_time < cutoff:

                    continue

            except:

                continue

            

            side = t.get('side', '')

            info = t.get('info', {})

            trade_side = info.get('tradeSide', '')

            

            trade_data = {

                'id': trade_id,

                'time': trade_time_str,

                'price': float(t.get('price', 0)),

                'amount': float(t.get('amount', 0)),

                'fee': float(t.get('fee', {}).get('cost', 0)) if t.get('fee') else 0,

                'side': side,

                'trade_side': trade_side

            }

            

            if 'open' in str(trade_side).lower():

                entries.append(trade_data)

            elif 'close' in str(trade_side).lower():

                exits.append(trade_data)

        

        for exit_trade in exits:

            if exit_trade['time'] in self.synced_trades:

                continue

            

            exit_time = exit_trade['time']

            exit_price = exit_trade['price']

            amount = exit_trade['amount']

            fee = exit_trade['fee']

            

            entry_price = exit_price

            entry_time = exit_time

            holding_seconds = 0

            

            for entry in reversed(entries):

                if entry['time'] < exit_time:

                    entry_price = entry['price']

                    entry_time = entry['time']

                    try:

                        entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00').split('+')[0])

                        exit_dt = datetime.fromisoformat(exit_time.replace('Z', '+00:00').split('+')[0])

                        holding_seconds = int((exit_dt - entry_dt).total_seconds())

                    except:

                        pass

                    self.synced_trades.add(entry['id'])

                    break

            

            if exit_trade['side'] == 'sell':

                pnl = (exit_price - entry_price) * amount

            else:

                pnl = (entry_price - exit_price) * amount

            

            pnl_percent = (pnl / (entry_price * amount)) * 100 if entry_price > 0 and amount > 0 else 0

            is_win = 1 if pnl > 0 else 0

            

            try:

                db.save_trade({

                    'strategy': '비트겟직접',

                    'exchange': 'BITGET',

                    'symbol': symbol,

                    'side': 'close_buy' if exit_trade['side'] == 'sell' else 'close_sell',

                    'amount': amount,

                    'price': exit_price,

                    'entry_price': entry_price,

                    'exit_price': exit_price,

                    'entry_time': entry_time,

                    'exit_time': exit_time,

                    'leverage': 1,

                    'pnl': round(pnl, 4),

                    'pnl_percent': round(pnl_percent, 2),

                    'is_win': is_win,

                    'fee': fee,

                    'holding_seconds': holding_seconds

                })

                self.synced_trades.add(exit_trade['time'])

                log_message(f"✅ [거래동기화] {symbol} | 손익: {pnl:.4f} USDT | 보유: {holding_seconds}초")

            except Exception as e:

                log_error_message(f"거래 저장 실패: {str(e)[:50]}", "Sync")

    

    def _send_alert(self, issue):

        log_message(f"⚠️ [리커버리] {issue['message']}")

    

    def get_status(self):

        return {

            'running': self.running,

            'last_check': self.last_check.isoformat() if self.last_check else None,

            'check_interval': self.check_interval,

            'auto_recover': self.auto_recover,

            'issues': self.issues_found

        }





recovery_engine = RecoveryEngine(check_interval=60, auto_recover=True)

