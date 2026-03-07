
import asyncio

import threading

import time

from datetime import datetime

from exchange.database import db

from exchange import get_bot

from exchange.utility import log_message, log_error_message



class RecoveryEngine:

    def __init__(self, check_interval=60, auto_recover=False):

        """

        check_interval: 체크 주기 (초)

        auto_recover: True면 자동 복구, False면 알림만

        """

        self.check_interval = check_interval

        self.auto_recover = auto_recover

        self.running = False

        self.thread = None

        self.last_check = None

        self.issues_found = []

    

    def start(self):

        """백그라운드에서 리커버리 엔진 시작"""

        if self.running:

            return

        

        self.running = True

        self.thread = threading.Thread(target=self._run_loop, daemon=True)

        self.thread.start()

        log_message(f"[리커버리 엔진] 시작됨 (주기: {self.check_interval}초, 자동복구: {self.auto_recover})")

    

    def stop(self):

        """리커버리 엔진 중지"""

        self.running = False

        if self.thread:

            self.thread.join(timeout=5)

        log_message("[리커버리 엔진] 중지됨")

    

    def _run_loop(self):

        """주기적 체크 루프"""

        while self.running:

            try:

                self.check_and_recover()

            except Exception as e:

                log_error_message(f"리커버리 엔진 에러: {str(e)[:100]}", "Recovery Engine")

            

            time.sleep(self.check_interval)

    

    def check_and_recover(self):

        """포지션 불일치 체크 및 복구"""

        self.last_check = datetime.now()

        self.issues_found = []

        

        try:

            # 1. 거래소 실제 포지션 가져오기

            exchange_positions = self._get_exchange_positions()

            

            # 2. DB 예상 포지션 가져오기

            db_positions = db.get_active_positions()

            

            # 3. 비교

            issues = self._compare_positions(exchange_positions, db_positions)

            

            if issues:

                self.issues_found = issues

                self._handle_issues(issues)

            

        except Exception as e:

            log_error_message(f"포지션 체크 실패: {str(e)[:100]}", "Recovery Engine")

    

    def _get_exchange_positions(self):

        """거래소에서 실제 포지션 가져오기"""

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

            log_error_message(f"거래소 포지션 조회 실패: {str(e)[:50]}", "Recovery Engine")

            return {}

    

    def _compare_positions(self, exchange_pos, db_pos):

        """포지션 비교하여 불일치 찾기"""

        issues = []

        

        # DB 포지션을 symbol 기준으로 정리

        db_by_symbol = {}

        if db_pos:

            for p in db_pos:

                db_by_symbol[p['symbol']] = p

        

        # Case 1: 거래소에 있는데 DB에 없음 (진입 누락 or 수동 거래)

        for symbol, ex_pos in exchange_pos.items():

            if symbol not in db_by_symbol:

                issues.append({

                    'type': 'missing_in_db',

                    'symbol': symbol,

                    'exchange_side': ex_pos['side'],

                    'exchange_amount': ex_pos['amount'],

                    'message': f"거래소에 {symbol} 포지션 있으나 DB에 없음 (수동거래 또는 진입 기록 누락)"

                })

        

        # Case 2: DB에 있는데 거래소에 없음 (종료 누락 or 청산됨)

        for symbol, db_p in db_by_symbol.items():

            if symbol not in exchange_pos:

                issues.append({

                    'type': 'missing_in_exchange',

                    'symbol': symbol,

                    'db_side': db_p['side'],

                    'db_amount': db_p['amount'],

                    'db_strategy': db_p['strategy'],

                    'message': f"DB에 {symbol} 포지션 있으나 거래소에 없음 (종료 누락 또는 청산됨)"

                })

        

        # Case 3: 둘 다 있지만 방향이 다름

        for symbol in db_by_symbol:

            if symbol in exchange_pos:

                db_side = db_by_symbol[symbol]['side']

                ex_side = exchange_pos[symbol]['side']

                if db_side != ex_side:

                    issues.append({

                        'type': 'side_mismatch',

                        'symbol': symbol,

                        'db_side': db_side,

                        'exchange_side': ex_side,

                        'message': f"{symbol} 방향 불일치: DB={db_side}, 거래소={ex_side}"

                    })

        

        return issues

    

    def _handle_issues(self, issues):

        """불일치 처리"""

        for issue in issues:

            if self.auto_recover:

                self._auto_recover(issue)

            else:

                self._send_alert(issue)

    

    def _auto_recover(self, issue):

        """자동 복구 시도"""

        try:

            bot = get_bot("BITGET")

            

            if issue['type'] == 'missing_in_exchange':

                # DB에만 있고 거래소에 없음 → DB에서 포지션 삭제

                log_message(f"[자동복구] {issue['symbol']} DB 포지션 정리 (거래소에 없음)")

                # DB에서 해당 포지션 삭제

                db.excute(

                    "DELETE FROM positions WHERE symbol = :symbol",

                    {'symbol': issue['symbol']}

                )

                self._send_alert(issue, recovered=True)

                

            elif issue['type'] == 'missing_in_db':

                # 거래소에만 있고 DB에 없음 → 알림만 (수동 거래일 수 있음)

                log_message(f"[알림] {issue['symbol']} 거래소 포지션 발견 (DB에 없음 - 수동거래?)")

                self._send_alert(issue)

                

            elif issue['type'] == 'side_mismatch':

                # 방향 불일치 → 위험하므로 알림만

                log_message(f"[경고] {issue['symbol']} 방향 불일치 - 수동 확인 필요")

                self._send_alert(issue)

                

        except Exception as e:

            log_error_message(f"자동복구 실패: {str(e)[:100]}", "Recovery Engine")

            self._send_alert(issue, error=str(e))

    

    def _send_alert(self, issue, recovered=False, error=None):

        """디스코드 알림 전송"""

        status = "✅ 복구됨" if recovered else "⚠️ 확인 필요"

        if error:

            status = f"❌ 복구 실패: {error[:50]}"

        

        msg = f"""🔔 [리커버리 엔진] 포지션 불일치 감지



{status}

유형: {issue['type']}

심볼: {issue['symbol']}

상세: {issue['message']}

시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

        

        log_message(msg)

    

    def get_status(self):

        """현재 상태 반환"""

        return {

            'running': self.running,

            'last_check': self.last_check.isoformat() if self.last_check else None,

            'check_interval': self.check_interval,

            'auto_recover': self.auto_recover,

            'issues_found': len(self.issues_found),

            'issues': self.issues_found

        }





# 전역 인스턴스

recovery_engine = RecoveryEngine(check_interval=60, auto_recover=False)

