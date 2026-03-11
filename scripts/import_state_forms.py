
import os
import sys
import openpyxl
import sqlite3
import logging

# Add project root to sys.path to import modules
sys.path.append(os.getcwd())

from suiteview.abrquote.models.abr_database import get_abr_database

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXCEL_FILE = r"C:\Users\ab7y02\Dev\SuiteViewP\docs\ABRQuote\StateForms.xlsx"

def import_state_forms():
    if not os.path.exists(EXCEL_FILE):
        logger.error(f"Excel file not found: {EXCEL_FILE}")
        return

    try:
        wb = openpyxl.load_workbook(EXCEL_FILE)
        ws = wb.active
        
        # headers are in the first row, data starts from second row
        rows_to_insert = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            # Row structure: CL_State_Code, StateAbbr, State, StateGroup, Election_Form, ...
            # Ensure we have enough columns or handle None
            if not row or not row[1]: # Skip if no StateAbbr
                continue
                
            # Maps to columns:
            # cl_state_code, state_abbr, state_name, state_group,
            # election_form, disclosure_form_critical, 
            # disclosure_form_chronic, disclosure_form_terminal
            
            # Excel columns order based on previous check:
            # 0: CL_State_Code
            # 1: StateAbbr
            # 2: State (Name)
            # 3: StateGroup
            # 4: Election_Form
            # 5: Disclosure_Form_Critical
            # 6: Disclosure_Form_Chronic
            # 7: Disclosure_Form_Terminal
            
            # Map to DB schema:
            # (state_abbr, cl_state_code, state_name, state_group,
            #  election_form, disclosure_form_critical, 
            #  disclosure_form_chronic, disclosure_form_terminal)
            
            # Note: DB schema has state_abbr first as PK in INSERT statement I used earlier, 
            # but I can specify columns in INSERT.
            
            # Let's clean up data
            cl_code = row[0]
            abbr = row[1]
            name = row[2]
            group = row[3]
            elect = row[4]
            crit = row[5]
            chron = row[6]
            term = row[7]
            
            rows_to_insert.append((
                abbr, cl_code, name, group, elect, crit, chron, term
            ))
            
        if not rows_to_insert:
            logger.warning("No data found in Excel file.")
            return

        db = get_abr_database()
        conn = db.connect()
        
        # Clear existing data? usually imports replace.
        conn.execute("DELETE FROM state_forms")
        
        conn.executemany(
            """
            INSERT INTO state_forms (
                state_abbr, cl_state_code, state_name, state_group,
                election_form, disclosure_form_critical, 
                disclosure_form_chronic, disclosure_form_terminal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows_to_insert
        )
        
        # Update metadata
        db.update_import_metadata("state_forms", len(rows_to_insert), EXCEL_FILE)
        
        conn.commit()
        logger.info(f"Successfully imported {len(rows_to_insert)} state forms.")
        
    except Exception as e:
        logger.error(f"Failed to import state forms: {e}", exc_info=True)

if __name__ == "__main__":
    import_state_forms()
