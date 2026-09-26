from datetime import datetime
from decimal import Decimal, InvalidOperation
from collections import defaultdict
import csv
import io

from flask import (
    Flask,
    redirect,
    render_template,
    request,
    session,
    url_for,
    Response,
    flash,
)

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie

from database import (
    add_transaction,
    delete_transaction,
    get_all_time_summary,
    get_monthly_summary,
    get_transaction_by_id,
    get_user_categories,
    get_user_transactions,
    login_user,
    register_user,
    update_transaction,
    set_budget,
    get_user_budgets,
    get_budget_status,
    delete_budget,
)


app = Flask(__name__)

app.secret_key = "supersecretkey"


# --------------------------------------------------
# HOME
# --------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# --------------------------------------------------
# REGISTER
# --------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]
        account_type = request.form["account_type"]

        try:

            user_id = register_user(
                username,
                password,
                account_type
            )

            print(f"New user registered with ID: {user_id}")

            return redirect(url_for("login"))

        except Exception as e:

            print(f"Error registering user: {e}")

            return f"Registration Error: {str(e)}", 400

    return render_template("register.html")


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        user = login_user(username, password)

        if user:

            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["account_type"] = user["account_type"]

            print(f"User {username} logged in successfully!")

            return redirect(url_for("dashboard"))

        else:

            return "Invalid username or password!", 400

    return render_template("login.html")


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    # Get selected month from URL
    # Example: /dashboard?month=2026-09
    selected_month = request.args.get("month", "")

    # Basic validation for YYYY-MM
    if selected_month:

        try:
            if len(selected_month) != 7:
                selected_month = ""

            elif selected_month[4] != "-":
                selected_month = ""

            else:
                int(selected_month[:4])
                int(selected_month[5:])

        except ValueError:
            selected_month = ""

    # Get user's categories
    categories = get_user_categories(user_id)

    # Get all user's transactions
    all_transactions = get_user_transactions(user_id)

    # --------------------------------------------------
    # FILTER TRANSACTIONS BY MONTH
    # --------------------------------------------------

    if selected_month:

        transactions = [
            tx for tx in all_transactions
            if tx[6].startswith(selected_month)
        ]

    else:

        transactions = all_transactions

    # --------------------------------------------------
    # CALCULATE TOTALS
    # --------------------------------------------------

    total_income_cents = 0
    total_expenses_cents = 0

    for tx in transactions:

        amount_cents = tx[3]
        transaction_type = tx[1]

        if transaction_type == "income":
            total_income_cents += amount_cents

        elif transaction_type == "expense":
            total_expenses_cents += amount_cents

    total_income = total_income_cents / 100.0
    total_expenses = total_expenses_cents / 100.0
    total_balance = total_income - total_expenses

    totals = {
        "balance": total_balance,
        "income": total_income,
        "expenses": total_expenses,
    }

    # --------------------------------------------------
    # CATEGORY BREAKDOWN
    # --------------------------------------------------

    breakdown = defaultdict(int)

    for tx in transactions:

        category_name = tx[2]
        transaction_type = tx[1]
        amount_cents = tx[3]

        breakdown[(category_name, transaction_type)] += amount_cents

    category_breakdown = []

    for (category_name, transaction_type), total_cents in breakdown.items():

        category_breakdown.append({
            "category": category_name,
            "type": transaction_type,
            "total": total_cents / 100.0,
        })

    # Put expenses first, then income
    category_breakdown.sort(
        key=lambda item: (
            0 if item["type"] == "expense" else 1,
            item["category"]
        )
    )

    # --------------------------------------------------
    # SUMMARY REPORTING (ALL-TIME VS MONTHLY)
    # --------------------------------------------------

    if selected_month:
        monthly_summary = get_monthly_summary(user_id, selected_month)
    else:
        monthly_summary = get_all_time_summary(user_id)

    # --------------------------------------------------
    # RENDER DASHBOARD
    # --------------------------------------------------

    return render_template(
        "dashboard.html",
        username=session["username"],
        account_type=session["account_type"],
        categories=categories,
        totals=totals,
        transactions=transactions,
        category_breakdown=category_breakdown,
        monthly_summary=monthly_summary,
        selected_month=selected_month,
    )


# --------------------------------------------------
# BUDGET ROUTES
# --------------------------------------------------

@app.route("/budgets", methods=["GET", "POST"])
def manage_budgets():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    selected_month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    
    if request.method == "POST":
        try:
            category_id = int(request.form.get("category_id"))
            limit_raw = float(request.form.get("limit"))
            limit_cents = int(limit_raw * 100)
            
            set_budget(user_id, category_id, selected_month, limit_cents)
            flash("Budget successfully saved!", "success")
        except (ValueError, TypeError) as e:
            flash(f"Error saving budget: {e}", "error")
            
        return redirect(url_for("manage_budgets", month=selected_month))
    
    all_categories = get_user_categories(user_id)
    expense_categories = [c for c in all_categories if c[2] == 'expense']
    budget_statuses = get_budget_status(user_id, selected_month)
    
    return render_template(
        "budgets.html",
        expense_categories=expense_categories,
        budget_statuses=budget_statuses,
        selected_month=selected_month
    )


@app.route("/budgets/delete/<int:budget_id>", methods=["POST"])
def remove_budget(budget_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    user_id = session["user_id"]
    selected_month = request.form.get("month", datetime.now().strftime("%Y-%m"))
    
    if delete_budget(budget_id, user_id):
        flash("Budget deleted successfully.", "success")
    else:
        flash("Could not delete budget.", "error")
        
    return redirect(url_for("manage_budgets", month=selected_month))


# --------------------------------------------------
# EXPORT TRANSACTIONS TO CSV
# --------------------------------------------------

@app.route("/export_transactions")
def export_transactions():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    # Get selected month
    selected_month = request.args.get("month", "")

    # Get all transactions
    all_transactions = get_user_transactions(user_id)

    # Filter by selected month
    if selected_month:

        transactions = [
            tx for tx in all_transactions
            if tx[6].startswith(selected_month)
        ]

    else:

        transactions = all_transactions

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "Date",
        "Type",
        "Category",
        "Amount (KES)",
        "Description",
        "Payment Method",
    ])

    for tx in transactions:

        transaction_type = tx[1]
        category_name = tx[2]
        amount_cents = tx[3]
        description = tx[4]
        payment_method = tx[5]
        transaction_date = tx[6]

        amount = amount_cents / 100

        writer.writerow([
            transaction_date,
            transaction_type,
            category_name,
            f"{amount:.2f}",
            description,
            payment_method,
        ])

    response = Response(
        output.getvalue(),
        mimetype="text/csv"
    )

    if selected_month:
        filename = f"money_tracker_transactions_{selected_month}.csv"
    else:
        filename = "money_tracker_transactions_all.csv"

    response.headers["Content-Disposition"] = (
        f"attachment; filename={filename}"
    )

    return response


# --------------------------------------------------
# EXPORT FINANCIAL REPORT TO PDF
# --------------------------------------------------

@app.route("/export_pdf")
def export_pdf():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    # ----------------------------------------------
    # GET SELECTED MONTH
    # ----------------------------------------------

    selected_month = request.args.get("month", "")

    all_transactions = get_user_transactions(user_id)

    if selected_month:

        transactions = [
            tx for tx in all_transactions
            if tx[6].startswith(selected_month)
        ]

    else:

        transactions = all_transactions


    # ----------------------------------------------
    # CALCULATE TOTALS
    # ----------------------------------------------

    total_income_cents = 0
    total_expenses_cents = 0

    expense_categories = defaultdict(int)

    for tx in transactions:

        amount_cents = tx[3]

        if tx[1] == "income":

            total_income_cents += amount_cents

        elif tx[1] == "expense":

            total_expenses_cents += amount_cents

            # Store expense amount by category
            expense_categories[tx[2]] += amount_cents


    net_savings_cents = (
        total_income_cents - total_expenses_cents
    )


    if total_income_cents > 0:

        savings_rate = (
            net_savings_cents / total_income_cents
        ) * 100

    else:

        savings_rate = 0


    # ----------------------------------------------
    # CASH FLOW STATUS
    # ----------------------------------------------

    if net_savings_cents >= 0:

        cash_flow_status = "Surplus"

    else:

        cash_flow_status = "Deficit"


    # ----------------------------------------------
    # CREATE PDF
    # ----------------------------------------------

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()

    story = []


    # ----------------------------------------------
    # TITLE
    # ----------------------------------------------

    report_period = (
        selected_month
        if selected_month
        else "All Transactions"
    )

    story.append(
        Paragraph(
            "Money Tracker Financial Report",
            styles["Title"]
        )
    )

    story.append(
        Paragraph(
            f"Period: {report_period}",
            styles["Heading2"]
        )
    )

    story.append(Spacer(1, 10))


    # ----------------------------------------------
    # FINANCIAL SUMMARY
    # ----------------------------------------------

    summary_data = [
        ["Financial Summary", "Amount"],

        [
            "Total Income",
            f"KES {total_income_cents / 100:,.2f}"
        ],

        [
            "Total Expenses",
            f"KES {total_expenses_cents / 100:,.2f}"
        ],

        [
            "Net Savings",
            f"KES {net_savings_cents / 100:,.2f}"
        ],

        [
            "Savings Rate",
            f"{savings_rate:.1f}%"
        ],

        [
            "Cash Flow Status",
            cash_flow_status
        ],
    ]


    summary_table = Table(
        summary_data,
        colWidths=[80 * mm, 70 * mm]
    )


    summary_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("PADDING", (0, 0), (-1, -1), 6),
        ])
    )


    story.append(summary_table)

    story.append(Spacer(1, 15))


    # ----------------------------------------------
    # EXPENSE BREAKDOWN CHART + TABLE
    # ----------------------------------------------

    if expense_categories:

        story.append(
            Paragraph(
                "Expense Breakdown",
                styles["Heading2"]
            )
        )

        story.append(Spacer(1, 5))


        # ------------------------------------------
        # PIE CHART
        # ------------------------------------------

        drawing = Drawing(
            450,
            250
        )

        pie = Pie()

        pie.x = 100
        pie.y = 20

        pie.width = 180
        pie.height = 180

        pie.labels = list(
            expense_categories.keys()
        )

        pie.data = list(
            expense_categories.values()
        )

        pie.sideLabels = True
        pie.simpleLabels = False

        drawing.add(pie)

        story.append(drawing)

        story.append(Spacer(1, 10))


        # ------------------------------------------
        # EXPENSE AMOUNT TABLE
        # ------------------------------------------

        expense_table_data = [
            [
                "Expense Category",
                "Amount",
                "% of Expenses"
            ]
        ]


        # Sort largest expenses first
        sorted_expenses = sorted(
            expense_categories.items(),
            key=lambda item: item[1],
            reverse=True
        )


        for category, amount_cents in sorted_expenses:

            percentage = (
                amount_cents / total_expenses_cents * 100
                if total_expenses_cents > 0
                else 0
            )

            expense_table_data.append([
                category,
                f"KES {amount_cents / 100:,.2f}",
                f"{percentage:.1f}%"
            ])


        expense_table = Table(
            expense_table_data,
            colWidths=[
                70 * mm,
                50 * mm,
                40 * mm
            ]
        )


        expense_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("PADDING", (0, 0), (-1, -1), 6),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ])
        )


        story.append(expense_table)

        story.append(Spacer(1, 15))


    # ----------------------------------------------
    # TRANSACTION HISTORY
    # ----------------------------------------------

    story.append(
        Paragraph(
            "Transaction History",
            styles["Heading2"]
        )
    )


    transaction_data = [
        [
            "Date",
            "Type",
            "Category",
            "Amount",
            "Payment",
            "Description",
        ]
    ]


    for tx in transactions:

        amount = tx[3] / 100

        transaction_data.append([
            tx[6],
            tx[1].title(),
            tx[2],
            f"KES {amount:,.2f}",
            tx[5],
            tx[4] or "",
        ])


    if len(transaction_data) == 1:

        transaction_data.append([
            "-",
            "-",
            "No transactions",
            "-",
            "-",
            "-",
        ])


    transaction_table = Table(
        transaction_data,
        repeatRows=1,
        colWidths=[
            25 * mm,
            20 * mm,
            30 * mm,
            30 * mm,
            25 * mm,
            45 * mm,
        ]
    )


    transaction_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 4),
        ])
    )


    story.append(transaction_table)


    # ----------------------------------------------
    # BUILD PDF
    # ----------------------------------------------

    document.build(story)

    buffer.seek(0)


    if selected_month:

        filename = (
            f"money_tracker_report_{selected_month}.pdf"
        )

    else:

        filename = (
            "money_tracker_report_all.pdf"
        )


    return Response(
        buffer.getvalue(),
        mimetype="application/pdf",
        headers={
            "Content-Disposition":
                f"attachment; filename={filename}"
        }
    )


# --------------------------------------------------
# ADD TRANSACTION
# --------------------------------------------------

@app.route("/add_transaction", methods=["POST"])
def add_trans():

    if "user_id" not in session:
        return redirect(url_for("login"))

    try:

        user_id = session["user_id"]

        category_id = request.form["category_id"]

        transaction_type = request.form["type"]

        # Convert amount safely into cents
        raw_amount = request.form["amount"]

        amount = Decimal(raw_amount)

        if amount <= 0:
            return "Amount must be greater than zero.", 400

        amount_cents = int(amount * 100)

        description = request.form.get(
            "description",
            ""
        )

        payment_method = request.form["payment_method"]

        transaction_date = request.form["transaction_date"]

        add_transaction(
            user_id,
            category_id,
            transaction_type,
            amount_cents,
            description,
            payment_method,
            transaction_date,
        )

        print("Transaction added successfully!")

        return redirect(url_for("dashboard"))

    except (InvalidOperation, ValueError):

        return "Invalid amount entered.", 400

    except Exception as e:

        print(f"Error adding transaction: {e}")

        return f"Error adding transaction: {str(e)}", 400


# --------------------------------------------------
# EDIT TRANSACTION
# --------------------------------------------------

@app.route("/edit_transaction/<int:tx_id>", methods=["GET", "POST"])
def edit_trans(tx_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    transaction = get_transaction_by_id(
        tx_id,
        user_id
    )

    if not transaction:

        return "Transaction not found or unauthorized.", 404

    if request.method == "POST":

        try:

            category_id = request.form["category_id"]

            transaction_type = request.form["type"]

            raw_amount = request.form["amount"]

            amount = Decimal(raw_amount)

            if amount <= 0:
                return "Amount must be greater than zero.", 400

            amount_cents = int(amount * 100)

            description = request.form.get(
                "description",
                ""
            )

            payment_method = request.form["payment_method"]

            transaction_date = request.form["transaction_date"]

            update_transaction(
                tx_id,
                user_id,
                category_id,
                transaction_type,
                amount_cents,
                description,
                payment_method,
                transaction_date,
            )

            print(
                f"Transaction {tx_id} updated successfully!"
            )

            return redirect(url_for("dashboard"))

        except (InvalidOperation, ValueError):

            return "Invalid amount entered.", 400

        except Exception as e:

            print(
                f"Error updating transaction: {e}"
            )

            return (
                f"Error updating transaction: {str(e)}",
                400
            )

    categories = get_user_categories(user_id)

    return render_template(
        "edit_transaction.html",
        transaction=transaction,
        categories=categories,
    )


# --------------------------------------------------
# DELETE TRANSACTION
# --------------------------------------------------

@app.route(
    "/delete_transaction/<int:tx_id>",
    methods=["POST"]
)
def delete_trans(tx_id):

    if "user_id" not in session:
        return redirect(url_for("login"))

    try:

        user_id = session["user_id"]

        delete_transaction(
            tx_id,
            user_id
        )

        print(
            f"Transaction {tx_id} deleted successfully!"
        )

        return redirect(url_for("dashboard"))

    except Exception as e:

        print(
            f"Error deleting transaction: {e}"
        )

        return (
            f"Error deleting transaction: {str(e)}",
            400
        )


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("index"))


# --------------------------------------------------
# START FLASK
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)