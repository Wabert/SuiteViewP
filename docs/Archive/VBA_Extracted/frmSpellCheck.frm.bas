' Module: frmSpellCheck.frm
' Type: Standard Module
' Stream Path: VBA/frmSpellCheck
' =========================================================

Attribute VB_Name = "frmSpellCheck"
Attribute VB_Base = "0{AA44A367-ADB2-4D7E-ADB3-34BDBA584877}{AB44C0F2-6071-41D6-9B89-16F7D1CC3B39}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
'Dim MSWord As Word.Application
'
'Private Sub UserForm_Initialize()
'    Set MSWord = New Word.Application
'End Sub
'
'
'Private Sub CommandButton1_Click()
'    Dim text As String
'    Dim suggestion As Word.SpellingSuggestion
'    Dim colSuggestions As Word.SpellingSuggestions
'
'    If MSWord.Documents.Count = 0 Then MSWord.Documents.Add
'    text = Trim$(Me.TextBox1.text)
'
'    ListBox_Suggestions.Clear
'    If MSWord.CheckSpelling(text) Then
'        ListBox_Suggestions.AddItem "(correct)"
'    Else
'        Set colSuggestions = MSWord.GetSpellingSuggestions(text)
'        If colSuggestions.Count = 0 Then
'            ListBox_Suggestions.AddItem "(no suggestions)"
'        Else
'            For Each suggestion In colSuggestions
'                ListBox_Suggestions.AddItem suggestion.Name
'            Next
'        End If
'    End If
'
'End Sub


