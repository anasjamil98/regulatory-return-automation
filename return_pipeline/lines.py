"""The lines of the return, in the order they appear on the form.

The SQL produces values; this file says which lines must exist. If the SQL
returns a line that isn't listed here, or misses one that is, the run stops.
"""

from collections import OrderedDict

# code -> (section, label, has_value)
RETURN_LINES = OrderedDict(
    [
        ("A1", ("A. Customer accounts", "Registered customers at period end", False)),
        ("A2", ("A. Customer accounts", "New registrations in period", False)),
        ("A3", ("A. Customer accounts", "Active customers in period", False)),
        ("B1", ("B. Successful transactions", "Person-to-person transfers", True)),
        ("B2", ("B. Successful transactions", "Merchant payments", True)),
        ("B3", ("B. Successful transactions", "Card payments", True)),
        ("B4", ("B. Successful transactions", "Bill payments", True)),
        ("B5", ("B. Successful transactions", "Cash in", True)),
        ("B6", ("B. Successful transactions", "Cash out", True)),
        ("B9", ("B. Successful transactions", "Total successful transactions", True)),
        ("C1", ("C. Incomplete transactions", "Failed transactions", True)),
        ("C2", ("C. Incomplete transactions", "Reversed transactions", True)),
        ("D1", ("D. Fees", "Fees charged", True)),
    ]
)

TYPE_LINES = ["B1", "B2", "B3", "B4", "B5", "B6"]
KNOWN_STATUSES = ("success", "failed", "reversed")
