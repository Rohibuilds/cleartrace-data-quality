# DataFix

DataFix is a small, local-first CSV data-quality prototype for the hackathon. It scans for missing values, exact duplicate rows, outer whitespace, case/spacing variants in categories, unrecognized dates in date/time columns, and possible numeric outliers.

## Run it

1. Install Python 3.9 or later.
2. In this folder, create and activate a virtual environment if you want dependency isolation.
3. Install dependencies with `python -m pip install -r requirements.txt`.
4. Start the app with `streamlit run app.py`.
5. Open the local URL printed by Streamlit. Choose **Load the demo dataset** or upload a CSV.

## Current prototype behavior

- CSV files are limited to 10 MB in the app.
- The working copy is held in the Streamlit session. Original upload is retained separately in session memory for comparison.
- Low-risk actions (trimming outer whitespace and removing exact duplicate rows) can be selected and applied.
- Category case/spacing normalization is offered as a review action and requires explicit selection.
- Missing values, invalid dates, and numeric outliers are findings only. The app does not invent replacements for them.
- The findings export describes the current working copy. The change-log export records accepted actions.
- These rule-based checks are indicators, not proof that data is correct or incorrect.

## Scope

The prototype does not claim to detect every data problem. It currently does not infer domain-specific rules, repair missing values, or validate that a value is true in the real world. The human reviewer remains responsible for ambiguous changes.
