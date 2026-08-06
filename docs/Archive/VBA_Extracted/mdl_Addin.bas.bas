' Module: mdl_Addin.bas
' Type: Standard Module
' Stream Path: VBA/mdl_Addin
' =========================================================

Attribute VB_Name = "mdl_Addin"
Sub SaveWorkbookAsAddIn()
    Dim addInPath As String
    Dim addInName As String
    Dim fso As Object
    Dim FileExists As Boolean
    Dim response As VbMsgBoxResult

    ' Define the add-in name and path based on the workbook name
    addInName = left(ThisWorkbook.name, InStrRev(ThisWorkbook.name, ".") - 1)
    addInFileName = addInName & ".xlam"
    addInFilePath = Application.UserLibraryPath & addInFileName


    If AddInFileExists(addInFilePath) Then
        ' Prompt the user to confirm overwrite
        response = MsgBox("The add-in already exists. Do you want to overwrite it? " & Chr(13) & Chr(13) & "This will overwrite you existing links.", vbYesNo + vbQuestion, "Overwrite Add-In")
        If response = vbNo Then Exit Sub
        
        If AddInIsLoaded(addInName) Then
            Set addIn = Application.AddIns(addInName)
            addIn.Installed = False
        End If
    End If
        
    
    On Error Resume Next
    Application.DisplayAlerts = False
    ' Save the workbook as an add-in
    ThisWorkbook.SaveAs filename:=addInFilePath, FileFormat:=xlOpenXMLAddIn
    Set addIn = Application.AddIns.Add(addInFilePath)
    addIn.Installed = True
    Application.DisplayAlerts = True
    
    If Err.Number > 0 Then GoTo ErrorHandler
    
    On Error GoTo 0
    
    MsgBox "Workbook saved as add-in successfully! " & Chr(13) & Chr(13) & "The Add-In will now appear for any excel workbook you open.  You can close this workbook and you dont have to open it again.", vbInformation, "Success"

    Exit Sub
    
ErrorHandler:
    MsgBox "There was an error trying to save the file.  Error Description:  " & Err.Description
    


End Sub

Sub OpenAddInsFolder()
    Dim addInPath As String
    ' Get the path to the user's add-in folder
    addInPath = Application.UserLibraryPath
    ' Open the add-in folder in Windows Explorer
    shell "explorer.exe " & addInPath, vbNormalFocus
End Sub

Function AddInFileExists(addInPath) As Boolean
    ' Check if file already exists
    Set fso = CreateObject("Scripting.FileSystemObject")
    AddInFileExists = fso.FileExists(addInPath)
End Function

Function AddInIsLoaded(addInTitle As String)
    'AddInTitle is the name of the workbook without the xlam extension
    On Error Resume Next
    Set addIn = Application.AddIns(addInTitle)
    On Error GoTo 0
    If IsEmpty(addIn) Then
        AddInIsLoaded = False
        Exit Function
    End If
    
    If addIn Is Nothing Then
        AddInIsLoaded = False
        Exit Function
    End If
        
    AddInIsLoaded = True
            
End Function

Sub CheckAddIn()
    Dim addInName As String
    Dim addInPath As String
    Dim addIn As addIn
    Dim addInTitle As String

    ' Define the add-in name based on the workbook name
    addInName = ThisWorkbook.name
    addInName = left(addInName, InStrRev(addInName, ".")) & "xlam"
    addInPath = Application.UserLibraryPath & addInName

    ' Extract the title of the add-in from the file name
    addInTitle = left(addInName, InStrRev(addInName, ".") - 1)

    ' Check if the add-in is already loaded
    On Error Resume Next
    Set addIn = Application.AddIns(addInTitle)
    On Error GoTo 0

    If addIn Is Nothing Then
        ' Add the add-in if it's not already loaded
        Set addIn = Application.AddIns.Add(addInPath)
    End If

    ' Check the add-in to make it active
    addIn.Installed = True

    MsgBox "Add-in '" & addInTitle & "' has been checked and is now active.", vbInformation, "Add-In Activated"
End Sub



