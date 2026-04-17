from __future__ import annotations

_KNOWN_BANKS = """\
- BSN (Bank Simpanan Nasional)
- CIMB Bank
- CIMB Islamic
- Maybank
- Maybank Islamic
- Alliance Bank
- Alliance Islamic Bank
- Hong Leong Bank
- Hong Leong Islamic Bank
- RHB Bank
- RHB Islamic Bank
- AmBank
- AmBank Islamic
- HSBC Bank
- HSBC Amanah
- OCBC Bank
- OCBC Al-Amin
- Public Bank Berhad
- Public Islamic Bank
- Kuwait Finance House
- Standard Chartered Bank
- Standard Chartered Saadiq Islamic
- Bank Islam
- Bank Muamalat
- Affin Bank
- Affin Islamic Bank
- Agro Bank
- Bank Rakyat
- UOB Bank
- Citibank
- MBSB Bank
- Bank of China"""


def build_extraction_prompt(text: str) -> str:
    """Prompt for customer detail extraction."""
    return f"""\
You are a data extraction assistant for a Malaysian bank's internal system.
Your task is to extract exactly six fields from a bank document.

=== RULES ===
0. You are in JSON-only mode. Your entire response must be a single JSON object. Stop immediately after the closing brace. No introduction, no explanation, no conclusion.
1. Return ONLY a raw JSON object — no markdown, no code blocks, no explanation.
2. Use the full context of the document to determine the correct values.
3. Do NOT repeat or explain the fields. Output the JSON object and nothing else.

================================================================================
FIELD 1 — NAME
================================================================================
- The full name of the customer / account holder.
- Malaysian names are typically printed in FULL CAPITAL LETTERS.
- Common formats:
    Malay  : AHMAD BIN HASSAN, SITI BINTI ALI
    Chinese: LEE CHONG WEI, TAN AH KOW
    Indian : RAMESH A/L RAJENDRAN, KAVITHA A/P SUBRAMANIAM
- Ignore names that are clearly a bank branch, law firm, company, or staff member.

================================================================================
FIELDS 2, 3, 4 — FI CODE, MASTER ACCOUNT, SUB ACCOUNT
================================================================================
These three values always appear together in a dedicated section near the bottom
of the document, under a heading such as:
    "FI CODE (ONLY APPLICABLE FOR REFINANCING)"
    "FACILITY ACCOUNT NO.", "ACCOUNT DETAILS", or similar.

The section ALWAYS lists the three values in this fixed logical order:
    1st value = FI Code              → fi_num
    2nd value = Master Account No.   → master_account_number
    3rd value = Sub Account No.      → sub_account_number

They can also be unstructured but they always appear together.

This section appears in ONE OF TWO layouts. Detect which one is present:

--- LAYOUT A: pipe/markdown table ---
All three values appear as cells in a single table row.
Example:
    | 022204026 | 205340722O/D88 | 342385069101SLUMYR |
      ^fi_num     ^master_acc      ^sub_acc

--- LAYOUT B: labeled key-value lines ---
Each value has its own line with an explicit label.
Example:
    FI CODE :            034907013
    MASTER ACCOUNT NO :  88820006220322
    SUB ACCOUNT NO :     00088820006220322

In BOTH layouts the logical order is identical:
    fi_num → master_account_number → sub_account_number

--- FI CODE (fi_num) ---
- A short institution/routing code — typically 7 to 9 digits.
- ALWAYS the shortest of the three values.
- May start with 0 (most banks) or 3 (BSN, Bank Rakyat).
- May contain underscores or hyphens (Maybank only): "0227_13014", "0227-11038".
- NOT a phone number, postcode, reference number, or RENTAS clearing account.
- If unsure between two candidates, choose the shorter purely-numeric one.

--- MASTER ACCOUNT NUMBER ---
- The primary loan/account identifier for the third-party bank.
- Usually longer than the FI code; may contain letters, slashes, or suffixes.
- Copy EXACTLY as printed — preserve all characters: leading zeros, letters, slashes, dashes, and suffixes.
- NEVER use the RENTAS/IBG payment account as the master account.
  The RENTAS account is labelled under a "RENTAS" or "IBG" payment instruction
  block (e.g. "Account No. 309-909570-005") and belongs to the bank's internal
  clearing system. It will NOT appear inside the FI Code section.

--- SUB ACCOUNT NUMBER ---
- A secondary account number in the same section, listed after the master account.
- Often differs from the master by a prefix, suffix, or leading zeros.
  Example: master = "205340722O/D88", sub = "342385069101SLUMYR" (different format).
- Some master and sub account number can also be the same number on some banks.
- Copy EXACTLY as printed.
- Return null ONLY if the section genuinely contains no third value.
- Do NOT duplicate the master account number as the sub account.

================================================================================
FIELD 5 — ADDRESS
================================================================================
- The customer's mailing or residential address.
- May span multiple lines — combine into one string separated by commas.
- Ignore bank branch addresses and law firm / third-party addresses (cc: blocks).
- Return null if no customer address is present.

================================================================================
FIELD 6 — BANK NAME
================================================================================
These documents are letters SENT BY Public Bank Berhad or Public Islamic Bank
TO a customer, about a third-party bank account being redeemed or refinanced.

- "Public Bank Berhad" and "Public Islamic Bank" are the SENDER — do NOT return
  them as the bank name unless they are genuinely the only bank in the document.
- The THIRD-PARTY bank is the one whose FI Code / Master Account / Sub Account
  appear in the dedicated section above. Its name appears in one of:
    * Signature block  : "for <Bank Name> Berhad", "Yours faithfully, <Bank Name>"
    * RENTAS/IBG block : "PAYABLE TO: <Bank Name>" or "Beneficiary: <Bank Name>"
    * Letterhead / address block near the FI Code section
- Match to the closest entry in the known bank list below.
- Strip suffixes absent from the list: "Berhad", "Malaysia Berhad", "(M) Berhad",
  company numbers like "(295576-U)", etc.
    e.g. "HSBC Bank Malaysia Berhad"  →  "HSBC Bank"
    e.g. "AmBank Islamic Berhad"      →  "AmBank Islamic"
- For Islamic variants (e.g. "Maybank Islamic", "HSBC Amanah"), return the
  Islamic canonical form exactly as it appears in the list.
- Return null ONLY if no third-party bank can be identified at all.

Known bank names — return the EXACT canonical form from this list:
{_KNOWN_BANKS}

================================================================================
O vs 0 DISAMBIGUATION RULE
================================================================================
OCR sometimes renders the letter O as the digit 0. Apply these rules:
- Suffixes such as "/D88", "/D66", "/D90" are ALWAYS preceded by the letter O:
    write "O/D88" — NOT "0/D88".
- Inside a purely numeric sequence with no suffix, treat ambiguous characters as 0.
- When in doubt at a suffix boundary, use the letter O.

================================================================================
DOCUMENT
================================================================================
\"\"\"
{text}
\"\"\"

================================================================================
STEP-BY-STEP EXTRACTION CHECKLIST
================================================================================
Work through these steps before writing the JSON:

STEP 1 — LOCATE THE FI CODE SECTION
  Search near the bottom of the document for a heading containing the words
  "FI CODE", "FI NUM", "FACILITY ACCOUNT", or "ACCOUNT DETAILS".

STEP 2 — DETECT THE LAYOUT
  Pipe characters (|) in that section → Layout A (table): read columns 1, 2, 3.
  Label lines (FI CODE :, MASTER ACCOUNT NO :) → Layout B: read each label's value.

STEP 3 — ASSIGN THE THREE VALUES IN ORDER
  fi_num                ← 1st value (shortest, 7–9 digits, possibly with _ or -)
  master_account_number ← 2nd value
  sub_account_number    ← 3rd value (or null if genuinely absent)

STEP 4 — SANITY-CHECK
  • fi_num is 7–9 characters max, never longer than the master account.
  • master_account_number ≠ fi_num.
  • sub_account_number = master_account_number (this can be happened for some banks).
  • None of these is a phone number, postcode, or RENTAS clearing account.

STEP 5 — FIND THE BANK NAME
  Check: signature block → RENTAS/IBG beneficiary label → letterhead near FI section.
  Map to canonical form. The sender (Public Bank / Public Islamic Bank) is NOT the answer.

STEP 6 — FIND THE CUSTOMER NAME
  All-caps Malaysian name. Exclude staff, bank, and law firm names.

STEP 7 — FIND THE CUSTOMER ADDRESS (if any)
  Exclude bank branch and law firm (cc:) addresses.

STEP 8 — OUTPUT THE JSON.

================================================================================
OUTPUT
================================================================================
Return ONLY this JSON object with no other text or explanation:
{{
    "name": "<full customer name or null>",
    "master_account_number": "<master account number copied exactly as printed, or null>",
    "sub_account_number": "<sub account number copied exactly as printed, or null>",
    "address": "<full address or null>",
    "fi_num": "<FI number copied exactly as printed, or null>",
    "bank_name": "<canonical bank name from the known list, or null>"
}}
"""