import re
import os

def extract_dict(dict_name, text):
    match = re.search(r'Set\s+' + dict_name + r'\s*=\s*CreateObject.*?End Function', text, re.DOTALL | re.IGNORECASE)
    if not match: return []
    items = []
    for line in match.group(0).split('\n'):
        if '.Add' in line:
            # Matches .Add "key", "value"
            m = re.search(r'\.Add\s+"([^"]+)"\s*,\s*"([^"]+)"', line)
            if m:
                items.append(f"{m.group(1)} - {m.group(2)}")
            else:
                # Sometimes it's .Add key:="key", item:="value"
                m2 = re.search(r'Item:="([^"]+)",\s*Key:="([^"]+)"', line)
                if m2:
                    items.append(f"{m2.group(2)} - {m2.group(1)}")
    return items

def main():
    try:
        with open('C:/Users/ab7y02/Dev/SuiteViewP/docs/VBA_Extracted/mdlDataItemSupport.bas.bas', encoding='utf-8', errors='ignore') as f:
            data_support_text = f.read()
    except Exception as e:
        print(f"Error reading mdlDataItemSupport: {e}")
        return

    try:
        with open('C:/Users/ab7y02/Dev/SuiteViewP/docs/VBA_Extracted/frmAudit.frm.bas', encoding='utf-8', errors='ignore') as f:
            frm_audit_text = f.read()
    except Exception as e:
        print(f"Error reading frmAudit: {e}")
        return

    out = []
    def print_section(title, items):
        out.append(f"### {title}")
        for item in items:
            out.append(f"- {item}")
        out.append("")

    # dictionaries from mdlDataItemSupport.bas.bas
    print_section('Status Code (01)', extract_dict('StatusDictionary', data_support_text))
    print_section('State', extract_dict('StateDictionary', data_support_text))
    print_section('Billing Form (01)', extract_dict('BillingFormDictionary', data_support_text))
    print_section('Primary & Secondary Dividend Option (01)', extract_dict('DividendOptionDictionary', data_support_text))
    print_section('Grace Period Rule Code (66)', extract_dict('GracePeriodRuleDictionary', data_support_text))
    
    # Inline lists from frmAudit.frm.bas
    def extract_array(listbox_name):
        # looks for ListBox_NAME.List = Array("...")
        match = re.search(f'{listbox_name}\\.List\\s*=\\s*Array\\((.*?)\\)', frm_audit_text, re.DOTALL | re.IGNORECASE)
        if match:
            # split by comma, ignoring newlines and underscores
            array_str = re.sub(r'_\\s*\\r?\\n', '', match.group(1))
            items = re.findall(r'"(.*?)"', array_str)
            return items
        return []

    print_section('Bill Mode (01)', extract_array('ListBox_BillMode'))
    print_section('Last Entry Code (01)', extract_array('ListBox_LastEntryCodes'))
    print_section('Grace Indicator (51 or 66)', extract_array('ListBox_GraceIndicator'))
    print_section('Suspense Code (01)', ["0 - Active", "2 - Suspend Processing", "3 - Death Claim Pending", "1 - Not used"])
    print_section('Definition of Life Insurance (66)', extract_array('ListBox_DefinitionOfLifeInsurance'))
    print_section('Loan Type (01)', extract_array('ListBox_LoanType'))
    print_section('Trad Overloan Ind (01)', extract_array('ListBox_OverloanIndicator'))
    print_section('Death Benefit Option (66)', extract_array('ListBox_DBOption'))
    print_section('NFO code (01)', extract_array('ListBox_NFO'))

    output_path = 'C:/Users/ab7y02/Dev/SuiteViewP/docs/audit/ListBoxItems.md'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# CL_POLREC_01_51_66 ListBox Items\\n\\n")
        f.write("\\n".join(out))
    
    print(f"Successfully generated {output_path}")

if __name__ == '__main__':
    main()
