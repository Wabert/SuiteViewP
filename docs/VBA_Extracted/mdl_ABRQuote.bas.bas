' Module: mdl_ABRQuote.bas
' Type: Standard Module
' Stream Path: VBA/mdl_ABRQuote
' =========================================================

Attribute VB_Name = "mdl_ABRQuote"
Public Const mABR_FOLDER As String = "\\sranico7\data\shared\+++PROCESS CONTROL+++\Systems\Shoebox Administration\Accelerated Death Benefit (ABR11 & ABR14)\Policies"
Public Const mABR_UL_TOOL_FOLDER = "\\sranico7\data\shared\+++PROCESS CONTROL+++\Systems\Shoebox Administration\Accelerated Death Benefit (ABR11 & ABR14)\UL&WL"
Public Const mRERUN_FOLDER = "\\sranico7\data\shared\+++PROCESS CONTROL+++\Tools\Illustration\RERUN"

Public mABRPolicyFolder As String
Private mPol As cls_PolicyInformation

Public Sub ABR_SetPolicy(pol As cls_PolicyInformation)
    Set mPol = pol
End Sub
Public Sub SetABRPolicyFolder(folderPath As String)
    mABRPolicyFolder = folderPath
End Sub

Public Sub ABR_CreatePolicyFolder()
    Dim fso As Object
    Dim folderPath As String
    
    mABRPolicyFolder = ABR_CheckForPolicyFolder
    
    If mABRPolicyFolder = "" Then
        ' If folder not found, create it
        mABRPolicyFolder = mABR_FOLDER & "\" & UCase(mPol.PolicyNumber)
        CreateFolder mABRPolicyFolder
    End If

End Sub



Public Function ABR_CheckForPolicyFolder() As String
    Dim fso As Object
    Dim folder As Object
    Dim folderPath As String
    Dim baseDirectory As String

    PolicyNumber = mPol.PolicyNumber
    baseDirectory = mABR_FOLDER

    ' Create FileSystemObject
    Set fso = CreateObject("Scripting.FileSystemObject")

    ' Check if base directory exists
    If Not fso.FolderExists(baseDirectory) Then
        MsgBox "Base directory does not exist.", vbExclamation
        ABR_CheckForPolicyFolder = False
        Exit Function
    End If

    Dim blnPolicyPolicyExists As Boolean
    folderPath = baseDirectory & "\" & PolicyNumber
    blnPolicyPolicyExists = FolderExists(baseDirectory & "\" & PolicyNumber)
    
    If blnPolicyPolicyExists Then
        mABRPolicyFolder = folderPath
        ABR_CheckForPolicyFolder = folderPath
    End If


End Function

Public Sub ABR_CopyMostRecentExcelFile(destinationFolder As String, baseFileName As String)
    Dim fso As Object
    Dim sourceDir As Object
    Dim file As Object
    Dim mostRecentFile As Object
    Dim highestVersion As Double
    Dim currentVersion As Double
    Dim versionStr As String
    Dim sourcefolder As String
    
    baseFileName = "ABR Quote System monthly calc"
    sourcefolder = mABRPolicyFolder
    
    ' Create FileSystemObject
    Set fso = CreateObject("Scripting.FileSystemObject")
    
    ' Check if source and destination folders exist
    If Not fso.FolderExists(sourcefolder) Or Not fso.FolderExists(destinationFolder) Then
        MsgBox "Source or destination folder does not exist.", vbExclamation
        
        Exit Sub
    End If
    
    ' Get the source directory
    Set sourceDir = fso.GetFolder(sourcefolder)
    
    ' Initialize highest version
    highestVersion = -1
    
    ' Loop through all files in the source folder
    For Each file In sourceDir.files
        ' Check if the file name starts with the base file name and ends with .xls or .xlsx
        If file.name Like baseFileName & "*.[xX][lL][sS]*" Then
            ' Extract version number
            versionStr = Mid(file.name, Len(baseFileName) + 2)
            versionStr = left(versionStr, Len(versionStr) - 4) ' Remove file extension
            versionStr = Replace(versionStr, ")", "") ' Remove closing parenthesis
            
            ' Convert version string to number
            If IsNumeric(versionStr) Then
                currentVersion = CDbl(versionStr)
                
                ' Update most recent file if current version is higher
                If currentVersion > highestVersion Then
                    highestVersion = currentVersion
                    Set mostRecentFile = file
                End If
            End If
        End If
    Next file
    
    ' Check if a file was found
    If mostRecentFile Is Nothing Then
        MsgBox "No matching files found.", vbExclamation
        Exit Sub
    End If
    
    ' Copy the most recent file to the destination folder
    fso.CopyFile mostRecentFile.path, destinationFolder & "\" & mostRecentFile.name

End Sub


