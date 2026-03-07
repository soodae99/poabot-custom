
import time

from exchange.utility import log_message, log_error_message



class OrderManager:

    def __init__(self, bot, max_retries=3, retry_delay=2):

        self.bot = bot

        self.max_retries = max_retries

        self.retry_delay = retry_delay

    

    def execute_with_retry(self, order_func, order_info, order_type="entry"):

        """주문 실행 + 체결 확인 + 재시도"""

        last_error = None

        

        for attempt in range(1, self.max_retries + 1):

            try:

                # 1. 주문 실행

                order_result = order_func(order_info)

                

                # 2. 주문 결과 확인

                if order_result and self.verify_order(order_result):

                    if attempt > 1:

                        log_message(f"[재시도 성공] {attempt}번째 시도에서 체결됨")

                    return order_result

                else:

                    log_message(f"[체결 미확인] 시도 {attempt}/{self.max_retries}")

                    

            except Exception as e:

                last_error = e

                log_message(f"[주문 실패] 시도 {attempt}/{self.max_retries}: {str(e)[:100]}")

            

            # 마지막 시도가 아니면 대기 후 재시도

            if attempt < self.max_retries:

                time.sleep(self.retry_delay)

        

        # 모든 재시도 실패

        self.send_critical_alert(order_info, last_error)

        raise Exception(f"주문 {self.max_retries}회 재시도 실패: {last_error}")

    

    def verify_order(self, order_result):

        """체결 확인"""

        if not order_result:

            return False

        

        # ccxt 주문 결과에서 상태 확인

        status = order_result.get('status', '')

        filled = order_result.get('filled', 0)

        amount = order_result.get('amount', 0)

        

        # 체결 완료 확인

        if status == 'closed':

            return True

        

        # 부분 체결이라도 수량이 있으면 성공으로 간주

        if filled and filled > 0:

            return True

        

        # order_id가 있으면 거래소에서 다시 확인

        order_id = order_result.get('id')

        if order_id:

            return self.check_order_status(order_id, order_result.get('symbol'))

        

        return False

    

    def check_order_status(self, order_id, symbol):

        """거래소에서 주문 상태 직접 확인"""

        try:

            time.sleep(1)  # 거래소 반영 대기

            order = self.bot.client.fetch_order(order_id, symbol)

            status = order.get('status', '')

            filled = order.get('filled', 0)

            

            if status == 'closed' or (filled and filled > 0):

                log_message(f"[체결 확인] 주문 {order_id} 체결됨")

                return True

            else:

                log_message(f"[체결 대기] 주문 {order_id} 상태: {status}")

                return False

        except Exception as e:

            log_message(f"[체결 확인 실패] {str(e)[:50]}")

            return False

    

    def send_critical_alert(self, order_info, error):

        """긴급 알림 전송"""

        msg = f"""🚨 긴급: 주문 실패 (재시도 {self.max_retries}회 초과)

        

거래소: {order_info.exchange}

심볼: {order_info.base}/{order_info.quote}

방향: {order_info.side}

에러: {str(error)[:200]}



⚠️ 수동 확인 필요"""

        

        log_error_message(msg, "주문 재시도 실패")

