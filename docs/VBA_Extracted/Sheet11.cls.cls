' Module: Sheet11.cls
' Type: Document Module
' Stream Path: VBA/Sheet11
' =========================================================

Attribute VB_Name = "Sheet11"
Attribute VB_Base = "0{00020820-0000-0000-C000-000000000046}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = True
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = True
Attribute VB_Control = "cmdPrintTables, 1, 0, MSForms, CommandButton"
Private Sub cmdPrintTables_Click()

PrintDB2TablesByPolicy Range("sPrintTables_PolicyNumber").value, Range("vPrintTables_TableList")


End Sub
