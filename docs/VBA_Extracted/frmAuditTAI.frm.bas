' Module: frmAuditTAI.frm
' Type: Standard Module
' Stream Path: VBA/frmAuditTAI
' =========================================================

Attribute VB_Name = "frmAuditTAI"
Attribute VB_Base = "0{D570EA39-2D7F-494F-83D9-442F1DAD1F40}{1627712B-BC47-42C3-8DA6-ADF90F367E96}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False




Private mPreMaxCount As Variant
Private blnIsPopulated As Boolean
Private WithEvents VDisplay As clsVBox
Attribute VDisplay.VB_VarHelpID = -1
Private SelectedTable As String



Public Sub PopulateForm()

    ComboBox_TableSelect.List = Array("TAICyberTAIFd", "TAICession", "TAICESS_Test")
    ComboBox_TableSelect.value = "TAICESS_Test"
    SelectedTable = ComboBox_TableSelect.value

    With Me.ComboBox_PolicynumberCriteria
        .AddItem "0 - Match"
        .AddItem "1 - starts with"
        .AddItem "2 - Ends with"
        .AddItem "3 - Contains"
        .value = "0 - Match"
    End With
    
    With ComboBox_PlanCriteria
        .AddItem "0 - Match"
        .AddItem "1 - starts with"
        .AddItem "2 - Ends with"
        .AddItem "3 - Contains"
        .value = "0 - Match"
    End With
    
    mPreMaxCount = 25
    TextBox_MaxCount = 25
    
    
    Me.ListBox_StatusCode.List = Array("CNT - Converted", "DTH - Death", "ETI - Extended Term", "EXP - Expired", "LAP - Lapsed", "NTO - Not Taken Out", "PDT - Pending Death", "PDU - Paid Up", "PMP - Prem Paying", "RPU - Reduced Paid Up", "SUR - Surrendered", "TRM", "WOP - Waiver of Prem ")
    DisableControl ListBox_StatusCode
 
    Me.ListBox_ReinsCo.List = Array("RGAO", "GB", "AC", "AL", "AN", "AU", "CG", "CL", "CN", "ER", "FF", "GC", "GG", "GL", "GN", "HA", "IN", "LN", "LR", "MG", "MU", "NA", "OP", "RG", "SW", "TR", "TT", "WI")
    DisableControl ListBox_ReinsCo
    ListBox_ReinsCo.height = 300
    
    Me.ListBox_RepCo.List = Array("RGAO", "GB", "RG", "AC", "AN", "AU", "SW", "CL", "MU", "ER", "FF", "GC", "GG", "GL", "GN", "HA", "IN", "LN", "OP", "TR", "TT", "WI")
    DisableControl ListBox_RepCo
    ListBox_RepCo.height = 300
    
    ListBox_ReinsType.List = Array("Y", "C")
    DisableControl ListBox_ReinsType
    
    ListBox_Mode.List = Array("AN", "MN", "MF")
    DisableControl ListBox_Mode
    
    ListBox_ProdCD.List = Array("T", "U", "V", "W")
    DisableControl ListBox_ProdCD
    ListBox_ProdCD.height = 80
        
    ListBox_Company.List = Array("101", "104", "106", "108", "130", "FFL")
    DisableControl ListBox_Company
    ListBox_Company.height = 80
    
    Dim monthoffset As Integer
    If Day(Now()) > 5 Then
        monthoffset = 1
    Else
        monthoffset = 2
    End If
    
    TextBox_LowDate.value = Format(DateSerial(Year(Now()), Month(Now()) - monthoffset, 1), "YYYYMM")
    TextBox_HighDate.value = TextBox_LowDate.value
    
    
     MultiPage1.value = MultiPage1.Pages("Page_Criteria1").Index
End Sub

Private Sub CheckBox_SpecifyCompany_Click()
    If CheckBox_SpecifyCompany Then
      EnableControl ListBox_Company
    Else
      DisableControl ListBox_Company
    End If
    ListBox_Company.height = 80
End Sub

Private Sub CheckBox_SpecifyMode_Click()
    If CheckBox_SpecifyMode Then
      EnableControl ListBox_Mode
    Else
      DisableControl ListBox_Mode
    End If
End Sub

Private Sub CheckBox_SpecifyProdCD_Click()
    If CheckBox_SpecifyProdCD Then
      EnableControl ListBox_ProdCD
    Else
      DisableControl ListBox_ProdCD
    End If
End Sub

Private Sub CheckBox_SpecifyReinsCo_Click()
    If CheckBox_SpecifyReinsCo Then
      EnableControl ListBox_ReinsCo
    Else
      DisableControl ListBox_ReinsCo
    End If
End Sub

Private Sub CheckBox_SpecifyReinsType_Click()
    If CheckBox_SpecifyReinsType Then
      EnableControl ListBox_ReinsType
    Else
      DisableControl ListBox_ReinsType
    End If
End Sub

Private Sub CheckBox_SpecifyRepCo_Click()
    If CheckBox_SpecifyRepCo Then
      EnableControl ListBox_RepCo
    Else
      DisableControl ListBox_RepCo
    End If
End Sub

Private Sub ComboBox_TableSelect_Change()

    Select Case ComboBox_TableSelect.value
        Case "TAICyberTAIFd": Label_DateListDescription.caption = "LastUpdate"
        Case "TAICession": Label_DateListDescription.caption = "Month End"
        Case "TAICESS_Test": Label_DateListDescription.caption = "Month End"
        Case Else:
    End Select

    ListBox_AvailableDates.Clear
    SelectedTable = ComboBox_TableSelect.value
End Sub



Private Sub CommandButton_RunAudit_Click()
    LoadAuditResults
End Sub

Private Sub Label_ExportToExcel_Click()
  If VDisplay.ListCount = 0 Then Exit Sub
  DumpArrayValuesIntoExcel VDisplay.TableData, , , True
End Sub

Private Sub Label212_Click()
    ActiveWorkbook.FollowHyperlink Address:="https://www.freeformatter.com/sql-formatter.html", NewWindow:=True
End Sub

Private Sub ListBox_AvailableDates_DblClick(ByVal Cancel As MSForms.ReturnBoolean)
    Dim DateSelected
    DateSelected = ListBox_AvailableDates.Column(0, ListBox_AvailableDates.ListIndex)
    TextBox_LowDate.value = DateSelected
    TextBox_HighDate.value = DateSelected
End Sub


Private Sub ToggleButton_GetAll_Click()
If ToggleButton_GetAll Then
  TextBox_MaxCount.Enabled = False
  mPreMaxCount = TextBox_MaxCount.value
  TextBox_MaxCount.value = "All"

Else
  TextBox_MaxCount.Enabled = True
  TextBox_MaxCount.value = mPreMaxCount
End If
End Sub

Private Sub UserForm_Activate()
    Set VDisplay = New clsVBox
    VDisplay.Initialize Me.Frame_Results, Me.Backcolor
   
   Me.height = 500
   Me.width = 920
   
End Sub


Property Get IsPopulated()
 'This property allows a test to see if PopulateForm has already been executed.  PopulateForm will clear all current settings and should not occur after the form is initially openned
 IsPopulated = blnIsPopulated
End Property

Private Sub CommandButton_GetDates_Click()
Dim sqlstring As String
Select Case SelectedTable
    Case "TAICyberTAIFd": sqlstring = "SELECT [_LastUpdate] FROM [TAICyberTAIFd] WHERE [_LastUpdate] > '" & DateSerial(Year(Now()), Month(Now()) - 1, Day(Now())) & "' GROUP BY [_LastUpdate]"
    Case "TAICession": sqlstring = "SELECT [_MonthEnd] FROM [TAICession] GROUP BY [_MonthEnd]"
    Case "TAICESS_Test": sqlstring = "SELECT [_MonthEnd] FROM [TAICESS_Test] GROUP BY [_MonthEnd]"
End Select

Dim dataArray As Variant
dataArray = FetchTable(sqlstring, "UL_Rates", False)

If IsEmpty(dataArray) Then
    ListBox_AvailableDates.List = Array("none found")
Else
    Dim X
    If SelectedTable = "TAICyberTAIFd" Then
        For X = LBound(dataArray, 1) To UBound(dataArray, 1)
            dataArray(X, 0) = Format(DateValue(dataArray(X, 0)), "mm/dd/yyyy")
        Next
    End If
    ListBox_AvailableDates.List = dataArray
End If

End Sub
Private Sub CheckBox_SpecifyStatusCodes_Click()
If CheckBox_SpecifyStatusCodes Then
  EnableControl ListBox_StatusCode
Else
  DisableControl ListBox_StatusCode
End If
End Sub
Private Sub DisableControl(ctl As Object)
With ctl
  .Enabled = False
  .Backcolor = &H8000000F
  .ForeColor = &H80000010
End With
End Sub
Private Sub EnableControl(ctl As Object)
With ctl
  .Enabled = True
  .Backcolor = -2147483643
  .ForeColor = -2147483630
  '.SetFocus = True
End With
End Sub
Private Sub AddListBoxEntriesToSQL(ByRef strSQL As String, lb As MSForms.Listbox, strTableAndFieldName, intLeftLength)
'This procedure reads the selected entries in a List box and assignes the values to the given field name.
'This can only be used if the listbox entry begins with the code to be assinged.  inLeftLength determines how many
'characters to pull from the listbox entry text
Dim dct As Dictionary
Set dct = New Dictionary
    Dim i As Integer
    For i = 0 To lb.ListCount - 1
        If lb.Selected(i) = True Then
            If UCase(lb.List(i)) = "NULL" Then
                dct.Add strTableAndFieldName & " IS NULL ", ""
            Else
                dct.Add strTableAndFieldName & " ='" & left(lb.List(i), intLeftLength) & "'", ""
            End If
        End If
    Next i
     If dct.Count > 0 Then strSQL = strSQL & "AND (" & Join(dct.Keys, " OR ") & ") "
   
Set dct = Nothing

End Sub


Private Function BuildSQLString()
Dim sqlstring  As String
    sqlstring = sqlstring & "SELECT " & IIf(Not (ToggleButton_GetAll), "  TOP " & TextBox_MaxCount & " ", "")
        If CheckBox_PullAllFields Then
            sqlstring = sqlstring & " * "
        Else
            sqlstring = sqlstring & " [_MonthEnd] "
            sqlstring = sqlstring & ",[_Co] "
            sqlstring = sqlstring & ",[_pol] "
            sqlstring = sqlstring & ",[_Cov] "
            sqlstring = sqlstring & ",[_CessSeq] "
            sqlstring = sqlstring & ",[_TransSeq] "
            sqlstring = sqlstring & ",[_ReinsCo] "
            sqlstring = sqlstring & ",[_RepCo] "
            sqlstring = sqlstring & ",[_TranTyp] "
            sqlstring = sqlstring & ",[_TranCnt] "
            sqlstring = sqlstring & ",[_FromDt] "
            sqlstring = sqlstring & ",[_ToDt] "
            sqlstring = sqlstring & ",[_RepDt] "
            sqlstring = sqlstring & ",[_Mode] "
            sqlstring = sqlstring & ",[_PolStatus] "
            sqlstring = sqlstring & ",[_Treaty] "
            sqlstring = sqlstring & ",[_TreatyRef] "
            sqlstring = sqlstring & ",[_ReinsTyp] "
            sqlstring = sqlstring & ",[_Plan] "
            sqlstring = sqlstring & ",[_SrchPlan] "
            sqlstring = sqlstring & ",[_ProdCD] "
            sqlstring = sqlstring & ",[_Face] "
            sqlstring = sqlstring & ",[_Retn] "
            sqlstring = sqlstring & ",[_Ceded] "
            sqlstring = sqlstring & ",[_NAR] "
            sqlstring = sqlstring & ",[_PMPrem] "
            sqlstring = sqlstring & ",[_WaivPrem] "
            sqlstring = sqlstring & ",[_Ben] "
            sqlstring = sqlstring & ",[_CV] "
            sqlstring = sqlstring & ",[_PMexCV] "
            sqlstring = sqlstring & ",[_PMNexCV] "
            sqlstring = sqlstring & ",[_PMBenefit] "
            sqlstring = sqlstring & ",[_UltFac] "
            sqlstring = sqlstring & ",[_UltCed] "
            sqlstring = sqlstring & ",[_CstCntr] "
            sqlstring = sqlstring & ",[_LOB] "
            sqlstring = sqlstring & ",[_Filler6] AS RGA_Ind "
        End If
    sqlstring = sqlstring & "FROM [" & SelectedTable & "] "
    sqlstring = sqlstring & "WHERE "
    sqlstring = sqlstring & "1 = 1 "
    If TextBox_PolicyNumberContains.value <> "" Then
        Select Case left(ComboBox_PolicynumberCriteria.value, 1)
            '1 = Starts with, 2 = Ends with, 3 = Contains
            Case 0: sqlstring = sqlstring & "AND ([_pol] =  '" & TextBox_PolicyNumberContains.value & "') "
            Case 1: sqlstring = sqlstring & "AND ([_pol] Like  '" & TextBox_PolicyNumberContains.value & "%') "
            Case 2: sqlstring = sqlstring & "AND ([_pol] Like  '%" & TextBox_PolicyNumberContains.value & "') "
            Case 3: sqlstring = sqlstring & "AND ([_pol] Like  '%" & TextBox_PolicyNumberContains.value & "%') "
            Case Else
        End Select
    End If
    
    If TextBox_PlanContains.value <> "" Then
        Select Case left(ComboBox_PlanCriteria.value, 1)
            '1 = Starts with, 2 = Ends with, 3 = Contains
            Case 0: sqlstring = sqlstring & "AND ([_Plan] =  '" & TextBox_PlanContains.value & "') "
            Case 1: sqlstring = sqlstring & "AND ([_Plan] Like  '" & TextBox_PlanContains.value & "%') "
            Case 2: sqlstring = sqlstring & "AND ([_Plan] Like  '%" & TextBox_PlanContains.value & "') "
            Case 3: sqlstring = sqlstring & "AND ([_Plan] Like  '%" & TextBox_PlanContains.value & "%') "
            Case Else
        End Select
    End If
    
    
    
    If Me.CheckBox_SpecifyStatusCodes Then AddListBoxEntriesToSQL sqlstring, ListBox_StatusCode, "[_PolStatus]", 3
    If CheckBox_SpecifyReinsCo Then AddListBoxEntriesToSQL sqlstring, ListBox_ReinsCo, "[_ReinsCo]", 4
    If CheckBox_SpecifyRepCo Then AddListBoxEntriesToSQL sqlstring, ListBox_RepCo, "[_RepCo]", 4
    If CheckBox_SpecifyReinsType Then AddListBoxEntriesToSQL sqlstring, ListBox_ReinsType, "[_ReinsType]", 1
    If CheckBox_SpecifyMode Then AddListBoxEntriesToSQL sqlstring, ListBox_Mode, "[_Mode]", 2
    If CheckBox_SpecifyProdCD Then AddListBoxEntriesToSQL sqlstring, ListBox_ProdCD, "[_ProdCD]", 1
    If CheckBox_SpecifyCompany Then AddListBoxEntriesToSQL sqlstring, ListBox_Company, "[_Co]", 3
    
    If CheckBox_IsRGA Then sqlstring = sqlstring & "AND [_Filler6] = 'R' "
    If TextBox_LowDate.value <> "" Then sqlstring = sqlstring & "AND [_MonthEnd] >= " & TextBox_LowDate & " "
    If TextBox_HighDate.value <> "" Then sqlstring = sqlstring & "AND [_MonthEnd] <= " & TextBox_LowDate & " "
    
    sqlstring = sqlstring & "ORDER BY [_MonthEnd], [_Cov], [_CessSeq] "
    
    
    Debug.Print sqlstring

BuildSQLString = sqlstring

End Function
Private Function BuildSQLString_TAICyberTAIFd()

Dim sqlstring  As String
    sqlstring = sqlstring & "SELECT " & IIf(Not (ToggleButton_GetAll), "  TOP " & TextBox_MaxCount & " ", "")
        If CheckBox_PullAllFields Then
            sqlstring = sqlstring & " * "
        Else
            sqlstring = sqlstring & " [_Co] "
            sqlstring = sqlstring & ",[_Pol] "
            sqlstring = sqlstring & ",[_Cov] "
            sqlstring = sqlstring & ",[_Status] "
            sqlstring = sqlstring & ",[_IssueDate] "
            sqlstring = sqlstring & ",[_PaidtoDate] "
            sqlstring = sqlstring & ",[_LastTransDate] "
            sqlstring = sqlstring & ",[_IssueType] "
            sqlstring = sqlstring & ",[_Plan] "
            sqlstring = sqlstring & ",[_ProdCode] "
            sqlstring = sqlstring & ",[_ProdCode01] "
            sqlstring = sqlstring & ",[_ProdCode02] "
            sqlstring = sqlstring & ",[_ReinsSw] "
            sqlstring = sqlstring & ",[_Par] "
            sqlstring = sqlstring & ",[_DBOption] "
            sqlstring = sqlstring & ",[_Face] "
            sqlstring = sqlstring & ",[_SpecPrem] "
            sqlstring = sqlstring & ",[_SpecPremType] "
            sqlstring = sqlstring & ",[_PolFee] "
            sqlstring = sqlstring & ",[_Skip1] "
            sqlstring = sqlstring & ",[_ValuesDate] "
            sqlstring = sqlstring & ",[_Benefit] "
            sqlstring = sqlstring & ",[_CashValue] "
            sqlstring = sqlstring & ",[_NextCashValue] "
            sqlstring = sqlstring & ",[_Skip2ClientID] "
            sqlstring = sqlstring & ",[_Sex] "
            sqlstring = sqlstring & ",[_DoB] "
            sqlstring = sqlstring & ",[_InsStatus] "
            sqlstring = sqlstring & ",[_Age] "
            sqlstring = sqlstring & ",[_Class] "
            sqlstring = sqlstring & ",[_Mort] "
            sqlstring = sqlstring & ",[_MortDur] "
            sqlstring = sqlstring & ",[_Skip3] "
            sqlstring = sqlstring & ",[_PermFlx] "
            sqlstring = sqlstring & ",[_PermDur] "
            sqlstring = sqlstring & ",[_TempFlx] "
            sqlstring = sqlstring & ",[_TempDur] "
            sqlstring = sqlstring & ",[_Skip03] "
            sqlstring = sqlstring & ",[_LastUpdate] "
    End If
    
    sqlstring = sqlstring & "FROM [" & SelectedTable & "] "
    sqlstring = sqlstring & "WHERE "
    sqlstring = sqlstring & "1 = 1 "
        
    If Me.CheckBox_SpecifyCompany Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_Company, "TAICyberTAIFd.[_Co]", 3
    
    If TextBox_PolicyNumberContains.value <> "" Then
        Select Case left(ComboBox_PolicynumberCriteria.value, 1)
            '1 = Starts with, 2 = Ends with, 3 = Contains
            Case 0: sqlstring = sqlstring & "AND ([_pol] =  '" & TextBox_PolicyNumberContains.value & "') "
            Case 1: sqlstring = sqlstring & "AND ([_pol] Like  '" & TextBox_PolicyNumberContains.value & "%') "
            Case 2: sqlstring = sqlstring & "AND ([_pol] Like  '%" & TextBox_PolicyNumberContains.value & "') "
            Case 3: sqlstring = sqlstring & "AND ([_pol] Like  '%" & TextBox_PolicyNumberContains.value & "%') "
            Case Else
        End Select
    End If
    
    
    If TextBox_PlanContains.value <> "" Then
        Select Case left(ComboBox_PlanCriteria.value, 1)
            '1 = Starts with, 2 = Ends with, 3 = Contains
            Case 0: sqlstring = sqlstring & "AND ([_Plan] =  '" & TextBox_PlanContains.value & "') "
            Case 1: sqlstring = sqlstring & "AND ([_Plan] Like  '" & TextBox_PlanContains.value & "%') "
            Case 2: sqlstring = sqlstring & "AND ([_Plan] Like  '%" & TextBox_PlanContains.value & "') "
            Case 3: sqlstring = sqlstring & "AND ([_Plan] Like  '%" & TextBox_PlanContains.value & "%') "
            Case Else
        End Select
    End If

    
    'If CheckBox_IsRGA Then sqlstring = sqlstring & "AND [_Filler6] = 'R' "
    If TextBox_LowDate.value <> "" Then sqlstring = sqlstring & "AND [_LastUpdate] >= '" & Format(CDate(TextBox_LowDate), "yyyy-mm-dd") & "' "
    If TextBox_HighDate.value <> "" Then sqlstring = sqlstring & "AND [_LastUpdate] <= '" & Format(CDate(TextBox_LowDate) + 1, "yyyy-mm-dd") & "' "
    
    
    sqlstring = sqlstring & "ORDER BY [_Co], [_Pol], [_Cov] "
    
    
    Debug.Print sqlstring

BuildSQLString_TAICyberTAIFd = sqlstring
    
End Function


Private Sub LoadAuditResults()
Dim dataArray
Dim temparray()
Dim ColumnIndex As Integer
Dim StartTime As Date
Dim StartTime2 As Date
Dim ElapsedTime As Date


'Clear out all the controls
Label_QueryTimeAmount = ""
Label_PrintTimeAmount = ""
Label_TotalTimeAmount = ""
Label_ResultCountAmount = ""


'Build main sql string
Dim str As String
If Me.ComboBox_TableSelect.value = "TAICyberTAIFd" Then
    str = BuildSQLString_TAICyberTAIFd
Else
    str = BuildSQLString
End If
TextBox_SQL.value = str


'Run query and display the amount of time it takes to run
StartTime = Now()
dataArray = FetchTable(str, "UL_Rates", True)
ElapsedTime = Now() - StartTime
Label_QueryTimeAmount = Format(ElapsedTime, "HH:MM:SS")


'Print query results and display the amount of time it takes to print
StartTime2 = Now()
If IsEmpty(dataArray) Then
    Dim ary(1, 0)
    ary(0, 0) = ""
    ary(1, 0) = "No Records"
    VDisplay.TableData = ary
    Exit Sub
End If

If CheckBox_NotifyBeforePrint And UBound(dataArray, 1) > 50000 Then
    ShouldPrint = MsgBox("The query returned " & UBound(dataArray, 1) & " rows of data.  Do you wish to display these results?", vbYesNo)
    If ShouldPrint = vbNo Then Exit Sub
End If


Dim DataCount As Long
DataCount = UBound(dataArray, 1) * UBound(dataArray, 2)
If DataCount <= 1000000 Then
    VDisplay.FilterOn = True
Else
    VDisplay.FilterOn = False
End If
    
VDisplay.TableData = dataArray
ElapsedTime = Now() - StartTime2
Label_PrintTimeAmount = Format(ElapsedTime, "HH:MM:SS")


'Print total time
ElapsedTime = Now() - StartTime
Label_TotalTimeAmount = Format(ElapsedTime, "HH:MM:SS")


'Display result count
Label_ResultCountAmount = VDisplay.ListCount - 1


'switch to Results tab
MultiPage1.value = MultiPage1.Pages("Page_Results").Index

End Sub

