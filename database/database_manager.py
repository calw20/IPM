# File: database/database_manager.py

import sqlite3
from datetime import datetime
import os
import logging

logging.basicConfig(level=logging.DEBUG, filename='import_transactions.log', filemode='w',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_file):
        self.db_file = db_file
        self.conn = None
        self.cursor = None

    def connect(self):
        self.conn = sqlite3.connect(self.db_file)
        self.cursor = self.conn.cursor()

    def disconnect(self):
        if self.conn:
            self.conn.close()

    def init_db(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        schema_file = os.path.join(current_dir, 'schema.sql')
        with open(schema_file, 'r') as f:
            schema = f.read()
        self.conn.executescript(schema)
        self.conn.commit()

    def execute(self, sql, params=None):
        if params is None:
            self.cursor.execute(sql)
        else:
            self.cursor.execute(sql, params)
        self.conn.commit()

    def fetch_one(self, sql, params=None):
        if params is None:
            self.cursor.execute(sql)
        else:
            self.cursor.execute(sql, params)
        return self.cursor.fetchone()

    def fetch_all(self, sql, params=None):
        if params is None:
            self.cursor.execute(sql)
        else:
            self.cursor.execute(sql, params)
        return self.cursor.fetchall()

    # Portfolio methods
    def create_portfolio(self, name):
        self.execute("INSERT INTO portfolios (name) VALUES (?)", (name,))
        return self.cursor.lastrowid

    def get_all_portfolios(self):
        return self.fetch_all("SELECT id, name FROM portfolios")

    def delete_portfolio(self, portfolio_id):
        self.execute("DELETE FROM portfolios WHERE id = ?", (portfolio_id,))

    # Stock methods
    def add_stock(self, yahoo_symbol, instrument_code, name=None, current_price=None):
        current_time = datetime.now().replace(microsecond=0)
        self.execute("""
            INSERT OR REPLACE INTO stocks (yahoo_symbol, instrument_code, name, current_price, last_updated)
            VALUES (?, ?, ?, ?, ?)
        """, (yahoo_symbol, instrument_code, name, current_price, current_time))
        return self.cursor.lastrowid

    def update_stock_price(self, yahoo_symbol, current_price):
        current_time = datetime.now().replace(microsecond=0)
        self.execute("""
            UPDATE stocks SET current_price = ?, last_updated = ? WHERE yahoo_symbol = ?
        """, (current_price, current_time, yahoo_symbol))

    def get_stock(self, yahoo_symbol):
        return self.fetch_one("SELECT * FROM stocks WHERE yahoo_symbol = ?", (yahoo_symbol,))

    def update_stock_info(self, stock_id, name, current_price, yahoo_symbol):
        """Update stock information in the database"""
        self.execute("""
            UPDATE stocks 
            SET name = ?,
                current_price = ?,
                last_updated = ?,
                yahoo_symbol = ?
            WHERE id = ?
        """, (
            name,
            current_price,
            datetime.now().replace(microsecond=0),
            yahoo_symbol,
            stock_id
        ))
        self.conn.commit()

    def update_stock_yahoo_override(self, instrument_code, yahoo_symbol):
        """
        Update the yahoo_symbol directly for manual market declarations.
        """
        current_time = datetime.now().replace(microsecond=0)
        self.execute("""
            UPDATE stocks 
            SET yahoo_symbol = ?,
                last_updated = ?,
                market_suffix = NULL  -- Clear market suffix to indicate manual override
            WHERE instrument_code = ?
        """, (yahoo_symbol, current_time, instrument_code))
        self.conn.commit()

    def get_stock_by_instrument_code(self, instrument_code):
        """
        Get stock information by instrument code.
        Returns the stock with its proper yahoo symbol, whether manual or market-based.
        """
        return self.fetch_one("""
            SELECT id, yahoo_symbol, instrument_code, name, current_price, 
                last_updated, market_suffix, drp
            FROM stocks
            WHERE instrument_code = ?
        """, (instrument_code,))
        
    # Transaction methods
    def add_transaction(self, stock_id, date, quantity, price, transaction_type):
        self.execute("""
            INSERT INTO transactions (stock_id, date, quantity, price, transaction_type)
            VALUES (?, ?, ?, ?, ?)
        """, (stock_id, date, quantity, price, transaction_type))

    def get_transactions_for_stock(self, stock_id):
        return self.fetch_all("""
            SELECT id, date, quantity, price, transaction_type
            FROM transactions
            WHERE stock_id = ?
            ORDER BY date
        """, (stock_id,))
    
    def bulk_insert_transactions(self, transactions):
        """
        Bulk insert transactions.
        transactions: list of tuples (stock_id, date, quantity, price, type, original_quantity, original_price)
        """
        self.cursor.executemany("""
            INSERT INTO transactions 
            (stock_id, date, quantity, price, transaction_type, original_quantity, original_price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, transactions)
        self.conn.commit()

    def bulk_insert_stock_splits(self, splits):
        """
        Bulk insert stock splits.
        splits: list of tuples (stock_id, date, ratio, verified_source, verification_date)
        """
        self.cursor.executemany("""
            INSERT INTO stock_splits 
            (stock_id, date, ratio, verified_source, verification_date)
            VALUES (?, ?, ?, ?, ?)
        """, splits)
        self.conn.commit()

    def bulk_insert_historical_prices(self, prices):
        """
        Bulk insert historical prices.
        
        Args:
            prices: list of tuples (stock_id, date, open, high, low, close, volume, 
                                adjusted_close, original_close, split_adjusted, dividend)
        """
        try:
            self.cursor.executemany("""
                INSERT OR REPLACE INTO historical_prices 
                (stock_id, date, open_price, high_price, low_price, close_price, volume, 
                adjusted_close, original_close, split_adjusted, dividend)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, prices)
            self.conn.commit()
        except Exception as e:
            logger.error(f"Error in bulk_insert_historical_prices: {str(e)}")
            raise

    # Portfolio-Stock relationship methods
    def add_stock_to_portfolio(self, portfolio_id, stock_id):
        self.execute("""
            INSERT OR IGNORE INTO portfolio_stocks (portfolio_id, stock_id)
            VALUES (?, ?)
        """, (portfolio_id, stock_id))

    def remove_stock_from_portfolio(self, portfolio_id, stock_id):
        self.execute("""
            DELETE FROM portfolio_stocks
            WHERE portfolio_id = ? AND stock_id = ?
        """, (portfolio_id, stock_id))

    def get_stocks_for_portfolio(self, portfolio_id):
        return self.fetch_all("""
            SELECT s.id, s.yahoo_symbol, s.instrument_code, s.name, s.current_price, s.last_updated
            FROM stocks s
            JOIN portfolio_stocks ps ON s.id = ps.stock_id
            WHERE ps.portfolio_id = ?
        """, (portfolio_id,))

    # Stock split methods
    def add_stock_split(self, stock_id, date, ratio):
        self.execute("""
            INSERT INTO stock_splits (stock_id, date, ratio)
            VALUES (?, ?, ?)
        """, (stock_id, date, ratio))

    def get_stock_splits(self, stock_id):
        return self.fetch_all("""
            SELECT date, ratio FROM stock_splits
            WHERE stock_id = ?
            ORDER BY date
        """, (stock_id,))
    
    # Dividend Reinvestment Plan methods
    def get_stock_drp(self, stock_id):
        result = self.fetch_one("SELECT drp FROM stocks WHERE id = ?", (stock_id,))
        return bool(result[0]) if result and result[0] is not None else False

    def update_stock_drp(self, stock_id, drp_status):
        self.execute("""
            UPDATE stocks 
            SET drp = ?
            WHERE id = ?
        """, (1 if drp_status else 0, stock_id))
        self.conn.commit()
        print(f"Database updated: Stock ID {stock_id} DRP status set to {drp_status}") 

    # Market code methods
    def get_all_market_codes(self):
        """
        Returns all market codes with their suffixes.
        Returns tuples of (market_or_index, market_suffix)
        """
        return self.fetch_all("""
            SELECT market_or_index, market_suffix 
            FROM market_codes 
            ORDER BY market_or_index
        """)

    def get_market_code_suffix(self, market_or_index):
        result = self.fetch_one("SELECT market_suffix FROM market_codes WHERE market_or_index = ?", (market_or_index,))
        return result[0] if result else None

    def update_stock_yahoo_symbol(self, instrument_code, yahoo_symbol):
        self.execute("UPDATE stocks SET yahoo_symbol = ? WHERE instrument_code = ?", (yahoo_symbol, instrument_code))

    def update_stock_market(self, instrument_code, market_suffix):
        self.execute("""
            UPDATE stocks 
            SET market_suffix = ?
            WHERE instrument_code = ?
        """, (market_suffix, instrument_code))

    def get_all_stocks(self):
        return self.fetch_all("""
            SELECT id, yahoo_symbol, instrument_code, name, current_price, last_updated, market_suffix, drp
            FROM stocks
        """)
    
    def get_stock(self, instrument_code):
        return self.fetch_one("""
            SELECT id, yahoo_symbol, instrument_code, name, current_price, last_updated, market_suffix
            FROM stocks
            WHERE instrument_code = ?
        """, (instrument_code,))