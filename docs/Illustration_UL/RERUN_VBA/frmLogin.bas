Attribute VB_Name = "frmLogin"
Attribute VB_Base = "0{BF7FD870-EF22-45D7-B3B9-85671F37D9FB}{E96CA161-6AA1-45E0-BD41-99D51BE66656}"
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
    TextBox_Comment.Value = strComment
End Property

