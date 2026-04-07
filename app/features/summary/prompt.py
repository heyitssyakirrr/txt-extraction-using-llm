from __future__ import annotations


def build_summary_prompt(text: str) -> str:
    """Prompt for bank statement summary extraction."""
    return f"""\
You are a data extraction assistant for a Malaysian bank's internal system.
Your task is to analyse a bank statement and extract a structured summary.

=== RULES ===
1. Extract data for EVERY day that has transactions — do not skip any day.
2. Extract data for EVERY month present in the statement.
3. All monetary values must be returned as strings, preserving decimal places (e.g. "1234.56").
4. Dates must be in YYYY-MM-DD format.
5. Months must be in YYYY-MM format.
6. Return ONLY a raw JSON object — no markdown, no code blocks, no explanation.
7. Do NOT repeat or explain the fields. Output the JSON object and nothing else.

=== DEFINING WITHDRAWAL AND DEPOSIT ===
The document may use different terminology. Map them as follows:
- WITHDRAWAL = money going OUT of the account (debit, DR, withdrawal, "-" amount)
- DEPOSIT    = money coming IN to the account  (credit, CR, deposit, "+" amount)

=== WHAT TO EXTRACT ===

DAILY SUMMARIES:
For each day that has at least one transaction:
- date               : The date in YYYY-MM-DD format
- total_withdrawal   : Sum of all withdrawal amounts for that day
- total_deposit      : Sum of all deposit amounts for that day
- closing_balance    : The account balance at end of that day

MONTHLY SUMMARIES:
For each month present in the statement:
- month              : The month in YYYY-MM format
- total_withdrawal   : Sum of all withdrawals for that month
- total_deposit      : Sum of all deposits for that month
- min_balance        : The lowest balance recorded during that month
- max_balance        : The highest balance recorded during that month

OVERALL TOTALS (across the entire statement):
- overall_total_withdrawal : Grand total of all withdrawal amounts
- overall_total_deposit    : Grand total of all deposit amounts

=== DOCUMENT ===
\"\"\"
{text}
\"\"\"

=== OUTPUT ===
Return ONLY this JSON object with no other text:
{{
    "daily_summaries": [
        {{
            "date": "YYYY-MM-DD",
            "total_withdrawal": "0.00",
            "total_deposit": "0.00",
            "closing_balance": "0.00"
        }}
    ],
    "monthly_summaries": [
        {{
            "month": "YYYY-MM",
            "total_withdrawal": "0.00",
            "total_deposit": "0.00",
            "min_balance": "0.00",
            "max_balance": "0.00"
        }}
    ],
    "overall_total_withdrawal": "0.00",
    "overall_total_deposit": "0.00"
}}
"""