import re

def main():
    file_path = 'C:/Users/ab7y02/Dev/SuiteViewP/docs/audit/ListBoxItems.md'
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Add Billing Form
    billing_form = """### Billing Form (01)
- 0 - Direct pay notice
- 1, A - Home office
- 2, B - Permanent APL
- 3, C - Premium depositor fund
- 4 - Discounted premium deposit
- 6, F - Government allotment
- 7, G - PAC
- 8, H - Salary deduction
- 9, I - Bank deduction
- J - Dividend
- Q - Permanent APP
- V - Net vanish (offset) premium
"""
    content = content.replace('### Billing Form (01)\n\n', billing_form + '\n')
    
    # Add DB Option
    db_option = """### Death Benefit Option (66)
- 1 - Level Death Benefit (Option A)
- 2 - Increasing Death Benefit (Option B)
- 3 - Return of Premium (Option C)
"""
    content = content.replace('### Death Benefit Option (66)\n\n', db_option + '\n')
    
    # Just to be safe, if DB option was literally at EOF:
    if '### Death Benefit Option (66)\n' in content and 'Level' not in content:
        content = content.replace('### Death Benefit Option (66)\n', db_option + '\n')

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content.strip() + '\n')
        
    print("Fixed ListBoxItems.md")

if __name__ == '__main__':
    main()
