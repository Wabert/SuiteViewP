' Module: frmLinkTip.frm
' Type: Standard Module
' Stream Path: VBA/frmLinkTip
' =========================================================

Attribute VB_Name = "frmLinkTip"
Attribute VB_Base = "0{0A3F93BE-3469-4F5C-A54F-8F542740283F}{61F39430-7750-4550-8D68-D6A1FED1A43E}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False

Private Sub Label_CoverAll_MouseUp(ByVal Button As Integer, ByVal Shift As Integer, ByVal X As Single, ByVal Y As Single)

    MsgBox "Hello " & Me.Label_Linkname

End Sub

