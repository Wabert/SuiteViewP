' Module: frmPolicyMasterTV.frm
' Type: Standard Module
' Stream Path: VBA/frmPolicyMasterTV
' =========================================================

Attribute VB_Name = "frmPolicyMasterTV"
Attribute VB_Base = "0{BB8AEE47-8221-425B-BBCA-FC0ADB1E94DE}{0C7B7294-C7D7-4E40-962A-2BE1EAD71D4B}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False

'1/13/2025 - RJH:   Added functionality for Policy Support tab
'12/8/2021 - RJH:   Changed SpecifiedAmountOnPrimaryInsured to only add up amounts on coverages that are currently inforce
'9/11/2018 - RJH:   Added "Rate" to the Coverages box display



Option Explicit

Private WithEvents mVBoxEvents As cls_ListBoxEvents
Attribute mVBoxEvents.VB_VarHelpID = -1

Private dctNavigator As Dictionary

Private mPolicySupportFolderPath As String
Private mPolicyIndexArray As Variant
Private mTaskArray As Variant

Private WithEvents mcTree As clsTreeView
Attribute mcTree.VB_VarHelpID = -1
Private mbExit As Boolean    ' to exit a SpinButton event


Dim CurrentRS As ADODB.Recordset
Dim mCurrentTable As Variant

Dim VBoxDisplay As clsVBox


Dim mPolDB2 As cls_PolicyData
Dim mPolicy As cls_PolicyInformation
Dim TblUniverse As Dictionary
Dim dctPols As Dictionary
Dim dctRS As Dictionary  'UserForms
Dim dctRates As Dictionary
Dim dctControlsMoveForTree As Dictionary
Dim dctControlsHideWithTree As Dictionary
Dim mLeftAdjust As Double
Dim blnTablesRetreived As Boolean
Dim blnRatesRetreived As Boolean
Dim blnTreeViewOn As Boolean
Dim mMaxAnnualLevelQualPrem As Double
Dim mInsuranceDefinitionMaturityAge As Integer
Dim colVBox As Collection
Dim colStorage As Collection
Dim mDisplayView As eDisplayView
Dim dctPolicyTables As Dictionary   'Contains dictoinary of all policy table and the current table view for each
Dim mProductGroup   'WL, TERM, UL, IUL, VUL, ISWL, DI...
Dim mConvertedPolicyNumber As String
Dim mReplacedPolicyNumber As String

Const DOWNCOLOR = &H80000003
Const SHOWTREE = "<-- Show"
Const HIDETREE = "--> Hide"

Public Enum eDisplayView
    AsColumn
    AsHeader
End Enum


Private RatesThatUseBand As Dictionary
Private Property Get PROCESSCONTROL_DIRECTORY() As String
    PROCESSCONTROL_DIRECTORY = "C:\Users\" & Environ("Username") & "\OneDrive - American National Insurance Company\Life Product - Process_Control"
End Property

Private Property Get PS_DIRECTORY() As String
    PS_DIRECTORY = PROCESSCONTROL_DIRECTORY & "\Policy Support"   'Location of the Policy Support directory.
End Property
Private Property Get ABR_DIRECTORY() As String
    PS_DIRECTORY = "C:\Users\" & Environ("Username") & "\OneDrive - American National Insurance Company\Life Product - Process_Control\Task\Accelerated Death Benefit"   'Location of the Policy Support directory.
End Property
Private Property Get ABR114_DIRECTORY() As String
    ABR114_DIRECTORY = ABR_DIRECTORY & "\ABR11 & ABR14"   'Location of the Policy Support directory.
End Property
Private Property Get POLICYINDEX_FILELOCATION() As String
    POLICYINDEX_FILELOCATION = PS_DIRECTORY & "\TOOLS\_Maintenance\policy_index.xlsx"
End Property

Sub classInitialize(objPolicy As cls_PolicyInformation)
  Set dctRS = New Dictionary
  Set mPolDB2 = objPolicy.DB2Data
  Set mPolicy = objPolicy
  Set dctRates = New Dictionary
  Set dctControlsHideWithTree = New Dictionary
  Set dctControlsMoveForTree = New Dictionary
  Set RatesThatUseBand = New Dictionary
  Set colVBox = New Collection
  Set colStorage = New Collection
  
  Set VBoxDisplay = New clsVBox
  VBoxDisplay.Initialize Frame_Display, Me.Backcolor
  Set mcTree = New clsTreeView
  Set mcTree.TreeControl = Frame_Tree
  Frame_Tree.Backcolor = vbWhite
  With mcTree
  .Indentation = 0.2
  End With
    
  DefaultSettings
  
  PopulatePolicy
 
    
  PopulateCoverges
  PopulateBenefits

  PopulateYearlyTAMRAValues
  PopulateCommissionTargets
  PopulateMinimumTargets
  Populate7702andPremiums
  
  
  If mPolicy.AdvancedProductIndicator = "1" Then
    MultiPage1.Pages("AdvProdValues").Visible = True
    PopulateMVValues       'PopulateMVValues must occur before PopulateActivityDetail
    PopulateBucketDetailAndSummary
    PopulatePremiumAllocation
    
    '9/6/2018 RJH: Line replaced
    'If colVBox("MVValues").ListCount = 0 Then MultiPage1.Pages("AdvProdValues").Visible = False
    If mPolicy.MVCount = 0 Then MultiPage1.Pages("AdvProdValues").Visible = False
    
  Else
    MultiPage1.Pages("AdvProdValues").Visible = False
  End If
  
  If mPolicy.UnappliedDivCount = 0 And mPolicy.DivOYTCount = 0 And mPolicy.DivDepositCount = 0 And mPolicy.DivPUACount = 0 Then
    MultiPage1.Pages("Dividends").Visible = False
  Else
    MultiPage1.Pages("Dividends").Visible = True
    PopulateUnappliedDivDetail
    PopulateDivsOnDeposit
    PopulateDivsPUA
    PopulateDivsOYT
  End If
  
  If mPolicy.AdvancedProductIndicator = "1" Then
    'RJH - 4/9/2024:  When an ISWL goes on RPU, the loans are considered trandiation a loans and the cash values are
    'just the NSP on the 02 segment (no more accumulation value from the 65 segment)
    If mPolicy.ProductType = "ISWL" And mPolicy.StatusCode = "45" Then
        PopulateTradLoanDetail
    Else
        PopulateLoanDetail
    End If
    
  Else
    PopulateTradLoanDetail
  End If
  
  
  'PopulateMVValues must occur before PopulateActivityDetail (for advanced products only)
  PopulateActivityDetail
  
  PopulatePersonDetail
  
  PlaceMultipageOverDiplay
    
  'Set default values
  
  MultiPage1.value = MultiPage1.Pages("Coverages").Index

  MultiPage1.Pages("Page_ABRAssist").Visible = False

  MultiPage1.Pages("Page_PolicySupport").Visible = False
  
  MultiPage1.Pages("Page_PolicyLibrary").Visible = False
  
  MultiPage1.Pages("Page_Reinsurance").Visible = False
  
  Label_ABRSupport.Visible = False
    
  Label_PolicySupport.Visible = False
  
  
  
  'Set widths for forms and controls
  Me.width = 1000
  Me.height = 550
  MultiPage1.width = 950
  MultiPage1.height = 450
  Frame_Coverages.width = 900
  

End Sub

Private Sub CommandButton_AddCustomSubtask_Click()
Dim foldername As String
Dim targetFolder As String

If TextBox_PolicyTask.value = "" Then
    Exit Sub
End If

foldername = TextBox_CustomSubTask.value
targetFolder = mPolicySupportFolderPath & "\" & TextBox_PolicyTask & "\" & foldername

CreateFolder targetFolder

Populate_ListBox_With_FolderContents ListBox_PolicyTaskDisplay, mPolicySupportFolderPath & "\" & TextBox_PolicyTask, FoldersOnly

End Sub

Private Sub CommandButton_AddCustomTask_Click()
Dim foldername As String
Dim targetFolder As String

If Not FolderExists(mPolicySupportFolderPath) Then
    CreateFolder mPolicySupportFolderPath
    TextBox_PolicyFolder.value = mPolicy.CompanyCode & "_" & mPolicy.PolicyNumber
End If

foldername = TextBox_CustomTask.value
targetFolder = mPolicySupportFolderPath & "\" & foldername

CreateFolder targetFolder

Populate_ListBox_With_FolderContents ListBoxPS_PolFolderDisplay, mPolicySupportFolderPath, FoldersOnly

End Sub

Private Sub CommandButton_AddTaskFolder_Click()
Dim FolderSelected As String
Dim targetFolder As String

If ListBoxPS_CategoryList.ListIndex = -1 Then
    Exit Sub
End If

If Not FolderExists(mPolicySupportFolderPath) Then
    CreateFolder mPolicySupportFolderPath
    TextBox_PolicyFolder.value = mPolicy.CompanyCode & "_" & mPolicy.PolicyNumber
End If
    

FolderSelected = ListBoxPS_CategoryList.Column(0, ListBoxPS_CategoryList.ListIndex)
targetFolder = mPolicySupportFolderPath & "\" & FolderSelected

CreateFolder targetFolder

Populate_ListBox_With_FolderContents ListBoxPS_PolFolderDisplay, mPolicySupportFolderPath, FoldersOnly

End Sub

Private Sub CommandButton_AddTool_Click()
Dim blnExists As Boolean
Dim sourcefolder As String
Dim destinationFolder As String
Dim filename As String
Dim TaskNav As cls_FolderNavigatorHost

If ListBox_ToolsTemplates.ListIndex = -1 Then
    Exit Sub
End If


Set TaskNav = dctNavigator("TaskNav")
destinationFolder = TaskNav.CurrentPath
sourcefolder = TextBox_ToolsTemplatesPath.value
filename = ListBox_ToolsTemplates.Column(0, ListBox_ToolsTemplates.ListIndex)

blnExists = FileExists(destinationFolder & "\" & filename)



If blnExists Then
    'Do not overwrite the existing file.
    Exit Sub
End If

If Not IsFile(sourcefolder & "\" & filename) Then
    MsgBox "Cannot copy a folder", vbOKOnly
    Exit Sub
End If
    

CopyFile sourcefolder, filename, destinationFolder, filename

Populate_ListBox_With_FolderContents ListBox_PolicyTaskDisplay, destinationFolder, FilesAndFolders

End Sub


Private Sub CommandButton_AddToolShortCut_Click()
Dim blnExists As Boolean
Dim sourcefolder As String
Dim destinationFolder As String
Dim filename As String
Dim TaskNav As cls_FolderNavigatorHost

If ListBox_ToolsTemplates.ListIndex = -1 Then
    Exit Sub
End If


Set TaskNav = dctNavigator("TaskNav")
destinationFolder = TaskNav.CurrentPath
sourcefolder = TextBox_ToolsTemplatesPath.value
filename = ListBox_ToolsTemplates.Column(0, ListBox_ToolsTemplates.ListIndex)


If blnExists Then
    'Do not overwrite the existing file.
    Exit Sub
End If


CopyAndCreateShortcut sourcefolder & "\" & filename, destinationFolder, filename

Populate_ListBox_With_FolderContents ListBox_PolicyTaskDisplay, destinationFolder, FilesAndFolders

End Sub


Private Sub CommandButton_CheckReinsurance_Click()
    MultiPage1.Pages("Page_Reinsurance").Visible = True
    PopulateReinsuranceDetail
    CommandButton_CheckReinsurance.Visible = False
    
    
End Sub

Private Sub Label_LoadPolicyLibrary_Click()
    LoadPolicyLibrary
End Sub

Private Sub Label_ABR_Policies_Click()

End Sub

Private Sub Label_Status_DblClick(ByVal Cancel As MSForms.ReturnBoolean)
  Label_ABRSupport.Visible = True
    
  Label_PolicySupport.Visible = True
End Sub



Private Sub Label313_Click()

End Sub

Private Sub LabelPS_PolicyLibrary_DblClick(ByVal Cancel As MSForms.ReturnBoolean)
    OpenFolder (LabelPS_PolicyLibrary)
End Sub

Private Sub ListBox_ToolBox_Click()
Dim folderPath As String
Dim ToolNav As cls_FolderNavigatorHost

If ListBox_ToolBox.ListIndex = -1 Then
    Exit Sub
End If

folderPath = ListBox_ToolBox.Column(0, ListBox_ToolBox.ListIndex)
TextBox_ToolsTemplatesPath = folderPath
Set ToolNav = New cls_FolderNavigatorHost
ToolNav.Initialize TextBox_ToolsTemplatesPath, ListBox_ToolsTemplates, folderPath, True
If dctNavigator.exists("ToolNav") Then dctNavigator.Remove ("ToolNav")
dctNavigator.Add "ToolNav", ToolNav

End Sub

Private Sub ListBoxPS_PolFolderDisplay_Click()
    Dim ary As Variant
    Dim foldername As String
    Dim fullPath As String
    Dim toolFolder As String
    Dim TaskNav As cls_FolderNavigatorHost
    Dim ToolNav As cls_FolderNavigatorHost

    
    
    Set dctNavigator = New Dictionary
    
    foldername = ListBoxPS_PolFolderDisplay.Column(0, ListBoxPS_PolFolderDisplay.ListIndex)
    
    fullPath = mPolicySupportFolderPath & "\" & foldername
    Set TaskNav = New cls_FolderNavigatorHost
    TaskNav.Initialize TextBox_PolicyTask, ListBox_PolicyTaskDisplay, fullPath, False
    dctNavigator.Add "TaskNav", TaskNav
     
    
    
    'ary = GetNamesFromContents(GetFolderContents(mPolicySupportFolderPath & "\" & foldername, FilesAndFolders, CurrentFolderOnly))
    'Populate_ListBox_With_Array ListBox_PolicyTaskDisplay, ary
    
    TextBox_ToolsTemplatesPath = ""
    ListBox_ToolBox.Clear
    ListBox_ToolsTemplates.Clear
    
    ary = GetArrayOfTools(foldername)
    
    If Not IsEmpty(ary) Then
        Populate_ListBox_With_Array ListBox_ToolBox, ary
    End If
   

End Sub

Private Function GetArrayOfTools(sTaskName As String) As Variant
Dim X As Integer
Dim idx As Integer

idx = -1
For X = LBound(mTaskArray) To UBound(mTaskArray)
    If mTaskArray(X) = sTaskName Then
        idx = X
        Exit For
    End If
Next

If idx > -1 Then
    Dim tool_folder As String
    Dim dct As Dictionary
    Set dct = New Dictionary
    
    TaskManagement.Activate
    X = 1
    tool_folder = Range("sTaskToolsTableStart").Offset(X, idx).value
    Do While tool_folder <> ""
        dct.Add tool_folder, tool_folder
        X = X + 1
        tool_folder = Range("sTaskToolsTableStart").Offset(X, idx).value
        
        
    Loop
    
    If dct.Count = 0 Then
        GetArrayOfTools = Empty
    Else
        GetArrayOfTools = dct.Keys
    End If
    
Else
    GetArrayOfTools = Empty
End If




End Function

Private Sub TextBox_PolicyFolder_DblClick(ByVal Cancel As MSForms.ReturnBoolean)
    If TextBox_PolicyFolder.value = "No Folder Found" Then
        Exit Sub
    Else
        OpenFolder (mPolicySupportFolderPath)
    End If
    
End Sub

'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
' PopulateListBox
'
' Purpose: Takes an array of names and a ListBox object and adds the names to
'          the ListBox. Clears any existing items from the ListBox first.
'
' Parameters:
'   lstBox     - ListBox object to populate
'   ary      - Array of names (output from GetNamesFromContents)
'
' Note: Does nothing if names parameter is Null
'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
Sub PopulateListBox_with_Filenames(sourcefolder As String, lb As Control)
    Dim FileSystem As Object
    Dim folder As Object
    Dim file As Object
    Dim toolFolder As String
    toolFolder = sourcefolder
    
    ' Create a FileSystemObject to access the file system
    Set FileSystem = CreateObject("Scripting.FileSystemObject")
    
    ' Get the folder object
    Set folder = FileSystem.GetFolder(toolFolder)
    
    ' Clear the list box before populating
    lb.Clear
    
    ' Loop through each file in the folder
    For Each file In folder.files
        ' Check if the file is an Excel file
        If Right(file.name, Len(".xlsx")) = ".xlsx" Or Right(file.name, Len(".xls")) = ".xls" Or Right(file.name, Len(".xlsm")) = ".xlsm" Or Right(file.name, Len(".xlsb")) = ".xlsb" Then
            ' Add the file name and last modified date to the list box
            lb.AddItem file.name '& " : " & File.DateLastModified
        End If
    Next file
    
    ' Clean up
    Set file = Nothing
    Set folder = Nothing
    Set FileSystem = Nothing
End Sub
Public Sub Populate_ListBox_With_FolderContents(lstbox As MSForms.Listbox, ByVal folderPath As String, ByVal contentType As contentType)
    Dim ary As Variant
    ary = GetNamesFromContents(GetFolderContents(folderPath, contentType, CurrentFolderOnly))
    Populate_ListBox_With_Array lstbox, ary

End Sub
Public Sub Populate_ListBox_With_Array(lstbox As MSForms.Listbox, ary As Variant)
    Dim i As Long
    
    ' Clear existing items
    lstbox.Clear
    
    ' Exit if names array is Null
    If IsNull(ary) Then Exit Sub
    

    
    ' Add each name to the ListBox
    For i = 0 To UBound(ary)
        lstbox.AddItem ary(i)
    Next i
End Sub

Private Sub PopulateABR()
    Dim strFolder As String
    
    ABR_SetPolicy mPolicy
    
    strFolder = ABR_CheckForPolicyFolder
    
    If strFolder = "" Then
        Label_ABRStatus = "No ABR folder for this policy"
        CommandButton_CreateABRFolder.Visible = True
        TextBox_ABRPolicyFolder.Text = "No folder exists"
    Else
        Label_ABRStatus = "ABR folder located"
        CommandButton_CreateABRFolder.Visible = False
        TextBox_ABRPolicyFolder.Text = GetLastFolderName(strFolder)
        PopulateListBox_with_Filenames strFolder, ListBox_ABRPolicyFiles
 
    End If
    Dim h
    
'    PopulateListBox_with_Filenames TextBox_ABRTool_Folder.Text, Me.ListBox_ABRULTools
'    PopulateListBox_with_Filenames TextBox_RERUN_Folder.Text, Me.ListBox_RERUNFolder
    
    Populate_ListBox_With_FolderContents Me.ListBox_ABRULTools, TextBox_ABRTool_Folder.Text, FilesOnly
    Populate_ListBox_With_FolderContents Me.ListBox_RERUNFolder, TextBox_RERUN_Folder.Text, FilesOnly
    
    
End Sub
Private Sub CommandButton_CreatePolicySupportFolder_Click()
    Dim targetFolder As String
    targetFolder = LabelPS_PolicyLibrary & "\" & mPolicy.CompanyCode & "_" & mPolicy.PolicyNumber
    If Not FolderExists(targetFolder) Then
        CreateFolder targetFolder
        TextBox_PolicyFolder.value = mPolicy.CompanyCode & "_" & mPolicy.PolicyNumber
        
    End If
    
End Sub


Private Sub PopulatePolicySupport()
Dim ary As Variant
Dim PolicyFolderPath As String
Dim Content As String
Dim targetFolder As String
Dim ProductGroup As String
Dim blnPolicyFolderExists As Boolean

MultiPage1.Pages("Page_PolicySupport").Visible = True

MultiPage1.value = MultiPage1.Pages("Page_PolicySupport").Index
Dim TableRange As String
TableRange = TaskManagement.Range("sTaskRange").value
mTaskArray = TaskManagement.Range(TableRange).value
mTaskArray = Convert2DTo1D(mTaskArray)

Populate_ListBox_With_Array ListBoxPS_CategoryList, mTaskArray

ProductGroup = Label_ProductType

LabelPS_PolicyLibrary = PS_DIRECTORY & "\" & "POLICY_LIBRARY" & "\" & ProductGroup

mPolicySupportFolderPath = LabelPS_PolicyLibrary & "\" & mPolicy.CompanyCode & "_" & mPolicy.PolicyNumber

blnPolicyFolderExists = FolderExists(mPolicySupportFolderPath)

If blnPolicyFolderExists Then
    TextBox_PolicyFolder.value = mPolicy.CompanyCode & "_" & mPolicy.PolicyNumber
    
    Content = GetFolderContents(mPolicySupportFolderPath, FoldersOnly, CurrentFolderOnly)
    
    ary = GetNamesFromContents(Content)
    
    Populate_ListBox_With_Array ListBoxPS_PolFolderDisplay, ary
    
    CommandButton_CreatePolicySupportFolder.Visible = False

Else
    TextBox_PolicyFolder.value = "No Folder Found"
    CommandButton_CreatePolicySupportFolder.Visible = True
End If

End Sub



Public Sub LoadPolicyLibrary()

MultiPage1.Pages("Page_PolicyLibrary").Visible = True
MultiPage1.value = MultiPage1.Pages("Page_PolicyLibrary").Index
mPolicyIndexArray = GetDataFromExcel(POLICYINDEX_FILELOCATION, "Policy Index")

Dim s As cls_Storage

Set s = New cls_Storage
s.AddColumn "Product"
s.AddColumn "PolicyNumber"
s.AddColumn "Task"
s.AddColumn "LastModified"
s.AddColumn "Owner"
s.AddColumn "Link"


Dim xcount
For xcount = 2 To UBound(mPolicyIndexArray, 1)
    s.AddRow
    s("Product") = Format(mPolicyIndexArray(xcount, 2), "m/dd/yyyy")
    s("PolicyNumber") = mPolicyIndexArray(xcount, 3)
    s("Task") = mPolicyIndexArray(xcount, 4)
    s("LastModified") = Format(mPolicyIndexArray(xcount, 5), "m/dd/yyyy")
    s("Owner") = mPolicyIndexArray(xcount, 6)
    s("Link") = mPolicyIndexArray(xcount, 1)
Next
  

Dim VBox As clsVBox
Set VBox = New clsVBox

VBox.Initialize Frame_PolicyLibrary, Me.Backcolor
VBox.TableData = s.GetArrayOfValues
VBox.ColumnWidths = "50;80;150;100;50;5"

Set mVBoxEvents = New cls_ListBoxEvents
Set mVBoxEvents.Listbox = VBox.Listbox
    
colStorage.Add s, "PolicyLibrary"
colVBox.Add VBox, "PolicyLibrary"

Label_PolicyLibraryLastDate = "Effective Date " & Format(GetFileLastModifiedDate(POLICYINDEX_FILELOCATION), "m/dd/yyyy")

End Sub

Private Sub mVBoxEvents_OnDoubleClick()
    ' Handle the double-click event here
    ' For example, if you want to handle clicks on policy numbers:
    Dim selectedValue As String
    Dim lb As MSForms.Listbox
    
    Set lb = colVBox("PolicyLibrary").Listbox
    
    If lb.ListIndex < 0 Then Exit Sub
    
    selectedValue = lb.List(lb.ListIndex, 4) ' Gets first column value
    
    OpenFolder selectedValue
    ' Example handling:
'    If mConvertedPolicyNumber <> "Null" And Trim(selectedValue) = mConvertedPolicyNumber Then
'        CreatePolicyForm GetPolicy(mConvertedPolicyNumber)
'    End If
    
    ' Add other double-click handling logic here
End Sub


Private Sub CommandButton_CopyFile1_Click()
    Dim filename As String
    Dim sourcefolder As String '
    Dim destinationFolder As String
    
    If ListBox_ABRULTools.ListIndex < 0 Then Exit Sub
    
    sourcefolder = TextBox_ABRTool_Folder.Text
    filename = ListBox_ABRULTools.Column(0, ListBox_ABRULTools.ListIndex)
    destinationFolder = mABRPolicyFolder
    
    If FileExists(destinationFolder & "\" & filename) Then
       MsgBox "This file already exists.  Operation cancelled."
    Else
       CopyFile sourcefolder, filename, destinationFolder, mPolicy.PolicyNumber & " - " & filename
    End If
    
    PopulateListBox_with_Filenames destinationFolder, ListBox_ABRPolicyFiles
    
End Sub

Private Sub CommandButton_CopyFile2_Click()
    Dim filename As String
    Dim sourcefolder As String '
    Dim destinationFolder As String
    
    If ListBox_RERUNFolder.ListIndex < 0 Then Exit Sub
    
    sourcefolder = TextBox_RERUN_Folder.Text
    filename = ListBox_RERUNFolder.Column(0, ListBox_RERUNFolder.ListIndex)
    destinationFolder = mABRPolicyFolder
    
    If FileExists(destinationFolder & "\" & filename) Then
       MsgBox "This file already exists.  Operation cancelled."
    Else
       CopyFile sourcefolder, filename, destinationFolder, mPolicy.PolicyNumber & " - " & filename
    End If
    
    PopulateListBox_with_Filenames destinationFolder, ListBox_ABRPolicyFiles
End Sub

Private Sub CommandButton_CreateABRFolder_Click()
    ABR_CreatePolicyFolder
    TextBox_ABRPolicyFolder.Text = GetLastFolderName(mABRPolicyFolder)
    Label_ABRStatus = "ABR Policy Folder exists."
    
End Sub
Private Sub Label_PolicySupport_Click()
    PopulatePolicySupport
End Sub

Private Sub Label_ABRSupport_Click()
   MultiPage1.Pages("Page_ABRAssist").Visible = True
   PopulateABR
End Sub

Private Sub TextBox_ABRPolicyFolder_DblClick(ByVal Cancel As MSForms.ReturnBoolean)
    Dim filename As String
    filename = mABR_FOLDER & "\" & TextBox_ABRPolicyFolder.value
    If Not FileExists(filename) Then OpenFolder mABR_FOLDER & "\" & TextBox_ABRPolicyFolder.value
End Sub


Private Sub PopulatePolicy()

Dim dI As cls_PolicyDataItem
Dim dI2 As cls_PolicyDataItem
Dim DB2 As cls_PolicyData
Set DB2 = mPolicy.DB2Data

'ListBox_Policy1

TextBox_PolicyID.value = mPolicy.PolicyID
TextBox_CompanyCode.value = mPolicy.CompanyCode
TextBox_SystemCode.value = mPolicy.SystemCode
TextBox_CyberlifeRegion.value = mPolicy.region

ListBox_Policy1Name.AddItem "Policynumber":  ListBox_Policy1Value.AddItem mPolicy.PolicyNumber
ListBox_Policy1Name.AddItem "Company":  ListBox_Policy1Value.AddItem mPolicy.Company
ListBox_Policy1Name.AddItem "Plancode":  ListBox_Policy1Value.AddItem mPolicy.CovPlancode(1)
ListBox_Policy1Name.AddItem "Product Line Code":  ListBox_Policy1Value.AddItem mPolicy.ProductLineCode
ListBox_Policy1Name.AddItem "ANICO Product Indicator":  ListBox_Policy1Value.AddItem DB2.DataItem("TH_COV_PHA", "AN_PRD_ID").value
ListBox_Policy1Name.AddItem "Advanced Product Indicator":  ListBox_Policy1Value.AddItem DB2.DataItem("LH_BAS_POL", "NON_TRD_POL_IND").value

ListBox_Policy1Name.AddItem " ":  ListBox_Policy1Value.AddItem " "
Set dI = DB2.DataItem("LH_BAS_POL", "POL_ISS_ST_CD"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem TranslateStateCodeToText(CInt(dI.value))
Set dI = DB2.DataItem("LH_BAS_POL", "PRM_PAY_STA_REA_CD"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem dI.value
Set dI = DB2.DataItem("LH_BAS_POL", "SUS_CD"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem dI.value
ListBox_Policy1Name.AddItem "Grace Indicator":  ListBox_Policy1Value.AddItem mPolicy.InGrace
ListBox_Policy1Name.AddItem "GPE Date":  ListBox_Policy1Value.AddItem Format(mPolicy.GPEDate, "m/dd/yyyy")


ListBox_Policy1Name.AddItem " ":  ListBox_Policy1Value.AddItem " "
Set dI = DB2.DataItem("LH_BAS_POL", "PRM_PAID_TO_DT"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem Format(dI.value, "m/dd/yyyy")
Set dI = DB2.DataItem("LH_BAS_POL", "PRM_BILL_TO_DT"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem Format(dI.value, "m/dd/yyyy")
Set dI = DB2.DataItem("LH_BAS_POL", "APP_WRT_DT"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem Format(dI.value, "m/dd/yyyy")
Set dI = DB2.DataItem("LH_BAS_POL", "LST_ANV_DT"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem Format(dI.value, "m/dd/yyyy")
Set dI = DB2.DataItem("LH_BAS_POL", "NXT_BIL_DT"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem Format(dI.value, "m/dd/yyyy")
Set dI = DB2.DataItem("LH_BAS_POL", "NXT_SCH_NOT_DT"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem Format(dI.value, "m/dd/yyyy")
Set dI = DB2.DataItem("LH_BAS_POL", "NXT_SCH_STT_DT"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem Format(dI.value, "m/dd/yyyy")
Set dI = DB2.DataItem("LH_BAS_POL", "NXT_MVRY_PRC_DT"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem Format(dI.value, "m/dd/yyyy")
Set dI = DB2.DataItem("LH_BAS_POL", "NXT_YR_END_PRC_DT"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem Format(dI.value, "m/dd/yyyy")
Set dI = DB2.DataItem("LH_BAS_POL", "LST_ACT_TRS_DT"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem Format(dI.value, "m/dd/yyyy")

ListBox_Policy1Name.AddItem " ":  ListBox_Policy1Value.AddItem " "
Set dI = DB2.DataItem("LH_BAS_POL", "POL_1035_XCG_IND"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem dI.value
Set dI = DB2.DataItem("LH_BAS_POL", "IDT_PRM_IND"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem dI.value
Set dI = DB2.DataItem("LH_BAS_POL", "TFDF_GDL_IND"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem dI.value
Set dI = DB2.DataItem("LH_BAS_POL", "INT_MLV_NBR"):  ListBox_Policy1Name.AddItem dI.CommonName:  ListBox_Policy1Value.AddItem dI.value

Set dI = DB2.DataItem("LH_BAS_POL", "REINSURED_CD"):  ListBox_Policy1Name.AddItem dI.CommonName:

'For Automatic reinsurance I added a comment, (Rein?), to remind me that  just because this policy
'went through the automatic reinsurance pathway doesnt mean any amount of the this policy was actually reinsured.  You would
'need to check the TAI reinsurance system for that
Dim ReCode
ReCode = ReinsuranceCodeDictionary(dI.value)
If ReCode = "Automatic" Then
    ListBox_Policy1Value.AddItem "Auto - (Rein?)"
Else
    ListBox_Policy1Value.AddItem ReCode
End If


ListBox_Policy3Name.AddItem "Marketing Org":  ListBox_Policy3Value.AddItem mPolicy.ServicingMarketOrganization
ListBox_Policy3Name.AddItem "Servicing Branch ":  ListBox_Policy3Value.AddItem mPolicy.ServicingBranchOrAgencyCode
ListBox_Policy3Name.AddItem "Agency Branch ":  ListBox_Policy3Value.AddItem mPolicy.AgencyBranch
ListBox_Policy3Name.AddItem "Servicing Agent ":  ListBox_Policy3Value.AddItem mPolicy.ServicingAgentNumber
Set dI = DB2.DataItem("LH_BAS_POL", "USR_RES_CD")
ListBox_Policy3Name.AddItem "MDO":  ListBox_Policy3Value.AddItem left(dI.value, 1)
ListBox_Policy3Name.AddItem " ":  ListBox_Policy3Value.AddItem ""
ListBox_Policy3Name.AddItem "Class ":  ListBox_Policy3Value.AddItem mPolicy.ClassCode(1)
ListBox_Policy3Name.AddItem "Base ":  ListBox_Policy3Value.AddItem mPolicy.BaseCode(1)
ListBox_Policy3Name.AddItem "Sub ":  ListBox_Policy3Value.AddItem mPolicy.SubseriesCode(1)

ListBox_Policy3Name.AddItem " ":  ListBox_Policy3Value.AddItem " "

Set dI = DB2.DataItem("LH_BAS_POL", "LN_TYP_CD")
If dI.value = "9" Then
    ListBox_Policy3Name.AddItem dI.CommonName:  ListBox_Policy3Value.AddItem "Loans not allowed"
Else
    ListBox_Policy3Name.AddItem dI.CommonName:  ListBox_Policy3Value.AddItem LoanInterestTypeCodeDictionary(dI.value)
    If dI.value = "6" Or dI.value = "7" Then
    '6 and 7 mean interest rate is variable and is not found on the 01 segment.  So dont print rate
    Else
        Set dI = DB2.DataItem("LH_BAS_POL", "LN_PLN_ITS_RT")
        ListBox_Policy3Name.AddItem dI.CommonName:  ListBox_Policy3Value.AddItem Format(dI.value / 100, "#0.00%")
    End If
End If


Dim tempValue As Variant
tempValue = TranslateBillModeCodeToText(DB2.DataItem("LH_BAS_POL", "PMT_FQY_PER").value, DB2.DataItem("LH_BAS_POL", "NSD_MD_CD").value)
ListBox_Policy2Name.AddItem "Premium Mode":  ListBox_Policy2Value.AddItem tempValue
ListBox_Policy2Name.AddItem "Modal Premium":  ListBox_Policy2Value.AddItem Format(mPolicy.BillPremium, "$#,##0.00")
Set dI = DB2.DataItem("LH_BAS_POL", "BIL_FRM_CD"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem TranslateBillFormCode(dI.value)
Set dI = DB2.DataItem("LH_BIL_FRM_CTL", "BIL_CTL_NBR")
ListBox_Policy2Name.AddItem "Billing Control Number"
If dI.FieldNotFound Then
    ListBox_Policy2Value.AddItem "not found"
Else
    ListBox_Policy2Value.AddItem DB2.DataItem("LH_BIL_FRM_CTL", "BIL_CTL_NBR").value
End If

ListBox_Policy2Name.AddItem " ":  ListBox_Policy2Value.AddItem " "

'A 52 segment type "R" is a replacement segment.  It means the policy was issued as a replacement for another policy (internal or external to the company)
Set dI = DB2.DataItem("TH_USER_REPLACEMENT", "SEGMENT_TYPE")
If Trim(dI.NullZ()) = "R" Then
    Set dI2 = DB2.DataItem("TH_USER_REPLACEMENT", "REPLACED_POLICY")
    ListBox_Policy2Name.AddItem "Replaced Policy":
    mReplacedPolicyNumber = Trim(dI2.value)
    ListBox_Policy2Value.AddItem mReplacedPolicyNumber
Else
    mReplacedPolicyNumber = "#none#"
End If



'OGN_ETR_CD of "E" means the policy was issued as a conversion or replacement from another policy
Set dI = DB2.DataItem("LH_BAS_POL", "OGN_ETR_CD"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem TranslateOriginalEntryCodeToText(dI.value)

Set dI2 = DB2.DataItem("TH_USER_GENERIC", "EXCH_POL_NUMBER")
ListBox_Policy2Name.AddItem "Converted Policy":
mConvertedPolicyNumber = Trim(dI2.value)
ListBox_Policy2Value.AddItem mConvertedPolicyNumber

Set dI = DB2.DataItem("LH_BAS_POL", "LST_ETR_CD"):
ListBox_Policy2Name.AddItem dI.CommonName:
ListBox_Policy2Value.AddItem TranslateLastEntryCodeToText(dI.value)
Set dI = DB2.DataItem("LH_BAS_POL", "LST_FIN_DT"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem dI.value
Set dI = DB2.DataItem("LH_BAS_POL", "USR_RES_CD")
ListBox_Policy2Name.AddItem "MDO":  ListBox_Policy2Value.AddItem left(dI.value, 1)
ListBox_Policy2Name.AddItem "ByPass Lapse":  ListBox_Policy2Value.AddItem Right(dI.value, 1)
Set dI = DB2.DataItem("LH_BAS_POL", "MEC_STATUS_CD"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem TranslateMECIndicatorToText(dI.value)



ListBox_Policy2Name.AddItem " ":  ListBox_Policy2Value.AddItem " "
If mPolicy.ProductLineCode = "U" Then
    tempValue = "Surrender value"
Else
    tempValue = NonForfeitureCodeDictionary(dI.value)
End If

Set dI = DB2.DataItem("LH_BAS_POL", "NFO_OPT_TYP_CD"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem tempValue

ListBox_Policy2Name.AddItem " ":  ListBox_Policy2Value.AddItem " "
Set dI = DB2.DataItem("LH_BAS_POL", "PRI_DIV_OPT_CD"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem DivOptionCodeDictionary(dI.value)
Set dI = DB2.DataItem("LH_BAS_POL", "DIV_2ND_OPT_CD"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem DivOptionCodeDictionary(dI.value)

ListBox_Policy2Name.AddItem " ":  ListBox_Policy2Value.AddItem " "
Set dI = DB2.DataItem("LH_COV_PHA", "MTL_FCT_TBL_CD"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem dI.value
ListBox_Policy2Name.AddItem "Description":  ListBox_Policy2Value.AddItem GetMortalityTableDescription(dI.value)

Set dI = DB2.DataItem("LH_COV_PHA", "RES_ITS_RT"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem Format(dI.value / 100, "#.00%")
Set dI = DB2.DataItem("LH_COV_PHA", "MTL_FUN_CD"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem dI.value
ListBox_Policy2Name.AddItem " ":  ListBox_Policy2Value.AddItem " "
Set dI = DB2.DataItem("LH_COV_PHA", "NSP_EI_TBL_CD"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem dI.value
ListBox_Policy2Name.AddItem "Description":  ListBox_Policy2Value.AddItem GetMortalityTableDescription(dI.value)
Set dI = DB2.DataItem("LH_COV_PHA", "NSP_RPU_TBL_CD"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem dI.value
ListBox_Policy2Name.AddItem "Description":  ListBox_Policy2Value.AddItem GetMortalityTableDescription(dI.value)

Set dI = DB2.DataItem("LH_COV_PHA", "NSP_ITS_RT")
If dI.value <> "Null" Then
    ListBox_Policy2Name.AddItem dI.CommonName: ListBox_Policy2Value.AddItem Format(dI.value / 100, "#.00%")
End If



If mPolicy.ProductLineCode = 0 Then
    ListBox_Policy2Name.AddItem " ":  ListBox_Policy2Value.AddItem " "
    Set dI = DB2.DataItem("LH_FXD_PRM_POL", "MD_PRM_SRC_CD"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem dI.value
    Set dI = DB2.DataItem("LH_FXD_PRM_POL", "SAN_MD_FCT"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem dI.value
    Set dI = DB2.DataItem("LH_FXD_PRM_POL", "QTR_MD_FCT"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem dI.value
    Set dI = DB2.DataItem("LH_FXD_PRM_POL", "MO_MD_FCT"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem dI.value
    Set dI = DB2.DataItem("LH_FXD_PRM_POL", "MD_PRM_MUL_ORD_CD"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem dI.value
    Set dI = DB2.DataItem("LH_FXD_PRM_POL", "RT_FCT_ORD_CD"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem dI.value
    Set dI = DB2.DataItem("LH_FXD_PRM_POL", "ROU_RLE_CD"):  ListBox_Policy2Name.AddItem dI.CommonName:  ListBox_Policy2Value.AddItem dI.value
End If




ListBox_Policy1Value.TextAlign = fmTextAlignRight
ListBox_Policy2Value.TextAlign = fmTextAlignRight
'ListBox_Policy3Value.TextAlign = fmTextAlignRight

ListBox_Policy1Value.ColumnWidths = "1"
ListBox_Policy2Value.ColumnWidths = "1"
'ListBox_Policy3Value.ColumnWidths = "1"

ListBox_Policy1Name.Backcolor = Me.Backcolor
ListBox_Policy1Value.Backcolor = Me.Backcolor
ListBox_Policy2Name.Backcolor = Me.Backcolor
ListBox_Policy2Value.Backcolor = Me.Backcolor
ListBox_Policy3Name.Backcolor = Me.Backcolor
ListBox_Policy3Value.Backcolor = Me.Backcolor

Label_TransposeView = "Transpose"
End Sub

Private Sub DefaultSettings()
Dim item

Frame_Display.height = 420
Frame_Display.width = 728
Frame_Display.top = 18
Frame_Display.left = 166

mLeftAdjust = Frame_Tree.width + Frame_Tree.left + 1

TextBox_PolicyNumber = mPolicy.PolicyNumber
TextBox_PolicyNumber.Backcolor = Me.Backcolor
TextBox_CompCd = mPolicy.CompanyCode
TextBox_CompCd.Backcolor = Me.Backcolor
TextBox_Region.value = mPolicy.region
TextBox_Region.Backcolor = Me.Backcolor
TextBox_SystemCd.value = mPolicy.SystemCode
TextBox_SystemCd.Backcolor = Me.Backcolor
TextBox_CurrentDisplay.Backcolor = Me.Backcolor

Label_ShowHideTree = SHOWTREE



With dctControlsHideWithTree
    .Add "Frame_Tree", Frame_Tree
    .Add "Label_TransposeView", Label_TransposeView
    .Add "ListBox_LoadingMessage", ListBox_LoadingMessage
    .Add "Label_LoadTables", Label_LoadTables
    .Add "Label_LoadRates", Label_LoadRates
End With


With dctControlsMoveForTree
'    .Add "Label_ViewDescription", Label_ViewDescription
    .Add "MultiPage1", MultiPage1
    .Add "Frame_Display", Frame_Display
'    .Add "ListBox_Policynumber", ListBox_Policynumber
'    .Add "ListBox_Region", ListBox_Region
    .Add "Label_ShowHideTree", Label_ShowHideTree
    .Add "Label_ReturnToMain", Label_ReturnToMain
    .Add "Label_Export", Label_Export
    .Add "TextBox_CurrentDisplay", TextBox_CurrentDisplay
End With

TurnOffTreeView

End Sub
Private Sub TurnOnTreeView()
Dim item
For Each item In dctControlsHideWithTree.items
    item.Visible = True
Next
ListBox_LoadingMessage.Visible = False
Label_LoadTables.Visible = Not (blnTablesRetreived)


For Each item In dctControlsMoveForTree.items
    item.left = item.left + mLeftAdjust
Next
Me.width = Me.width + mLeftAdjust
blnTreeViewOn = True
Label_ShowHideTree = HIDETREE
End Sub
Private Sub TurnOffTreeView()
Dim item
For Each item In dctControlsHideWithTree.items
    item.Visible = False
Next
For Each item In dctControlsMoveForTree.items
    item.left = item.left - mLeftAdjust
Next
Me.width = Me.width - mLeftAdjust
blnTreeViewOn = False
Label_ShowHideTree = SHOWTREE
End Sub


Private Sub Label_Coverages_Click()
    Dim Covs, bens
    Covs = colVBox("Coverages").TableData
    
    Err.Clear
    On Error Resume Next
    colVBox("Benefits").ListCount
    If Err.Number = 0 Then
        bens = colVBox("Benefits").TableData
        bens = ExpandArray(bens, 2, UBound(Covs, 2) - UBound(bens, 2), "")
        DumpArrayValuesIntoExcel CombineTwoDArrays(Covs, bens)
    Else
        DumpArrayValuesIntoExcel Covs
    End If
    Err.Clear
    On Error GoTo 0
    
    
End Sub

Private Sub Label_Export_Click()
    If IsEmpty(VBoxDisplay.TableData) Then Exit Sub
    DumpArrayValuesIntoExcel VBoxDisplay.TableData
End Sub
Private Sub Label_ExportActivity_Click()
    DumpArrayValuesIntoExcel colVBox("ActivityDetail").TableData
End Sub

Private Sub Label_ExportBucketDetail_Click()
    DumpArrayValuesIntoExcel colVBox("BucketDetail").TableData
End Sub

Private Sub Label_ExportCommissioTargets_Click()
    DumpArrayValuesIntoExcel colVBox("CovCTP").TableData
End Sub

Private Sub Label_ExportLoanDetail_Click()
    DumpArrayValuesIntoExcel colVBox("LoanDetail").TableData
End Sub

Private Sub Label_ExportMinimumTargets_Click()
    DumpArrayValuesIntoExcel colVBox("CovMTP").TableData
End Sub

Private Sub Label_LoadRates_Click()
    LoadRatesInTreeView
    dctControlsHideWithTree.Remove ("Label_LoadRates")
    Label_LoadRates.Visible = False
End Sub

Private Sub Label_LoadTables_Click()
    LoadTablesInTreeView
    dctControlsHideWithTree.Remove ("Label_LoadTables")
    Label_LoadTables.Visible = False
End Sub

Private Sub Label_LoadTables_MouseDown(ByVal Button As Integer, ByVal Shift As Integer, ByVal X As Single, ByVal Y As Single)
  ListBox_LoadingMessage.List = Array("Loading...")
  ListBox_LoadingMessage.left = Frame_Tree.left + 10
  ListBox_LoadingMessage.top = Frame_Tree.top + 100
  
  ListBox_LoadingMessage.Visible = True
End Sub

Private Sub Label_ReturnToMain_Click()
  PlaceMultipageOverDiplay

  
End Sub

Private Sub Label_ShowHideTree_Click()
If Label_ShowHideTree = SHOWTREE Then
  TurnOnTreeView
Else
  TurnOffTreeView
End If

End Sub
Private Sub Label_YearlyTAMARAValues_Click()
    DumpArrayValuesIntoExcel colVBox("YearlyTAMRAValues").TableData
End Sub






'===============================================================================================================================================================================
'===============================================================================================================================================================================
'The code below is used to populate and handle the displays on the Multipage
'===============================================================================================================================================================================
'===============================================================================================================================================================================


Private Sub PopulateCoverges()

Label_PolicySuspense = mPolicy.SuspenseCode & " - " & TranslateSuspenseCodeToText(mPolicy.SuspenseCode)
Label_PolicySuspense.Backcolor = Me.Backcolor
If mPolicy.SuspenseCode > 0 Then Label_PolicySuspense.Backcolor = &HC0C0FF

Label_PolicyStatus = mPolicy.StatusCode & " - " & mPolicy.StatusText
Label_PolicyStatus.Backcolor = Me.Backcolor
If CInt(mPolicy.StatusCode) >= 97 Then Label_PolicyStatus.Backcolor = &HC0C0FF

Label_JointInsured = IIf(mPolicy.IsJointInsured, "Joint insured policy", "Single insured policy")

mProductGroup = GetPlancodeDescription(mPolicy.CovPlancode(1), Group)
Label_ProductType = mProductGroup

If mPolicy.InGrace = "1" Then
    Label_InGrace = "Policy is in the Grace period"
    Label_InGrace.Backcolor = &HFFC0C0
Else
    Label_InGrace = "Not in Grace"
    Label_InGrace.Backcolor = Me.Backcolor
End If


If mPolicy.CovCount = 0 Then Exit Sub

Dim s As cls_Storage
Set s = New cls_Storage

s.AddColumn "Phs"
s.AddColumn "Form"
s.AddColumn "COLA"
s.AddColumn "GIO"
s.AddColumn "Plancode"
s.AddColumn "IssueDate"
s.AddColumn "Mat Date"
s.AddColumn "Amount"

If mPolicy.ProductLineCode = "U" Then
    s.AddColumn "Orig Amt"
End If

s.AddColumn "IssAge"
s.AddColumn "Gender"
s.AddColumn "Class"
s.AddColumn "Tbl"


If mPolicy.IsJointInsured Then

    s.AddColumn "IssAge2"
    s.AddColumn "Gender2"
    s.AddColumn "Class2"
    s.AddColumn "Tbl2"
Else
    
    'I dont think any joint insured policies have flat extra, so only display these fields is policy is not a joint insured
    s.AddColumn "Flat"
    s.AddColumn "Flat Cease Dt"
    'These fields arent that important to me and space is at a premium so they are only displayed if policy is not a joint insured
    s.AddColumn "PRS"   'Person Code
    s.AddColumn "LIV"   'Lives Covered Code
    s.AddColumn "AA"    'Attained Age
End If

s.AddColumn "VPU"
s.AddColumn "Status"
s.AddColumn "CeaseDate"
s.AddColumn "Rate"


Dim xcount As Integer, tempValue
For xcount = 1 To mPolicy.CovCount
    s.AddRow
    s("Phs") = mPolicy.CovPhase(xcount)
    
    If mPolicy.CovCOLAIndicator(xcount) = "1" Then
      s("COLA") = "COLA"
    Else
      s("COLA") = " "
    End If
    
    If mPolicy.CovGIOIndicator(xcount) = "Y" Then
      s("GIO") = "GIO"
    Else
      s("GIO") = " "
    End If
    
    
    s("Plancode") = mPolicy.CovPlancode(xcount)
    s("Form") = WorksheetFunction.Trim(mPolicy.CovFormNumber(xcount))
    s("IssueDate") = Format(mPolicy.CovIssueDate(xcount), "m/dd/yyyy")
    s("Mat Date") = Format(mPolicy.CovMaturityDate(xcount), "m/dd/yyyy")
    
    'Only display decimals if needed
    tempValue = mPolicy.CovAmount(xcount) - WorksheetFunction.RoundDown(mPolicy.CovAmount(xcount), 0)
    If tempValue > 0 Then
        s("Amount") = Format(mPolicy.CovAmount(xcount), "#,##0.00")
    Else
        s("Amount") = Format(mPolicy.CovAmount(xcount), "#,##0")
    End If
    
    
    If mPolicy.ProductLineCode = "U" Then
        tempValue = mPolicy.CovOrigAmount(xcount) - WorksheetFunction.RoundDown(mPolicy.CovOrigAmount(xcount), 0)
        If tempValue > 0 Then
            s("Orig Amt") = Format(mPolicy.CovOrigAmount(xcount), "#,##0.00")
        Else
            s("Orig Amt") = Format(mPolicy.CovOrigAmount(xcount), "#,##0")
        End If
    End If
    
    If mPolicy.CovVPU(xcount) = 1000 Then
        s("VPU") = Format(mPolicy.CovVPU(xcount), "#,##0")
    Else
        s("VPU") = Format(mPolicy.CovVPU(xcount), "#,##0.000")
    End If
    
    s("IssAge") = mPolicy.CovIssueAge(xcount)
    s("Gender") = mPolicy.CovSex(xcount)
    s("Class") = mPolicy.CovRateclass(xcount)
    s("Tbl") = IIf(mPolicy.CovTable(xcount) = 0, " ", mPolicy.CovTable(xcount))
    
    s("Status") = mPolicy.CovStatus(xcount)
    If mPolicy.CovStatus(xcount) = "0" Then
        s("CeaseDate") = mPolicy.DB2Data.DataItem("LH_COV_PHA", "NXT_CHG_DT").value(xcount)
    Else
        s("CeaseDate") = " "
    End If
    
    If mPolicy.IsJointInsured Then
        s("IssAge2") = mPolicy.CovIssueAge(xcount, 1)
        s("Gender2") = mPolicy.CovSex(xcount, 1)
        s("Class2") = mPolicy.CovRateclass(xcount, 1)
        s("Tbl2") = IIf(mPolicy.CovTable(xcount, 1) = 0, " ", mPolicy.CovTable(xcount, 1))
    Else
        'I dont think any joint insured policies have flat extras, so only display these fields is policy is not a joint insured
        If mPolicy.CovFlat(xcount) > 0 Then
            s("Flat") = Format(mPolicy.CovFlat(xcount), "#0.00")
            s("Flat Cease Dt") = Format(mPolicy.CovFlatCeaseDate(xcount), "m/dd/yyyy")
        Else
            s("Flat") = " "
            s("Flat Cease Dt") = " "
        End If
        
        'Dont print these for joint insured.  I just dont think they are important enough and space is at a premium
        s("PRS") = mPolicy.DB2Data.DataItem("LH_COV_PHA", "PRS_CD").value(xcount)
        s("LIV") = mPolicy.DB2Data.DataItem("LH_COV_PHA", "LIVES_COV_CD").value(xcount)
        
        If mPolicy.ValuationDate = "Null" Then
            s("AA") = ""
        Else
            s("AA") = mPolicy.CovIssueAge(xcount) + CompletedDateParts("YYYY", mPolicy.CovIssueDate(1), mPolicy.ValuationDate) - CompletedDateParts("YYYY", mPolicy.CovIssueDate(1), mPolicy.CovIssueDate(xcount))
        End If
        
        If mPolicy.AdvancedProductIndicator = "1" Then
            If mPolicy.ProductLineCode = "I" Then
                s("Rate") = mPolicy.RenewalCovRate(xcount, "C") / 100
            Else
                s("Rate") = mPolicy.RenewalCovRate(xcount, "C") / 100000
            End If
        Else
            s("Rate") = mPolicy.DB2Data.DataItem("LH_COV_PHA", "ANN_PRM_UNT_AMT").value(xcount)
        End If
        
    End If
Next

Dim VBox As clsVBox
Set VBox = New clsVBox

VBox.Initialize Frame_Coverages, Me.Backcolor
VBox.TableData = s.GetArrayOfValues
'VBox.ColumnWidths = "23;47;29;53;59;53;41;53;41;41;35;23;29;83;23;23;17;35;41;59"
colStorage.Add s, "Coverages"
colVBox.Add VBox, "Coverages"



With mPolicy
If .ValuationDate = "Null" Then
    ListBox_Coverages1.AddItem "Eff Date": ListBox_Coverages2.AddItem "None Found"
    ListBox_Coverages1.AddItem "Policy Year": ListBox_Coverages2.AddItem "None Found"
    ListBox_Coverages1.AddItem "Month of Yr": ListBox_Coverages2.AddItem "None Found"
    ListBox_Coverages1.AddItem "Att Age": ListBox_Coverages2.AddItem "None Found"
Else
    ListBox_Coverages1.AddItem "Eff Date": ListBox_Coverages2.AddItem Format(.ValuationDate, "m/dd/yyyy")
    ListBox_Coverages1.AddItem "Policy Year": ListBox_Coverages2.AddItem .PolicyYear
    ListBox_Coverages1.AddItem "Month of Yr": ListBox_Coverages2.AddItem .PolicyMonth
    ListBox_Coverages1.AddItem "Att Age": ListBox_Coverages2.AddItem .CovIssueAge(1) + .PolicyYear - 1

  
End If

'ListBox_Coverages1.AddItem " ": ListBox_Coverages2.AddItem " "
If .ProductLineCode = "U" Then
    'ListBox_Coverages1.AddItem " ": ListBox_Coverages2.AddItem " "
    ListBox_Coverages1.AddItem "DB Option": ListBox_Coverages2.AddItem .DBOption
End If
    
ListBox_Coverages1.AddItem " ": ListBox_Coverages2.AddItem " "
ListBox_Coverages1.AddItem "Age at Maturity": ListBox_Coverages2.AddItem .AgeAtMaturity
ListBox_Coverages1.AddItem " ": ListBox_Coverages2.AddItem " "
If Len(.Rein_Partner(1)) >= 1 Then ListBox_Coverages1.AddItem "Rein Partner": ListBox_Coverages2.AddItem .Rein_Partner(1)

ListBox_CoveragesNames2.AddItem "  Specified Amount on Primary Insured:": ListBox_CoveragesValues2.AddItem SpecifiedAmountOnPrimaryInsured
If .DivPUACurrent > 0 Then ListBox_CoveragesNames2.AddItem "+ Paid Up Additions:":  ListBox_CoveragesValues2.AddItem .DivPUACurrent
If .DivDepositCurrent > 0 Then ListBox_CoveragesNames2.AddItem "+ Dividends On Deposit:": ListBox_CoveragesValues2.AddItem .DivDepositCurrent
If .DivOYTCurrent > 0 Then ListBox_CoveragesNames2.AddItem "+ One Year Team:": ListBox_CoveragesValues2.AddItem .DivOYTCurrent
If .DBOptionAmount > 0 Then ListBox_CoveragesNames2.AddItem "+ " & .DBOption & " Amount:": ListBox_CoveragesValues2.AddItem .DBOptionAmount

If .PolicyDebt > 0 Then ListBox_CoveragesNames2.AddItem "- Policy Debt:": ListBox_CoveragesValues2.AddItem .PolicyDebt
ListBox_CoveragesNames2.AddItem "------------------------------------": ListBox_CoveragesValues2.AddItem "------------"
ListBox_CoveragesNames2.AddItem "  Total DB on Primary Insured:": ListBox_CoveragesValues2.AddItem SpecifiedAmountOnPrimaryInsured + .DBOptionAmount + .DivPUACurrent + .DivDepositCurrent + .DivOYTCurrent - .PolicyDebt



ListBox_Coverages1.Backcolor = Me.Backcolor
ListBox_Coverages2.Backcolor = Me.Backcolor
ListBox_CoveragesNames2.Backcolor = Me.Backcolor
ListBox_CoveragesNames2.TextAlign = fmTextAlignRight
ListBox_CoveragesValues2.Backcolor = Me.Backcolor

End With


End Sub

Private Function SpecifiedAmountOnPrimaryInsured() As Double
Dim X As Integer, subtotal As Double
With mPolicy
For X = 1 To .CovCount
    'Only add the amount if coverage is covering primary insured
    If .DB2Data.DataItem("LH_COV_PHA", "PRS_CD").value(X) = "00" And .DB2Data.DataItem("LH_COV_PHA", "LIVES_COV_CD").value(X) <> "7" And .DB2Data.DataItem("LH_COV_PHA", "PRS_SEQ_NBR").value(X) = 1 Then
        'Only add amount if coverage is currently inforce
        If .DB2Data.DataItem("LH_COV_PHA", "NXT_CHG_TYP_CD").value(X) = "2" Then
            subtotal = subtotal + .CovAmount(X)
        End If
    End If
Next
End With
SpecifiedAmountOnPrimaryInsured = subtotal
End Function

Private Sub PopulateBenefits()

If mPolicy.BenCount = 0 Then Exit Sub

Dim s As cls_Storage
Set s = New cls_Storage

s.AddColumn "Code"
s.AddColumn "Phs"
s.AddColumn "Type"
s.AddColumn "Form"
s.AddColumn "IssueDate"
s.AddColumn "CeaseDate"
s.AddColumn "OrigCease"
s.AddColumn "Units"
s.AddColumn "VPU"
s.AddColumn "IssAge"
s.AddColumn "Rating"
s.AddColumn "Renew"
s.AddColumn "Rate"

Dim xcount As Integer
For xcount = 1 To mPolicy.BenCount
    s.AddRow
    s("Code") = mPolicy.BenPlancode(xcount)
    s("Phs") = mPolicy.BenCovPhase(xcount)
    s("Type") = mPolicy.BenTypeCode(xcount)
    s("Form") = WorksheetFunction.Trim(mPolicy.BenFormNumber(xcount))
    s("IssueDate") = Format(mPolicy.BenIssueDate(xcount), "m/dd/yyyy")
    s("CeaseDate") = Format(mPolicy.BenCeaseDate(xcount), "m/dd/yyyy")
    s("OrigCease") = Format(mPolicy.BenOriginalCeaseDate(xcount), "m/dd/yyyy")
    s("Units") = Format(mPolicy.BenUnits(xcount), "#,##0.00")
    s("VPU") = IIf(mPolicy.BenVPU(xcount) = 1000, Format(mPolicy.BenVPU(xcount), "#,##0"), Format(mPolicy.BenVPU(xcount), "#,##0.000"))
    s("IssAge") = mPolicy.BenIssueAge(xcount)
    s("Rating") = Format(mPolicy.BenRatingFactor(xcount), "#,##0%")
    s("Renew") = mPolicy.BenRenewalIndicator(xcount)
  
  
    'if rate is a renewal rate, find benefit renewal rate (prem type "B" from the policy record 67 segment).  Otherwise the rate is found on the benefit (04) segment
    Dim tempValue
    tempValue = "No renew"
    Dim ycount As Integer
    If mPolicy.BenRenewalIndicator(xcount) = "1" Then
        For ycount = 1 To mPolicy.RenewalBenCount
            'Prem type "B" means the rate is a benefit COI rate
            If mPolicy.RenewalBenPremiumTypeCode(ycount) = "B" And mPolicy.BenPlancode(xcount) = mPolicy.RenewalBenTypeCode(ycount) & mPolicy.RenewalBenSubTypeCode(ycount) Then
                tempValue = mPolicy.RenewalBenRate(ycount)
            End If
        Next
        If IsNumeric(tempValue) Then
            tempValue = tempValue / 100000
            tempValue = Format(tempValue, "##0.000")

        Else
            tempValue = " "
        End If
    Else
        tempValue = Format(mPolicy.BenCOIRate(xcount), "##0.00")
    End If
    s("Rate") = tempValue

Next
  
'Load VBox with data from S
Dim VBox As clsVBox
Set VBox = New clsVBox
VBox.Initialize Frame_Benefits, Me.Backcolor
VBox.TableData = s.GetArrayOfValues
VBox.ColumnWidths = "22;35;50;55;55;55;55;63;35;40;30;50"
colVBox.Add VBox, "Benefits"
colStorage.Add s, "Benefits"
Set VBox = Nothing
Set s = Nothing


End Sub


Private Sub PopulateYearlyTAMRAValues()

If mPolicy.NoTAMRAValues Then
    Frame_TamraValues.Visible = False
Else
    
    Dim s As cls_Storage
    Set s = New cls_Storage

    s.AddColumn "Seq"
    s.AddColumn "Premium"
    s.AddColumn "Withdrawal"
    
    Dim xcount As Integer
    For xcount = 1 To 7
        s.AddRow
        s("Seq") = xcount
        s("Premium") = Format(mPolicy.TAMRA_7PayPremiumPaid(xcount), "#,##0.00")
        s("Withdrawal") = Format(mPolicy.TAMRA_7PayWithdrawal(xcount), "#,##0.00")
    Next
     
    'Load VBox with data from S
    Dim VBox As clsVBox
    Set VBox = New clsVBox
    VBox.Initialize Frame_YearlyTAMRAValues, Me.Backcolor
    VBox.TableData = s.GetArrayOfValues
    VBox.ColumnWidths = "30;54;54"

    
    colVBox.Add VBox, "YearlyTAMRAValues"
    colStorage.Add s, "YearlyTAMRAValues"
    Set VBox = Nothing
    Set s = Nothing
    
    'Populate Labels
    Frame_TamraValues.Visible = True
    Label_MECStatus = TranslateMECIndicatorToText(mPolicy.MEC_Indicator)
    Label_7PayPremium = Format(mPolicy.TAMRA_7PayLevel, "#,##0.00")
    Label_7PayStartDate = Format(mPolicy.TAMRA_7PayStartDate, "m/dd/yyyy")
    Label_1035Count = mPolicy.CountOf1035Payments
    Label_7PayAV = mPolicy.TAMRA_7PayAV
End If

End Sub

Private Sub PopulateCommissionTargets()

If mPolicy.CovCount = 0 Then Exit Sub
If mPolicy.CTPCount = 0 Then Exit Sub
Dim s As cls_Storage
Set s = New cls_Storage


s.AddColumn "Phs"
s.AddColumn "Face"
s.AddColumn "Target"
s.AddColumn "Date"
s.AddColumn "Rate"

Dim xcount As Integer, CTPRIndex As Integer, tempValue
  For xcount = 1 To mPolicy.CTPCount
      s.AddRow
      s("Phs") = mPolicy.CovCTPhase(xcount)
      s("Face") = Format(mPolicy.CovAmount(xcount), "#,##0")
      s("Target") = Format(mPolicy.CovCTP(xcount), "#,##0.00")
      s("Date") = Format(mPolicy.CovCTDate(xcount), "m/dd/yyyy")
    
      tempValue = mPolicy.RenewalCovRate(xcount, "T")
      If Not IsEmpty(tempValue) Then
           s("Rate") = Format(tempValue / 1000, "##0.000")
           s("Face") = Format(mPolicy.CovAmount(xcount) / 1000 * tempValue / 1000, "#,##0.00")
      Else
           s("Rate") = " "
      End If
  Next

  'Load VBox with data from S
  Dim VBox As clsVBox
  Set VBox = New clsVBox
  VBox.Initialize Frame_CovCTP, Me.Backcolor
  VBox.TableData = s.GetArrayOfValues
  VBox.ColumnWidths = "25;54;49;54;40"
  colVBox.Add VBox, "CovCTP"
  colStorage.Add s, "CovCTP"
  Set VBox = Nothing
  Set s = Nothing


'Populate Labels
Label_CommissionTargetPremium = Format(mPolicy.CTP, "#,##0.00")

If colVBox("CovCTP").ListCount = 0 Then
    Frame_CommissionTargets.Visible = False
Else
    Frame_CommissionTargets.Visible = True
End If

End Sub


Private Sub PopulateMinimumTargets()
'This procedure will create a record set of data and populate the VBox with that recordset
'The recordset is stored in a dictionary and can be called upon later for filtering, ordering etc

If (mPolicy.MTP = 0 Or IsEmpty(mPolicy.MTP)) And mPolicy.MAPDate = 0 Then
    Frame_MinimumPremium.Visible = False
    Exit Sub
End If

Frame_MinimumPremium.Visible = True

Dim s As cls_Storage
Set s = New cls_Storage

s.AddColumn "Phs"
s.AddColumn "CovType"
s.AddColumn "Face"
s.AddColumn "Target"
s.AddColumn "Rate"

Dim xcount As Integer, MTPRIndex As Integer, tempValue
For xcount = 1 To mPolicy.CovCount
    s.AddRow
    s("Phs") = mPolicy.CovPhase(xcount)
    s("Face") = Format(mPolicy.CovAmount(xcount), "#,##0")
    
    s("CovType") = IIf(mPolicy.CovPlancode(xcount) = mPolicy.CovPlancode(1), "BASE", "RIDER")
 
    tempValue = mPolicy.RenewalCovRate(xcount, "M")
    
    If Not IsEmpty(tempValue) Then
         s("Rate") = Format(tempValue / 1000, "##0.000")
         s("Target") = Format(mPolicy.CovAmount(xcount) / 1000 * tempValue / 1000, "#,##0.00")
    Else
        s("Rate") = " "
    End If
    

Next

'Load VBox with data from S
Dim VBox As clsVBox
Set VBox = New clsVBox
VBox.Initialize Frame_CovMTP, Me.Backcolor
VBox.TableData = s.GetArrayOfValues
VBox.ColumnWidths = "25;45;55;50;40"
colVBox.Add VBox, "CovMTP"
colStorage.Add s, "CovMTP"
Set VBox = Nothing
Set s = Nothing


'Populate Labels
If mPolicy.MTP = "Null" Then
    Label_MinimumAnnualPremium = "Null"
    Label_MonthlyMin = "Null"
    Label_AccumMTP = "Null"
    Label_MAPDate = "Null"
Else
    Label_MinimumAnnualPremium = Format(mPolicy.MTP * 12, "#,##0.00")
    Label_MonthlyMin = Format(mPolicy.MTP, "#,##0.00")
    Label_AccumMTP = Format(mPolicy.AccumMTP, "#,##0.00")
    Label_MAPDate = Format(mPolicy.MAPDate, "m/dd/yyyy")
End If

End Sub

Private Sub Populate7702andPremiums()

If mPolicy.PolicyTotalsCount > 0 Then
    Label_CostBasis.Visible = True
    Label_AccumWDs.Visible = True
    Label_CostBasisLabel.Visible = True
    Label_AccumWDsLabel.Visible = True
    Label_RegularPremiumsPaid = True
    Label_AdditionalPremiumsPaid = True
    Label_CostBasis = Format(mPolicy.CostBasis, "#,##0.00")
    Label_AccumWDs = Format(mPolicy.AccumWithdrawals, "#,##0.00")
    Label_PremiumsPaid = Format(mPolicy.PremiumTD, "#,##0.00")
    Label_RegularPremiumsPaid = Format(mPolicy.TotalRegularPremium, "#,##0.00")
    Label_AdditionalPremiumsPaid = Format(mPolicy.TotalAdditionalPremium, "#,##0.00")
    Label_PremiumYTD = Format(mPolicy.PremiumYTD, "#,##0.00")
Else
    Label_CostBasis.Visible = False
    Label_AccumWDs.Visible = False
    Label_CostBasisLabel.Visible = False
    Label_AccumWDsLabel.Visible = False
    Label_RegularPremiumsPaid = False
    Label_AdditionalPremiumsPaid = False
    Label_PremiumsPaid = Format(mPolicy.TRAD_AccumulatedPremium, "#,##0.00")
End If

If mPolicy.AdvancedProductIndicator = "1" Then
    Frame_DefinitionOfLifeInsurance.Visible = True
'Determinate Definition of Life insurance
If mPolicy.GP_CVAT = "GP" Then
  ListBox_DefOfInsurance_Name.AddItem "TEFRA/DEFRA": ListBox_DefOfInsurance_Value.AddItem mPolicy.TEFRA_DEFRA
  ListBox_DefOfInsurance_Name.AddItem "Guideline/CVAT": ListBox_DefOfInsurance_Value.AddItem mPolicy.GP_CVAT
  ListBox_DefOfInsurance_Name.AddItem "GSP": ListBox_DefOfInsurance_Value.AddItem Format(mPolicy.GSP, "#,##0.00")
  ListBox_DefOfInsurance_Name.AddItem "GLP": ListBox_DefOfInsurance_Value.AddItem Format(mPolicy.GLP, "#,##0.00")
  ListBox_DefOfInsurance_Name.AddItem "Accum GLP": ListBox_DefOfInsurance_Value.AddItem Format(mPolicy.AccumGLP, "#,##0.00")
  ListBox_DefOfInsurance_Name.AddItem "Corr Pct": ListBox_DefOfInsurance_Value.AddItem Format(mPolicy.NonTrad_CorridorPercent / 100, "#.00")

    If mPolicy.StatusCode < 97 And mPolicy.ValuationDate <> "Null" And mPolicy.AccumGLP <> "Null" And mPolicy.GLP <> "Null" Then
      
      'Calculate the max level annual qualifying premium to maturity
      'This is the maxium premium they can pay each year and still have the policy qualify as life insurance each year.
      'If the policy cannot get to maturity with this premium then it will eventually need guideline exception premiums
      Dim PremiumPayingYears_To_GLPMat As Integer, AccumGLP_at_GLPMat As Double
      mInsuranceDefinitionMaturityAge = fmin(100, mPolicy.AgeAtMaturity)
      PremiumPayingYears_To_GLPMat = fmax(0, mInsuranceDefinitionMaturityAge - mPolicy.AttainedAge - 1)
      
      AccumGLP_at_GLPMat = mPolicy.GLP * PremiumPayingYears_To_GLPMat + mPolicy.AccumGLP
      
      If PremiumPayingYears_To_GLPMat = 0 Then
        mMaxAnnualLevelQualPrem = 0
      Else
        mMaxAnnualLevelQualPrem = Format((AccumGLP_at_GLPMat - (mPolicy.PremiumTD - mPolicy.AccumWithdrawals)) / PremiumPayingYears_To_GLPMat, "#,##.00")
      End If
      
      ListBox_DefOfInsurance_Name.AddItem " ": ListBox_DefOfInsurance_Value.AddItem " "
      
      ListBox_DefOfInsurance_Name.AddItem "Prem paying years left": ListBox_DefOfInsurance_Value.AddItem PremiumPayingYears_To_GLPMat
    
      ListBox_DefOfInsurance_Name.AddItem "MaxAnnualLevelQualPrem": ListBox_DefOfInsurance_Value.AddItem mMaxAnnualLevelQualPrem
    
      
      
      Dim MinQualifyingGLP As Double
      If PremiumPayingYears_To_GLPMat = 0 Then
        MinQualifyingGLP = 0
      Else
        MinQualifyingGLP = -(mPolicy.AccumGLP - (mPolicy.PremiumTD - mPolicy.AccumWithdrawals)) / PremiumPayingYears_To_GLPMat
        If MinQualifyingGLP < 0 Then
          ListBox_DefOfInsurance_Name.AddItem "MinQualifyingGLP": ListBox_DefOfInsurance_Value.AddItem Format(MinQualifyingGLP, "#,##.00")
        End If
      End If
      
    End If
Else
    ListBox_DefOfInsurance_Name.AddItem "TEFRA/DEFRA":  ListBox_DefOfInsurance_Value.AddItem mPolicy.TEFRA_DEFRA
    ListBox_DefOfInsurance_Name.AddItem "Guideline/CVAT": ListBox_DefOfInsurance_Value.AddItem mPolicy.GP_CVAT
    ListBox_DefOfInsurance_Name.AddItem "Base NSP": ListBox_DefOfInsurance_Value.AddItem Format(mPolicy.NSP_Base, "#,##0.00")
    If mPolicy.NSP_Other = "Null" Then
        ListBox_DefOfInsurance_Name.AddItem "Other NSP": ListBox_DefOfInsurance_Value.AddItem Format(0, "#,##0.00")
    Else
        ListBox_DefOfInsurance_Name.AddItem "Other NSP": ListBox_DefOfInsurance_Value.AddItem Format(mPolicy.NSP_Other, "#,##0.00")
    End If
End If

ListBox_DefOfInsurance_Name.Backcolor = Me.Backcolor
ListBox_DefOfInsurance_Value.Backcolor = Me.Backcolor

Else
    Frame_DefinitionOfLifeInsurance.Visible = False
    Frame_Accumulators.left = Frame_DefinitionOfLifeInsurance.left
    Frame_Accumulators.top = Frame_DefinitionOfLifeInsurance.top
End If


End Sub


Private Sub PopulateUnappliedDivDetail()

If mPolicy.UnappliedDivCount = 0 Then Exit Sub

Dim s As cls_Storage
Set s = New cls_Storage

s.AddColumn "Type"
s.AddColumn "Date"
s.AddColumn "Cov"
s.AddColumn "FromPUA"
s.AddColumn "Cash Rt"
s.AddColumn "Cash Proj"
s.AddColumn "Cash Int"
s.AddColumn "PUA Rt"
s.AddColumn "PUA Units"
s.AddColumn "PUA Mort"
s.AddColumn "PUA Int"
s.AddColumn "PUA Mat Dur"
s.AddColumn "OYT Rt"
s.AddColumn "OYT Mort"
s.AddColumn "OYT Int"

Dim xcount As Integer
For xcount = 1 To mPolicy.UnappliedDivCount
    s.AddRow
    s("Type") = mPolicy.UnappliedDivType(xcount)
    s("Date") = Format(DateSerial(1900, mPolicy.UnappliedDivDate(xcount), Day(mPolicy.CovIssueDate(1))), "m/yyyy")
    s("Cov") = mPolicy.UnappliedDivCovPhase(xcount)
    s("FromPUA") = mPolicy.UnappliedDivFromPUA(xcount)
    s("Cash Rt") = Format(mPolicy.UnappliedDivCashRate(xcount), "#,##0.00")
    s("Cash Proj") = Format(mPolicy.UnappliedDivProjectedCashRate(xcount), "#,##0.00")
    s("Cash Int") = Format(CDbl(mPolicy.UnappliedDivOnDepositInterestRate(xcount)) / 100, "#0.00%")
    s("PUA Rt") = Format(mPolicy.UnappliedDivPUARate(xcount), "#,##0.00")
    s("PUA Units") = Format(mPolicy.UnappliedDivPUAUnits(xcount), "#,##0.000")
    s("PUA Mort") = mPolicy.UnappliedDivPUAMortality(xcount)
    s("PUA Int") = Format(CDbl(mPolicy.UnappliedDivPUAInterestRate(xcount)) / 100, "#0.00%")
    s("PUA Mat Dur") = mPolicy.UnappliedDivPUAMaturityDuration(xcount)
    s("OYT Rt") = Format(mPolicy.UnappliedDivOYTRate(xcount), "#,##0.00")
    s("OYT Mort") = Format(mPolicy.UnappliedDivOYTMortality(xcount), "#,##0.00")
    s("OYT Int") = Format(CDbl(mPolicy.UnappliedDivOYTInterestRate(xcount)) / 100, "#0.00%")
Next
  
'Load VBox with data from S
Dim VBox As clsVBox
Set VBox = New clsVBox
VBox.Initialize Frame_UnappliedDivDetail, Me.Backcolor
VBox.TableData = s.GetArrayOfValues
VBox.ColumnWidths = "30;45;30;46;39;48;50;44;50;38;45;51;44;38;44"
colVBox.Add VBox, "UnappliedDivDetail"
colStorage.Add s, "UnappliedDivDetail"
Set VBox = Nothing
Set s = Nothing
  
  


End Sub


Sub PopulateDivsOnDeposit()


If mPolicy.DivDepositCount = 0 Then Exit Sub

Dim s As cls_Storage
Set s = New cls_Storage

s.AddColumn "Last Ann"
s.AddColumn "Interest Date"
s.AddColumn "Amount"
s.AddColumn "Int Rate"
s.AddColumn "Int Withheld"
s.AddColumn "Interest On WD"

'Add records to recordset
Dim xcount As Integer
For xcount = 1 To mPolicy.DivDepositCount
    s.AddRow
    s("Last Ann") = Format(mPolicy.DivDepositLastAnniversary(xcount), "m/dd/yyyy")
    s("Interest Date") = Format(DateSerial(1900, mPolicy.DivDepositInterestDate(xcount), Day(mPolicy.CovIssueDate(1))), "m/yyyy")
    s("Amount") = Format(mPolicy.DivDepositAmount(xcount), "#,##0.00")
    s("Int Rate") = Format(CDbl(mPolicy.DivDepositInterestRate(xcount)) / 100, "#0.00%")
    s("Int Withheld") = Format(mPolicy.DivDepositAccumInterestWithheld(xcount), "#,##0.00")
    s("Interest On WD") = Format(CDbl(mPolicy.DivDepositInterestOnWDs(xcount)), "#,##0.00")
Next
  
'Load VBox with data from S
Dim VBox As clsVBox
Set VBox = New clsVBox
VBox.Initialize Frame_DivsOnDeposit, Me.Backcolor
VBox.TableData = s.GetArrayOfValues
VBox.ColumnWidths = "55;60;45;45;54;65"
colVBox.Add VBox, "DivsOnDeposit"
colStorage.Add s, "DivsOnDeposit"
Set VBox = Nothing
Set s = Nothing

End Sub


Sub PopulateDivsPUA()

If mPolicy.DivPUACount = 0 Then Exit Sub

Dim s As cls_Storage
Set s = New cls_Storage

s.AddColumn "Eff Date"
s.AddColumn "Phs"
s.AddColumn "FromPrem"
s.AddColumn "Mat Date"
s.AddColumn "Amount"
s.AddColumn "Mort Tbl"
s.AddColumn "Int Rate"

Dim xcount As Integer
For xcount = 1 To mPolicy.DivPUACount
    s.AddRow
    s("Eff Date") = Format(mPolicy.DivPUADate(xcount), "m/dd/yyyy")
    s("Phs") = mPolicy.DivPUACovPhase(xcount)
    s("FromPrem") = mPolicy.DivPUAFundingSource(xcount)
    s("Mat Date") = Format(DateSerial(1900, mPolicy.DivPUAMaturityDate(xcount), Day(mPolicy.CovIssueDate(1))), "m/yyyy")
    s("Amount") = Format(mPolicy.DivPUAAmount(xcount), "#,##0.00")
    s("Mort Tbl") = mPolicy.DivPUAMortality(xcount)
    s("Int Rate") = Format(CDbl(mPolicy.DivPUAInterestRate(xcount)) / 100, "#0.00%")
Next
  
'Load VBox with data from S
Dim VBox As clsVBox
Set VBox = New clsVBox
VBox.Initialize Frame_DivsPUA, Me.Backcolor
VBox.TableData = s.GetArrayOfValues
VBox.ColumnWidths = "54;25;45;50;60;45;45"
colVBox.Add VBox, "DivsPUA"
colStorage.Add s, "DivsPUA"
Set VBox = Nothing
Set s = Nothing

End Sub


Sub PopulateDivsOYT()

If mPolicy.DivOYTCount = 0 Then Exit Sub

Dim s As cls_Storage
Set s = New cls_Storage

s.AddColumn "Eff Date"
s.AddColumn "Mat Date"
s.AddColumn "Amount"
s.AddColumn "Mort Tbl"
s.AddColumn "Int Rate"

Dim xcount As Integer
For xcount = 1 To mPolicy.DivOYTCount
    s.AddRow
    s("Eff Date") = Format(mPolicy.DivOYTDate(xcount), "m/dd/yyyy")
    s("Mat Date") = Format(DateSerial(1900, mPolicy.DivOYTExpiryDate(xcount), Day(mPolicy.CovIssueDate(1))), "m/yyyy")
    s("Amount") = Format(mPolicy.DivOYTAmount(xcount), "#,##0.00")
    s("Mort Tbl") = mPolicy.DivOYTMortality(xcount)
    s("Int Rate") = Format(CDbl(mPolicy.DivOYTInterestRate(xcount)), "#,##0.00")
Next
  
'Load VBox with data from S
Dim VBox As clsVBox
Set VBox = New clsVBox
VBox.Initialize Frame_DivsOYT, Me.Backcolor
VBox.TableData = s.GetArrayOfValues
VBox.ColumnWidths = "58;55;59;46;46"
colVBox.Add VBox, "DivsOYT"
colStorage.Add s, "DivsOYT"
Set VBox = Nothing
Set s = Nothing


End Sub


Sub PopulateTradLoanDetail()


'04985373 is trad product but has FND_VAL table
If mPolicy.TradLoanCount = 0 Then
    Me.MultiPage1.Pages("Loans").Visible = False
    Exit Sub
Else
    Me.MultiPage1.Pages("Loans").Visible = True
End If

Dim s As cls_Storage
Set s = New cls_Storage

s.AddColumn "Eff Date"
s.AddColumn "Pref"
s.AddColumn "Principle"
s.AddColumn "Accru Int"
s.AddColumn "Chrg Rt"
s.AddColumn "Int Type"
s.AddColumn "Int Status"

Dim xcount As Integer
For xcount = 1 To mPolicy.TradLoanCount
    s.AddRow
    s("Eff Date") = Format(mPolicy.TradLoanEffectiveDate(xcount), "m/dd/yyyy")
    s("Pref") = mPolicy.TradLoanPrefIndicator(xcount)
    s("Principle") = Format(mPolicy.TradLoanLoanPrinciple(xcount), "#,##0.00")
    s("Accru Int") = Format(mPolicy.TradLoanAccuredInt(xcount), "#,##0.00")
    s("Chrg Rt") = Format(mPolicy.TradLoanChargeRate(xcount), "#0.00") & "%"
    s("Int Type") = TranslateLoanIntTypeCodeToText(mPolicy.TradLoanIntType(xcount))
    s("Int Status") = TranslateLoanIntStatusCodeToText(mPolicy.TradLoanInterestStatusCode(xcount))
Next

'Load VBox with data from S
Dim VBox As clsVBox
Set VBox = New clsVBox
VBox.Initialize Frame_LoanDetail, Me.Backcolor
VBox.TableData = s.GetArrayOfValues
colVBox.Add VBox, "LoanDetail"
colStorage.Add s, "LoanDetail"
Set VBox = Nothing
Set s = Nothing


Label_RegLoanPrinicple = Format(mPolicy.TotalRegLnPrinciple, "#,##0.00")
Label_RegLoanInt = Format(mPolicy.TotalRegLnAccrued, "#,##0.00")

Dim IsVariableInterestRate As Boolean
With mPolicy.DB2Data
    IsVariableInterestRate = (.DataItem("LH_BAS_POL", "LN_TYP_CD").value = "6" Or mPolicy.DB2Data.DataItem("LH_BAS_POL", "LN_TYP_CD").value = "7")
    'Label_LoanTypeCode = .DataItem("LH_BAS_POL", "LN_TYP_CD").Value
    Label_LoanTypeDescription = LoanInterestTypeCodeDictionary(.DataItem("LH_BAS_POL", "LN_TYP_CD").value)

    Label_RegLoanImpairedInt.Visible = False
    If IsVariableInterestRate Then
        'If loan is variable loan the loan charge rate will not be on the 01 segment so dont display it
        Label_RegLoanChargeInt.Visible = False
        Label_LoanChargeRateLabel.Visible = False
    Else
        Label_RegLoanChargeInt = Format(.DataItem("LH_BAS_POL", "LN_PLN_ITS_RT").value, "#0.00") & "%"
    End If
    Label_RegImpairedCreditingRtLable.Visible = False

End With

If mPolicy.TotalFundPrefLnPrinciple = 0 Then
    Frame_FixedLoanPreferred.Visible = False
Else
    Frame_FixedLoanPreferred.Visible = True
    Label_PrefLoanChargeInt.Visible = False
    Label_PrefImpairedCreditingRtLable.Visible = False
End If

Frame_VariableLoan.Visible = False

Label_PolicyDebt = Format(mPolicy.PolicyDebt, "#,##0.00")
End Sub

Sub PopulateLoanDetail()

Dim VBox As clsVBox
Dim s As cls_Storage

If mPolicy.LoanFundCount = 0 Then

    Me.MultiPage1.Pages("Loans").Visible = False
    Exit Sub
Else
    Me.MultiPage1.Pages("Loans").Visible = True
End If


Set s = New cls_Storage

s.AddColumn "Eff Date"
s.AddColumn "Pref"
s.AddColumn "Fund"
s.AddColumn "Phs"
s.AddColumn "Prinicple"
s.AddColumn "Accru Int"
s.AddColumn "Chrg Rt"
s.AddColumn "Credit Rt"
s.AddColumn "Int Status"

Dim xcount As Integer
For xcount = 1 To mPolicy.LoanFundCount
    s.AddRow
    s("Eff Date") = Format(mPolicy.LoanEffectiveDate(xcount), "m/dd/yyyy")
    s("Pref") = mPolicy.LoanFundPrefIndicator(xcount)
    s("Fund") = mPolicy.LoanFundID(xcount)
    s("Phs") = mPolicy.LoanFundPhase(xcount)
    s("Prinicple") = Format(mPolicy.LoanFundPrinciple(xcount), "#,##0.00")
    s("Accru Int") = Format(mPolicy.LoanFundAccuredInt(xcount), "#,##0.00")
    s("Chrg Rt") = Format(mPolicy.LoanFundChargeRate(xcount), "#0.00")
    s("Credit Rt") = TranslateLoanIntTypeCodeToText(mPolicy.LoanFundIntType(xcount))
    s("Int Status") = TranslateLoanIntStatusCodeToText(mPolicy.LoanFundInterestStatusCode(xcount))
Next

'Load VBox with data from S

Set VBox = New clsVBox
VBox.Initialize Frame_LoanDetail, Me.Backcolor
VBox.TableData = s.GetArrayOfValues
colVBox.Add VBox, "LoanDetail"
colStorage.Add s, "LoanDetail"
Set VBox = Nothing
Set s = Nothing


'----------------------------------------------
'ImpairedSummary
Set s = New cls_Storage

s.AddColumn "FundID"
s.AddColumn "Amount"

Dim dct As Dictionary
Dim tempValue
Set dct = mPolicy.LoanValuesDictionary

Dim Fund
For Each Fund In dct.Keys
    'VAriable loans do not impair the account vlaue so exclude them from this list
    If Fund <> "LZ" Then
        s.AddRow
        s("FundID") = Fund
        s("Amount") = Format(dct(Fund), "#,##.00")
    End If
Next

If s.rowCount > 0 Then
    
    Set VBox = New clsVBox
    VBox.Initialize Frame_ImpairedSummary, Me.Backcolor
    VBox.TableData = s.GetArrayOfValues
    colVBox.Add VBox, "ImpairedSummary"
    colStorage.Add s, "ImpairedSummary"
    Set VBox = Nothing
    Set s = Nothing
    
    Frame_ImpairedSummary.Visible = True
    Label_ImpairedSummaryLabel.Visible = True
Else
    Frame_ImpairedSummary.Visible = False
    Label_ImpairedSummaryLabel.Visible = False
End If




Label_RegLoanPrinicple = mPolicy.TotalRegLnPrinciple
Label_RegLoanInt = mPolicy.TotalRegLnAccrued
Label_RegLoanImpairedInt = Format(mPolicy.NonTrad_RegLoanCreditRate / 100, "#0.00%")
Label_RegLoanChargeInt = Format(mPolicy.NonTrad_RegLoanChargeRate / 100, "#0.00%")


If mPolicy.AdvancedProductIndicator = "1" Then
    
    'Preferred Loans
    If mPolicy.PreferredLoansAvailable Then
        Frame_FixedLoanPreferred.Visible = True
        Label_PrefLoanPrinicple = mPolicy.TotalPrefLnPrinciple
        Label_PrefLoanInt = mPolicy.TotalPrefLnAccrued
        Label_PrefLoanImpairedInt = Format(mPolicy.NonTrad_PrefLoanCreditRate / 100, "#0.00%")
        Label_PrefLoanChargeInt = Format(mPolicy.NonTrad_PrefLoanChargeRate / 100, "#0.00%")
    Else
        Frame_FixedLoanPreferred.Visible = False
    End If
    
    'Variable loan on IUL
    If mPolicy.ProductType = "IUL" Then
        Frame_VariableLoan.Visible = True
        Label_VariableLoanPrinciple = Format(mPolicy.TotalFundVarLnPrinciple, "#,##0.00")
        Label_VariableLoanInt = Format(mPolicy.TotalFundVarLnAccrued, "#,##0.00")
    Else
        Frame_VariableLoan.Visible = False
    End If
Else
    Frame_FixedLoanPreferred.Visible = False
End If

Label_PolicyDebt = Format(mPolicy.PolicyDebt, "#,##0.00")
End Sub

Sub PopulatePersonDetail()

If mPolicy.PersonCount = 0 Then Exit Sub
Dim s As cls_Storage
Set s = New cls_Storage


Dim xcount As Integer
For xcount = 0 To mPolicy.PersonCount
  If xcount = 0 Then
    s.AddColumn "Data Type"
  Else
    s.AddColumn "Person " & xcount
  End If
Next
Dim FirstColumnArray, tempValue As String

'An array is created that will have the data names in the first column
FirstColumnArray = Array("Effective Date", "Person Code", "Description", "Sequence", "Gender", "Class", "BirthDay", "First Name", "Last Name", "Suffix", "OwnerCode")

Dim xRow As Integer
For xRow = 0 To UBound(FirstColumnArray)
    s.AddRow
    For xcount = 0 To mPolicy.PersonCount
        If xcount = 0 Then
            s("Data Type") = FirstColumnArray(xRow)
        Else
            Select Case FirstColumnArray(xRow)
                Case "Effective Date": tempValue = Format(mPolicy.PersonEffectiveDate(xcount), "mm/dd/yyyy")
                Case "Person Code": tempValue = mPolicy.PersonCode(xcount)
                Case "Description": tempValue = TranslatePersonCodeToText(mPolicy.PersonCode(xcount))
                Case "Sequence": tempValue = mPolicy.PersonSequenceCode(xcount)
                Case "Gender": tempValue = mPolicy.PersonGender(xcount)
                Case "Class": tempValue = mPolicy.PersonClass(xcount)
                Case "BirthDay": tempValue = mPolicy.PersonBirthDay(xcount)
                Case "First Name": tempValue = WorksheetFunction.Trim(mPolicy.PersonFirstName(xcount))
                Case "Last Name": tempValue = WorksheetFunction.Trim(mPolicy.PersonLastName(xcount))
                Case "Suffix": tempValue = WorksheetFunction.Trim(mPolicy.PersonSuffix(xcount))
                Case "OwnerCode": tempValue = IIf(WorksheetFunction.Trim(mPolicy.OwnerCode(xcount)) = "A", "Owner", " ")
            End Select
            s("Person " & xcount) = tempValue
        End If
    Next
Next

'Load VBox with data from S
Dim VBox As clsVBox
Set VBox = New clsVBox
VBox.Initialize Frame_PersonDetail, Me.Backcolor
VBox.TableData = s.GetArrayOfValues
colVBox.Add VBox, "PersonDetail"
colStorage.Add s, "PersonDetail"
Set VBox = Nothing
Set s = Nothing


End Sub

Sub PopulateActivityDetail()

If mPolicy.TransactionCount = 0 Then
    Me.MultiPage1.Pages("Activity").Visible = False
    Exit Sub
Else
    Me.MultiPage1.Pages("Activity").Visible = True
End If

Dim s As cls_Storage
Set s = New cls_Storage

s.AddColumn "Eff Date"
s.AddColumn "SeqNo"
s.AddColumn "Code"
s.AddColumn "GrossAmt"
s.AddColumn "NetAmt"
s.AddColumn "Fund"
s.AddColumn "Phs"
s.AddColumn "Int Rate"
s.AddColumn "Reversal"
s.AddColumn "EntryDate"
s.AddColumn "Origin"


'If mPolicy.MVCount > 0 Then
'    S.AddColumn "Interest"
'    S.AddColumn "AccountValue"
'End If

Dim xcount As Integer, tempValue, tempInt, tempMV, LastDate
For xcount = 1 To mPolicy.TransactionCount
    s.AddRow
    s("Eff Date") = Format(mPolicy.TransactionDate(xcount), "mm/dd/yyyy")
    s("SeqNo") = mPolicy.TransactionSequence(xcount)
    s("Code") = mPolicy.TransactionType(xcount)
    'S("TypeDescription") = TransactionTypeAndSubtypeDictionary(mPolicy.TransactionType(xCount))
    s("GrossAmt") = Format(mPolicy.TransactionGrossAmount(xcount), "#,##0.00")
    s("NetAmt") = Format(mPolicy.TransactionNetAmount(xcount), "#,##0.00")
    s("Fund") = IIf(mPolicy.TransactionFundID(xcount) = "Null", " ", WorksheetFunction.Trim(mPolicy.TransactionFundID(xcount)))
    s("Phs") = WorksheetFunction.Trim(mPolicy.TransactionFundPhase(xcount))
    
    tempValue = WorksheetFunction.Trim(mPolicy.TransactionInterestRate(xcount))
    tempValue = IIf(tempValue > 0, Format(tempValue, "#0.00"), " ")
    s("Int Rate") = tempValue
    
    tempValue = " "
    If mPolicy.TransactionRevInd(xcount) = "1" Then tempValue = "Rev"
    If mPolicy.TransactionRevApplied(xcount) = "1" Then tempValue = "RV"
    If mPolicy.TransactionRevInd(xcount) = "1" And mPolicy.TransactionRevApplied(xcount) = "1" Then tempValue = "RR"
    
    s("Reversal") = tempValue
    
    s("EntryDate") = Format(WorksheetFunction.Trim(mPolicy.TransactionEntryDate(xcount)), "mm/dd/yyyy")
    s("Origin") = mPolicy.TransactionOrigin(xcount)
    
    
'    If mPolicy.MVCount > 0 Then
'        tempInt = ""
'        tempMV = ""
'            'There could be many entries for "CD" with the same date if money is coming out of mulitple funds.
'            'We want the MV values to only show up on the first occurance of "CD" for a particular date.
'            'This assumes that the transactions are ordered by date
'            If S("Eff Date") <> LastDate Then
'                Dim MV As cls_Storage
'                Set MV = colStorage("MVValues")
'                MV.MoveFirst
'                Do While Not MV.EOF
'                    If MV("Eff Date") = S("Eff Date") Then
'                        LastDate = S("Eff Date")
'                        tempMV = MV("AccountValue")
'                        tempInt = MV("Interest")
'                        Exit Do
'                    End If
'                    MV.MoveNext
'                Loop
'            End If
'
'        S("Interest") = tempInt
'        S("AccountValue") = tempMV
'        Set MV = Nothing
'    End If
     
            
Next

'Load VBox with data from S
Dim VBox As clsVBox
Set VBox = New clsVBox
VBox.Initialize Frame_ActivityDetail, Me.Backcolor
VBox.TableData = s.GetArrayOfValues
VBox.ColumnWidths = "55;30;30;60;60;30;25;45;45;55;45" ';57;60"
colVBox.Add VBox, "ActivityDetail"
colStorage.Add s, "ActivityDetail"
Set VBox = Nothing
Set s = Nothing

Dim skey
For Each skey In TransactionTypeAndSubtypeDictionary.Keys
    Me.ListBox_TransactionTypeAndSubtype.AddItem skey & " - " & TransactionTypeAndSubtypeDictionary(skey)
Next

End Sub


Sub PopulateReinsuranceDetail()
Dim LastReinsuranceValuationDate
Dim ValDate As String, TAICompanyCode As String
Dim aryRein
Dim k

'It takes time to load the TAI data so look back about 45 days
LastReinsuranceValuationDate = DateSerial(Year(Now), Month(Now()), -45)
ValDate = Year(LastReinsuranceValuationDate) & Format(Month(LastReinsuranceValuationDate), "00")

If mPolicy.CompanyCode = "26" Then
    If mPolicy.DB2Data.DataItem("TH_USER_GENERIC", "ISSUE_CMP_CODE").value = "26" Then
        If left(mPolicy.PolicyNumber, 3) <> "000" Then
            'I just want to know if any policy doesnt start with '000' but does have ISSUE_CMP_CODE = '26' which indicates they were issued in LifePro and later converted
            MsgBox "This policy has been marked as 'FFL' but policy number does not start with '000'"
        End If
        TAICompanyCode = "FFL"
    Else
        If left(mPolicy.PolicyNumber, 3) = "000" Then
            'I just want to know if any policy dont start with '000' but do have ISSUE_CMP_CODE = '26' which indicates they were issued in LifePro and later converted
            MsgBox "This policy has been marked as '130' but policy number starts with '000'"
        End If
        TAICompanyCode = "130"
    End If
Else
    TAICompanyCode = "1" & mPolicy.CompanyCode
End If



aryRein = TAI_Quick_Policy_Data(ValDate, TAICompanyCode, mPolicy.PolicyNumber)


Label_ReinsuranceStatus.caption = ""
If IsEmpty(aryRein) Then
    Label_ReinsuranceStatus.caption = "Report Month " & ValDate & ":  No reinsurance cessions found"
    ListBox_Coverages1.AddItem ""
    ListBox_Coverages2.AddItem ""
    ListBox_Coverages1.AddItem "Inuring Reinsurance"
    ListBox_Coverages2.AddItem "No"
    Exit Sub
Else
    Label_ReinsuranceStatus.caption = "Report Month " & ValDate & ":  Reinsurance cessions found"
End If

Dim s As cls_Storage
Set s = New cls_Storage

Dim X As Long
Dim ReinRecordCount As Long
Dim ReinFieldCount As Long


ReinFieldCount = UBound(aryRein, 2) - LBound(aryRein, 2)
ReinRecordCount = UBound(aryRein, 1) - LBound(aryRein, 1)

For ReinFieldCount = LBound(aryRein, 2) To UBound(aryRein, 2)
    s.AddColumn (aryRein(0, ReinFieldCount))
Next


'If ReinRecordCount > 0 Then
'    ListBox_Coverages1.AddItem ""
'    ListBox_Coverages2.AddItem ""
'    ListBox_Coverages1.AddItem "Reinsurance"
'    ListBox_Coverages2.AddItem "Loaded"
'End If


Dim xcount As Long, col As Long
Dim sField As String, sValue As String

For xcount = 1 To ReinRecordCount
    s.AddRow
    For col = 1 To ReinFieldCount - 1
        sField = aryRein(0, col)
        sValue = aryRein(xcount, col)
        s(sField) = sValue
    Next
            
Next

'Load VBox with data from S
Dim VBox As clsVBox
Set VBox = New clsVBox
VBox.Initialize Frame_ReinsuranceInfo, Me.Backcolor
VBox.TableData = s.GetArrayOfValues
VBox.ColumnWidths = "55;30;60;60;30;25;45;45;55;45" ';57;60"
colVBox.Add VBox, "ReinsuranceDetail"
colStorage.Add s, "ReinsuranceDetail"
Set VBox = Nothing
Set s = Nothing

End Sub


Private Sub PopulateMVValues()
'This procedure will create a record set of data and populate the VBox with that recordset
'The recordset is stored in a dictionary and can be called upon later for filtering, ordering etc

If mPolicy.MVCount = 0 Then
    Exit Sub
End If

Dim s As cls_Storage
Set s = New cls_Storage

Dim xcount As Integer

s.AddColumn "Eff Date"
s.AddColumn "Y"
s.AddColumn "M"
s.AddColumn "Interest"
s.AddColumn "AccountValue"
s.AddColumn "COIChrg"
s.AddColumn "OtherChrg"
s.AddColumn "Expenses"
s.AddColumn "NAR"

For xcount = 1 To mPolicy.MVCount
    s.AddRow
    s("Eff Date") = Format(mPolicy.MVDate(xcount), "mm/dd/yyyy")
    s("Y") = mPolicy.MVPolicyYear(xcount)
    s("M") = mPolicy.MVMonthOfYear(xcount)
    s("Interest") = Format(mPolicy.MVCurrentInterest(xcount), "#,##0.00")
    s("AccountValue") = Format(mPolicy.MVAV(xcount), "#,##0.00")
    s("COIChrg") = Format(mPolicy.MVCOICharge(xcount), "#,##0.00")
    s("OtherChrg") = Format(mPolicy.MVOtherChrg(xcount), "#,##0.00")
    s("Expenses") = Format(mPolicy.MVExpChrg(xcount), "#,##0.00")
    s("NAR") = Format(mPolicy.MVNAR(xcount), "#,##0.00")

Next

'Load VBox with data from S
Dim VBox As clsVBox
Set VBox = New clsVBox
VBox.Initialize Frame_U1MV, Me.Backcolor
VBox.TableData = s.GetArrayOfValues
VBox.ColumnWidths = "55;20;20;65;60;50;56;50;62"
colVBox.Add VBox, "MVValues"
colStorage.Add s, "MVValues"
Set VBox = Nothing
Set s = Nothing


Dim DB2 As cls_PolicyData
Set DB2 = mPolicy.DB2Data
Dim tempValue As Variant


ListBox_AdvProdValues_Name1.AddItem "Total AV": ListBox_AdvProdValues_Value1.AddItem Format(mPolicy.MVAV, "#,##0.00")

'Get total unimpaired value
Dim dctFunds As Dictionary
Set dctFunds = New Dictionary
Set dctFunds = mPolicy.FundValuesDictionary
Dim Fnd As Variant
For Each Fnd In dctFunds
    tempValue = tempValue + dctFunds(Fnd)
Next
ListBox_AdvProdValues_Name1.AddItem "Unimpaired AV": ListBox_AdvProdValues_Value1.AddItem Format(tempValue, "#,##0.00")

ListBox_AdvProdValues_Name1.AddItem "Impaired AV": ListBox_AdvProdValues_Value1.AddItem Format(mPolicy.TotalFundPrefLnPrinciple + mPolicy.TotalFundRegLnPrinciple, "#,##0.00")
ListBox_AdvProdValues_Name1.AddItem " ": ListBox_AdvProdValues_Value1.AddItem " "

If Not IsEmpty(mPolicy.GAV) Then
    ListBox_AdvProdValues_Name1.AddItem "GAV": ListBox_AdvProdValues_Value1.AddItem Format(mPolicy.GAV, "#,##0.00")
End If

If Not IsEmpty(mPolicy.CCV) Then
    ListBox_AdvProdValues_Name1.AddItem "CCV": ListBox_AdvProdValues_Value1.AddItem Format(mPolicy.CCV, "#,##0.00")
End If
ListBox_AdvProdValues_Name1.AddItem "Guar Int Rate": ListBox_AdvProdValues_Value1.AddItem Format(mPolicy.GuaranteedInterestRate / 100, "#0.00%")

'Load Grace Rule code and a description if one exists
Label_GraceRuleDescription.Font.Italic = False
Label_GraceRuleDescription.Font.Size = 7
Label_GraceRuleDescription.Backcolor = Me.Backcolor

tempValue = DB2.DataItem("LH_NON_TRD_POL", "GRA_THD_RLE_CD").value
If GracePeriodRuleDictionary.exists(tempValue) Then
    ListBox_AdvProdValues_Name1.AddItem "Grace Rule Code*": ListBox_AdvProdValues_Value1.AddItem DB2.DataItem("LH_NON_TRD_POL", "GRA_THD_RLE_CD").value
    Label_GraceRuleDescription.Visible = True
    Label_GraceRuleDescription = "*" & GracePeriodRuleDictionary(tempValue)
Else
  ListBox_AdvProdValues_Name1.AddItem "Grace Rule Code": ListBox_AdvProdValues_Value1.AddItem " "
  Label_GraceRuleDescription.Visible = False
  Label_GraceRuleDescription = ""
End If

tempValue = DB2.DataItem("TH_USER_GENERIC", "INITIAL_PAY_DUR").value
If tempValue > 0 Then
    If Not IsEmpty(mPolicy.ShortPayPrem) Then ListBox_AdvProdValues_Name2.AddItem "Short Pay Prem":      ListBox_AdvProdValues_Value2.AddItem mPolicy.ShortPayPrem
    ListBox_AdvProdValues_Name2.AddItem "Short Pay Dur":     ListBox_AdvProdValues_Value2.AddItem DB2.DataItem("TH_USER_GENERIC", "INITIAL_PAY_DUR").value
    ListBox_AdvProdValues_Name2.AddItem "Short Pay Mode":    ListBox_AdvProdValues_Value2.AddItem DB2.DataItem("TH_USER_GENERIC", "INITIAL_MODE").value
    ListBox_AdvProdValues_Name2.AddItem "SP Billing Cease Date":   ListBox_AdvProdValues_Value2.AddItem mPolicy.ShortPayDate
    If Not IsEmpty(mPolicy.ShortPayPrem) Then ListBox_AdvProdValues_Name2.AddItem "SP Prem Cease Age (calc)":    ListBox_AdvProdValues_Value2.AddItem CInt(tempValue) + mPolicy.CovIssueAge(1)
End If
tempValue = DB2.DataItem("TH_USER_GENERIC", "DIAL_TO_PREM_AGE").value
If tempValue > 0 Then ListBox_AdvProdValues_Name2.AddItem "DB Dial-To Age":    ListBox_AdvProdValues_Value2.AddItem tempValue


ListBox_AdvProdValues_Name2.Backcolor = Me.Backcolor
ListBox_AdvProdValues_Value2.Backcolor = Me.Backcolor
ListBox_AdvProdValues_Name1.Backcolor = Me.Backcolor
ListBox_AdvProdValues_Value1.Backcolor = Me.Backcolor
End Sub


Private Sub PopulateBucketDetailAndSummary()

If mPolicy.FundBucketCount = 0 Then
    Exit Sub
End If

'BucketDetail
Dim s As cls_Storage
Set s = New cls_Storage
s.AddColumn "FundID"
s.AddColumn "Phase"
s.AddColumn "MVDate"
s.AddColumn "StartDate"
s.AddColumn "BucketValue"

If mPolicy.FundBucketCount > 0 Then
    Dim xcount As Integer
    Dim l
    For xcount = 1 To mPolicy.FundBucketCount
        s.AddRow
        s("FundID") = mPolicy.FundBucketID(xcount)
        l = s("FundID")
        s("Phase") = mPolicy.FundBucketPhaseCode(xcount)
        s("MVDate") = Format(mPolicy.FundBucketMVDate(xcount), "mm/dd/yyyy")
        s("StartDate") = Format(mPolicy.FundBucketStartDate(xcount), "m/dd/yyyy")
        s("BucketValue") = Format(mPolicy.FundBucketValue(xcount), "#,##0.00")
    Next
    
    'Load VBox with data from S
    Dim VBox As clsVBox
    Set VBox = New clsVBox
    VBox.Initialize Frame_BucketDetail, Me.Backcolor
    VBox.TableData = s.GetArrayOfValues
    VBox.ColumnWidths = "35;35;60;60;65"
    colVBox.Add VBox, "BucketDetail"
    colStorage.Add s, "BucketDetail"
    Set VBox = Nothing
End If
Set s = Nothing

'----------------------------------------------
'FundSummary
Set s = New cls_Storage
s.AddColumn "FundID"
s.AddColumn "Amount"

Dim dctFunds As Dictionary
Set dctFunds = New Dictionary
Set dctFunds = mPolicy.FundValuesDictionary

If dctFunds.Count > 0 Then
    Dim Fnd As Variant
    For Each Fnd In dctFunds
        s.AddRow
        s("FundID") = Fnd
        s("Amount") = Format(dctFunds(Fnd), "#,##0.00")
    Next
    
    
    'Load VBox with data from S
    Set VBox = New clsVBox
    VBox.Initialize Frame_FundSummary, Me.Backcolor
    VBox.TableData = s.GetArrayOfValues
    VBox.ColumnWidths = "35;61"
    colVBox.Add VBox, "FundSummary"
    colStorage.Add s, "FundSummary"
    Set VBox = Nothing
End If

Set s = Nothing

End Sub

Private Sub PopulatePremiumAllocation()

If mPolicy.ProductType <> "IUL" Then
    Label_AllocationPercentLabel.Visible = False
    Frame_PremiumAllocation.Visible = False
Else
    Label_AllocationPercentLabel.Visible = True
    Frame_PremiumAllocation.Visible = True

    If mPolicy.PremiumAllocationPercentages.Count = 0 Then
        Exit Sub
    End If
    
    Dim s As cls_Storage
    Set s = New cls_Storage
    
    s.AddColumn "FundID"
    s.AddColumn "Percent"

    Dim dct As Dictionary, key As Variant
    Set dct = mPolicy.PremiumAllocationPercentages
    For Each key In dct
        s.AddRow
        s("FundID") = key
        s("Percent") = Format(dct(key) / 100, "#0.00%")
    Next
    
    'Load VBox with data from S
    Dim VBox As clsVBox
    Set VBox = New clsVBox
    VBox.Initialize Frame_PremiumAllocation, Me.Backcolor
    VBox.TableData = s.GetArrayOfValues
    VBox.ColumnWidths = "35;61"
    colVBox.Add VBox, "PremiumAllocation"
    colStorage.Add s, "PrmeiumAllocation"
    Set VBox = Nothing
    Set s = Nothing
    
End If
End Sub


'===================================================================================================================================
'Code below is used to implement treeview functionality
'===================================================================================================================================

Private Sub PopulateLBwithRS(lb As MSForms.Listbox, rs As ADODB.Recordset)

lb.Clear
lb.ColumnCount = rs.Fields.Count
rs.MoveFirst
Dim X As Integer, Y As Integer
Do While Not rs.EOF
    lb.AddItem
    For X = 0 To lb.ColumnCount - 1
        lb.Column(X, Y) = rs.Fields(X)
    Next
    rs.MoveNext
    Y = Y + 1
Loop

End Sub

Private Sub LoadULPolicyRatesToRecordset(Optional intScale As Integer = 1)
Dim dct As Dictionary, temparray
Set dct = New Dictionary

Dim rs As ADODB.Recordset
Set rs = New ADODB.Recordset

Dim fldname As String
Dim xmax As Integer
Dim aryRateFields, aryRateInfo
Dim intBand As Integer

fldname = "RateFields"
'Data needs to start at index = 1 so " " is added as a filler
aryRateFields = Array(" ", "Policy", "Product", "Plancode", "IssueDate", "IssueAge", "Sex", "Rateclass", "Band", "Scale")
dct.Add fldname, aryRateFields

fldname = "RateInfo"
'Data needs to start at index = 1 so "NA" is added as a filler
aryRateInfo = Array(" ", mPolicy.PolicyNumber, mPolicy.ProductType, mPolicy.CovPlancode(1), mPolicy.CovIssueDate(1), mPolicy.CovIssueAge(1), mPolicy.CovSex(1), mPolicy.CovRateclass(1), IIf(IsEmpty(mPolicy.CovBand(1)), "Not Found", mPolicy.CovBand(1)), intScale)
dct.Add fldname, aryRateInfo

fldname = "Date"
dct.Add fldname, ""

fldname = "Year"
dct.Add fldname, ""

fldname = "AttainedAge"
dct.Add fldname, ""

fldname = "TPP"
dct.Add fldname, IIf(IsEmpty(mPolicy.RATES_TPP(intScale)), Array("NA", "Not Found"), mPolicy.RATES_TPP(intScale))


fldname = "EPP"
dct.Add fldname, IIf(IsEmpty(mPolicy.RATES_EPP(intScale)), Array("NA", "Not Found"), mPolicy.RATES_EPP(intScale))
rs.Fields.Append fldname, adVarChar, 10

fldname = "MFEE"
dct.Add fldname, IIf(IsEmpty(mPolicy.RATES_MFEE(intScale)), Array("NA", "Not Found"), mPolicy.RATES_MFEE(intScale))

fldname = "CORR"
dct.Add fldname, IIf(IsEmpty(mPolicy.RATES_CORR), Array("NA", "Not Found"), mPolicy.RATES_CORR)

'Find max length of all the arrays to be displayed
xmax = CompletedDateParts("YYYY", mPolicy.CovIssueDate(1), mPolicy.CovMaturityDate(1))
xmax = fmax(xmax, aryRateFields)
Dim xcount As Integer
Dim skey
'Add records to recordset
Dim tempValue As Variant

ReDim aryMatrix(xmax, dct.Count - 1)

Dim xColumn As Integer, xRow As Integer
For xColumn = 0 To dct.Count - 1
    For xRow = 0 To xmax
        If xRow = 0 Then
            aryMatrix(xRow, xColumn) = dct.Keys(xColumn)
        Else
            
            Dim k

            Select Case dct.Keys(xColumn)
                Case "Year":  aryMatrix(xRow, xColumn) = xRow
                Case "AttainedAge": aryMatrix(xRow, xColumn) = mPolicy.CovIssueAge(1) + xRow - 1
                Case "Date": aryMatrix(xRow, xColumn) = Format(DateAdd("YYYY", xRow - 1, mPolicy.CovIssueDate(1)), "MM/DD/YYYY")
                Case Else:
                
                    If xRow > UBound(dct.items(xColumn)) Then
                        aryMatrix(xRow, xColumn) = ""
                    Else
                        aryMatrix(xRow, xColumn) = dct.items(xColumn)(xRow)
                    End If
            End Select
        End If
    Next
Next

dctRates("Policy") = aryMatrix
Set dct = Nothing

End Sub


Private Sub LoadULCoverageRatesToRecordset(CovIndex As Integer, Optional intScale As Integer = 1)
Dim dct As Dictionary, temparray
Set dct = New Dictionary

Dim aryMatrix As Variant

Dim fldname As String, tempMTP, tempCTP, tempTBL1MTP, tempTBL1CTP
Dim xmax As Integer
Dim aryRateFields, aryRateInfo
Dim intBand As Integer


fldname = "RateFields"
aryRateFields = Array(" ", "Policy", "Cov Index", "Plancode", "IssueDate", "IssueAge", "Sex", "Rateclass", "Amout", "OrigAmount", "Band", "Table", "Flat", "Flat Duration", " ", "MTP", "CTP", "TBL1MTP", "TBL1CTP", " ", "Substandard is not", "included in rates")
dct.Add fldname, aryRateFields

tempMTP = mPolicy.RATES_MTP(CovIndex)
tempCTP = mPolicy.RATES_CTP(CovIndex)
tempTBL1MTP = mPolicy.RATES_TBL1MTP(CovIndex)
tempTBL1CTP = mPolicy.RATES_TBL1CTP(CovIndex)

Dim FlatDuration
If mPolicy.CovFlat(CovIndex) = 0 Then
    FlatDuration = 0
Else
    FlatDuration = CompletedDateParts("YYYY", mPolicy.CovIssueDate(CovIndex), mPolicy.CovFlatCeaseDate(CovIndex))
End If

fldname = "RateInfo"
aryRateInfo = Array(" ", mPolicy.PolicyNumber, CovIndex, mPolicy.CovPlancode(CovIndex), mPolicy.CovIssueDate(CovIndex), mPolicy.CovIssueAge(CovIndex), mPolicy.CovSex(CovIndex), mPolicy.CovRateclass(CovIndex), mPolicy.CovAmount(CovIndex), mPolicy.CovOrigAmount(CovIndex), IIf(IsEmpty(mPolicy.CovBand(CovIndex)), "Not Found", mPolicy.CovBand(CovIndex)), mPolicy.CovTable(CovIndex), mPolicy.CovFlat(CovIndex), FlatDuration, " ", tempMTP, tempCTP, tempTBL1MTP, tempTBL1CTP, " ", " ", " ")
dct.Add fldname, aryRateInfo

fldname = "Date"
dct.Add fldname, ""

fldname = "Age"
dct.Add fldname, ""

fldname = "Year"
dct.Add fldname, ""

fldname = "COI"
dct.Add fldname, IIf(IsEmpty(mPolicy.RATES_COI(CovIndex)), Array("NA", "Not Found"), mPolicy.RATES_COI(CovIndex))

fldname = "EPU"
dct.Add fldname, IIf(IsEmpty(mPolicy.RATES_EPU(CovIndex)), Array("NA", "Not Found"), mPolicy.RATES_EPU(CovIndex))

fldname = "SCR"
dct.Add fldname, IIf(IsEmpty(mPolicy.RATES_SCR(CovIndex)), Array("NA", "Not Found"), mPolicy.RATES_SCR(CovIndex))

fldname = "GuarCOI"
dct.Add fldname, IIf(IsEmpty(mPolicy.RATES_COI(CovIndex, 0)), Array("NA", "Not Found"), mPolicy.RATES_COI(CovIndex, 0))

fldname = "GuarEPU"
dct.Add fldname, IIf(IsEmpty(mPolicy.RATES_EPU(CovIndex, 0)), Array("NA", "Not Found"), mPolicy.RATES_EPU(CovIndex, 0))



'Find max length of all the arrays to be displayed
xmax = CompletedDateParts("YYYY", mPolicy.CovIssueDate(CovIndex), mPolicy.CovMaturityDate(CovIndex))
xmax = fmax(xmax, aryRateFields)
Dim xColumn As Integer, xRow As Integer
Dim skey
'Add records to matrix


ReDim aryMatrix(xmax, dct.Count - 1)

For xColumn = 0 To dct.Count - 1
    For xRow = 0 To xmax
        If xRow = 0 Then
            aryMatrix(xRow, xColumn) = dct.Keys(xColumn)
        Else
            Select Case dct.Keys(xColumn)
                Case "Age": aryMatrix(xRow, xColumn) = xRow + mPolicy.CovIssueAge(CovIndex) - 1
                Case "Year": aryMatrix(xRow, xColumn) = xRow
                Case "Date": aryMatrix(xRow, xColumn) = Format(DateAdd("YYYY", xRow - 1, mPolicy.CovIssueDate(CovIndex)), "MM/DD/YYYY")
                Case Else:
                    If xRow > UBound(dct.items(xColumn)) Then
                        aryMatrix(xRow, xColumn) = ""
                    Else
                        aryMatrix(xRow, xColumn) = dct.items(xColumn)(xRow)
                    End If
            End Select
        End If
    Next
Next

dctRates("Cov" & CovIndex) = aryMatrix
Set dct = Nothing

End Sub

Private Sub LoadULBenefitRatesToRecordset(BenIndex As Integer, Optional intScale As Integer = 1)
Dim dct As Dictionary, temparray
Set dct = New Dictionary

Dim aryMatrix As Variant

Dim fldname As String, tempMTP, tempCTP
Dim xmax As Integer
Dim aryRateFields, aryRateInfo
Dim intBand As Integer


fldname = "RateFields"
aryRateFields = Array(" ", "Policy", "Ben Index", "Benefit Code", "Benefit", "IssueAge", "Sex", "Rateclass", "Band", "Scale", " ", "MTP", "CTP")
dct.Add fldname, aryRateFields


tempMTP = mPolicy.RATES_BENMTP(BenIndex)
tempCTP = mPolicy.RATES_BENCTP(BenIndex)


fldname = "RateInfo"
aryRateInfo = Array(" ", mPolicy.PolicyNumber, BenIndex, mPolicy.BenPlancode(BenIndex), mPolicy.BenTypeCode(BenIndex), mPolicy.BenIssueAge(BenIndex), mPolicy.CovSex(1), mPolicy.CovRateclass(1), IIf(IsEmpty(mPolicy.CovBand(1)), "Not Found", mPolicy.CovBand(1)), intScale, " ")
dct.Add fldname, aryRateInfo

fldname = "Date"
dct.Add fldname, ""

fldname = "Age"
dct.Add fldname, ""

fldname = "Year"
dct.Add fldname, ""

fldname = "COI"
dct.Add fldname, IIf(IsEmpty(mPolicy.RATES_BENCOI(BenIndex, intScale)), Array("NA", "Not Found"), mPolicy.RATES_BENCOI(BenIndex, intScale))

'Find max length of all the arrays to be displayed
xmax = CompletedDateParts("YYYY", mPolicy.CovIssueDate(1), mPolicy.CovMaturityDate(1))
xmax = fmax(xmax, aryRateFields)
Dim xColumn As Integer, xRow As Integer
Dim skey
'Add records to matrix

ReDim aryMatrix(xmax, dct.Count - 1)

For xColumn = 0 To dct.Count - 1
    For xRow = 0 To xmax
        If xRow = 0 Then
            aryMatrix(xRow, xColumn) = dct.Keys(xColumn)
        Else
            Select Case dct.Keys(xColumn)
                Case "Age": aryMatrix(xRow, xColumn) = xRow + mPolicy.BenIssueAge(BenIndex) - 1
                Case "Year": aryMatrix(xRow, xColumn) = xRow
                Case "Date": aryMatrix(xRow, xColumn) = Format(DateAdd("YYYY", xRow - 1, mPolicy.BenIssueDate(BenIndex)), "MM/DD/YYYY")
                Case Else:
                    If xRow > UBound(dct.items(xColumn)) Then
                        aryMatrix(xRow, xColumn) = ""
                    Else
                        aryMatrix(xRow, xColumn) = dct.items(xColumn)(xRow)
                    End If
            End Select
        End If
    Next
Next

dctRates("Ben" & BenIndex) = aryMatrix
Set dct = Nothing

End Sub




Private Sub PlaceMultipageOverDiplay()
  MultiPage1.height = Frame_Display.height
  MultiPage1.width = 930
  MultiPage1.top = Frame_Display.top
  MultiPage1.left = Frame_Display.left
  MultiPage1.Visible = True
  'Label_ViewDescription.Visible = False
  Label_Export.Visible = False
  TextBox_CurrentDisplay.value = mPolicy.Company & " - " & mPolicy.PolicyNumber
End Sub


Private Sub LoadRatesInTreeView()
Dim Rootnode As String, NodeKey As String, NodeName As String


RatesThatUseBand.Add "COI", ""
RatesThatUseBand.Add "EPU", ""
RatesThatUseBand.Add "MFEE", ""
RatesThatUseBand.Add "EPP", ""
RatesThatUseBand.Add "TPP", ""
RatesThatUseBand.Add "RateFields", ""
RatesThatUseBand.Add "RateInfo", ""

With mcTree

    'Add Rates rootnote
    Rootnode = "Rates"
    .AddRoot Rootnode, Rootnode
    
    'Add Coverage node and add childnode for each covergae
    NodeName = "Coverages"
    NodeKey = Rootnode & .PathSeparator & NodeName
    .NodeAdd Rootnode, tvTreeRelationship.tvChild, NodeKey, NodeName
    Dim X As Integer, strX As String
    For X = 1 To mPolicy.CovCount
        strX = Format(X, "00")
        NodeName = "Cov " & strX & " (" & mPolicy.CovPlancode(X) & ")"
        .NodeAdd NodeKey, tvTreeRelationship.tvChild, NodeKey & "\" & NodeName, NodeName
        LoadULCoverageRatesToRecordset CInt(strX)
    Next
    
    'Add Benefit node and add childnode for each Benefit
    NodeName = "Benefits"
    NodeKey = Rootnode & .PathSeparator & NodeName
    .NodeAdd Rootnode, tvTreeRelationship.tvChild, NodeKey, NodeName

    For X = 1 To mPolicy.BenCount
        strX = Format(X, "00")
        NodeName = "Ben " & strX & " (" & mPolicy.BenTypeCode(X) & ")"
        .NodeAdd NodeKey, tvTreeRelationship.tvChild, NodeKey & "\" & NodeName, NodeName
        LoadULBenefitRatesToRecordset CInt(strX)
    Next
        
    'Add policy node
    NodeName = "Policy"
    NodeKey = Rootnode & .PathSeparator & NodeName
    .NodeAdd Rootnode, tvTreeRelationship.tvChild, NodeKey, NodeName
    LoadULPolicyRatesToRecordset 1

    .Refresh
End With
End Sub


Private Sub LoadTablesInTreeView()

'Pull all the Policy Record IDs and their associated DB2 tables from the spreadsheet
'This will be an array used to determine what tables go under what policy record in the tree
'Note that the relationship is sometimes many-to-many.
Dim PRTables
Dim rng As Range
Set rng = PolicyRecordDB2Tables.Range("PolicyRecordDB2Tables")
'Array will need to be sorted by first column (Policy Record id)
rng.Sort Key1:=rng.Cells(1, 1), _
    Order1:=xlAscending, header:=xlYes, OrderCustom:=1, MatchCase:=False, _
    Orientation:=xlTopToBottom, DataOption1:=xlSortNormal
PRTables = rng.value

'Load all the DB2 Tables Names that will be checked for policy data into TblUniverse
'Check each table for policy data, if data exists, set TblUniverse to True for that table.
'This will be used later to determine if tables should be displayed in treeview
Set TblUniverse = New Dictionary
Dim X As Integer
For X = LBound(PRTables, 1) + 1 To UBound(PRTables, 1)
    TblUniverse(PRTables(X, 2)) = ""
Next
Dim skey

'Create dictionary of tables that exist for the policy.
'The dictionary will associate a default view for that table
Set dctPolicyTables = New Dictionary
For Each skey In TblUniverse
   If Not IsEmpty(mPolDB2.GetTable((skey))) Then
        If skey = "FH_FIXED" Or skey = "LH_POL_FND_VAL_TOT" Then
            dctPolicyTables.Add skey, eDisplayView.AsHeader
        Else
            dctPolicyTables.Add skey, eDisplayView.AsColumn
        End If
  End If
Next

With mcTree
    Dim ParentNode As clsTreeViewNode
    Dim RootText As String, NodeKey As String, PolRec As String, DBTbl As String
    
    'Add a "Tables" rootnode to treeview
    RootText = "Tables"
    
    .AddRoot "Tables", "Tables"
    
    'Add Policy Records as children under rootnode and add
    'Tables as children under Policy Record
    X = LBound(PRTables, 1)
    PolRec = ""
    Do
        If PolRec <> PRTables(X, 1) Then
            PolRec = PRTables(X, 1)
            NodeKey = RootText & .PathSeparator & PolRec
            .NodeAdd RootText, tvTreeRelationship.tvChild, NodeKey, PolRec
            Set ParentNode = .Nodes(NodeKey)
        End If
        DBTbl = PRTables(X, 2)
        If dctPolicyTables.exists(DBTbl) Then
            NodeKey = ParentNode.key & .PathSeparator & DBTbl
            .NodeAdd ParentNode.key, tvTreeRelationship.tvChild, NodeKey, DBTbl
        End If
        X = X + 1
    Loop Until X > UBound(PRTables, 1)
    
    Dim Node As clsTreeViewNode
    'Find all Policy Record nodes that do not have any children
    Dim dct As Dictionary
    Set dct = New Dictionary
    
    For Each Node In .Nodes
        If InStr(1, Node.caption, "Policy Record") <> 0 Then
            If Node.ChildNodes Is Nothing Then
                dct.Add Node.key, Node.caption
            End If
        End If
    Next
    
    'Remove all Policy Record items that do not have children

    For Each skey In dct.Keys
        .NodeRemove .Nodes(skey)
    Next
End With


For Each Node In mcTree.Nodes
    Node.Expanded = False
Next

mcTree.Refresh
blnTablesRetreived = True
ListBox_LoadingMessage.Visible = False

End Sub

Private Sub ListBox_Policy2Value_DblClick(ByVal Cancel As MSForms.ReturnBoolean)
    If mConvertedPolicyNumber <> "Null" And Trim(ListBox_Policy2Value.value) = mConvertedPolicyNumber Then
        CreatePolicyForm GetPolicy(mConvertedPolicyNumber)
    End If

    'This will only work if the replacement was an internal replacement
    If Trim(ListBox_Policy2Value.value) = mReplacedPolicyNumber Then
        CreatePolicyForm GetPolicy(mReplacedPolicyNumber)
    End If


End Sub

Private Sub mcTree_Click(cNode As clsTreeViewNode)
Dim aryPath As Variant, X As Integer, nodeLv As Integer
Dim Node As clsTreeViewNode
Set Node = cNode

aryPath = Split(Node.key, mcTree.PathSeparator)

nodeLv = UBound(aryPath)

If aryPath(0) = "Rates" Then

    If nodeLv = 1 And aryPath(nodeLv) = "Policy" Then
            mCurrentTable = dctRates("Policy")
            PopulateTableView mCurrentTable
            Me.MultiPage1.Visible = False
            TextBox_CurrentDisplay.value = "Policy Level Rates "
            Label_Export.Visible = True
            
    End If

    If nodeLv = 2 Then
        If aryPath(nodeLv - 1) = "Coverages" Then
            X = CInt(Mid(Node.caption, 5, 2))
            If Not dctRates.exists("Cov" & X) Then
                MsgBox "Error, rates not found"
                Exit Sub
            End If
            mCurrentTable = dctRates("Cov" & X)
            PopulateTableView mCurrentTable
            Me.MultiPage1.Visible = False
            TextBox_CurrentDisplay.value = "Rates for Coverage " & X
            Label_Export.Visible = True
        End If

        If aryPath(nodeLv - 1) = "Benefits" Then
            X = CInt(Mid(Node.caption, 5, 2))
            If Not dctRates.exists("Ben" & X) Then
                MsgBox "Error, rates not found"
                Exit Sub
            End If
            mCurrentTable = dctRates("Ben" & X)
            PopulateTableView mCurrentTable
            Me.MultiPage1.Visible = False
            TextBox_CurrentDisplay.value = "Rates for Benefit " & X
            Label_Export.Visible = True
        End If
    End If
    Label_TransposeView.Visible = False
End If

If aryPath(0) = "Tables" Then
    If nodeLv = 2 Then
        If InStr(1, Node.ParentNode.key, "Policy Record") <> 0 Then
            mCurrentTable = mPolDB2.GetTable(Node.caption)
            If IsEmpty(mCurrentTable) Then
                mcTree.Nodes.Remove (Node.Index)
            Else
                PopulateTableView mCurrentTable, Node.caption
                Me.MultiPage1.Visible = False
                TextBox_CurrentDisplay.value = Node.caption
                Label_Export.Visible = True
                
             End If
        End If
    End If
    Label_TransposeView.Visible = True
End If
End Sub
Private Sub PopulateTableView(rs As Variant, Optional strTable As String = "")
    Dim blnTranspose As Boolean
    
    'Determine if ary data needs to be transposed for display
    blnTranspose = False
    If strTable <> "" Then
        If dctPolicyTables.exists(strTable) Then
            If dctPolicyTables(strTable) = eDisplayView.AsColumn Then blnTranspose = True
        End If
    Else
        If strTable = "FH_FIXED" Then blnTranspose = False
    End If
    
    'Trasnspose array data if needed
    If blnTranspose Then
        'Transpose array
         Dim aryData As Variant
         aryData = Transpose2DArray_to_2DArray(rs)
            
        'Create array with column headers in add to data arary for display
        Dim aryHeaders As Variant
        ReDim ary(LBound(rs, 2) To UBound(rs, 2))
        Dim X As Integer
        For X = LBound(rs, 2) To UBound(rs, 2)
            ary(X) = "Col" & X
        Next
        InsertRowIntoArray aryData, LBound(aryData, 2), aryHeaders
     Else
         aryData = rs
     End If
    
    'Display array data
    VBoxDisplay.TableData = aryData
End Sub

Private Sub Label_TransposeView_Click()
    Dim strTable As String
    
    'If current display is not a table, exit procedure
    strTable = TextBox_CurrentDisplay.value
    If Not dctPolicyTables.exists(strTable) Then Exit Sub
    
    'Flip the current view for this table in the view dictionary
    If dctPolicyTables(strTable) = eDisplayView.AsColumn Then
        dctPolicyTables(strTable) = eDisplayView.AsHeader
    Else
        dctPolicyTables(strTable) = eDisplayView.AsColumn
    End If
    
    'Display table with the new view
    PopulateTableView mPolDB2.GetTable(strTable), strTable

End Sub
Private Function DefaultView(strTableName As String) As eDisplayView
If strTableName = "FH_FIXED" Then
    DefaultView = eDisplayView.AsHeader
Else
    DefaultView = eDisplayView.AsColumn
End If
End Function





Private Sub UserForm_QueryClose(Cancel As Integer, CloseMode As Integer)
    'Disconnect event handlers
    Set mcTree = Nothing
    
    'Clean up any remaining object references
    Dim ctrl As Control
    For Each ctrl In Me.Controls
        Set ctrl = Nothing
    Next ctrl
End Sub
Private Sub UserForm_Terminate()
    'Clean up collections and dictionaries
    Set dctNavigator = Nothing
    Set dctRS = Nothing
    Set mPolDB2 = Nothing
    Set mPolicy = Nothing
    Set dctRates = Nothing
    Set dctControlsHideWithTree = Nothing
    Set dctControlsMoveForTree = Nothing
    Set VBoxDisplay = Nothing
    Set mcTree = Nothing
    Set RatesThatUseBand = Nothing
    
    'Clean up collections
    Set colVBox = Nothing
    Set colStorage = Nothing
    
    'Clean up other objects
    Set TblUniverse = Nothing
    Set dctPolicyTables = Nothing
End Sub
