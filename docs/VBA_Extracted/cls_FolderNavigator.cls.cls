' Module: cls_FolderNavigator.cls
' Type: Class Module
' Stream Path: VBA/cls_FolderNavigator
' =========================================================

Attribute VB_Name = "cls_FolderNavigator"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
' Class Module: FolderNavigator
Option Explicit

Private Type TNavigator
    txtPath As MSForms.textBox
    lstContent As MSForms.Listbox
    targetFolder As String
    parentFolder As String
    CurrentPath As String
    lastRightClick As Double
    lastRightClickIndex As Long
    ShowFullPath As Boolean
End Type

Private this As TNavigator
Private fso As FileSystemObject

Private Sub Class_Initialize()
    Set fso = New FileSystemObject
    this.lastRightClick = 0
    this.lastRightClickIndex = -1
End Sub

Private Sub Class_Terminate()
    Set fso = Nothing
    Set this.txtPath = Nothing
    Set this.lstContent = Nothing
End Sub

Public Sub Initialize(ByRef txtBox As MSForms.textBox, ByRef lstbox As MSForms.Listbox, ByVal baseFolder As String, Optional ByVal ShowFullPath As Boolean = False)
    Set this.txtPath = txtBox
    Set this.lstContent = lstbox
    
    this.targetFolder = baseFolder
    
    ' Set the current path to the last folder name
    this.CurrentPath = baseFolder
    this.parentFolder = fso.GetParentFolderName(baseFolder)
    
    ' Set the path display mode
    this.ShowFullPath = ShowFullPath
    
    ' Set up control events
    InitializeEvents
    
    ' Populate the listbox with initial folder contents
    RefreshContent
End Sub

Private Sub InitializeEvents()
    ' Note: These events need to be set up in the form where the controls exist
    ' This is just a reference for what needs to be wired up
    
    ' txtPath_MouseUp Event (for right-click navigation up)
    ' If Button = vbRightButton Then
    '     NavigateUp
    ' End If
    
    ' lstContent_DblClick Event
    ' NavigateToSelected
    
    ' lstContent_MouseUp Event (for right-click delete)
    ' If Button = vbRightButton Then
    '     DeleteSelected
    ' End If
End Sub

Public Sub RefreshContent()
    Dim fullPath As String
    Dim item As Object
    Dim folder As folder
    
    ' Clear existing items
    this.lstContent.Clear
    
    ' Update the text box based on display mode
    If this.ShowFullPath Then
        this.txtPath.Text = this.CurrentPath
    Else
        this.txtPath.Text = GetRelativePath(this.CurrentPath)
    End If
    
    fullPath = this.CurrentPath
    
    ' Check if path exists
    If Not fso.FolderExists(fullPath) Then
        MsgBox "Folder not found: " & fullPath, vbExclamation
        Exit Sub
    End If
    
    Set folder = fso.GetFolder(fullPath)
    
    ' Add folders first
    For Each item In folder.SubFolders
        this.lstContent.AddItem item.name
    Next item
    
    ' Then add files
    For Each item In folder.files
        If left(item.name, 1) <> "~" Then this.lstContent.AddItem item.name
    Next item
End Sub

Public Sub NavigateToSelected()
    If this.lstContent.ListIndex = -1 Then Exit Sub
    
    Dim selectedItem As String
    Dim fullPath As String
    
    selectedItem = this.lstContent.List(this.lstContent.ListIndex)
    fullPath = fso.BuildPath(this.CurrentPath, selectedItem)
    
    ' Check if selected item is a folder
    If fso.FolderExists(fullPath) Then
        ' Update currentPath
        this.CurrentPath = fullPath
        
        ' Refresh the display
        RefreshContent
    End If
    
    ' Check if selected item is a file, if so open it
    If fso.FileExists(fullPath) Then
        CreateObject("Shell.Application").ShellExecute fullPath, "", "", "open", 1
    End If
    
End Sub

Public Sub NavigateUp()
    If Len(this.CurrentPath) = 0 Then Exit Sub
    
    ' Get parent folder path
    this.CurrentPath = fso.GetParentFolderName(this.CurrentPath)
    
    ' Refresh the display
    RefreshContent
End Sub

Public Property Get CurrentPath() As String
    CurrentPath = this.CurrentPath
End Property

Public Property Get ShowFullPath() As Boolean
    ShowFullPath = this.ShowFullPath
End Property

Public Property Let ShowFullPath(ByVal value As Boolean)
    this.ShowFullPath = value
    RefreshContent  ' Refresh display when changing mode
End Property


Private Function GetRelativePath(CurrentPath As String)
    GetRelativePath = Replace(CurrentPath, this.parentFolder, "")
    
    'Remove leading "\" if present
    If left(GetRelativePath, 1) = "\" Then
        GetRelativePath = Right(GetRelativePath, Len(GetRelativePath) - 1)
    End If
        
End Function
