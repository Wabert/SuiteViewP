import re

def main():
    vba_file = 'C:/Users/ab7y02/Dev/SuiteViewP/docs/VBA_Extracted/mdlDataItemSupport.bas.bas'
    frm_file = 'C:/Users/ab7y02/Dev/SuiteViewP/docs/VBA_Extracted/frmAudit.frm.bas'
    
    with open(vba_file, 'r', encoding='utf-8', errors='ignore') as f:
        vba_text = f.read()
        
    with open(frm_file, 'r', encoding='utf-8', errors='ignore') as f:
        frm_text = f.read()

    # Find all VBA Dictionary functions
    functions = re.finditer(r'(Public\s+)?(Function|Property Get)\s+([A-Za-z0-9_]+)\(\)(.*?)(End Function|End Property)', vba_text, re.DOTALL | re.IGNORECASE)

    dict_data = {}
    for f in functions:
        func_name = f.group(3)
        body = f.group(4)
        items = []
        for line in body.split('\n'):
            line = line.strip()
            # match: .Add "key", value (could be "string" or number)
            m1 = re.search(r'\.Add\s+"([^"]+)"\s*,\s*("[^"]+"|[^"\s]+)', line)
            if m1:
                val = m1.group(2).strip('"')
                items.append(f"{m1.group(1)} - {val}")
            else:
                # match: .Add Item:="value", Key:="key"  -- or numeric
                m2 = re.search(r'\.Add\s+Item:=\s*("[^"]+"|[^"\s]+)\s*,\s*Key:="([^"]+)"', line)
                if m2:
                    val = m2.group(1).strip('"')
                    items.append(f"{m2.group(2)} - {val}")
                else:
                    m3 = re.search(r'\.Add\s+Key:="([^"]+)"\s*,\s*Item:=\s*("[^"]+"|[^"\s]+)', line)
                    if m3:
                        val = m3.group(2).strip('"')
                        items.append(f"{m3.group(1)} - {val}")
                        
        if items:
            dict_data[func_name] = items

    # Find simple Array(...) assignments in frmAudit.frm.bas
    def extract_array(listbox_name):
        match = re.search(f'{listbox_name}\\.List\\s*=\\s*Array\\((.*?)\\)', frm_text, re.DOTALL | re.IGNORECASE)
        if match:
            array_str = re.sub(r'_\s*\r?\n', '', match.group(1))
            items = re.findall(r'"([^"]+)"', array_str)
            return items
        return []

    # Map the requested fields
    out = []
    def print_section(title, items):
        out.append(f"### {title}")
        for item in items:
            out.append(f"- {item}")
        out.append("")

    # dictionaries from mdlDataItemSupport.bas.bas
    print_section('Status Code (01)', dict_data.get('StatusDictionary', []))
    print_section('State', dict_data.get('StateDictionary', []))
    print_section('Billing Form (01)', dict_data.get('BillingFormDictionary', []))
    print_section('Primary & Secondary Dividend Option (01)', dict_data.get('DivOptionCodeDictionary', []))
    print_section('Grace Period Rule Code (66)', dict_data.get('GracePeriodRuleDictionary', []))
    print_section('Loan Type (01)', dict_data.get('LoanInterestTypeCodeDictionary', []))
    print_section('NFO code (01)', dict_data.get('NonForfeitureCodeDictionary', []))
    
    # Inline lists from frmAudit.frm.bas
    print_section('Bill Mode (01)', extract_array('ListBox_BillMode'))
    print_section('Last Entry Code (01)', dict_data.get('EntryCodeDictionary', [])) 
    print_section('Grace Indicator (51 or 66)', extract_array('ListBox_GraceIndicator'))
    print_section('Suspense Code (01)', extract_array('ListBox_SuspenseCode') or ["0 - Active", "2 - Suspend Processing", "3 - Death Claim Pending", "1 - Not used"])
    print_section('Definition of Life Insurance (66)', extract_array('ListBox_DefinitionOfLifeInsurance'))
    print_section('Trad Overloan Ind (01)', extract_array('ListBox_OverloanIndicator'))
    print_section('Death Benefit Option (66)', extract_array('ListBox_DBOption'))

    output_path = 'C:/Users/ab7y02/Dev/SuiteViewP/docs/audit/ListBoxItems.md'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# CL_POLREC_01_51_66 ListBox Items (VBA Exact Edition)\n\n")
        f.write("\n".join(out))
    
    print(f"Successfully generated {output_path}")

if __name__ == '__main__':
    main()
