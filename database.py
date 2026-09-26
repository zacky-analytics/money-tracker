import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash, check_password_hash


DATABASE = "database/MoneyTracker.db"


# --------------------------------------------------
# DATABASE SETUP
# --------------------------------------------------

def create_database():
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    # USERS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            account_type TEXT NOT NULL
                CHECK(account_type IN ('personal', 'business')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # CATEGORIES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT NOT NULL,
            type TEXT NOT NULL
                CHECK(type IN ('income', 'expense')),
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
    """)

    # TRANSACTIONS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            type TEXT NOT NULL
                CHECK(type IN ('income', 'expense')),
            amount_cents INTEGER NOT NULL
                CHECK(amount_cents > 0),
            description TEXT,
            payment_method TEXT NOT NULL,
            transaction_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (category_id)
                REFERENCES categories(id)
                ON DELETE RESTRICT
        )
    """)

    # --------------------------------------------------
    # BUDGETS
    # --------------------------------------------------
    #
    # One budget per user + expense category + month.
    #
    # Example:
    # user_id = 1
    # category_id = Food
    # month = 2026-09
    # limit_cents = 500000  -> KES 5,000
    #
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            month TEXT NOT NULL,
            limit_cents INTEGER NOT NULL
                CHECK(limit_cents > 0),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,

            FOREIGN KEY (category_id)
                REFERENCES categories(id)
                ON DELETE CASCADE,

            UNIQUE(user_id, category_id, month)
        )
    """)

    connection.commit()
    connection.close()


# --------------------------------------------------
# DEFAULT CATEGORIES
# --------------------------------------------------

def create_default_categories(user_id, account_type):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    if account_type == "personal":
        categories = [
            ("Salary", "income"),
            ("Freelance", "income"),
            ("Other Income", "income"),
            ("Food", "expense"),
            ("Transport", "expense"),
            ("Rent", "expense"),
            ("Bills", "expense"),
            ("Shopping", "expense"),
            ("Other Expense", "expense")
        ]

    else:
        categories = [
            ("Sales", "income"),
            ("Services", "income"),
            ("Other Income", "income"),
            ("Supplies", "expense"),
            ("Rent", "expense"),
            ("Transport", "expense"),
            ("Salaries", "expense"),
            ("Marketing", "expense"),
            ("Utilities", "expense"),
            ("Other Expense", "expense")
        ]

    for name, category_type in categories:
        cursor.execute("""
            INSERT INTO categories (user_id, name, type)
            VALUES (?, ?, ?)
        """, (user_id, name, category_type))

    connection.commit()
    connection.close()


# --------------------------------------------------
# REGISTER USER
# --------------------------------------------------

def register_user(username, password, account_type):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    password_hash = generate_password_hash(password)

    cursor.execute("""
        INSERT INTO users (username, password_hash, account_type)
        VALUES (?, ?, ?)
    """, (username, password_hash, account_type))

    user_id = cursor.lastrowid

    connection.commit()
    connection.close()

    create_default_categories(user_id, account_type)

    return user_id


# --------------------------------------------------
# LOGIN USER
# --------------------------------------------------

def login_user(username, password):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id, username, password_hash, account_type
        FROM users
        WHERE username = ?
    """, (username,))

    user = cursor.fetchone()

    connection.close()

    if user and check_password_hash(user[2], password):
        return {
            "id": user[0],
            "username": user[1],
            "account_type": user[3]
        }

    return None


# --------------------------------------------------
# USER CATEGORIES
# --------------------------------------------------

def get_user_categories(user_id):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id, name, type
        FROM categories
        WHERE user_id = ?
        ORDER BY type, name
    """, (user_id,))

    categories = cursor.fetchall()

    connection.close()

    return categories


# --------------------------------------------------
# ADD TRANSACTION
# --------------------------------------------------

def add_transaction(
    user_id,
    category_id,
    t_type,
    amount_cents,
    description,
    payment_method,
    t_date
):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    # Make sure the category belongs to this user
    # and matches the transaction type.
    cursor.execute("""
        SELECT id
        FROM categories
        WHERE id = ?
          AND user_id = ?
          AND type = ?
    """, (category_id, user_id, t_type))

    category = cursor.fetchone()

    if not category:
        connection.close()
        raise ValueError("Invalid category for this transaction.")

    if not isinstance(amount_cents, int) or amount_cents <= 0:
        connection.close()
        raise ValueError(
            "Amount must be a positive integer number of cents."
        )

    cursor.execute("""
        INSERT INTO transactions (
            user_id,
            category_id,
            type,
            amount_cents,
            description,
            payment_method,
            transaction_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        category_id,
        t_type,
        amount_cents,
        description,
        payment_method,
        t_date
    ))

    connection.commit()
    connection.close()


# --------------------------------------------------
# TOTALS
# --------------------------------------------------

def get_user_totals(user_id, month=None):
    """
    Get income, expenses and balance.

    If month is provided, it must be in YYYY-MM format,
    for example: 2026-09.

    If month is None, all transactions are included.
    """

    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    if month:
        cursor.execute("""
            SELECT SUM(amount_cents)
            FROM transactions
            WHERE user_id = ?
              AND type = 'income'
              AND strftime('%Y-%m', transaction_date) = ?
        """, (user_id, month))
    else:
        cursor.execute("""
            SELECT SUM(amount_cents)
            FROM transactions
            WHERE user_id = ?
              AND type = 'income'
        """, (user_id,))

    income_res = cursor.fetchone()[0]
    total_income_cents = income_res if income_res else 0

    if month:
        cursor.execute("""
            SELECT SUM(amount_cents)
            FROM transactions
            WHERE user_id = ?
              AND type = 'expense'
              AND strftime('%Y-%m', transaction_date) = ?
        """, (user_id, month))
    else:
        cursor.execute("""
            SELECT SUM(amount_cents)
            FROM transactions
            WHERE user_id = ?
              AND type = 'expense'
        """, (user_id,))

    expense_res = cursor.fetchone()[0]
    total_expense_cents = expense_res if expense_res else 0

    connection.close()

    total_income = total_income_cents / 100.0
    total_expenses = total_expense_cents / 100.0
    total_balance = total_income - total_expenses

    return {
        "balance": total_balance,
        "income": total_income,
        "expenses": total_expenses,
    }


# --------------------------------------------------
# TRANSACTION HISTORY
# --------------------------------------------------

def get_user_transactions(user_id, month=None):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    if month:
        cursor.execute("""
            SELECT
                transactions.id,
                transactions.type,
                categories.name,
                transactions.amount_cents,
                transactions.description,
                transactions.payment_method,
                transactions.transaction_date
            FROM transactions
            JOIN categories
                ON transactions.category_id = categories.id
            WHERE transactions.user_id = ?
              AND strftime('%Y-%m', transactions.transaction_date) = ?
            ORDER BY transactions.transaction_date DESC,
                     transactions.id DESC
        """, (user_id, month))
    else:
        cursor.execute("""
            SELECT
                transactions.id,
                transactions.type,
                categories.name,
                transactions.amount_cents,
                transactions.description,
                transactions.payment_method,
                transactions.transaction_date
            FROM transactions
            JOIN categories
                ON transactions.category_id = categories.id
            WHERE transactions.user_id = ?
            ORDER BY transactions.transaction_date DESC,
                     transactions.id DESC
        """, (user_id,))

    transactions = cursor.fetchall()

    connection.close()

    return transactions


# --------------------------------------------------
# GET ONE TRANSACTION
# --------------------------------------------------

def get_transaction_by_id(transaction_id, user_id):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            category_id,
            type,
            amount_cents,
            description,
            payment_method,
            transaction_date
        FROM transactions
        WHERE id = ?
          AND user_id = ?
    """, (transaction_id, user_id))

    transaction = cursor.fetchone()

    connection.close()

    return transaction


# --------------------------------------------------
# UPDATE TRANSACTION
# --------------------------------------------------

def update_transaction(
    transaction_id,
    user_id,
    category_id,
    t_type,
    amount_cents,
    description,
    payment_method,
    t_date
):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT id
        FROM categories
        WHERE id = ?
          AND user_id = ?
          AND type = ?
    """, (category_id, user_id, t_type))

    category = cursor.fetchone()

    if not category:
        connection.close()
        raise ValueError("Invalid category for this transaction.")

    if not isinstance(amount_cents, int) or amount_cents <= 0:
        connection.close()
        raise ValueError(
            "Amount must be a positive integer number of cents."
        )

    cursor.execute("""
        UPDATE transactions
        SET
            category_id = ?,
            type = ?,
            amount_cents = ?,
            description = ?,
            payment_method = ?,
            transaction_date = ?
        WHERE id = ?
          AND user_id = ?
    """, (
        category_id,
        t_type,
        amount_cents,
        description,
        payment_method,
        t_date,
        transaction_id,
        user_id
    ))

    connection.commit()
    connection.close()


# --------------------------------------------------
# DELETE TRANSACTION
# --------------------------------------------------

def delete_transaction(transaction_id, user_id):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM transactions
        WHERE id = ?
          AND user_id = ?
    """, (transaction_id, user_id))

    connection.commit()
    connection.close()


# --------------------------------------------------
# CATEGORY BREAKDOWN
# --------------------------------------------------

def get_category_breakdown(user_id, month=None):
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    if month:
        query = """
            SELECT
                c.name AS category_name,
                t.type,
                SUM(t.amount_cents) AS total_cents
            FROM transactions t
            JOIN categories c
                ON t.category_id = c.id
            WHERE t.user_id = ?
              AND strftime('%Y-%m', t.transaction_date) = ?
            GROUP BY c.id, t.type
            ORDER BY total_cents DESC
        """

        cursor.execute(query, (user_id, month))

    else:
        query = """
            SELECT
                c.name AS category_name,
                t.type,
                SUM(t.amount_cents) AS total_cents
            FROM transactions t
            JOIN categories c
                ON t.category_id = c.id
            WHERE t.user_id = ?
            GROUP BY c.id, t.type
            ORDER BY total_cents DESC
        """

        cursor.execute(query, (user_id,))

    rows = cursor.fetchall()

    connection.close()

    breakdown = []

    for row in rows:
        breakdown.append({
            "category": row["category_name"],
            "type": row["type"],
            "total": row["total_cents"] / 100.0,
        })

    return breakdown


# --------------------------------------------------
# MONTHLY & ALL-TIME SUMMARY REPORTS
# --------------------------------------------------

def get_monthly_summary(user_id, year_month):
    """Calculates high-level metrics for a specific month."""

    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT SUM(amount_cents)
        FROM transactions
        WHERE user_id = ?
          AND type = 'income'
          AND strftime('%Y-%m', transaction_date) = ?
    """, (user_id, year_month))

    income_res = cursor.fetchone()[0]
    income_cents = income_res if income_res else 0

    cursor.execute("""
        SELECT SUM(amount_cents)
        FROM transactions
        WHERE user_id = ?
          AND type = 'expense'
          AND strftime('%Y-%m', transaction_date) = ?
    """, (user_id, year_month))

    expense_res = cursor.fetchone()[0]
    expense_cents = expense_res if expense_res else 0

    connection.close()

    total_income = income_cents / 100.0
    total_expenses = expense_cents / 100.0
    net_savings = total_income - total_expenses

    savings_rate = 0.0

    if total_income > 0:
        savings_rate = round(
            (net_savings / total_income) * 100,
            1
        )

    return {
        "label": f"Monthly Financial Summary ({year_month})",
        "income": total_income,
        "expenses": total_expenses,
        "net_savings": net_savings,
        "savings_rate": savings_rate,
    }


def get_all_time_summary(user_id):
    """Calculates high-level metrics across all lifetime transactions."""

    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT SUM(amount_cents)
        FROM transactions
        WHERE user_id = ?
          AND type = 'income'
    """, (user_id,))

    income_res = cursor.fetchone()[0]
    income_cents = income_res if income_res else 0

    cursor.execute("""
        SELECT SUM(amount_cents)
        FROM transactions
        WHERE user_id = ?
          AND type = 'expense'
    """, (user_id,))

    expense_res = cursor.fetchone()[0]
    expense_cents = expense_res if expense_res else 0

    connection.close()

    total_income = income_cents / 100.0
    total_expenses = expense_cents / 100.0
    net_savings = total_income - total_expenses

    savings_rate = 0.0

    if total_income > 0:
        savings_rate = round(
            (net_savings / total_income) * 100,
            1
        )

    return {
        "label": "All-Time Financial Summary",
        "income": total_income,
        "expenses": total_expenses,
        "net_savings": net_savings,
        "savings_rate": savings_rate,
    }


# ==================================================
# BUDGET MANAGEMENT
# ==================================================

# --------------------------------------------------
# VALIDATE MONTH
# --------------------------------------------------

def validate_budget_month(month):
    """
    Make sure the budget month uses YYYY-MM format.
    Example: 2026-09
    """

    try:
        datetime.strptime(month, "%Y-%m")
    except (ValueError, TypeError):
        raise ValueError(
            "Budget month must be in YYYY-MM format."
        )


# --------------------------------------------------
# SET / UPDATE BUDGET
# --------------------------------------------------

def set_budget(
    user_id,
    category_id,
    month,
    limit_cents
):
    """
    Create or update a monthly budget.

    Only expense categories belonging to the current
    user can have budgets.
    """

    validate_budget_month(month)

    if not isinstance(limit_cents, int) or limit_cents <= 0:
        raise ValueError(
            "Budget limit must be a positive integer number of cents."
        )

    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    # Make sure the category belongs to the user
    # and is an expense category.
    cursor.execute("""
        SELECT id
        FROM categories
        WHERE id = ?
          AND user_id = ?
          AND type = 'expense'
    """, (category_id, user_id))

    category = cursor.fetchone()

    if not category:
        connection.close()
        raise ValueError(
            "Invalid expense category for this budget."
        )

    # Check whether this budget already exists.
    cursor.execute("""
        SELECT id
        FROM budgets
        WHERE user_id = ?
          AND category_id = ?
          AND month = ?
    """, (user_id, category_id, month))

    existing_budget = cursor.fetchone()

    if existing_budget:
        cursor.execute("""
            UPDATE budgets
            SET limit_cents = ?
            WHERE id = ?
              AND user_id = ?
        """, (
            limit_cents,
            existing_budget[0],
            user_id
        ))

    else:
        cursor.execute("""
            INSERT INTO budgets (
                user_id,
                category_id,
                month,
                limit_cents
            )
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            category_id,
            month,
            limit_cents
        ))

    connection.commit()
    connection.close()


# --------------------------------------------------
# GET USER BUDGETS
# --------------------------------------------------

def get_user_budgets(user_id, month):
    """
    Return all budgets for a user for a specific month.
    """

    validate_budget_month(month)

    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            b.id,
            b.category_id,
            c.name AS category_name,
            b.month,
            b.limit_cents
        FROM budgets b
        JOIN categories c
            ON b.category_id = c.id
        WHERE b.user_id = ?
          AND b.month = ?
        ORDER BY c.name
    """, (user_id, month))

    rows = cursor.fetchall()

    connection.close()

    budgets = []

    for row in rows:
        budgets.append({
            "id": row["id"],
            "category_id": row["category_id"],
            "category": row["category_name"],
            "month": row["month"],
            "limit": row["limit_cents"] / 100.0,
            "limit_cents": row["limit_cents"],
        })

    return budgets


# --------------------------------------------------
# BUDGET STATUS
# --------------------------------------------------

def get_budget_status(user_id, month):
    """
    Compare each monthly budget against actual spending.

    Status rules:

        0% - 79.99%  -> On Track
        80% - 99.99% -> Near Limit
        100%+        -> Over Budget
    """

    validate_budget_month(month)

    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            b.id AS budget_id,
            b.category_id,
            c.name AS category_name,
            b.month,
            b.limit_cents,

            COALESCE(
                SUM(
                    CASE
                        WHEN t.type = 'expense'
                        THEN t.amount_cents
                        ELSE 0
                    END
                ),
                0
            ) AS spent_cents

        FROM budgets b

        JOIN categories c
            ON b.category_id = c.id

        LEFT JOIN transactions t
            ON t.category_id = b.category_id
            AND t.user_id = b.user_id
            AND t.type = 'expense'
            AND strftime('%Y-%m', t.transaction_date) = b.month

        WHERE b.user_id = ?
          AND b.month = ?

        GROUP BY
            b.id,
            b.category_id,
            c.name,
            b.month,
            b.limit_cents

        ORDER BY c.name
    """, (user_id, month))

    rows = cursor.fetchall()

    connection.close()

    budget_status = []

    for row in rows:
        limit_cents = row["limit_cents"]
        spent_cents = row["spent_cents"]

        if limit_cents > 0:
            percentage = (
                spent_cents / limit_cents
            ) * 100
        else:
            percentage = 0

        if percentage >= 100:
            status = "Over Budget"
        elif percentage >= 80:
            status = "Near Limit"
        else:
            status = "On Track"

        budget_status.append({
            "budget_id": row["budget_id"],
            "category_id": row["category_id"],
            "category": row["category_name"],
            "month": row["month"],

            "limit": limit_cents / 100.0,
            "limit_cents": limit_cents,

            "spent": spent_cents / 100.0,
            "spent_cents": spent_cents,

            "percentage": round(percentage, 1),
            "status": status,
        })

    return budget_status


# --------------------------------------------------
# DELETE BUDGET
# --------------------------------------------------

def delete_budget(budget_id, user_id):
    """
    Delete a budget belonging to the current user.
    """

    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM budgets
        WHERE id = ?
          AND user_id = ?
    """, (budget_id, user_id))

    connection.commit()

    deleted = cursor.rowcount

    connection.close()

    return deleted > 0


# --------------------------------------------------
# DATABASE STARTUP
# --------------------------------------------------

if __name__ == "__main__":
    create_database()
    print("Database is ready!")