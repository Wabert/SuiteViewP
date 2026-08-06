' Module: mdlFindFilesAndFolders.bas
' Type: Standard Module
' Stream Path: VBA/mdlFindFilesAndFolders
' =========================================================

Attribute VB_Name = "mdlFindFilesAndFolders"

Public Enum contentType
    FilesOnly = 1
    FoldersOnly = 2
    FilesAndFolders = 3
End Enum


Public Enum searchDepth
    CurrentFolderOnly = 1
    IncludeSubfolders = 2
End Enum

' Purpose: Lists the contents of a specified folder, with options to control what
'          items are included (files/folders) and how deep to search (current
'          folder only or include subfolders).
Public Function GetFolderContents(ByVal folderPath As String, _
                                ByVal contentType As contentType, _
                                ByVal searchDepth As searchDepth) As String

    
    Dim fso As Object
    Dim folder As Object
    Dim subFolder As Object
    Dim file As Object
    Dim result As String
    
    ' Initialize FileSystemObject
    Set fso = CreateObject("Scripting.FileSystemObject")
    
    ' Validate folder path
    If Not fso.FolderExists(folderPath) Then
        GetFolderContents = "Folder path not found"
        GoTo Cleanup
    End If
    
    ' Get the folder object
    Set folder = fso.GetFolder(folderPath)
    
    ' Process current folder contents
    ' Add folders if requested
    If contentType = FoldersOnly Or contentType = FilesAndFolders Then
        For Each subFolder In folder.SubFolders
            result = result & "FOLDER: " & subFolder.path & vbCrLf
            
            ' Recursively process subfolders if requested
            If searchDepth = IncludeSubfolders Then
                result = result & GetSubfolderContents(subFolder.path, contentType)
            End If
        Next subFolder
    End If
    
    ' Add files if requested.
    'Do not include temporary files (ones that begin with "~")
    If contentType = FilesOnly Or contentType = FilesAndFolders Then
        For Each file In folder.files
            result = result & "FILE: " & file.path & vbCrLf
        Next file
    End If
    
    GetFolderContents = result
    
Cleanup:
    Set fso = Nothing
    Set folder = Nothing
    Set subFolder = Nothing
    Set file = Nothing
End Function

' Helper function to process subfolders recursively
Private Function GetSubfolderContents(ByVal folderPath As String, _
                                    ByVal contentType As contentType) As String
    Dim fso As Object
    Dim folder As Object
    Dim subFolder As Object
    Dim file As Object
    Dim result As String
    
    Set fso = CreateObject("Scripting.FileSystemObject")
    Set folder = fso.GetFolder(folderPath)
    
    ' Process subfolders
    If contentType = FoldersOnly Or contentType = FilesAndFolders Then
        For Each subFolder In folder.SubFolders
            result = result & "FOLDER: " & subFolder.path & vbCrLf
            ' Recursive call for nested subfolders
            result = result & GetSubfolderContents(subFolder.path, contentType)
        Next subFolder
    End If
    
    ' Process files
    If contentType = FilesOnly Or contentType = FilesAndFolders Then
        For Each file In folder.files
            result = result & "FILE: " & file.path & vbCrLf
        Next file
    End If
    
    GetSubfolderContents = result
    
    Set fso = Nothing
    Set folder = Nothing
    Set subFolder = Nothing
    Set file = Nothing
End Function


' Purpose: Searches through a base directory structure to find a specific policy
'          folder by its policy number. The function expects the base directory
'          to contain product-specific folders (like WL, UL, IUL) and searches
'          within each of these for the policy number folder.
Public Function FindPolicyFolderPath(ByVal PolicyNumber As String, ByVal baseDirectory As String) As String
    Dim fso As Object
    Dim mainFolder As Object
    Dim productFolder As Object
    
    ' Initialize return value
    FindPolicyFolderPath = ""
    
    ' Create FileSystemObject
    Set fso = CreateObject("Scripting.FileSystemObject")
    
    ' Validate base directory
    If Not fso.FolderExists(baseDirectory) Then
        FindPolicyFolderPath = "Base directory not found"
        GoTo Cleanup
    End If
    
    ' Get the main folder
    Set mainFolder = fso.GetFolder(baseDirectory)
    
    ' Loop through each product folder (WL, UL, IUL, etc.)
    For Each productFolder In mainFolder.SubFolders
        ' Check if policy folder exists in this product folder
        If fso.FolderExists(productFolder.path & "\" & PolicyNumber) Then
            ' Found the policy folder - return the full path
            FindPolicyFolderPath = productFolder.path & "\" & PolicyNumber
            GoTo Cleanup
        End If
    Next productFolder
    
Cleanup:
    ' Clean up objects
    Set fso = Nothing
    Set mainFolder = Nothing
    Set productFolder = Nothing
End Function

' Purpose: Takes a file or folder path and returns just the name portion.
'          For example, if given 'C:\Documents\Work\report.txt', returns 'report.txt'.
'          If given 'C:\Documents\Work\MyFolder', returns 'MyFolder'.
Function GetNameFromPath(fullPath As String) As String
    Dim fso As Object
    Set fso = CreateObject("Scripting.FileSystemObject")
    
    If fso.FileExists(fullPath) Then
        GetNameFromPath = fso.GetFileName(fullPath)
    ElseIf fso.FolderExists(fullPath) Then
        GetNameFromPath = fso.GetFolder(fullPath).name
    Else
        GetNameFromPath = "Path not found"
    End If
End Function


'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
' GetNamesFromContents
'
' Purpose: Takes the string output from GetFolderContents and returns an array
'          containing just the file/folder names, without paths or prefixes.
'          For example, converts "FILE: C:\Folder\report.txt" to just "report.txt"
' Returns:
'   - Null if input is empty or "Folder path not found"
'   - String array containing just the names, with no paths or prefixes
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
Public Function GetNamesFromContents(ByVal contents As String) As Variant
    Dim contentLines() As String
    Dim result() As String
    Dim i As Long
    Dim resultCount As Long
    
    ' Check for empty or error input
    If contents = "" Or contents = "Folder path not found" Then
        GetNamesFromContents = Null
        Exit Function
    End If
    
    ' Split into lines
    contentLines = Split(contents, vbCrLf)
    
    ' Initialize result array
    ReDim result(0 To UBound(contentLines)) As String
    resultCount = 0
    
    ' Process each line
    For i = 0 To UBound(contentLines)
        ' Skip empty lines
        If Trim(contentLines(i)) <> "" Then
            ' Remove "FILE:" or "FOLDER:" prefix and get just the name
            result(resultCount) = GetNameFromPath(Mid(contentLines(i), InStr(contentLines(i), ":") + 2))
            resultCount = resultCount + 1
        End If
    Next i
    
    ' Resize array to actual number of items
    If resultCount > 0 Then
        ReDim Preserve result(0 To resultCount - 1)
        GetNamesFromContents = result
    Else
        GetNamesFromContents = Null
    End If
End Function

Public Function FolderExists(ByVal folderPath As String) As Boolean
    'Returns True if the folder exists, False if it doesn't
    
    On Error Resume Next
    FolderExists = (GetAttr(folderPath) And vbDirectory) = vbDirectory
    On Error GoTo 0
End Function

Public Function IsFile(ByVal fullPath As String) As Boolean
    On Error Resume Next
    
    ' Check if the path exists first
    If Dir(fullPath, vbDirectory + vbHidden + vbSystem) = "" Then
        IsFile = False
        Exit Function
    End If
    
    ' GetAttr returns file/folder attributes
    ' vbDirectory (16) is the flag for directories
    IsFile = Not (GetAttr(fullPath) And vbDirectory) = vbDirectory
End Function

Function FileExists(filepath As String) As Boolean
    Dim FileSystem As Object
    Set FileSystem = CreateObject("Scripting.FileSystemObject")
    FileExists = FileSystem.FileExists(filepath)
    Set FileSystem = Nothing
End Function

Public Function GetFileLastModifiedDate(ByVal filepath As String) As Variant
    Dim fso As Object
    Dim fileObj As Object
    
    On Error GoTo ErrorHandler
    
    ' Create FileSystemObject
    Set fso = CreateObject("Scripting.FileSystemObject")
    
    ' Check if file exists
    If Not fso.FileExists(filepath) Then
        GetFileLastModifiedDate = "File not found"
        Exit Function
    End If
    
    ' Get file object
    Set fileObj = fso.GetFile(filepath)
    
    ' Get last modified date
    GetFileLastModifiedDate = fileObj.DateLastModified
    
    Exit Function

ErrorHandler:
    GetFileLastModifiedDate = "Error: " & Err.Description
End Function

Public Sub CreateFolder(folderPath As String)
    Dim fso As Object
    
    Set fso = CreateObject("Scripting.FileSystemObject")
    
    If Not fso.FolderExists(folderPath) Then fso.CreateFolder folderPath

End Sub
Public Sub OpenFolder(folderPath)
    On Error Resume Next
    shell "explorer.exe """ & folderPath & """", vbNormalFocus
    If Err.Number <> 0 Then
        MsgBox "Unable to open the folder. Please check if the path is correct.", vbExclamation
    End If
    On Error GoTo 0
End Sub

Public Function GetFileName(fullPath As String) As String
    Dim FileSystem As Object
    Set FileSystem = CreateObject("Scripting.FileSystemObject")
    GetFileName = FileSystem.GetFileName(fullPath)
    Set FileSystem = Nothing
End Function

Function GetLastFolderName(fullFolderPath As String) As String
    Dim FileSystem As Object
    Dim folder As Object
    Set FileSystem = CreateObject("Scripting.FileSystemObject")
    
    ' Ensure the path ends with a backslash
    If Right(fullFolderPath, 1) <> "\" Then
        fullFolderPath = fullFolderPath & "\"
    End If
    
    ' Get the parent folder object
    Set folder = FileSystem.GetFolder(fullFolderPath)
    
    ' Get the name of the last folder
    GetLastFolderName = folder.name
    
    ' Clean up
    Set folder = Nothing
    Set FileSystem = Nothing
End Function

Public Sub CopyFile(sourcefolder As String, sourcefilename As String, destinationFolder As String, destinationfilename)
    Dim FileSystem As Object
   

    sourcefolder = sourcefolder & "\"
    destinationFolder = destinationFolder & "\"
    
   
    ' Create a FileSystemObject to access the file system
    Set FileSystem = CreateObject("Scripting.FileSystemObject")
    
    ' Copy the file from source to destination
    FileSystem.CopyFile Source:=sourcefolder & sourcefilename, Destination:=destinationFolder & destinationfilename
    
    ' Clean up
    Set FileSystem = Nothing
End Sub
Public Sub CopyAndCreateShortcut(sourcePath As String, destinationFolder As String, shortcutName As String)
    Dim WshShell As Object
    Dim shortcut As Object
    Dim fso As Object
    
    Set fso = CreateObject("Scripting.FileSystemObject")
    Set WshShell = CreateObject("WScript.Shell")
    
    'Create the shortcut (.lnk file)
    Set shortcut = WshShell.CreateShortcut(fso.BuildPath(destinationFolder, shortcutName & ".lnk"))
    shortcut.targetPath = sourcePath
    shortcut.Save
    
    'Clean up
    Set shortcut = Nothing
    Set WshShell = Nothing
    Set fso = Nothing
End Sub
' Example usage:
Public Sub TestGetFileDate()
    Dim filepath As String
    Dim modDate As Variant
    
    filepath = "C:\Path\To\Your\File.xlsx"
    modDate = GetFileLastModifiedDate(filepath)
    
    If IsDate(modDate) Then
        Debug.Print "File was last modified on: " & modDate
    Else
        Debug.Print modDate ' Will print error message
    End If
End Sub
Sub test()
    'Create link to a file
    CopyAndCreateShortcut "C:\Users\ab7y02\OneDrive - American National Insurance Company\Documents\2022 project.xlsm", "C:\Users\ab7y02\OneDrive - American National Insurance Company\Documents", "2022 project.xlsm"
    
    'Create link to a folder
    CopyAndCreateShortcut "C:\Users\ab7y02\OneDrive - American National Insurance Company\Documents\Geogebra", "C:\Users\ab7y02\OneDrive - American National Insurance Company\Documents", "Link to folder"
End Sub

Sub TestGetNamesFromContents()
' Get the full contents first

testFolderPath = FindPolicyFolderPath("U0903852", "\\sranico7\data\shared\+++PROCESS CONTROL+++\Policy Support\POLICY_LIBRARY")

Dim contents As String
contents = GetFolderContents(testFolderPath, contentType.FilesAndFolders, searchDepth.CurrentFolderOnly)

' Convert to array of just names
Dim names As Variant
names = GetNamesFromContents(contents)

' Use the names
If Not IsNull(names) Then
    For i = 0 To UBound(names)
        Debug.Print names(i)
    Next i
End If
End Sub


' Test function
Sub TestGetFolderContents()
    Dim result As String
    Dim testFolderPath As String
    
    ' First find a policy folder using our previous function
    testFolderPath = FindPolicyFolderPath("U0903852", "\\sranico7\data\shared\+++PROCESS CONTROL+++\Policy Support\POLICY_LIBRARY")
    
    If testFolderPath = "" Or testFolderPath = "Base directory not found" Then
        Debug.Print "Could not find policy folder"
        Exit Sub
    End If
    
    ' Test different combinations
    Debug.Print "Files Only - Current Folder:"
    result = GetFolderContents(testFolderPath, FilesOnly, CurrentFolderOnly)
    Debug.Print result
    
    Debug.Print "Folders Only - With Subfolders:"
    result = GetFolderContents(testFolderPath, FoldersOnly, IncludeSubfolders)
    Debug.Print result
    
    Debug.Print "Files and Folders - Current Folder:"
    result = GetFolderContents(testFolderPath, FilesAndFolders, CurrentFolderOnly)
    Debug.Print result

    Debug.Print "Files and Folders - With Subfolders:"
    result = GetFolderContents(testFolderPath, FilesAndFolders, IncludeSubfolders)
    Debug.Print result

End Sub

' Test function
Sub TestFindPolicyPath()
    Dim result As String
    Dim testPolicyNumber As String
    Dim testBasePath As String
    
    testPolicyNumber = "U0903852"
    testBasePath = "\\sranico7\data\shared\+++PROCESS CONTROL+++\Policy Support\POLICY_LIBRARY"
    testBasePath = "\\sranico7\data\shared\+++PROCESS CONTROL+++\Systems\Shoebox Administration\Accelerated Death Benefit (ABR11 & ABR14)\Policies"
    result = FindPolicyFolderPath(testPolicyNumber, testBasePath)
    
    Debug.Print result
 
End Sub

