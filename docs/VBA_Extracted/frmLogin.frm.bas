' Module: frmLogin.frm
' Type: Standard Module
' Stream Path: VBA/frmLogin
' =========================================================

Attribute VB_Name = "frmLogin"
Attribute VB_Base = "0{9D99AE67-410D-46E2-B7FF-EA3A544476C5}{D59DDE6A-948F-4674-8BCB-73E383E4D7F1}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False

Private dctInfo As Dictionary

Public Property Set DataDictionary(dct As Dictionary)
    Set dctInfo = dct
End Property


Private Sub btn_SubmitUserID_Click()
    dctInfo.RemoveAll
    dctInfo.Add "UserID", Me.txt_UserID
    dctInfo.Add "PWD", Me.txt_PWD
    Unload Me
End Sub

Public Property Let Comment(strComment As String)
    TextBox_Comment.value = strComment
End Property

