
# main.py의 order 함수에 적용할 패치

# 기존: order_result = bot.market_entry(bot.order_info)

# 변경: OrderManager를 통한 재시도 로직 적용



PATCH_IMPORT = """from exchange.order_manager import OrderManager"""



PATCH_ENTRY = """

                order_manager = OrderManager(bot, max_retries=3, retry_delay=2)

                order_result = order_manager.execute_with_retry(

                    bot.market_entry, bot.order_info, "entry"

                )"""



PATCH_CLOSE = """

                order_manager = OrderManager(bot, max_retries=3, retry_delay=2)

                order_result = order_manager.execute_with_retry(

                    bot.market_close, bot.order_info, "close"

                )"""

