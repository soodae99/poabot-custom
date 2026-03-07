import sqlite3
import traceback
import os
from pathlib import Path
from datetime import datetime

current_file_direcotry = os.path.dirname(os.path.realpath(__file__))
parent_directory = Path(current_file_direcotry).parent

class Database:
    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, database_url: str = f"{parent_directory}/store.db"):
        cls = type(self)
        if not hasattr(cls, "_init"):
            self.database_url = database_url
            self.con = sqlite3.connect(self.database_url, check_same_thread=False)
            self.con.row_factory = sqlite3.Row
            self.cursor = self.con.cursor()
            cls._init = True

    def close(self):
        self.con.close()

    def excute(self, query: str, value: dict | tuple):
        self.cursor.execute(query, value)
        self.con.commit()

    def excute_many(self, query: str, values: list[dict | tuple]):
        self.cursor.executemany(query, values)
        self.con.commit()

    def fetch_one(self, query: str, value: dict | tuple):
        self.cursor.execute(query, value)
        return self.cursor.fetchone()

    def fetch_all(self, query: str, value: dict | tuple):
        self.cursor.execute(query, value)
        return self.cursor.fetchall()

    def set_auth(self, exchange, access_token, access_token_token_expired):
        query = """
        INSERT INTO auth (exchange, access_token, access_token_token_expired)
        VALUES (:exchange, :access_token, :access_token_token_expired)
        ON CONFLICT(exchange) DO UPDATE SET
        access_token=excluded.access_token,
        access_token_token_expired=excluded.access_token_token_expired;
        """
        return self.excute(query, {"exchange": exchange, "access_token": access_token, "access_token_token_expired": access_token_token_expired})

    def get_auth(self, exchange):
        query = """
        SELECT access_token, access_token_token_expired FROM auth WHERE exchange = :exchange;
        """
        return self.fetch_one(query, {"exchange": exchange})

    def clear_auth(self):
        self.set_auth("KIS1", "nothing", "nothing")
        self.set_auth("KIS2", "nothing", "nothing")
        self.set_auth("KIS3", "nothing", "nothing")
        self.set_auth("KIS4", "nothing", "nothing")

    def save_trade(self, trade_data: dict):
        query = """
        INSERT INTO trades (
            strategy, exchange, symbol, side, amount, price, 
            leverage, pnl, pnl_percent, is_win, created_at
        ) VALUES (
            :strategy, :exchange, :symbol, :side, :amount, :price,
            :leverage, :pnl, :pnl_percent, :is_win, :created_at
        )
        """
        trade_data['created_at'] = datetime.now().isoformat()
        return self.excute(query, trade_data)

    def save_entry(self, strategy: str, exchange: str, symbol: str, side: str, 
                   amount: float, price: float, leverage: int = 1):
        query = """
        INSERT OR REPLACE INTO positions (
            strategy, exchange, symbol, side, amount, entry_price, leverage, created_at
        ) VALUES (
            :strategy, :exchange, :symbol, :side, :amount, :entry_price, :leverage, :created_at
        )
        """
        return self.excute(query, {
            'strategy': strategy,
            'exchange': exchange,
            'symbol': symbol,
            'side': side,
            'amount': amount,
            'entry_price': price,
            'leverage': leverage,
            'created_at': datetime.now().isoformat()
        })

    def get_position(self, strategy: str, exchange: str, symbol: str):
        query = """
        SELECT * FROM positions 
        WHERE strategy = :strategy AND exchange = :exchange AND symbol = :symbol
        ORDER BY created_at DESC LIMIT 1
        """
        return self.fetch_one(query, {
            'strategy': strategy, 'exchange': exchange, 'symbol': symbol
        })

    def close_position(self, strategy: str, exchange: str, symbol: str, 
                       exit_price: float, exit_amount: float):
        position = self.get_position(strategy, exchange, symbol)
        if not position:
            return None
        
        entry_price = position['entry_price']
        side = position['side']
        leverage = position['leverage'] or 1
        
        if side == 'buy':
            pnl_percent = ((exit_price - entry_price) / entry_price) * 100 * leverage
        else:
            pnl_percent = ((entry_price - exit_price) / entry_price) * 100 * leverage
        
        pnl = (exit_price - entry_price) * exit_amount if side == 'buy' else (entry_price - exit_price) * exit_amount
        is_win = 1 if pnl > 0 else 0
        
        self.save_trade({
            'strategy': strategy,
            'exchange': exchange,
            'symbol': symbol,
            'side': 'close_' + side,
            'amount': exit_amount,
            'price': exit_price,
            'leverage': leverage,
            'pnl': pnl,
            'pnl_percent': pnl_percent,
            'is_win': is_win
        })
        
        delete_query = """
        DELETE FROM positions 
        WHERE strategy = :strategy AND exchange = :exchange AND symbol = :symbol
        """
        self.excute(delete_query, {
            'strategy': strategy, 'exchange': exchange, 'symbol': symbol
        })
        
        return {'pnl': pnl, 'pnl_percent': pnl_percent, 'is_win': is_win}

    def get_strategy_stats(self, strategy: str = None):
        if strategy:
            query = """
            SELECT 
                strategy,
                COUNT(*) as total_trades,
                SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN is_win = 0 THEN 1 ELSE 0 END) as losses,
                ROUND(SUM(pnl), 2) as total_pnl,
                ROUND(AVG(pnl_percent), 2) as avg_pnl_percent,
                ROUND(MAX(pnl_percent), 2) as max_win_percent,
                ROUND(MIN(pnl_percent), 2) as max_loss_percent
            FROM trades WHERE strategy = :strategy AND pnl IS NOT NULL
            GROUP BY strategy
            """
            return self.fetch_one(query, {'strategy': strategy})
        else:
            query = """
            SELECT 
                strategy,
                COUNT(*) as total_trades,
                SUM(CASE WHEN is_win = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN is_win = 0 THEN 1 ELSE 0 END) as losses,
                ROUND(SUM(pnl), 2) as total_pnl,
                ROUND(AVG(pnl_percent), 2) as avg_pnl_percent,
                ROUND(MAX(pnl_percent), 2) as max_win_percent,
                ROUND(MIN(pnl_percent), 2) as max_loss_percent
            FROM trades WHERE pnl IS NOT NULL
            GROUP BY strategy
            """
            return self.fetch_all(query, {})

    def get_all_trades(self, strategy: str = None, limit: int = 100):
        if strategy:
            query = "SELECT * FROM trades WHERE strategy = :strategy ORDER BY created_at DESC LIMIT :limit"
            return self.fetch_all(query, {'strategy': strategy, 'limit': limit})
        else:
            query = "SELECT * FROM trades ORDER BY created_at DESC LIMIT :limit"
            return self.fetch_all(query, {'limit': limit})

    def get_active_positions(self):
        query = "SELECT * FROM positions ORDER BY created_at DESC"
        return self.fetch_all(query, {})

    def init_db(self):
        self.excute("""
        CREATE TABLE IF NOT EXISTS auth (
            exchange TEXT PRIMARY KEY,
            access_token TEXT,
            access_token_token_expired TEXT
        );""", {})
        
        self.excute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy TEXT NOT NULL,
            exchange TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            amount REAL,
            price REAL,
            leverage INTEGER DEFAULT 1,
            pnl REAL,
            pnl_percent REAL,
            is_win INTEGER,
            created_at TEXT NOT NULL
        );""", {})
        
        self.excute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy TEXT NOT NULL,
            exchange TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            amount REAL NOT NULL,
            entry_price REAL NOT NULL,
            leverage INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            UNIQUE(strategy, exchange, symbol)
        );""", {})


db = Database()
try:
    db.init_db()
except Exception as e:
    print(traceback.format_exc())
