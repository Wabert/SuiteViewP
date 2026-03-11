' Module: frmChooseLink.frm
' Type: Standard Module
' Stream Path: VBA/frmChooseLink
' =========================================================

Attribute VB_Name = "frmChooseLink"
Attribute VB_Base = "0{C7EC5850-6301-4414-8E42-EB43BE030308}{AFFDE2A0-D4FE-4947-97D1-C943708016FC}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False

Private Const INT_FORM_WIDTH = 245
Private Const INT_FORM_HEIGHT = 72
Private Const URL_FORM_WIDTH = 492
Private Const URL_FORM_HEIGHT = 125

Private dctInfo As Dictionary

Public Property Set DataDictionary(dct As Dictionary)
    Me.width = INT_FORM_WIDTH
    Me.height = INT_FORM_HEIGHT
    Set dctInfo = dct
End Property
Private Function FileFolderPicker(dtype As MsoFileDialogType)
   Dim fd As FileDialog
   Set fd = Application.FileDialog(dtype)
    With fd
        .AllowMultiSelect = False
        If .Show = -1 Then FileFolderPicker = .SelectedItems(1)
    End With
End Function

Private Sub Label_LinkAction_Click()
    If OptionButton_File Then
        dctInfo.Add "linkpath", FileFolderPicker(msoFileDialogFilePicker)
        dctInfo.Add "linkname", LastComponent(dctInfo("linkpath"))
        dctInfo.Add "linktype", "File"
    End If
    If OptionButton_Folder Then
        dctInfo.Add "linkpath", FileFolderPicker(msoFileDialogFolderPicker)
        dctInfo.Add "linkname", LastComponent(dctInfo("linkpath"))
        dctInfo.Add "linktype", "Folder"
    End If
    If Me.OptionButton_URL Then
            Dim link As String, name As String
            link = TextBox_URLPath.value
            name = TextBox_URLLinkName
            If Not IsValidUrl(link) Then
                MsgBox "URL not valid, please try again.", vbOKCancel
                Exit Sub
            Else
                If name = "" Then
                    MsgBox "Please input Name", vbOKCancel
                    Exit Sub
                End If
                dctInfo.Add "linkpath", link
                dctInfo.Add "linkname", name
                dctInfo.Add "linktype", "Web"
            End If
    End If
    Unload Me
End Sub


Private Sub OptionButton_File_Click()
        Me.width = INT_FORM_WIDTH
        Me.height = INT_FORM_HEIGHT
End Sub

Private Sub OptionButton_Folder_Click()
        Me.width = INT_FORM_WIDTH
        Me.height = INT_FORM_HEIGHT
End Sub

Private Sub OptionButton_URL_Click()
        Me.width = URL_FORM_WIDTH
        Me.height = URL_FORM_HEIGHT
End Sub
