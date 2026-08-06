' Module: DBConnection.frm
' Type: Standard Module
' Stream Path: VBA/DBConnection
' =========================================================

Attribute VB_Name = "DBConnection"
Attribute VB_Base = "0{29452E47-8956-4CC4-8F31-30BADE089B03}{2178F13D-F20D-4208-8F12-BDB8DECC75C7}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Private pDct As Dictionary

Property Set ParamterDictionary(dct As Dictionary)
    Set pDct = dct
End Property
Property Get PromptLabel() As MSForms.Label
    Set PromptLabel = Me.Label1
End Property
Private Sub CommandButton1_Click()
  pDct(1) = TextBox_PWD.value
  Me.Hide
End Sub
