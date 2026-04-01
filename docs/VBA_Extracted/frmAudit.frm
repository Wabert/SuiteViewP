VERSION 5.00
Begin {C62A69F0-16DC-11CE-9E98-00AA00574A4F} frmAudit 
   Caption         =   "Transactions"
   ClientHeight    =   8940.001
   ClientLeft      =   -15
   ClientTop       =   90
   ClientWidth     =   19155
   OleObjectBlob   =   "frmAudit.frx":0000
   StartUpPosition =   1  'CenterOwner
End
Attribute VB_Name = "frmAudit"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False

'11/14/2023 RJH:  Make updates to anyting that was for Show or Display to use LEFT OUTER JOIN instead of INNER JOIN
'09/06/2018 RJH:  Added SuspenseCode logic

Option Explicit
Private mfrmPlans As frmPlancodeSelection

Private blnIsPopulated As Boolean

Private mMaxCount As Long
Private blnQueryBenefit As Boolean

Private blnIssuedBefore As Boolean
Private blnIssuedAfter As Boolean

Private blnRiderPersonCode1 As Boolean
Private blnRiderPersonCode2 As Boolean
Private blnRiderPersonCode3 As Boolean
Private blnQueryRider1 As Boolean
Private blnQueryRider2 As Boolean
Private blnQueryRider3 As Boolean
Private blnQueryBenefit1 As Boolean
Private blnQueryBenefit2 As Boolean
Private blnQueryBenefit3 As Boolean

Private blnTransaction1 As Boolean
Private blnTransaction2 As Boolean
Private blnTransaction3 As Boolean

Private blnHas77Segment As Boolean

Private blnMaxIsForPolicies As Boolean
Private mPreMaxCount As Variant
Private Const ANY_SELECTION = ""

Private mMainTbl As String

Private WithEvents VDisplay As clsVBox
Attribute VDisplay.VB_VarHelpID = -1

Private Sub Label_PasteFromClipboard_Click()
    PasteFromClipboard Me.ListBox_MultiplePlancodes
End Sub

Private Sub UserForm_Initialize()
    Set VDisplay = New clsVBox
    VDisplay.Initialize Frame_Display, Me.Backcolor
End Sub

Private Sub CheckBox_ShowTerminationDate_from_69_Click()
    If CheckBox_ShowTerminationDate_from_69 Then
        MsgBox "Viewing termination dates requires querying the FH_FIXED table (69 segment).  This may take a few mins depending on other query criteria", vbOKOnly
    End If
    
    
End Sub

' Requires reference to "Microsoft Forms 2.0 Object Library" for DataObject
' (Go to Tools > References in VBA editor)

Public Sub PasteFromClipboard(ByVal targetListBox As MSForms.Listbox)
    Dim clipboardText As String
    Dim dataObj As New MSForms.DataObject
    Dim arrCodes() As String
    Dim i As Long
    Dim code As String
    Dim exists As Boolean
    
    On Error GoTo ErrHandler
    
    ' Get clipboard content
    dataObj.GetFromClipboard
    clipboardText = Trim(dataObj.GetText)
    
    ' Validate clipboard content
    If Len(clipboardText) = 0 Then
        MsgBox "Clipboard is empty or does not contain text.", vbExclamation
        Exit Sub
    End If
    
    ' Split by common delimiters: newline, tab, comma, space
    arrCodes = Split(Replace(Replace(Replace(clipboardText, vbTab, vbCrLf), ",", vbCrLf), " ", vbCrLf), vbCrLf)
    
    ' Loop through codes and add to listbox if not empty and not duplicate
    For i = LBound(arrCodes) To UBound(arrCodes)
        code = Trim(arrCodes(i))
        If Len(code) > 0 Then
            exists = False
            Dim j As Long
            For j = 0 To targetListBox.ListCount - 1
                If StrComp(targetListBox.List(j), code, vbTextCompare) = 0 Then
                    exists = True
                    Exit For
                End If
            Next j
            
            If Not exists Then
                targetListBox.AddItem code
            End If
        End If
    Next i
    
    Exit Sub
    
ErrHandler:
    MsgBox "Error accessing clipboard. Please ensure you copied text.", vbCritical
End Sub



Private Sub ComboBox_SystemCode_Change()

    If ComboBox_SystemCode.value = "I" Then
        MultiPage1.Pages("Page_NewBusiness").Visible = False
    Else
        MultiPage1.Pages("Page_NewBusiness").Visible = True
    End If
End Sub

Private Sub CommandButton_SelectInforce_Click()
    EnableControl ListBox_StatusCode
    CheckBox_SpecifyStatusCodes = True
    
    Dim i As Integer
    Dim StatusCode As Integer
    With Me.ListBox_StatusCode
        For i = 0 To .ListCount - 1
            StatusCode = CInt(left(.List(i), 2))
            If StatusCode < 97 Then
                .Selected(i) = True
            Else
                .Selected(i) = False
            End If
        Next i
    End With
    
End Sub




Private Sub Label212_Click()
    ActiveWorkbook.FollowHyperlink Address:="https://www.freeformatter.com/sql-formatter.html", NewWindow:=True
End Sub

Private Sub UserForm_Activate()

   
   Me.height = 470
   Me.width = 920
   
End Sub

Public Sub PopulateForm()
Dim temparray()
Dim skey
Dim tempstr As String
Dim blnUsePolicyData As Boolean


  Set mfrmPlans = New frmPlancodeSelection
  mfrmPlans.classInitialize Me
  Me.caption = "Audit"




  Me.TextBox_PlancodeAllCovs = ""
  Me.ComboBox_Region.List = Array("CKPR", "CKMO", "CKAS", "CKSR")   ', "CKCS")
  Me.ComboBox_Region = "CKPR"
  
  Me.TextBox_MaxCount = 25
  
  temparray = CompanyDictionary.Keys
  InsertElementIntoArray temparray, 0, ANY_SELECTION
  Me.ComboBox_Company.List = temparray
  Me.ComboBox_Company.value = ANY_SELECTION
        
  temparray = Array(ANY_SELECTION, "MLM", "CSSD", "IMG", "DIRECT")
  ComboBox_MarketOrg.List = temparray
  ComboBox_MarketOrg.value = ANY_SELECTION
        
  Me.ComboBox_Rider1ProductLineCode.AddItem ANY_SELECTION
  Me.ComboBox_Rider2ProductLineCode.AddItem ANY_SELECTION
  Me.ComboBox_Rider3ProductLineCode.AddItem ANY_SELECTION
  For Each skey In ProductLineCodeDictionary.Keys
    tempstr = skey & " - " & ProductLineCodeDictionary(skey)
    Me.ListBox_ProductLineCodeAllCovs.AddItem tempstr
    Me.ComboBox_Rider1ProductLineCode.AddItem tempstr
    Me.ComboBox_Rider2ProductLineCode.AddItem tempstr
    Me.ComboBox_Rider3ProductLineCode.AddItem tempstr
    Me.ComboBox_Cov1ProductLineCode.AddItem tempstr
  Next
  DisableControl ListBox_ProductLineCodeAllCovs

  Me.ComboBox_Rider1ProductIndicator.AddItem ANY_SELECTION
  Me.ComboBox_Rider2ProductIndicator.AddItem ANY_SELECTION
  Me.ComboBox_Rider3ProductIndicator.AddItem ANY_SELECTION
  Me.ComboBox_Cov1ProductLineCode.AddItem ANY_SELECTION
  For Each skey In ANICOProductDictionary.Keys
    tempstr = skey & " - " & ANICOProductDictionary(skey)
    Me.ListBox_ProductIndicatorAllCovs.AddItem tempstr
    Me.ComboBox_Rider1ProductIndicator.AddItem tempstr
    Me.ComboBox_Rider2ProductIndicator.AddItem tempstr
    Me.ComboBox_Rider3ProductIndicator.AddItem tempstr
    Me.ComboBox_Cov1ProductIndicator.AddItem tempstr
  
  Next
  
 
    
  
  DisableControl ListBox_ProductIndicatorAllCovs

  Me.ComboBox_Rider1LivesCoveredCode.AddItem ANY_SELECTION
  For Each skey In LivesCoveredDictionary.Keys
    tempstr = skey & " - " & LivesCoveredDictionary(skey)
    Me.ListBox_ProductIndicatorAllCovs.AddItem tempstr
    Me.ComboBox_Rider1LivesCoveredCode.AddItem tempstr
  Next

  ComboBox_SystemCode.List = Array("", "I", "P")
  ComboBox_SystemCode.value = "I"
  'ComboBox_SystemCode.Enabled = False
  
  Me.ListBox_NFO.List = Array("0 - No cash value", "1 - APL-->ETI", "2 - APL-->RPU", "3 - APL", "4 - ETI", "5 - RPU", "9 - Special Other")
  DisableControl ListBox_NFO
    
  Me.ListBox_LoanType.List = Array("0 - Advance, fixed", "1 - Arrears, fixed", "6 - Advance, variable", "7 - Arrears - Variable", "9 - Loans not allowed")
  DisableControl ListBox_LoanType


  Me.ListBox_InitialTermPeriod.List = Array("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "30", "65", "70", "85", "90", "99", "100", "121")
  DisableControl ListBox_InitialTermPeriod
  
  temparray = Array("0 - Non Participating", "1 - Cash", "2 - Premium reduction", "3 - Deposit at interest", "4 - Paid-up additions", "5 - OYT", "6 - OYT. Limit CV", "7 - OYT. Limit Face", "8 - Loan reduction", "9 - No further values", "D - OYT. Other")
  ListBox_PrimaryDivOption.List = temparray
  DisableControl ListBox_PrimaryDivOption
  ListBox_SecondaryDivOption.List = temparray
  DisableControl ListBox_SecondaryDivOption
  
  temparray = Array("0 - Direct pay notice", "G - PAC", "H - Salary deduction", "F - Government allotment", "4 - Discount prem deposit")
  Me.ListBox_BillingForm.List = temparray
  Me.ListBox_SLRBillingForm.List = temparray
  DisableControl ListBox_BillingForm
  DisableControl ListBox_SLRBillingForm
    
    
  ListBox_DefinitionOfLifeInsurance.List = Array("1 - TEFRA GP", "2 - DEFRA GP", "3 - DEFRA CVAT", "4 - GP Selected", "5 - CVAT Selected")
  DisableControl ListBox_DefinitionOfLifeInsurance
  
  ListBox_DBOption.List = Array("1 - Level(A)", "2 - Increasing(B)", "3  - Return Of Prem(C)")
  DisableControl Me.ListBox_DBOption
  
  Me.ListBox_State.List = StateDictionary.Keys
  DisableControl ListBox_State
  
  'Me.ListBox_SuspenseCode.List = Array("0 - Active", "2 - Suspend Processing", "3 - Death Claim Pending")
  'DisableControl ListBox_SuspenseCode
  
  ComboBox_Rider1RateclassCode67.AddItem ""
  ComboBox_Rider2RateclassCode67.AddItem ""
  ComboBox_Rider3RateclassCode67.AddItem ""
  For Each skey In RateclassDictionary.Keys
    tempstr = skey & " - " & LCase(RateclassDictionary(skey))
    Me.ListBox_Cov1Rateclass.AddItem tempstr
    ComboBox_Rider1RateclassCode67.AddItem tempstr
    ComboBox_Rider2RateclassCode67.AddItem tempstr
    ComboBox_Rider3RateclassCode67.AddItem tempstr
  Next
  ListBox_Cov1Rateclass.IntegralHeight = False
  DisableControl ListBox_Cov1Rateclass
   
  
  'Sex code on 67 segment
  ComboBox_Rider1SexCode67.AddItem ""
  ComboBox_Rider2SexCode67.AddItem ""
  ComboBox_Rider3SexCode67.AddItem ""
  For Each skey In SexCodeDictionary.Keys
    tempstr = skey & " - " & SexCodeDictionary(skey)
    Me.ListBox_Cov1SexCode.AddItem tempstr
    Me.ComboBox_Rider1SexCode67.AddItem tempstr
    Me.ComboBox_Rider2SexCode67.AddItem tempstr
    Me.ComboBox_Rider3SexCode67.AddItem tempstr
  Next
  DisableControl ListBox_Cov1SexCode
  
  'Sex code on 02 segment
  temparray = Array("1 - Male", "2 - Female", "3 - Joint")
  Me.ListBox_Cov1SexCodeFrom02.List = temparray
  ListBox_Cov1SexCodeFrom02.IntegralHeight = False
  DisableControl ListBox_Cov1SexCodeFrom02
  Me.ComboBox_Rider1SexCode02.List = temparray
  Me.ComboBox_Rider2SexCode02.List = temparray
  Me.ComboBox_Rider3SexCode02.List = temparray
  
  temparray = Array("", "0", "1")
  ComboBox_Rider1COLAIndicator.List = temparray
'  ComboBox_Rider2COLAIndicator.List = temparray
'  ComboBox_Rider3COLAIndicator.List = temparray

  temparray = Array("", "blank", "N", "Y")
  ComboBox_Rider1GIOFIOIndicator.List = temparray


'  For Each sKey In GetTransactionTypeDictionary.Keys
'    Me.ListBox_TransactionType.AddItem sKey & " - " & GetTransactionTypeDictionary(sKey)
'  Next
'  DisableControl ListBox_TransactionType
  
  ComboBox_Transaction1.AddItem ""

  For Each skey In TransactionTypeAndSubtypeDictionary.Keys
    Me.ListBox_TransactionTypeAndSubtype.AddItem skey & " - " & TransactionTypeAndSubtypeDictionary(skey)
    ComboBox_Transaction1.AddItem skey & " - " & TransactionTypeAndSubtypeDictionary(skey)
  Next
  'DisableControl ListBox_TransactionTypeAndSubtype
  
  For Each skey In StatusDictionary.Keys
    Me.ListBox_StatusCode.AddItem skey & "-" & StatusDictionary(skey)
  Next
  DisableControl ListBox_StatusCode
  
  Me.ListBox_BillMode.List = Array("Monthly", "Quarterly", "Semiannual", "Annual", "BiWeekly", "SemiMonthly", "9thly", "10thly")
  DisableControl ListBox_BillMode

  
  temparray = Array("IC - Index 1 yr PTP with 1.5% and Cap", "IF - Index 1 yr PTP uncapped with fee", "IS - Index 1 yr PTP with Specified Rate", "IX - Index 1 yr PTP with Cap", "IP - Index with Multiplier", "IR - Index with high Multiplier", "NX - NASDAQ100", "M1 - SPMARC5", "U1 - Fixed Fund")
  ListBox_PremiumAllocationFunds.List = temparray
  DisableControl ListBox_PremiumAllocationFunds
  
  Me.ComboBox_Benefit1.AddItem ANY_SELECTION
  Me.ComboBox_Benefit2.AddItem ANY_SELECTION
  Me.ComboBox_Benefit3.AddItem ANY_SELECTION
  For Each skey In BenefitDictionary.Keys
    Me.ComboBox_Benefit1.AddItem BenefitDictionary(skey) & " - " & skey
    Me.ComboBox_Benefit2.AddItem BenefitDictionary(skey) & " - " & skey
    Me.ComboBox_Benefit3.AddItem BenefitDictionary(skey) & " - " & skey
  Next
  
  temparray = Array(ANY_SELECTION, "00 - Insured or primary insured", "40 - Spouse", "50 - Dependent", "60 - Other", "01 - Joint insured")
  Me.ComboBox_Rider1Person.List = temparray
  Me.ComboBox_Rider2Person.List = temparray
  Me.ComboBox_Rider3Person.List = temparray
     
  
  temparray = Array("", "1 - Cease Dt = Orig Cease Dt", "2 - Cease Dt < Orig Cease Dt", "3 - Cease Dt > Orig Cease Dt")
  ComboBox_Benefit1CeaseDateStatus.List = temparray
  ComboBox_Benefit2CeaseDateStatus.List = temparray
  ComboBox_Benefit3CeaseDateStatus.List = temparray
  
  
  temparray = Array("", "1 - Same as base", "2 - Different than base")
  ComboBox_Rider1AdditionalPlancodeCriteria.List = temparray
  ComboBox_Rider2AdditionalPlancodeCriteria.List = temparray
  ComboBox_Rider3AdditionalPlancodeCriteria.List = temparray
  
  temparray = Array("0", "1", "2", "3", "4", "5", "6", "7", "9")
  ListBox_EliminationPeriodCodeForAccident.List = temparray
  DisableControl ListBox_EliminationPeriodCodeForAccident
  
  temparray = Array("0", "1", "2", "3", "4", "5", "6", "7", "8", "9")
  Me.ListBox_EliminationPeriodCodeForSickness.List = temparray
  DisableControl ListBox_EliminationPeriodCodeForSickness
  
  temparray = Array("B", "E", "F", "G", "J", "L", "R", "S", "X")
  Me.ListBox_BenefitPeriodCodeForAccident.List = temparray
  DisableControl ListBox_BenefitPeriodCodeForAccident

  temparray = Array("B", "E", "F", "G", "J", "L", "R", "S", "X")
  Me.ListBox_BenefitPeriodCodeForSickness.List = temparray
  DisableControl ListBox_BenefitPeriodCodeForSickness
    
  ListBox_GraceIndicator.List = Array("0 - Not In Grace", "1 - In Grace")
  DisableControl ListBox_GraceIndicator
    
  
  ListBox_OverloanIndicator.List = Array("0 - FALSE", "1 - TRUE")
  DisableControl ListBox_OverloanIndicator
    
  '09/06/2018 RJH:  Added SuspenseCode logic
  ListBox_SuspenseCode.List = Array("0 - Active", "1 - Not used", "2 - Suspended", "3 - Death claim pending")
  DisableControl ListBox_SuspenseCode
    
  For Each skey In MortalityTableDictionary.Keys
    ListBox_MortalityTableCodes.AddItem skey & " - " & MortalityTableDictionary(skey)
  Next
      
  For Each skey In GracePeriodRuleDictionary.Keys
    ListBox_GracePeriodRuleCode.AddItem skey & " - " & GracePeriodRuleDictionary(skey)
  Next
  DisableControl ListBox_GracePeriodRuleCode


  '05/15/2023 RJH:  Added Reinsurance cod
  ListBox_ReinsuranceCode.List = Array(" - none (space)", "F - Facultative", "A - Administrative", "N - ", "1 - Partial Reinsurance", "2 - Multiple Cov Reinsured")
  DisableControl ListBox_ReinsuranceCode

  ListBox_LastEntryCodes.List = Array("A - New Business (not paid for)", "B - Normal entry to file", "C - Active policy record", "D - Correction entry to database", "J - Termination - no pol exhibit", "L - Termination - death claim", "M - Termination - maturity", "N - Termination - expiration", "O - Termination - conversion", "P - Termination - surrender", "Q - Termination - lapse", "R - Termination - RPU/ETI", "X - Termination - free look")
  DisableControl ListBox_LastEntryCodes

  ListBox_OrigEntryCode.List = Array("A - New business", "B - Group conversion", "C - Block reinsurance", "D - Reinstatement", "E - Exchange or conversion new pol", "F - Exchange or conversion same pol", "G - Policy change", "H - Advanced product complex change", "Z - Old life business converted to the system")
  DisableControl ListBox_OrigEntryCode

  MultiPage1.value = 0
  
  blnMaxIsForPolicies = True
  blnIsPopulated = True
  
  Me.CheckBox_TableRating = False
  Me.CheckBox_FlatExtra.value = False
  Me.CheckBox_HasLoan = False
  Me.CheckBox_HasPreferredLoan.Enabled = False
  Me.CheckBox_HasPreferredLoan.value = False
    
  
  ListBox_NonTradIndicator.List = Array("0 - Trad", "1 - Advanced")
  DisableControl ListBox_NonTradIndicator

'  DisableControl Me.ListBox_MultiplePlancodes
'  DisableControl TextBox_SinglePlancode
  
  
  OptionButton_ShowPoliciesOnly.value = True
  
  ComboBox_Rider1ChangeType.List = Array("", "0 - Terminated", "1 - Paid Up", "2 - Prem paying")
  
  Me.ComboBox_PolicynumberCriteria.AddItem " "
  Me.ComboBox_PolicynumberCriteria.AddItem "1 - starts with"
  Me.ComboBox_PolicynumberCriteria.AddItem "2 - Ends with"
  Me.ComboBox_PolicynumberCriteria.AddItem "3 - Contains"
  Me.ComboBox_PolicynumberCriteria.value = " "
    
  Dim ChangeCodeArray
  ChangeCodeArray = Array("1 - Plan option change A to B or B to A", "2 - Planned periodic premium change", _
                            "3 - Specified amount increase", "4 - Specified amount decrease", _
                            "5 - Rate class", "6 - Mode change, fixed premium products only", _
                            "7 - Automatic increase, the result of a cost of living benefit", _
                            "8 - Variable loan interest change.", "9 - Termination data.", _
                            "A  - Plan rerating.", "B  - Sex code change.", "C  - Band code change.", _
                            "D  - Internal decrease in specified amount.", "E  - RMD payout/calculation rule change.", _
                            "F  - Policy fee (EIL only).", "G  - Fund restriction (variable funds only).", _
                            "H  - Long term care/dread disease monthliversary decrease.", "I  - Element structure change.", _
                            "J  - Bonus type change.", "L  - Lump sum deposit or unscheduled payment (proposals only).", _
                            "O  - Plan option change other than A to B or B to A.", "P  - Benefit/elimination period change (A&H).", _
                            "Q  - Loan repayment.", "R  - Re-entry term.", "S  - Mortality and expense (M&E) band change.", _
                            "T  - Remaining lifetime benefit change (LTC only).", "U  - Maturity date extension.", _
                            "Z - Set up reoccuring payments")

  ListBox_68SegmentChangeCodes.List = ChangeCodeArray
  DisableControl ListBox_68SegmentChangeCodes
  
End Sub


Private Sub CheckBox_BaseSearchShowPolicies_Click()
If CheckBox_BaseSearchShowPolicies Then
  Me.Label_BaseSearchCount = "Policy number"
Else
  Me.Label_BaseSearchCount = "Rider Count"
End If
End Sub

Private Sub CheckBox_BenefitPeriodCodeForAccident_Click()
If CheckBox_BenefitPeriodCodeForAccident Then
  EnableControl ListBox_BenefitPeriodCodeForAccident
Else
  DisableControl ListBox_BenefitPeriodCodeForAccident
End If
End Sub

Private Sub CheckBox_BenefitPeriodCodeForSickness_Click()
If CheckBox_BenefitPeriodCodeForSickness Then
  EnableControl ListBox_BenefitPeriodCodeForSickness
Else
  DisableControl ListBox_BenefitPeriodCodeForSickness
End If
End Sub


Private Sub CheckBox_EliminationPeriodCodeForAccident_Click()
If CheckBox_EliminationPeriodCodeForAccident Then
  EnableControl ListBox_EliminationPeriodCodeForAccident
Else
  DisableControl ListBox_EliminationPeriodCodeForAccident
End If
End Sub

Private Sub CheckBox_EliminationPeriodCodeForSickness_Click()
If CheckBox_EliminationPeriodCodeForSickness Then
  EnableControl ListBox_EliminationPeriodCodeForSickness
Else
  DisableControl ListBox_EliminationPeriodCodeForSickness
End If
End Sub

Private Sub CheckBox_GraceIndicator_Click()
If Me.CheckBox_GraceIndicator Then
    EnableControl ListBox_GraceIndicator
Else
    DisableControl ListBox_GraceIndicator
End If
End Sub

Private Sub CheckBox_GracePeriodRuleCode_Click()
If Me.CheckBox_GracePeriodRuleCode Then
    EnableControl ListBox_GracePeriodRuleCode
Else
    DisableControl ListBox_GracePeriodRuleCode
End If
End Sub

Private Sub CheckBox_HasLoan_Click()
  If Me.CheckBox_HasLoan.value Then
   Me.CheckBox_HasPreferredLoan.Enabled = True
     Else
   Me.CheckBox_HasPreferredLoan.Enabled = False
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


Private Sub CheckBox_MultiplePlancodes_Click()
If CheckBox_MultiplePlancodes Then
  EnableControl Me.ListBox_MultiplePlancodes
  EnableControl TextBox_SinglePlancode
  MultiPage1.value = MultiPage1.Pages("Plancodes").Index
Else
  DisableControl Me.ListBox_MultiplePlancodes
  DisableControl TextBox_SinglePlancode
End If
End Sub

Private Sub CheckBox_PremiumAllocationFunds_Click()
If CheckBox_PremiumAllocationFunds Then
  EnableControl ListBox_PremiumAllocationFunds
Else
  DisableControl ListBox_PremiumAllocationFunds
End If
End Sub

Private Sub CheckBox_RiderSearchShowPolicies_Click()
If CheckBox_RiderSearchShowPolicies Then
  Me.Label_RiderSearchCount = "Policy number"
Else
  Me.Label_RiderSearchCount = "Rider Count"
End If
End Sub


Private Sub CheckBox_SpecifyBillingForm_Click()
If CheckBox_SpecifyBillingForm Then
  EnableControl Me.ListBox_BillingForm
Else
  DisableControl ListBox_BillingForm
End If
End Sub

Private Sub CheckBox_SpecifySLRBillingForm_Click()
If CheckBox_SpecifySLRBillingForm Then
  EnableControl Me.ListBox_SLRBillingForm
Else
  DisableControl ListBox_SLRBillingForm
End If
End Sub


Private Sub CheckBox_SpecifyBillingModes_Click()
If CheckBox_SpecifyBillingModes Then
  EnableControl ListBox_BillMode
Else
  DisableControl ListBox_BillMode
End If
End Sub

Private Sub CheckBox_SpecifyDBOption_Click()
If CheckBox_SpecifyDBOption Then
  EnableControl ListBox_DBOption
Else
  DisableControl ListBox_DBOption
End If
End Sub

Private Sub CheckBox_SpecifyDefinitionOfLifeInsurance_Click()
If CheckBox_SpecifyDefinitionOfLifeInsurance Then
  EnableControl Me.ListBox_DefinitionOfLifeInsurance
Else
  DisableControl ListBox_DefinitionOfLifeInsurance
End If
End Sub

Private Sub CheckBox_ReinsuranceCode_Click()
If CheckBox_ReinsuranceCode Then
  EnableControl Me.ListBox_ReinsuranceCode
Else
  DisableControl ListBox_ReinsuranceCode
End If
End Sub

Private Sub CheckBox_SpecifyLoanType_Click()
If CheckBox_SpecifyLoanType Then
  EnableControl ListBox_LoanType
Else
  DisableControl ListBox_LoanType
End If
End Sub

Private Sub CheckBox_HasChangeSegment_Click()
If CheckBox_HasChangeSegment Then
  EnableControl ListBox_68SegmentChangeCodes
Else
  DisableControl ListBox_68SegmentChangeCodes
End If
End Sub


Private Sub CheckBox_OverloanIndicator_Click()
If CheckBox_OverloanIndicator Then
  EnableControl ListBox_OverloanIndicator
Else
  DisableControl ListBox_OverloanIndicator
End If
End Sub

Private Sub CheckBox_NonTradIndicator_Click()
If CheckBox_OverloanIndicator Then
  EnableControl ListBox_NonTradIndicator
Else
  DisableControl ListBox_NonTradIndicator
End If
End Sub


Private Sub CheckBox_SpecifyNFO_Click()
If CheckBox_SpecifyNFO Then
  EnableControl ListBox_NFO
Else
  DisableControl ListBox_NFO
End If
End Sub


Private Sub CheckBox_SpecifyCov1Rateclass_Click()
If CheckBox_SpecifyCov1Rateclass Then
  EnableControl ListBox_Cov1Rateclass
Else
  DisableControl ListBox_Cov1Rateclass
End If
End Sub

Private Sub CheckBox_SpecifyPrimaryDivOpt_Click()
If CheckBox_SpecifyPrimaryDivOpt Then
  EnableControl ListBox_PrimaryDivOption
Else
  DisableControl ListBox_PrimaryDivOption
End If
End Sub

Private Sub CheckBox_SpecifyProductIndicatorAllCovs_Click()
If CheckBox_SpecifyProductIndicatorAllCovs Then
  EnableControl ListBox_ProductIndicatorAllCovs
Else
  DisableControl ListBox_ProductIndicatorAllCovs
End If
End Sub

Private Sub CheckBox_SpecifyProductLineCodeAllCovs_Click()
If CheckBox_SpecifyProductLineCodeAllCovs Then
  EnableControl Me.ListBox_ProductLineCodeAllCovs
Else
  DisableControl ListBox_ProductLineCodeAllCovs
End If
End Sub

Private Sub CheckBox_SpecifyLastEntryCode_Click()
If CheckBox_SpecifyLastEntryCode Then
  EnableControl ListBox_LastEntryCodes
Else
  DisableControl ListBox_LastEntryCodes
End If
End Sub

Private Sub CheckBox_SpecifyOrigEntryCode_Click()
If CheckBox_SpecifyOrigEntryCode Then
  EnableControl ListBox_OrigEntryCode
Else
  DisableControl ListBox_OrigEntryCode
End If
End Sub

Private Sub CheckBox_SpecifySecondaryDivOpt_Click()
If CheckBox_SpecifySecondaryDivOpt Then
  EnableControl ListBox_SecondaryDivOption
Else
  DisableControl ListBox_SecondaryDivOption
End If
End Sub

Private Sub CheckBox_SpecifyCov1Sexcode_Change()
If CheckBox_SpecifyCov1Sexcode Then
  EnableControl Me.ListBox_Cov1SexCode
Else
  DisableControl Me.ListBox_Cov1SexCode
End If
End Sub
Private Sub CheckBox_SpecifyCov1Sexcode_Click()
If CheckBox_SpecifyCov1Sexcode Then
  EnableControl Me.ListBox_Cov1SexCode
Else
  DisableControl Me.ListBox_Cov1SexCode
End If
End Sub

Private Sub CheckBox_SpecifyCov1SexcodeFrom02_Click()
If CheckBox_SpecifyCov1SexcodeFrom02 Then
  EnableControl Me.ListBox_Cov1SexCodeFrom02
Else
  DisableControl Me.ListBox_Cov1SexCodeFrom02
End If
End Sub

Private Sub CheckBox_SpecifyState_Click()
If CheckBox_SpecifyState Then
  EnableControl Me.ListBox_State
Else
  DisableControl Me.ListBox_State
End If
End Sub

Private Sub CheckBox_SpecifyInitialTermPeriod_Click()
If CheckBox_SpecifyInitialTermPeriod Then
  EnableControl ListBox_InitialTermPeriod
Else
  DisableControl ListBox_InitialTermPeriod
End If
End Sub

Private Sub CheckBox_SpecifyStatusCodes_Click()
If CheckBox_SpecifyStatusCodes Then
  EnableControl ListBox_StatusCode
Else
  DisableControl ListBox_StatusCode
End If
End Sub

Private Sub CheckBox_SuspenseCode_Click()
'09/06/2018 RJH:  Added SuspenseCode logic
    If CheckBox_SuspenseCode Then
        EnableControl ListBox_SuspenseCode
    Else
        DisableControl ListBox_SuspenseCode
    End If
End Sub



Private Sub ComboBox_MarketOrg_Change()
Dim temparray()

'If ComboBox_MarketOrg.value = "CSSD" Then
'    ComboBox_Company.List = Array("ANICO")
'    ComboBox_Company.value = "ANICO"
'End If
'
'If ComboBox_MarketOrg.value = "IMG" Or ComboBox_MarketOrg.value = "MLM" Or ComboBox_MarketOrg.value = "DIRECT" Then
'    ComboBox_Company.List = Array(ANY_SELECTION, "ANICO", "ANICONY")
'    If ComboBox_Company.value <> ANY_SELECTION And ComboBox_Company.value <> "ANICO" And ComboBox_Company.value <> "ANICONY" Then
'        ComboBox_Company.value = ANY_SELECTION
'    End If
'End If
'
'
'
'
'If ComboBox_MarketOrg.value = ANY_SELECTION Then
'  tempArray = CompanyDictionary.Keys
'  InsertElementIntoArray tempArray, 0, ANY_SELECTION
'  Me.ComboBox_Company.List = tempArray
'End If

End Sub
 
Private Sub ComboBox_Company_Change()
Dim Company As String
Dim CurrentValue As String

CurrentValue = ComboBox_MarketOrg.value

Dim temparray As Variant
  With ComboBox_Company
    Company = .List(.ListIndex)
  End With
  
  If Company = "GSL" Or Company = "ANTEX" Or Company = "SLAICO" Or Company = "FFL" Then
    ComboBox_MarketOrg.value = ANY_SELECTION
    DisableControl ComboBox_MarketOrg
  Else
    EnableControl ComboBox_MarketOrg
  End If
    
  If Company = ANY_SELECTION Then
    temparray = Array(ANY_SELECTION, "MLM", "CSSD", "IMG", "DIRECT")
    ComboBox_MarketOrg.List = temparray
    ComboBox_MarketOrg.value = CurrentValue
  Else
    'Company is either ANICO or ANICONY
    temparray = MarketDictionary(Company).Keys
    InsertElementIntoArray temparray, 0, ANY_SELECTION
    ComboBox_MarketOrg.List = temparray
    If MarketDictionary(Company).exists(CurrentValue) Then
      ComboBox_MarketOrg.value = CurrentValue
    Else
      ComboBox_MarketOrg.value = ANY_SELECTION
    End If
  End If
  
  
End Sub


Private Sub Label_AddPlancode_Click()
    ListBox_MultiplePlancodes.AddItem TextBox_SinglePlancode.value
End Sub

Private Sub Label_ExportToExcel_Click()
  If VDisplay.ListCount = 0 Then Exit Sub
   DumpArrayValuesIntoExcel VDisplay.TableData, , , True
End Sub

Private Sub Label_ExportBaseWithRider_Click()
 If ListBox_QueryBaseWithRider.ListCount = 0 Then Exit Sub
   
  Dim ary, header
  ary = Me.ListBox_QueryBaseWithRider.List
  header = Array("Rider Plancode", "Rider Form", "Base Plancode", "Base Form", Label_BaseSearchCount.caption)

  Call InsertRowIntoArray(ary, 0, header)
  DumpArrayValuesIntoExcel ary

End Sub

Private Sub Label_ExportRiderOnBase_Click()
  If Me.ListBox_QueryRidersOnBase.ListCount = 0 Then Exit Sub
  
  Dim ary, header
  ary = Me.ListBox_QueryRidersOnBase.List
  header = Array("Base Plancode", "Base Form", "Rider Plancode", "Rider Form", Label_RiderSearchCount.caption)
  
  Call InsertRowIntoArray(ary, 0, header)
  DumpArrayValuesIntoExcel ary

End Sub

Private Sub Label_ExportValueSearch_Click()
  If Me.ListBox_QueryResultsValueSearch.ListCount = 0 Then Exit Sub
  
  Dim ary, header
  ary = Me.ListBox_QueryResultsValueSearch.List
  header = Array("Field Value", "Policy Count")
  
  Call InsertRowIntoArray(ary, 0, header)
  DumpArrayValuesIntoExcel ary
End Sub


Private Sub CommandButton_FindBase_Click()
Dim DB2Data As Variant

DB2Data = FetchTable(BuildSQLStringToFindBase, ComboBox_Region.value, False)

If IsEmpty(DB2Data) Then
  ListBox_QueryBaseWithRider.List = Array("none found")
Else
 Me.ListBox_QueryBaseWithRider.List = DB2Data
End If

End Sub

Private Sub CommandButton_FindRiders_Click()
Dim DB2Data As Variant

DB2Data = FetchTable(BuildSQLStringToFindRiders, ComboBox_Region.value, False)

If IsEmpty(DB2Data) Then
  ListBox_QueryRidersOnBase.List = Array("none found")
Else
 ListBox_QueryRidersOnBase.List = DB2Data
End If

End Sub

Private Sub CommandButton_ValueSearch_Click()
Dim DB2Data As Variant

DB2Data = FetchTable(BuildSQLStringToFindValues, ComboBox_Region.value, False)

If IsEmpty(DB2Data) Then
  ListBox_QueryResultsValueSearch.List = Array("none found")
Else
 ListBox_QueryResultsValueSearch.List = DB2Data
End If

End Sub

Private Sub CommandButton_RunAudit_Click()
    LoadAuditResults
End Sub
Private Sub LoadAuditResults()
Dim DB2Data
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
str = BuildSQLString
TextBox_SQL.value = str


'Run query and display the amount of time it takes to run
StartTime = Now()
DB2Data = FetchTable(str, ComboBox_Region.value, True)
ElapsedTime = Now() - StartTime
Label_QueryTimeAmount = Format(ElapsedTime, "HH:MM:SS")


'Print query results and display the amount of time it takes to print
StartTime2 = Now()
If IsEmpty(DB2Data) Then
    Dim ary(1, 0)
    ary(0, 0) = ""
    ary(1, 0) = "No Records"
    VDisplay.TableData = ary
    Exit Sub
End If

'VDisplay.FilterOn = True
VDisplay.TableData = DB2Data
   


ElapsedTime = Now() - StartTime2
Label_PrintTimeAmount = Format(ElapsedTime, "HH:MM:SS")


'Print total time
ElapsedTime = Now() - StartTime
Label_TotalTimeAmount = Format(ElapsedTime, "HH:MM:SS")


'Display result count
Label_ResultCountAmount = VDisplay.ListCount - 1


'switch to Results tab
MultiPage1.value = MultiPage1.Pages("Results").Index




End Sub


Private Function BuildRiderTable()
Dim dct As Dictionary
Set dct = New Dictionary
Dim tempSQL As String

    'Build RIDER_INTERSECT (COV_PHA_NBR > 1)
    '-----------------------------------------------------------------------------------------------------------------------------------------
    
    blnQueryRider1 = TextBox_Rider1Plancode <> "" Or ComboBox_Rider1Person <> "" Or ComboBox_Rider1SexCode02 <> "" Or CheckBox_Rider1PostIssue Or CheckBox_Rider1TableRating Or _
                    CheckBox_Rider1FlatExtra Or ComboBox_Rider1ProductIndicator.value <> "" Or ComboBox_Rider1RateclassCode67.value <> "" Or ComboBox_Rider1SexCode67.value <> "" Or _
                    ComboBox_Rider1ProductLineCode <> "" Or ComboBox_Rider1AdditionalPlancodeCriteria <> "" Or TextBox_Rider1LowIssueDate.value <> "" Or TextBox_Rider1HighIssueDate.value <> "" Or _
                    ComboBox_Rider1COLAIndicator.value <> "" Or ComboBox_Rider1GIOFIOIndicator <> "" Or ComboBox_Rider1ChangeType <> "" Or ComboBox_Rider1LivesCoveredCode <> ""
    
    blnQueryRider2 = TextBox_Rider2Plancode <> "" Or ComboBox_Rider2Person <> "" Or ComboBox_Rider2SexCode02 <> "" Or CheckBox_Rider2PostIssue Or CheckBox_Rider2TableRating Or _
                    CheckBox_Rider2FlatExtra Or ComboBox_Rider2ProductIndicator.value <> "" Or ComboBox_Rider2RateclassCode67.value <> "" Or ComboBox_Rider2SexCode67.value <> "" Or _
                    ComboBox_Rider2ProductLineCode <> "" Or ComboBox_Rider2AdditionalPlancodeCriteria <> "" Or ComboBox_Rider2ChangeType <> ""
    
    blnQueryRider3 = TextBox_Rider3Plancode <> "" Or ComboBox_Rider3Person <> "" Or ComboBox_Rider3SexCode02 <> "" Or CheckBox_Rider3PostIssue Or CheckBox_Rider3TableRating Or _
                    CheckBox_Rider3FlatExtra Or ComboBox_Rider3ProductIndicator.value <> "" Or ComboBox_Rider3RateclassCode67.value <> "" Or ComboBox_Rider3SexCode67.value <> "" Or _
                    ComboBox_Rider3ProductLineCode <> "" Or ComboBox_Rider3AdditionalPlancodeCriteria <> "" Or ComboBox_Rider3ChangeType <> ""
   
    
  
    
    If blnQueryRider1 Or blnQueryRider2 Or blnQueryRider3 Then
     
        'RIDER 1
        If blnQueryRider1 Then
            tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_COV_PHA RIDER1  "
                tempSQL = tempSQL & "ON POLICY1.CK_SYS_CD = RIDER1.CK_SYS_CD "
                tempSQL = tempSQL & "AND POLICY1.CK_CMP_CD = RIDER1.CK_CMP_CD "
                tempSQL = tempSQL & "AND POLICY1.TCH_POL_ID = RIDER1.TCH_POL_ID "
                tempSQL = tempSQL & "AND RIDER1.COV_PHA_NBR > 1 "
                If TextBox_Rider1Plancode <> "" Then tempSQL = tempSQL & "AND RIDER1.PLN_DES_SER_CD = '" & Me.TextBox_Rider1Plancode & "' "
                If ComboBox_Rider1Person <> "" Then tempSQL = tempSQL & " AND RIDER1.PRS_CD = '" & left(Me.ComboBox_Rider1Person, 2) & "' "
                If ComboBox_Rider1SexCode02 <> "" Then tempSQL = tempSQL & " AND RIDER1.INS_SEX_CD = '" & left(Me.ComboBox_Rider1SexCode02.value, 1) & "' "
                If CheckBox_Rider1PostIssue Then tempSQL = tempSQL & " AND RIDER1.ISSUE_DT > COVERAGE1.ISSUE_DT "
                If TextBox_Rider1LowIssueDate.value <> "" Then tempSQL = tempSQL & " AND RIDER1.ISSUE_DT >= '" & Format(TextBox_Rider1LowIssueDate.value, "yyyy-mm-dd") & "' "
                If TextBox_Rider1HighIssueDate.value <> "" Then tempSQL = tempSQL & " AND RIDER1.ISSUE_DT <= '" & Format(TextBox_Rider1HighIssueDate.value, "yyyy-mm-dd") & "' "
                If ComboBox_Rider1ProductLineCode.value <> "" Then tempSQL = tempSQL & " AND RIDER1.PRD_LIN_TYP_CD = '" & left(ComboBox_Rider1ProductLineCode.value, 1) & "' "
                If ComboBox_Rider1ChangeType.value <> "" Then tempSQL = tempSQL & " AND RIDER1.NXT_CHG_TYP_CD = '" & left(ComboBox_Rider1ChangeType.value, 1) & "' "
                If TextBox_Rider1LowChangeDate <> "" Then tempSQL = tempSQL & " AND RIDER1.NXT_CHG_DT >= '" & Format(TextBox_Rider1LowChangeDate.value, "yyyy-mm-dd") & "' "
                If TextBox_Rider1HighChangeDate <> "" Then tempSQL = tempSQL & " AND RIDER1.NXT_CHG_DT <= '" & Format(TextBox_Rider1HighChangeDate.value, "yyyy-mm-dd") & "' "
                If ComboBox_Rider1LivesCoveredCode <> "" Then tempSQL = tempSQL & " AND RIDER1.LIVES_COV_CD = '" & left(ComboBox_Rider1LivesCoveredCode.value, 1) & "' "
                
                
                If ComboBox_Rider1AdditionalPlancodeCriteria.value <> "" Then
                    If left(ComboBox_Rider1AdditionalPlancodeCriteria.value, 1) = "1" Then tempSQL = tempSQL & "AND RIDER1.PLN_DES_SER_CD = COVERAGE1.PLN_DES_SER_CD "
                    If left(ComboBox_Rider1AdditionalPlancodeCriteria.value, 1) = "2" Then tempSQL = tempSQL & "AND RIDER1.PLN_DES_SER_CD <> COVERAGE1.PLN_DES_SER_CD "
                End If
                    
            'Table Rating.  LH_SST_XTR_CRG
            If CheckBox_Rider1TableRating Then
                tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_SST_XTR_CRG RIDER1_TABLE_RATING  "
                    tempSQL = tempSQL & "ON RIDER1.CK_SYS_CD = RIDER1_TABLE_RATING.CK_SYS_CD "
                    tempSQL = tempSQL & "AND RIDER1.CK_CMP_CD = RIDER1_TABLE_RATING.CK_CMP_CD "
                    tempSQL = tempSQL & "AND RIDER1.TCH_POL_ID = RIDER1_TABLE_RATING.TCH_POL_ID "
                    tempSQL = tempSQL & "AND RIDER1.COV_PHA_NBR = RIDER1_TABLE_RATING.COV_PHA_NBR "
                    tempSQL = tempSQL & "AND (RIDER1_TABLE_RATING.SST_XTR_TYP_CD ='0' Or RIDER1_TABLE_RATING.SST_XTR_TYP_CD ='1' Or RIDER1_TABLE_RATING.SST_XTR_TYP_CD ='3') "
            End If
            
            'Flat Extra.  LH_SST_XTR_CRG
            If CheckBox_Rider1FlatExtra Then
                tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_SST_XTR_CRG RIDER1_FLAT_EXTRA  "
                    tempSQL = tempSQL & "ON RIDER1.CK_SYS_CD = RIDER1_FLAT_EXTRA.CK_SYS_CD "
                    tempSQL = tempSQL & "AND RIDER1.CK_CMP_CD = RIDER1_FLAT_EXTRA.CK_CMP_CD "
                    tempSQL = tempSQL & "AND RIDER1.TCH_POL_ID = RIDER1_FLAT_EXTRA.TCH_POL_ID "
                    tempSQL = tempSQL & "AND RIDER1.COV_PHA_NBR = RIDER1_FLAT_EXTRA.COV_PHA_NBR "
                    tempSQL = tempSQL & "AND (RIDER1_FLAT_EXTRA.SST_XTR_TYP_CD ='2' Or RIDER1_FLAT_EXTRA.SST_XTR_TYP_CD ='4') "
            End If
            
            If ComboBox_Rider1ProductIndicator.value <> "" Or ComboBox_Rider1GIOFIOIndicator <> "" Or ComboBox_Rider1COLAIndicator.value <> "" Then
                tempSQL = tempSQL & "INNER JOIN DB2TAB.TH_COV_PHA RIDER1COVMOD "
                    tempSQL = tempSQL & "ON RIDER1COVMOD.CK_SYS_CD = RIDER1.CK_SYS_CD "
                    tempSQL = tempSQL & "AND RIDER1COVMOD.CK_CMP_CD = RIDER1.CK_CMP_CD "
                    tempSQL = tempSQL & "AND RIDER1COVMOD.TCH_POL_ID = RIDER1.TCH_POL_ID "
                    tempSQL = tempSQL & "AND RIDER1COVMOD.COV_PHA_NBR = RIDER1.COV_PHA_NBR "
                    If ComboBox_Rider1ProductIndicator.value <> "" Then tempSQL = tempSQL & "AND (RIDER1COVMOD.AN_PRD_ID = '" & left(ComboBox_Rider1ProductIndicator, 1) & "') "
                    If ComboBox_Rider1COLAIndicator.value <> "" Then tempSQL = tempSQL & "AND RIDER1COVMOD.COLA_INCR_IND = '" & ComboBox_Rider1COLAIndicator.value & "' "
            
                    If ComboBox_Rider1GIOFIOIndicator <> "" Then
                        If ComboBox_Rider1GIOFIOIndicator = "blank" Then
                            tempSQL = tempSQL & "AND RIDER1COVMOD.OPT_EXER_IND = '' "
                        Else
                            tempSQL = tempSQL & "AND RIDER1COVMOD.OPT_EXER_IND = '" & ComboBox_Rider1GIOFIOIndicator.value & "' "
                        End If
                    End If
            End If
          
            If ComboBox_Rider1RateclassCode67.value <> "" Or ComboBox_Rider1SexCode67.value <> "" Then
                tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_COV_INS_RNL_RT RIDER1_RENEWALS  "
                    tempSQL = tempSQL & "ON RIDER1.CK_SYS_CD = RIDER1_RENEWALS.CK_SYS_CD "
                    tempSQL = tempSQL & "AND RIDER1.CK_CMP_CD = RIDER1_RENEWALS.CK_CMP_CD "
                    tempSQL = tempSQL & "AND RIDER1.TCH_POL_ID = RIDER1_RENEWALS.TCH_POL_ID "
                    tempSQL = tempSQL & "AND RIDER1.COV_PHA_NBR = RIDER1_RENEWALS.COV_PHA_NBR "
                    'Set PRM_TYP_CD to 'C' so you only get one record from this table for this rider
                    tempSQL = tempSQL & "AND RIDER1_RENEWALS.PRM_RT_TYP_CD = 'C' "
                    If ComboBox_Rider1RateclassCode67.value <> "" Then tempSQL = tempSQL & "AND (RIDER1_RENEWALS.RT_CLS_CD = '" & left(ComboBox_Rider1RateclassCode67.value, 1) & "') "
                    If ComboBox_Rider1SexCode67.value <> "" Then tempSQL = tempSQL & "AND (RIDER1_RENEWALS.RT_SEX_CD = '" & left(ComboBox_Rider1SexCode67.value, 1) & "') "
            End If
        End If
            
        'RIDER 2
        If blnQueryRider2 Then
            tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_COV_PHA RIDER2 "
                tempSQL = tempSQL & "ON RIDER2.CK_SYS_CD = POLICY1.CK_SYS_CD "
                tempSQL = tempSQL & "AND RIDER2.CK_CMP_CD = POLICY1.CK_CMP_CD "
                tempSQL = tempSQL & "AND RIDER2.TCH_POL_ID = POLICY1.TCH_POL_ID "
                tempSQL = tempSQL & "AND RIDER2.COV_PHA_NBR > 1 "
                If TextBox_Rider2Plancode <> "" Then tempSQL = tempSQL & "AND RIDER2.PLN_DES_SER_CD = '" & Me.TextBox_Rider2Plancode & "' "
                If ComboBox_Rider2Person <> "" Then tempSQL = tempSQL & " AND RIDER2.PRS_CD = '" & left(Me.ComboBox_Rider2Person, 2) & "' "
                If ComboBox_Rider2SexCode02 <> "" Then tempSQL = tempSQL & " AND RIDER2.INS_SEX_CD = '" & left(Me.ComboBox_Rider2SexCode02.value, 1) & "' "
                If CheckBox_Rider2PostIssue Then tempSQL = tempSQL & " AND RIDER2.ISSUE_DT > COVERAGE1.ISSUE_DT "
                If ComboBox_Rider2ProductLineCode <> "" Then tempSQL = tempSQL & " AND RIDER2.PRD_LIN_TYP_CD = '" & left(ComboBox_Rider2ProductLineCode.value, 1) & "' "
                If ComboBox_Rider2ChangeType.value <> "" Then tempSQL = tempSQL & " AND RIDER2.NXT_CHG_TYP_CD = '" & left(ComboBox_Rider2ChangeType.value, 1) & "' "
                If ComboBox_Rider2AdditionalPlancodeCriteria.value <> "" Then
                    If left(ComboBox_Rider2AdditionalPlancodeCriteria.value, 1) = "1" Then tempSQL = tempSQL & "AND RIDER2.PLN_DES_SER_CD = COVERAGE1.PLN_DES_SER_CD "
                    If left(ComboBox_Rider2AdditionalPlancodeCriteria.value, 1) = "2" Then tempSQL = tempSQL & "AND RIDER2.PLN_DES_SER_CD <> COVERAGE1.PLN_DES_SER_CD "
                End If
            
            'Table Rating.  LH_SST_XTR_CRG
            If CheckBox_Rider2TableRating Then
                tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_SST_XTR_CRG RIDER2_TABLE_RATING  "
                    tempSQL = tempSQL & "ON RIDER2.CK_SYS_CD = RIDER2_TABLE_RATING.CK_SYS_CD "
                    tempSQL = tempSQL & "AND RIDER2.CK_CMP_CD = RIDER2_TABLE_RATING.CK_CMP_CD "
                    tempSQL = tempSQL & "AND RIDER2.TCH_POL_ID = RIDER2_TABLE_RATING.TCH_POL_ID "
                    tempSQL = tempSQL & "AND RIDER2.COV_PHA_NBR = RIDER2_TABLE_RATING.COV_PHA_NBR "
                    tempSQL = tempSQL & "AND (RIDER2_TABLE_RATING.SST_XTR_TYP_CD ='0' Or RIDER2_TABLE_RATING.SST_XTR_TYP_CD ='1' Or RIDER2_TABLE_RATING.SST_XTR_TYP_CD ='3') "
            End If
            
            'Flat Extra.  LH_SST_XTR_CRG
            If CheckBox_Rider2FlatExtra Then
                tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_SST_XTR_CRG RIDER2_FLAT_EXTRA  "
                    tempSQL = tempSQL & "ON RIDER2.CK_SYS_CD = RIDER2_FLAT_EXTRA.CK_SYS_CD "
                    tempSQL = tempSQL & "AND RIDER2.CK_CMP_CD = RIDER2_FLAT_EXTRA.CK_CMP_CD "
                    tempSQL = tempSQL & "AND RIDER2.TCH_POL_ID = RIDER2_FLAT_EXTRA.TCH_POL_ID "
                    tempSQL = tempSQL & "AND RIDER2.COV_PHA_NBR = RIDER2_FLAT_EXTRA.COV_PHA_NBR "
                    tempSQL = tempSQL & "AND (RIDER2_FLAT_EXTRA.SST_XTR_TYP_CD ='2' Or RIDER2_FLAT_EXTRA.SST_XTR_TYP_CD ='4') "
            End If
            
            If ComboBox_Rider2ProductIndicator.value <> "" Then
                tempSQL = tempSQL & "INNER JOIN DB2TAB.TH_COV_PHA RIDER2COVMOD "
                    tempSQL = tempSQL & "ON RIDER2COVMOD.CK_SYS_CD = RIDER2.CK_SYS_CD "
                    tempSQL = tempSQL & "AND RIDER2COVMOD.CK_CMP_CD = RIDER2.CK_CMP_CD "
                    tempSQL = tempSQL & "AND RIDER2COVMOD.TCH_POL_ID = RIDER2.TCH_POL_ID "
                    tempSQL = tempSQL & "AND RIDER2COVMOD.COV_PHA_NBR = RIDER2.COV_PHA_NBR "
                    tempSQL = tempSQL & "AND (RIDER2COVMOD.AN_PRD_ID = '" & left(ComboBox_Rider2ProductIndicator, 1) & "') "
            End If
          
            If ComboBox_Rider2RateclassCode67.value <> "" Or ComboBox_Rider2SexCode67.value <> "" Then
                tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_COV_INS_RNL_RT RIDER2_RENEWALS  "
                    tempSQL = tempSQL & "ON RIDER2.CK_SYS_CD = RIDER2_RENEWALS.CK_SYS_CD "
                    tempSQL = tempSQL & "AND RIDER2.CK_CMP_CD = RIDER2_RENEWALS.CK_CMP_CD "
                    tempSQL = tempSQL & "AND RIDER2.TCH_POL_ID = RIDER2_RENEWALS.TCH_POL_ID "
                    tempSQL = tempSQL & "AND RIDER2.COV_PHA_NBR = RIDER2_RENEWALS.COV_PHA_NBR "
                    'Set PRM_TYP_CD to 'C' so you only get one record from this table for this rider
                    tempSQL = tempSQL & "AND (RIDER2_RENEWALS.PRM_RT_TYP_CD = 'C') "
                    If ComboBox_Rider2RateclassCode67.value <> "" Then tempSQL = tempSQL & "AND (RIDER2_RENEWALS.RT_CLS_CD = '" & left(ComboBox_Rider2RateclassCode67.value, 1) & "') "
                    If ComboBox_Rider2SexCode67.value <> "" Then tempSQL = tempSQL & "AND (RIDER2_RENEWALS.RT_SEX_CD = '" & left(ComboBox_Rider2SexCode67.value, 1) & "') "
            End If
        End If
            
        'RIDER 3
        If blnQueryRider3 Then
            tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_COV_PHA RIDER3 "
                tempSQL = tempSQL & "ON RIDER3.CK_SYS_CD = POLICY1.CK_SYS_CD "
                tempSQL = tempSQL & "AND RIDER3.CK_CMP_CD = POLICY1.CK_CMP_CD "
                tempSQL = tempSQL & "AND RIDER3.TCH_POL_ID = POLICY1.TCH_POL_ID "
                tempSQL = tempSQL & "AND RIDER3.COV_PHA_NBR > 1 "
                If TextBox_Rider3Plancode <> "" Then tempSQL = tempSQL & "AND Rider3.PLN_DES_SER_CD = '" & Me.TextBox_Rider3Plancode & "' "
                If ComboBox_Rider3Person <> "" Then tempSQL = tempSQL & " AND Rider3.PRS_CD = '" & left(Me.ComboBox_Rider3Person, 2) & "' "
                If ComboBox_Rider3SexCode02 <> "" Then tempSQL = tempSQL & " AND Rider3.INS_SEX_CD = '" & left(Me.ComboBox_Rider3SexCode02.value, 1) & "' "
                If CheckBox_Rider3PostIssue Then tempSQL = tempSQL & " AND Rider3.ISSUE_DT > COVERAGE1.ISSUE_DT "
                If ComboBox_Rider3ProductLineCode <> "" Then tempSQL = tempSQL & " AND Rider3.PRD_LIN_TYP_CD = '" & left(ComboBox_Rider3ProductLineCode.value, 1) & "' "
                If ComboBox_Rider3ChangeType.value <> "" Then tempSQL = tempSQL & " AND RIDER3.NXT_CHG_TYP_CD = '" & left(ComboBox_Rider3ChangeType.value, 1) & "' "
                If ComboBox_Rider3AdditionalPlancodeCriteria.value <> "" Then
                    If left(ComboBox_Rider3AdditionalPlancodeCriteria.value, 1) = "1" Then tempSQL = tempSQL & "AND Rider3.PLN_DES_SER_CD = COVERAGE1.PLN_DES_SER_CD "
                    If left(ComboBox_Rider3AdditionalPlancodeCriteria.value, 1) = "2" Then tempSQL = tempSQL & "AND Rider3.PLN_DES_SER_CD <> COVERAGE1.PLN_DES_SER_CD "
                End If
                
            'Table Rating.  LH_SST_XTR_CRG
            If CheckBox_Rider3TableRating Then
                tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_SST_XTR_CRG Rider3_TABLE_RATING  "
                    tempSQL = tempSQL & "ON Rider3.CK_SYS_CD = Rider3_TABLE_RATING.CK_SYS_CD "
                    tempSQL = tempSQL & "AND Rider3.CK_CMP_CD = Rider3_TABLE_RATING.CK_CMP_CD "
                    tempSQL = tempSQL & "AND Rider3.TCH_POL_ID = Rider3_TABLE_RATING.TCH_POL_ID "
                    tempSQL = tempSQL & "AND Rider3.COV_PHA_NBR = Rider3_TABLE_RATING.COV_PHA_NBR "
                    tempSQL = tempSQL & "AND (Rider3_TABLE_RATING.SST_XTR_TYP_CD ='0' Or Rider3_TABLE_RATING.SST_XTR_TYP_CD ='1' Or Rider3_TABLE_RATING.SST_XTR_TYP_CD ='3') "
            End If
            
            'Flat Extra.  LH_SST_XTR_CRG
            If CheckBox_Rider3FlatExtra Then
                tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_SST_XTR_CRG Rider3_FLAT_EXTRA  "
                    tempSQL = tempSQL & "ON Rider3.CK_SYS_CD = Rider3_FLAT_EXTRA.CK_SYS_CD "
                    tempSQL = tempSQL & "AND Rider3.CK_CMP_CD = Rider3_FLAT_EXTRA.CK_CMP_CD "
                    tempSQL = tempSQL & "AND Rider3.TCH_POL_ID = Rider3_FLAT_EXTRA.TCH_POL_ID "
                    tempSQL = tempSQL & "AND Rider3.COV_PHA_NBR = Rider3_FLAT_EXTRA.COV_PHA_NBR "
                    tempSQL = tempSQL & "AND (Rider3_FLAT_EXTRA.SST_XTR_TYP_CD ='2' Or Rider3_FLAT_EXTRA.SST_XTR_TYP_CD ='4') "
            End If
            
            If ComboBox_Rider3ProductIndicator.value <> "" Then
                tempSQL = tempSQL & "INNER JOIN DB2TAB.TH_COV_PHA Rider3COVMOD "
                    tempSQL = tempSQL & "ON Rider3COVMOD.CK_SYS_CD = Rider3.CK_SYS_CD "
                    tempSQL = tempSQL & "AND Rider3COVMOD.CK_CMP_CD = Rider3.CK_CMP_CD "
                    tempSQL = tempSQL & "AND Rider3COVMOD.TCH_POL_ID = Rider3.TCH_POL_ID "
                    tempSQL = tempSQL & "AND Rider3COVMOD.COV_PHA_NBR = Rider3.COV_PHA_NBR "
                    tempSQL = tempSQL & "AND (Rider3COVMOD.AN_PRD_ID = '" & left(ComboBox_Rider3ProductIndicator, 1) & "') "
            End If
          
            If ComboBox_Rider3RateclassCode67.value <> "" Or ComboBox_Rider3SexCode67.value <> "" Then
                tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_COV_INS_RNL_RT Rider3_RENEWALS  "
                    tempSQL = tempSQL & "ON Rider3.CK_SYS_CD = Rider3_RENEWALS.CK_SYS_CD "
                    tempSQL = tempSQL & "AND Rider3.CK_CMP_CD = Rider3_RENEWALS.CK_CMP_CD "
                    tempSQL = tempSQL & "AND Rider3.TCH_POL_ID = Rider3_RENEWALS.TCH_POL_ID "
                    tempSQL = tempSQL & "AND Rider3.COV_PHA_NBR = Rider3_RENEWALS.COV_PHA_NBR "
                    'Set PRM_TYP_CD to 'C' so you only get one record from this table for this rider
                    tempSQL = tempSQL & "AND (Rider3_RENEWALS.PRM_RT_TYP_CD = 'C') "
                    If ComboBox_Rider3RateclassCode67.value <> "" Then tempSQL = tempSQL & "AND (Rider3_RENEWALS.RT_CLS_CD = '" & left(ComboBox_Rider3RateclassCode67.value, 1) & "') "
                    If ComboBox_Rider3SexCode67.value <> "" Then tempSQL = tempSQL & "AND (Rider3_RENEWALS.RT_SEX_CD = '" & left(ComboBox_Rider3SexCode67.value, 1) & "') "
            End If
        End If
    End If

    BuildRiderTable = tempSQL

End Function

Private Function BuildWithClause() As String
Dim i
Dim tempSQL As String
Dim dct As Dictionary
Set dct = New Dictionary
Dim dctWith As Dictionary
Set dctWith = New Dictionary

'Begin WITH clause
'=============================================================================================================
    
    'Coverage 1 details are needed through the rest of the query
    tempSQL = tempSQL & "COVERAGE1 AS (SELECT * FROM DB2TAB.LH_COV_PHA C1 WHERE C1.COV_PHA_NBR = 1) "
                
    dctWith.Add tempSQL, "COVERAGE1"
    tempSQL = ""
    
   
    If CheckBox_RPUOriginalAmt Then
    '68 Segment Type 9 change
    '---------------------------------------------------------------------------------------------------------
         tempSQL = tempSQL & "CHANGE_TYPE9 AS ( "
            tempSQL = tempSQL & "SELECT TMN.CK_SYS_CD, TMN.CK_CMP_CD, TMN.TCH_POL_ID "
                tempSQL = tempSQL & ",SUM(TMN.OGN_COV_UNT_QTY) TOTALORIGUNITS "
            tempSQL = tempSQL & "FROM DB2TAB.LH_COV_TMN TMN "
            
            tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_NT_COV_CHG COVCHG "
                tempSQL = tempSQL & "ON COVCHG.CK_SYS_CD = TMN.CK_SYS_CD "
                tempSQL = tempSQL & "AND COVCHG.CK_CMP_CD = TMN.CK_CMP_CD "
                tempSQL = tempSQL & "AND COVCHG.TCH_POL_ID = TMN.TCH_POL_ID "
                tempSQL = tempSQL & "AND COVCHG.COV_PHA_NBR = TMN.COV_PHA_NBR "
                tempSQL = tempSQL & "AND COVCHG.CHG_TYP_CD = '9' "
            
'            tempSQL = tempSQL & "INNER JOIN DB2TAB.TH_NT_COV_CHG THCOVCHG "
'                tempSQL = tempSQL & "ON THCOVCHG.CK_SYS_CD = COVCHG.CK_SYS_CD "
'                tempSQL = tempSQL & "AND THCOVCHG.CK_CMP_CD = COVCHG.CK_CMP_CD "
'                tempSQL = tempSQL & "AND THCOVCHG.TCH_POL_ID = COVCHG.TCH_POL_ID "
'                tempSQL = tempSQL & "AND THCOVCHG.COV_PHA_NBR = COVCHG.COV_PHA_NBR "
'                tempSQL = tempSQL & "AND COVCHG.CHG_TYP_CD = THCOVCHG.CHG_TYP_CD "
             
             tempSQL = tempSQL & "GROUP BY TMN.CK_SYS_CD, TMN.CK_CMP_CD, TMN.TCH_POL_ID "
        
        tempSQL = tempSQL & ") "
        
        dctWith.Add tempSQL, "CHANGE_TYPE9"
        tempSQL = ""
    End If
    
    

    If TextBox_LowGPEDate.value <> "" Or TextBox_HighGPEDate.value <> "" Or Me.CheckBox_GraceIndicator Or CheckBox_ShowGPEDate Then
        tempSQL = tempSQL & "GRACE_TABLE AS (SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, GRA_PER_EXP_DT, IN_GRA_PER_IND FROM DB2TAB.LH_NON_TRD_POL "
        tempSQL = tempSQL & "            UNION  SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, GRA_PER_EXP_DT, IN_GRA_PER_IND FROM DB2TAB.LH_TRD_POL) "
    
        dctWith.Add tempSQL, "GRACE_TABLE"
        tempSQL = ""
    End If
    
    If CheckBox_ISWL_GCVGTCurrCV Or CheckBox_ISWL_GCVLTCurrCV Or CheckBox_DisplayTradCVCov1 Or CheckBox_DisplayAccountValue_02_75 Then
        tempSQL = tempSQL & "INTERPOLATION_MONTHS AS ( "
            tempSQL = tempSQL & "SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID "
                tempSQL = tempSQL & ",REAL(12 - MONTHS_BETWEEN(BASPOL.NXT_MVRY_PRC_DT, BASPOL.LST_ANV_DT)) MONTHS_TO_NEXT_ANN "
                tempSQL = tempSQL & ",REAL(MONTHS_BETWEEN(BASPOL.NXT_MVRY_PRC_DT, BASPOL.LST_ANV_DT)) MONTHS_YTD "
            tempSQL = tempSQL & "FROM DB2TAB.LH_BAS_POL BASPOL "
        tempSQL = tempSQL & ") "
        
        dctWith.Add tempSQL, "INTERPOLATION_MONTHS"
        tempSQL = ""
    End If
    
    If CheckBox_MulitpleBaseCoverages Or _
        TextBox_CurrentSAGreaterThan <> "" Or _
        TextBox_CurrentSALessThan <> "" Or _
        CheckBox_ShowSpecifiedAmount Or _
        CheckBox_ULInCorridor Or _
        CheckBox_AccumulationValueGTPremiumPaid Or _
        CheckBox_CurrentSAGTOriginalSA Or _
        CheckBox_CurrentSALTOriginalSA Or _
        CheckBox_ISWL_GCVGTCurrCV Or _
        CheckBox_ISWL_GCVLTCurrCV Then
    
    'Create table which contains a record for each coverage that has the same plancode as the base (include APB Rider is indicated)
    '----------------------------------------------------------------------------------------------------------
        tempSQL = tempSQL & "ALL_BASE_COVS AS ( "
        tempSQL = tempSQL & "SELECT "
            tempSQL = tempSQL & "TEMPCOV1.CK_SYS_CD "
            tempSQL = tempSQL & ",TEMPCOV1.TCH_POL_ID "
            tempSQL = tempSQL & ",TEMPCOV1.CK_CMP_CD "
            tempSQL = tempSQL & ",TEMPCOVALL.COV_PHA_NBR "
            tempSQL = tempSQL & ",TEMPCOVALL.PLN_DES_SER_CD "
            If CheckBox_ISWL_GCVGTCurrCV Or CheckBox_ISWL_GCVLTCurrCV Then tempSQL = tempSQL & ",ROUND(TEMPCOVALL.LOW_DUR_CSV_AMT * TEMPCOVALL.COV_UNT_QTY) CV0 "
            If CheckBox_ISWL_GCVGTCurrCV Or CheckBox_ISWL_GCVLTCurrCV Then tempSQL = tempSQL & ",ROUND(TEMPCOVALL.LOW_DUR_1_CSV_AMT * TEMPCOVALL.COV_UNT_QTY) CV1 "
            If CheckBox_ISWL_GCVGTCurrCV Or CheckBox_ISWL_GCVLTCurrCV Then tempSQL = tempSQL & ",ROUND(TEMPCOVALL.LOW_DUR_2_CSV_AMT * TEMPCOVALL.COV_UNT_QTY) CV2 "
            
            tempSQL = tempSQL & ",ROUND(REAL(TEMPCOVALL.COV_UNT_QTY) * REAL(TEMPCOVALL.COV_VPU_AMT),2) SPECAMT "
            tempSQL = tempSQL & ",ROUND(REAL(TEMPCOVALL.OGN_SPC_UNT_QTY) * REAL(TEMPCOVALL.COV_VPU_AMT),2) ORIGSPECAMT "

        tempSQL = tempSQL & "FROM "
            tempSQL = tempSQL & "DB2TAB.LH_COV_PHA TEMPCOV1  "
                tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_COV_PHA TEMPCOVALL  "
                    tempSQL = tempSQL & "ON TEMPCOV1.COV_PHA_NBR = 1 "
                    tempSQL = tempSQL & "AND TEMPCOV1.CK_SYS_CD = TEMPCOVALL.CK_SYS_CD "
                    tempSQL = tempSQL & "AND TEMPCOV1.CK_CMP_CD = TEMPCOVALL.CK_CMP_CD "
                    tempSQL = tempSQL & "AND TEMPCOV1.TCH_POL_ID = TEMPCOVALL.TCH_POL_ID "
                    
                    
                    If CheckBox_IncludeAPBasBaseCoverage Then
                        tempSQL = tempSQL & "AND (TEMPCOVALL.PLN_DES_SER_CD = TEMPCOV1.PLN_DES_SER_CD OR TEMPCOVALL.PLN_DES_SER_CD = '1U144A00') "
                    Else
                        tempSQL = tempSQL & "AND (TEMPCOVALL.PLN_DES_SER_CD = TEMPCOV1.PLN_DES_SER_CD) "
                    End If
  
  
        tempSQL = tempSQL & ") "

        dctWith.Add tempSQL, "ALL_BASE_COVS"
        tempSQL = ""


    'Sum total current specified amount units and total original specifed amount units
    '----------------------------------------------------------------------------------------------------------
        tempSQL = tempSQL & "COVSUMMARY AS ( "
            tempSQL = tempSQL & "SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID "
                tempSQL = tempSQL & ",SUM(ALL_BASE_COVS.SPECAMT) TOTAL_SA "
                tempSQL = tempSQL & ",SUM(ALL_BASE_COVS.ORIGSPECAMT) TOTAL_ORIGINAL_SA "
                tempSQL = tempSQL & ",COUNT(ALL_BASE_COVS.COV_PHA_NBR) BASECOVCOUNT "
                If CheckBox_ISWL_GCVGTCurrCV Or CheckBox_ISWL_GCVLTCurrCV Then tempSQL = tempSQL & ",SUM(ALL_BASE_COVS.CV0) TOTAL_CV0 "
                If CheckBox_ISWL_GCVGTCurrCV Or CheckBox_ISWL_GCVLTCurrCV Then tempSQL = tempSQL & ",SUM(ALL_BASE_COVS.CV1) TOTAL_CV1 "
                If CheckBox_ISWL_GCVGTCurrCV Or CheckBox_ISWL_GCVLTCurrCV Then tempSQL = tempSQL & ",SUM(ALL_BASE_COVS.CV2) TOTAL_CV2 "
                
            tempSQL = tempSQL & "FROM ALL_BASE_COVS "
            tempSQL = tempSQL & "GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID "
            tempSQL = tempSQL & ") "

        dctWith.Add tempSQL, "COVSUMMARY"
        tempSQL = ""


       
        If CheckBox_ISWL_GCVGTCurrCV Or CheckBox_ISWL_GCVLTCurrCV Then
            tempSQL = tempSQL & "ISWL_INTERPOLATED_GCV AS ( "
                tempSQL = tempSQL & "SELECT COVSUMMARY.CK_SYS_CD, COVSUMMARY.CK_CMP_CD, COVSUMMARY.TCH_POL_ID "
                tempSQL = tempSQL & ",ROUND((INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN * COVSUMMARY.TOTAL_CV2 + INTERPOLATION_MONTHS.MONTHS_YTD * COVSUMMARY.TOTAL_CV1)/12, 2) ISWL_GCV "
                tempSQL = tempSQL & "FROM COVSUMMARY "
                    tempSQL = tempSQL & "INNER JOIN INTERPOLATION_MONTHS "
                        tempSQL = tempSQL & "ON COVSUMMARY.CK_SYS_CD = INTERPOLATION_MONTHS.CK_SYS_CD "
                        tempSQL = tempSQL & "AND COVSUMMARY.CK_CMP_CD = INTERPOLATION_MONTHS.CK_CMP_CD "
                        tempSQL = tempSQL & "AND COVSUMMARY.TCH_POL_ID = INTERPOLATION_MONTHS.TCH_POL_ID "
            tempSQL = tempSQL & ") "
            
            dctWith.Add tempSQL, "ISWL_INTERPOLATED_GCV"
            tempSQL = ""
        End If
        
        
    End If


    'Billing modes.  Creating BILLMODE_POOL table would be unecessary except if you want to include the special modes (BiWeekly and SemiMonthly)
    '----------------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_SpecifyBillingModes Or CheckBox_ShowBillingMode Then
        'Possible modes are "Monthly", "Quarterly", "Semiannual", "Annual", "BiWeekly", "SemiMonthly", "10thly"
        Dim dctBillMode As Dictionary
        Dim dctNonStandardBillMode As Dictionary
        Set dctBillMode = New Dictionary
        Set dctNonStandardBillMode = New Dictionary
     
        'Translate listbox entries to Cyberlife codes
        For i = 0 To Me.ListBox_BillMode.ListCount - 1
            If ListBox_BillMode.Selected(i) = True Then
                Select Case ListBox_BillMode.List(i)
                    Case "Weekly": dctNonStandardBillMode.Add "DB2TAB.LH_BAS_POL.NSD_MD_CD = '1'", ""
                    Case "9thly": dctNonStandardBillMode.Add "DB2TAB.LH_BAS_POL.NSD_MD_CD = '9'", ""
                    Case "10thly": dctNonStandardBillMode.Add "DB2TAB.LH_BAS_POL.NSD_MD_CD = 'A'", ""
                    Case "BiWeekly": dctNonStandardBillMode.Add "DB2TAB.LH_BAS_POL.NSD_MD_CD = '2'", ""
                    Case "SemiMonthly": dctNonStandardBillMode.Add "DB2TAB.LH_BAS_POL.NSD_MD_CD = 'S'", ""
                    Case "Monthly": dctBillMode.Add "DB2TAB.LH_BAS_POL.PMT_FQY_PER = 1", ""
                    Case "Quarterly": dctBillMode.Add "DB2TAB.LH_BAS_POL.PMT_FQY_PER = 3", ""
                    Case "Semiannual": dctBillMode.Add "DB2TAB.LH_BAS_POL.PMT_FQY_PER = 6", ""
                    Case "Annual": dctBillMode.Add "DB2TAB.LH_BAS_POL.PMT_FQY_PER = 12", ""
                End Select
            End If
        Next i
     
        If dctNonStandardBillMode.Count > 0 Or dctBillMode.Count > 0 Or CheckBox_ShowBillingMode Then
            tempSQL = tempSQL & "BILLMODE_POOL AS ("
                tempSQL = tempSQL & "SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, PMT_FQY_PER, NSD_MD_CD FROM DB2TAB.LH_BAS_POL   "
                tempSQL = tempSQL & "WHERE  "
                
                If dctNonStandardBillMode.Count > 0 Then
                    'If non standard mode is used, Cyberlife sets the PMT_FQY_PER = 1
                    tempSQL = tempSQL & "(DB2TAB.LH_BAS_POL.PMT_FQY_PER = 1 "
                    tempSQL = tempSQL & "AND (" & Join(dctNonStandardBillMode.Keys, " OR ") & ") "
                    tempSQL = tempSQL & ") "
                End If
                If dctNonStandardBillMode.Count > 0 And dctBillMode.Count > 0 Then tempSQL = tempSQL & " OR "
                If dctBillMode.Count > 0 Then tempSQL = tempSQL & " (" & Join(dctBillMode.Keys, " OR ") & ") "
            tempSQL = tempSQL & ") "
        End If
        dctWith.Add tempSQL, "BILLMODE_POOL"
        tempSQL = ""
    End If



    'Fund Allocations.
    '----------------------------------------------------------------------------------------------------------------------------------------------
    'This temp table has a list of policies that have allocations to the all the requested fund IDs.
    'This is used only for IUL policies.
    If CheckBox_PremiumAllocationFunds Then
        If SelectedCount(ListBox_PremiumAllocationFunds) > 0 Then
            tempSQL = tempSQL & "ALLOCATION_FUNDS AS ( "
            Dim FundCount As Integer
            For i = 0 To ListBox_PremiumAllocationFunds.ListCount - 1
                If ListBox_PremiumAllocationFunds.Selected(i) = True Then
                    FundCount = FundCount + 1
                    If FundCount > 1 Then tempSQL = tempSQL & "INTERSECT "
                    tempSQL = tempSQL & "SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID FROM DB2TAB.LH_FND_ALC  WHERE FND_ID_CD = '" & left(ListBox_PremiumAllocationFunds.List(i), 2) & "' AND FND_ALC_PCT > 0 AND FND_ALC_TYP_CD = 'P' "
                End If
            Next i
            tempSQL = tempSQL & ") "
            dctWith.Add tempSQL, "ALLOCATION_FUNDS"
            tempSQL = ""
        End If
    End If

'    'Fund Values (65 segment) LH_POL_FND_VAL_TOT
'    '----------------------------------------------------------------------------------------------------------------------------------------------
    If TextBox_FundIDs.value <> "" Then
        tempSQL = tempSQL & "FUND_VALUES AS ( "
            tempSQL = tempSQL & "SELECT "
                tempSQL = tempSQL & " CK_CMP_CD "
                tempSQL = tempSQL & ", CK_SYS_CD "
                tempSQL = tempSQL & ", TCH_POL_ID "
                tempSQL = tempSQL & ", FND_ID_CD "
                tempSQL = tempSQL & ", Sum(CSV_AMT) FUNDAMT "
            tempSQL = tempSQL & "FROM DB2TAB.LH_POL_FND_VAL_TOT "
            tempSQL = tempSQL & "WHERE MVRY_DT = '9999-12-31' "
            tempSQL = tempSQL & "GROUP BY CK_CMP_CD, CK_SYS_CD, TCH_POL_ID, FND_ID_CD "
        tempSQL = tempSQL & ") "
        dctWith.Add tempSQL, "FUND_VALUES"
        tempSQL = ""
    End If



    If Me.CheckBox_HasChangeSegment Then
        tempSQL = tempSQL & "CHANGE_SEGMENT AS ( "
        tempSQL = tempSQL & "SELECT "
            tempSQL = tempSQL & " CK_SYS_CD, "
            tempSQL = tempSQL & " CK_CMP_CD, "
            tempSQL = tempSQL & " TCH_POL_ID "
                tempSQL = tempSQL & " FROM DB2TAB.LH_COV_TMN "
        
            tempSQL = tempSQL & " UNION "

        tempSQL = tempSQL & "SELECT "
            tempSQL = tempSQL & " CK_SYS_CD, "
            tempSQL = tempSQL & " CK_CMP_CD, "
            tempSQL = tempSQL & " TCH_POL_ID "
                tempSQL = tempSQL & " FROM DB2TAB.LH_NT_COV_CHG "
        
            tempSQL = tempSQL & " UNION "

        tempSQL = tempSQL & "SELECT "
            tempSQL = tempSQL & " CK_SYS_CD, "
            tempSQL = tempSQL & " CK_CMP_CD, "
            tempSQL = tempSQL & " TCH_POL_ID "
                tempSQL = tempSQL & " FROM DB2TAB.LH_NT_COV_CHG_SCH "
        
            tempSQL = tempSQL & " UNION "

        tempSQL = tempSQL & "SELECT "
            tempSQL = tempSQL & " CK_SYS_CD, "
            tempSQL = tempSQL & " CK_CMP_CD, "
            tempSQL = tempSQL & " TCH_POL_ID "
                tempSQL = tempSQL & " FROM DB2TAB.LH_SPM_BNF_CHG_SCH "
    
        tempSQL = tempSQL & " ) "
        
        dctWith.Add tempSQL, "CHANGE_SEGMENT"
        tempSQL = ""
    End If
    

    'Loan tables - this is a union of the Trad loan and UL loan tables, so that there is one place to look to see if a policy has a loan
    '----------------------------------------------------------------------------------------------------------------------------------------------
    'TRAD loans are in the LH_CSH_VAL_LOAN table and ADV Product loans are in the LH_FND_VAL_LOAN table
    'Create temporary table (ALL_LOANS) that has both TRAD loans and ADV loans
    'A UNION query must have the same fields selected (so you can't just use * since these tables have slighly different fields

    blnHas77Segment = CheckBox_HasLoan Or CheckBox_HasPreferredLoan Or TextBox_LoanPrincipleGreaterThan <> "" Or TextBox_LoanPrincipleLessThan <> "" Or TextBox_LoanAccruedIntGreaterThan <> "" Or TextBox_LoanAccruedIntLessThan <> ""
        
    If CheckBox_ShowPolicyDebt Or blnHas77Segment Then
    
        tempSQL = tempSQL & "ALL_LOANS AS ( "
            tempSQL = tempSQL & "SELECT "
                tempSQL = tempSQL & " CK_SYS_CD "
                tempSQL = tempSQL & ", CK_CMP_CD "
                tempSQL = tempSQL & ", TCH_POL_ID "
                tempSQL = tempSQL & ", PRF_LN_IND "
                tempSQL = tempSQL & ", LN_PRI_AMT "
                tempSQL = tempSQL & ",(CASE LN_ITS_AMT_TYP_CD "
                    tempSQL = tempSQL & " WHEN '2' THEN POL_LN_ITS_AMT "
                    tempSQL = tempSQL & " ELSE 0 "
                    tempSQL = tempSQL & " END) LN_INT "
                tempSQL = tempSQL & " "
                
            tempSQL = tempSQL & " FROM DB2TAB.LH_FND_VAL_LOAN "
            tempSQL = tempSQL & " WHERE MVRY_DT = '9999-12-31' "
            tempSQL = tempSQL & " UNION "
            
            tempSQL = tempSQL & " SELECT "
                tempSQL = tempSQL & " CK_SYS_CD "
                tempSQL = tempSQL & ", CK_CMP_CD "
                tempSQL = tempSQL & ", TCH_POL_ID "
                tempSQL = tempSQL & ", PRF_LN_IND "
                tempSQL = tempSQL & ", LN_PRI_AMT "
                tempSQL = tempSQL & ",(CASE LN_ITS_AMT_TYP_CD "
                    tempSQL = tempSQL & " WHEN '2' THEN POL_LN_ITS_AMT "
                    tempSQL = tempSQL & " ELSE 0 "
                    tempSQL = tempSQL & " END) LN_INT "
                tempSQL = tempSQL & " "
                
            tempSQL = tempSQL & " FROM DB2TAB.LH_CSH_VAL_LOAN "
            tempSQL = tempSQL & " WHERE MVRY_DT = '9999-12-31' "
        tempSQL = tempSQL & " ) "
        dctWith.Add tempSQL, "ALL_LOANS"
        tempSQL = ""
    
    
        'POLICYDEBT will sum up all the outstanding loans from ALL_LOANS
        tempSQL = tempSQL & "POLICYDEBT AS (SELECT "
                    tempSQL = tempSQL & "CK_SYS_CD, "
                    tempSQL = tempSQL & "CK_CMP_CD, "
                    tempSQL = tempSQL & "TCH_POL_ID, "
                    tempSQL = tempSQL & "SUM(ALL_LOANS.LN_PRI_AMT) LOAN_PRINCIPLE, "
                    tempSQL = tempSQL & "SUM(ALL_LOANS.LN_INT) LOAN_ACCRUED "
        tempSQL = tempSQL & "FROM ALL_LOANS "
        tempSQL = tempSQL & "GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID "
        tempSQL = tempSQL & ") "
        
        dctWith.Add tempSQL, "POLICYDEBT"
        tempSQL = ""
    End If
    


    'Table with UL values for last monthliversary
    '----------------------------------------------------------------------------------------------------------------------------------------------
    If Me.CheckBox_DisplayAccountValue_02_75 Or _
        Me.CheckBox_ULInCorridor Or _
        CheckBox_AccumulationValueGTPremiumPaid Or _
        CheckBox_ISWL_GCVGTCurrCV Or _
        CheckBox_ISWL_GCVLTCurrCV Or _
        CheckBox_ShowAccumulationValue Or _
        CheckBox_ShowPremiumPTD Or _
        TextBox_AVGreaterThan <> "" Or _
        TextBox_AVLessThan <> "" Then
        
        'LASTMV - returns the most recent monthly deduction date for each policy
        tempSQL = tempSQL & "LASTMV AS ( "
        tempSQL = tempSQL & "SELECT DISTINCT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, MAX(MVRY_DT) LASTMVDT "

        tempSQL = tempSQL & "FROM DB2TAB.LH_POL_MVRY_VAL "
        tempSQL = tempSQL & "GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID "
        tempSQL = tempSQL & ") "

        dctWith.Add tempSQL, "LASTMV"
        tempSQL = ""
    
        'MVVAL - this table has the account value,  charges and NAR from the last monthly deduction date (using the date for LASTMV)
        tempSQL = tempSQL & "MVVAL AS ( "
            tempSQL = tempSQL & "SELECT "
                tempSQL = tempSQL & " MV.CK_SYS_CD "
                tempSQL = tempSQL & ",MV.CK_CMP_CD "
                tempSQL = tempSQL & ",MV.TCH_POL_ID  "
                tempSQL = tempSQL & ",MV.EXP_CRG_AMT "
                tempSQL = tempSQL & ",IFNULL(MV.OTH_PRM_AMT,0) OTHERPREM "
                tempSQL = tempSQL & ",MV.CINS_AMT "
                tempSQL = tempSQL & ",MV.CSV_AMT "
                tempSQL = tempSQL & ",LASTMV.LASTMVDT "
                tempSQL = tempSQL & ",ADVPROD.POL_GUA_ITS_RT  "
                tempSQL = tempSQL & ",REAL(ADVPROD.CDR_PCT)/100 CorrPct "
                tempSQL = tempSQL & ",ADVPROD.NAR_AMT "
                tempSQL = tempSQL & ",ADVPROD.DTH_BNF_PLN_OPT_CD "
                tempSQL = tempSQL & ",REAL(MV.CINS_AMT) + REAL(IFNULL(MV.OTH_PRM_AMT,0)) + REAL(MV.EXP_CRG_AMT) LASTMD "
                tempSQL = tempSQL & ",ROUND(REAL(MV.CSV_AMT) * REAL(ADVPROD.CDR_PCT)/100,2) DB "
                tempSQL = tempSQL & ",(TEMPPOLTOTALS.TOT_REG_PRM_AMT + TEMPPOLTOTALS.TOT_ADD_PRM_AMT) TotalPrem "
                
                tempSQL = tempSQL & ",(CASE ADVPROD.DTH_BNF_PLN_OPT_CD "
                    tempSQL = tempSQL & "WHEN '1' THEN 0 "
                    tempSQL = tempSQL & "WHEN '2' THEN REAL(MV.CSV_AMT) "
                    tempSQL = tempSQL & "WHEN '3' THEN (TEMPPOLTOTALS.TOT_REG_PRM_AMT + TEMPPOLTOTALS.TOT_ADD_PRM_AMT) "
                    tempSQL = tempSQL & "ELSE 0 "
                tempSQL = tempSQL & "End) OPTDB "
                
            tempSQL = tempSQL & "FROM DB2TAB.LH_POL_MVRY_VAL MV  "
                tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_NON_TRD_POL ADVPROD "
                    tempSQL = tempSQL & " ON (MV.TCH_POL_ID = ADVPROD.TCH_POL_ID) "
                    tempSQL = tempSQL & " AND (MV.CK_CMP_CD = ADVPROD.CK_CMP_CD) "
                    tempSQL = tempSQL & " AND (MV.CK_SYS_CD = ADVPROD.CK_SYS_CD) "

                tempSQL = tempSQL & "INNER JOIN LASTMV "
                    tempSQL = tempSQL & " ON (MV.TCH_POL_ID = LASTMV.TCH_POL_ID) "
                    tempSQL = tempSQL & " AND (MV.CK_CMP_CD = LASTMV.CK_CMP_CD) "
                    tempSQL = tempSQL & " AND (MV.CK_SYS_CD = LASTMV.CK_SYS_CD) "
                    tempSQL = tempSQL & " AND (MV.MVRY_DT = LASTMV.LASTMVDT) "

                tempSQL = tempSQL & "INNER JOIN DB2TAB.LH_POL_TOTALS TEMPPOLTOTALS "
                    tempSQL = tempSQL & " ON (MV.TCH_POL_ID = TEMPPOLTOTALS.TCH_POL_ID) "
                    tempSQL = tempSQL & " AND (MV.CK_CMP_CD = TEMPPOLTOTALS.CK_CMP_CD) "
                    tempSQL = tempSQL & " AND (MV.CK_SYS_CD = TEMPPOLTOTALS.CK_SYS_CD) "
 

        tempSQL = tempSQL & ") "
 
        dctWith.Add tempSQL, "MVVAL"
        tempSQL = ""
    End If


    'Guideline Level Premium
    '----------------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_GLPIsNegative Or CheckBox_ShowGLP Then
        tempSQL = tempSQL & "GLP AS ( "
            tempSQL = tempSQL & "SELECT DISTINCT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, TEMPGLP.GDL_PRM_AMT GLP_VALUE "
                tempSQL = tempSQL & "FROM DB2TAB.LH_COV_INS_GDL_PRM TEMPGLP "
                    tempSQL = tempSQL & " WHERE (TEMPGLP.COV_PHA_NBR = 1) "
                    tempSQL = tempSQL & " AND (TEMPGLP.PRM_RT_TYP_CD = 'A') "
        tempSQL = tempSQL & ") "
    
        dctWith.Add tempSQL, "GLP"
        tempSQL = ""
    End If


    'Guideline Single Premium
    '----------------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_ShowGSP Then
        tempSQL = tempSQL & "GSP AS ( "
            tempSQL = tempSQL & "SELECT DISTINCT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, TEMPGSP.GDL_PRM_AMT GSP_VALUE "
                tempSQL = tempSQL & "FROM DB2TAB.LH_COV_INS_GDL_PRM TEMPGSP "
                    tempSQL = tempSQL & " WHERE (TEMPGSP.COV_PHA_NBR = 1) "
                    tempSQL = tempSQL & " AND (TEMPGSP.PRM_RT_TYP_CD = 'S') "
        tempSQL = tempSQL & ") "
    
        dctWith.Add tempSQL, "GSP"
        tempSQL = ""
    End If



    'TRAD Cash value based on CV Rate or NSP Rate
    '----------------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_DisplayAccountValue_02_75 Then
        tempSQL = tempSQL & "TRAD_CV AS ( "
            tempSQL = tempSQL & "SELECT "
                tempSQL = tempSQL & " COVERAGE1.CK_SYS_CD "
                tempSQL = tempSQL & ", COVERAGE1.CK_CMP_CD "
                tempSQL = tempSQL & ", COVERAGE1.TCH_POL_ID "
      
                tempSQL = tempSQL & ", (CASE WHEN COVERAGE1.LOW_DUR_1_CSV_AMT IS NULL THEN 0 ELSE COVERAGE1.LOW_DUR_1_CSV_AMT END)*COVERAGE1.COV_UNT_QTY/12*INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN + (CASE WHEN COVERAGE1.LOW_DUR_2_CSV_AMT IS NULL THEN 0 ELSE COVERAGE1.LOW_DUR_2_CSV_AMT END)*COVERAGE1.COV_UNT_QTY/12*INTERPOLATION_MONTHS.MONTHS_YTD INTERP_CV "
                tempSQL = tempSQL & ", (CASE WHEN COVERAGE1.LOW_DUR_NSP_AMT IS NULL THEN 0 ELSE COVERAGE1.LOW_DUR_NSP_AMT END)*COVERAGE1.COV_UNT_QTY/12*INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN + (CASE WHEN COVERAGE1.LOW_DUR_1_NSP_AMT IS NULL THEN 0 ELSE COVERAGE1.LOW_DUR_1_NSP_AMT END)*COVERAGE1.COV_UNT_QTY/12*INTERPOLATION_MONTHS.MONTHS_YTD INTERP_NSP "
                
                
            tempSQL = tempSQL & " FROM COVERAGE1 "
                tempSQL = tempSQL & "INNER JOIN INTERPOLATION_MONTHS "
                    tempSQL = tempSQL & "ON COVERAGE1.CK_SYS_CD = INTERPOLATION_MONTHS.CK_SYS_CD "
                    tempSQL = tempSQL & "AND COVERAGE1.CK_CMP_CD = INTERPOLATION_MONTHS.CK_CMP_CD "
                    tempSQL = tempSQL & "AND COVERAGE1.TCH_POL_ID = INTERPOLATION_MONTHS.TCH_POL_ID "
                tempSQL = tempSQL & ") "
        dctWith.Add tempSQL, "TRAD_CV"
        tempSQL = ""
    End If


'    'Max year for Yr totals
'    '----------------------------------------------------------------------------------------------------------------------------------------------
'    'If CheckBox_ShowPremiumPaidYTD Then
        tempSQL = tempSQL & "LH_POL_YR_TOT_withMaxDuration AS ( "
             tempSQL = tempSQL & "SELECT CK_SYS_CD, CK_CMP_CD, TCH_POL_ID, MAX(POL_YR_DUR) MAX_DURATION "
             tempSQL = tempSQL & "FROM DB2TAB.LH_POL_YR_TOT "
             tempSQL = tempSQL & "GROUP BY CK_SYS_CD, CK_CMP_CD, TCH_POL_ID "
            tempSQL = tempSQL & " ) "

            dctWith.Add tempSQL, "LH_POL_YR_TOT_withMaxDuration"
            tempSQL = ""


'        tempSQL = tempSQL & "LH_POL_YR_TOT_at_MaxDuration AS (SELECT * FROM LH_POL_YR_TOT_withMaxDuration) "
'            dctWith.Add tempSQL, "LH_POL_YR_TOT_at_MaxDuration"
'            tempSQL = ""

        tempSQL = tempSQL & "LH_POL_YR_TOT_at_MaxDuration AS ( "
             'tempSQL = tempSQL & "SELECT YEARTOTS.CK_SYS_CD, YEARTOTS.CK_CMP_CD, YEARTOTS.TCH_POL_ID "
             tempSQL = tempSQL & "SELECT YEARTOTS.* "
             tempSQL = tempSQL & "FROM DB2TAB.LH_POL_YR_TOT YEARTOTS "
             tempSQL = tempSQL & "INNER JOIN LH_POL_YR_TOT_withMaxDuration "
             tempSQL = tempSQL & "   ON (YEARTOTS.CK_SYS_CD = LH_POL_YR_TOT_withMaxDuration.CK_SYS_CD) "
             tempSQL = tempSQL & "   AND (YEARTOTS.CK_CMP_CD = LH_POL_YR_TOT_withMaxDuration.CK_CMP_CD) "
             tempSQL = tempSQL & "   AND (YEARTOTS.TCH_POL_ID = LH_POL_YR_TOT_withMaxDuration.TCH_POL_ID) "
             tempSQL = tempSQL & "WHERE POL_YR_DUR=LH_POL_YR_TOT_withMaxDuration.MAX_DURATION "
            tempSQL = tempSQL & " ) "

            dctWith.Add tempSQL, "LH_POL_YR_TOT_at_MaxDuration"
            tempSQL = ""
    
    
    
    If TextBox_TerminationLowDate <> "" Or TextBox_TerminationHighDate <> "" Or CheckBox_ShowTerminationDate_from_69 Then
      tempSQL = tempSQL & "PRE_TERMINATION_DATES AS ( "
        tempSQL = tempSQL & "SELECT "
        tempSQL = tempSQL & "   FH.CK_CMP_CD, "
        tempSQL = tempSQL & "   FH.TCH_POL_ID, "
        tempSQL = tempSQL & "   MAX(FH.ENTRY_DT) AS TERM_ENTRY_DT "
        tempSQL = tempSQL & "FROM DB2TAB.FH_FIXED AS FH "
        tempSQL = tempSQL & "WHERE "
        tempSQL = tempSQL & "   FH.TRANS IN ('SI', 'SF', 'TD', 'TM', 'TN', 'TL', 'TO') "
        tempSQL = tempSQL & "   AND FH.FCB0_REV_IND = '0' "
        tempSQL = tempSQL & "   AND FH.FCB2_REV_APPL_IND = '0' "
        tempSQL = tempSQL & "GROUP BY "
        tempSQL = tempSQL & "   FH.CK_CMP_CD, "
        tempSQL = tempSQL & "   FH.TCH_POL_ID "
      tempSQL = tempSQL & " ) "
      
      dctWith.Add tempSQL, "PRE_TERMINATION_DATES"
      tempSQL = ""
    End If
        
    If TextBox_TerminationLowDate <> "" Or TextBox_TerminationHighDate <> "" Or CheckBox_ShowTerminationDate_from_69 Then
      tempSQL = tempSQL & "TERMINATION_DATES AS ( "
        tempSQL = tempSQL & "SELECT * FROM PRE_TERMINATION_DATES WHERE 1=1 "
        If TextBox_TerminationLowDate <> "" Then tempSQL = tempSQL & " AND PRE_TERMINATION_DATES.TERM_ENTRY_DT >= '" & Format(TextBox_TerminationLowDate, "yyyy-mm-dd") & "' "
        If TextBox_TerminationHighDate <> "" Then tempSQL = tempSQL & " AND PRE_TERMINATION_DATES.TERM_ENTRY_DT <= '" & Format(TextBox_TerminationHighDate, "yyyy-mm-dd") & "' "
        tempSQL = tempSQL & " ) "
      dctWith.Add tempSQL, "TERMINATION_DATES"
      tempSQL = ""
    End If
    




'    If CheckBox_ShowInsured1Info Then
'        tempSQL = tempSQL & "INSURED1_INFO AS ( "
'            tempSQL = "SELECT T1.PRS_CD, T1.CK_CMP_CD CK_CMP_CD, T1.CK_SYS_CD CK_SYS_CD, T1.TCH_POL_ID TCH_POL_ID,  "
'            tempSQL = "T1.BIR_DT BIRTHDT, T2.CK_FST_NM FNAME, T2.MDL_INT_NM MINIT, T2.CK_LST_NM LNAME, T2.TAXPAYER_NBR TAXNBR, T2.BIR_PLC_CD, T2.DT_OF_DTH "
'            tempSQL = tempSQL & "FROM DB2TAB_LH_CTT_CLIENT T1 "
'            tempSQL = tempSQL & "INNER JOIN DB2TAB_VH_POL_HAS_LOC_CLT T2 "
'                tempSQL = tempSQL & "ON T1.PRS_SEQ_NBR = T2.PRS_SEQ_NBR "
'                tempSQL = tempSQL & "AND T1.PRS_CD = T2.PRS_CD "
'                tempSQL = tempSQL & "AND T1.TCH_POL_ID = T2.TCH_POL_ID "
'                tempSQL = tempSQL & "AND T1.CK_SYS_CD = T2.CK_SYS_CD "
'                tempSQL = tempSQL & "AND T1.CK_CMP_CD = T2.CK_CMP_CD "
'            tempSQL = tempSQL & "WHERE T1.PRS_CD='00' "
'        tempSQL = tempSQL & ") "
'
'        dctWith.Add tempSQL, "INSURED1_INFO"
'        tempSQL = ""
'    End If

If dctWith.Count > 0 Then
  tempSQL = "WITH " & Join(dctWith.Keys, ",") & " "
End If

BuildWithClause = tempSQL
    
    'End If
    

'        'FOR DISPLAY ONLY - All Coverages
'        '-----------------------------------------------------------------------------------------------------------------------------------------
'        tempSQL = tempSQL & "DISPLAY_COVERAGES AS (SELECT "
'            tempSQL = tempSQL & "DISPLAY_COVS.CK_SYS_CD "
'            tempSQL = tempSQL & ",DISPLAY_COVS.CK_CMP_CD "
'            tempSQL = tempSQL & ",DISPLAY_COVS.TCH_POL_ID "
'            tempSQL = tempSQL & ",DISPLAY_COVS.COV_PHA_NBR "
'            tempSQL = tempSQL & ",DISPLAY_COVS.PLN_DES_SER_CD "
'            tempSQL = tempSQL & ",DISPLAY_COVS.POL_FRM_NBR "
'            tempSQL = tempSQL & ",DISPLAY_COVS.ISSUE_DT "
'            tempSQL = tempSQL & ",DISPLAY_COVS.INS_ISS_AGE "
'            tempSQL = tempSQL & ",TRUNCATE(MONTHS_BETWEEN('" & Format(Now(), "yyyy-mm-dd") & "',DISPLAY_COVS.ISSUE_DT)/12,0) + 1 PolicyYear "
'            tempSQL = tempSQL & ",TRUNCATE(MONTHS_BETWEEN('" & Format(Now(), "yyyy-mm-dd") & "',DISPLAY_COVS.ISSUE_DT)/12,0) + DISPLAY_COVS.INS_ISS_AGE CurrentAge "
'            tempSQL = tempSQL & ",DISPLAY_COVS_RENEWALS.RT_CLS_CD  "
'            tempSQL = tempSQL & ",DISPLAY_COVS_RENEWALS.RT_SEX_CD "
'            tempSQL = tempSQL & ",DISPLAY_TABLE_RATINGS.SST_XTR_RT_TBL_CD "
'            tempSQL = tempSQL & ",DISPLAY_FLAT_EXTRAS.SST_XTR_UNT_AMT "
'
'            tempSQL = tempSQL & "FROM DB2TAB.LH_COV_PHA DISPLAY_COVS "
'
'                'Table Rating.  LH_SST_XTR_CRG
'                tempSQL = tempSQL & "LEFT OUTER JOIN DB2TAB.LH_SST_XTR_CRG DISPLAY_TABLE_RATINGS  "
'                    tempSQL = tempSQL & "ON DISPLAY_COVS.CK_SYS_CD = DISPLAY_TABLE_RATINGS.CK_SYS_CD "
'                    tempSQL = tempSQL & "AND DISPLAY_COVS.CK_CMP_CD = DISPLAY_TABLE_RATINGS.CK_CMP_CD "
'                    tempSQL = tempSQL & "AND DISPLAY_COVS.TCH_POL_ID = DISPLAY_TABLE_RATINGS.TCH_POL_ID "
'                    tempSQL = tempSQL & "AND DISPLAY_COVS.COV_PHA_NBR = DISPLAY_TABLE_RATINGS.COV_PHA_NBR "
'                    tempSQL = tempSQL & "AND (DISPLAY_TABLE_RATINGS.SST_XTR_TYP_CD ='0' Or DISPLAY_TABLE_RATINGS.SST_XTR_TYP_CD ='1' Or DISPLAY_TABLE_RATINGS.SST_XTR_TYP_CD ='3') "
'
'                'Flat Extra.  LH_SST_XTR_CRG
'                tempSQL = tempSQL & "LEFT OUTER JOIN DB2TAB.LH_SST_XTR_CRG DISPLAY_FLAT_EXTRAS  "
'                    tempSQL = tempSQL & "ON DISPLAY_COVS.CK_SYS_CD = DISPLAY_FLAT_EXTRAS.CK_SYS_CD "
'                    tempSQL = tempSQL & "AND DISPLAY_COVS.CK_CMP_CD = DISPLAY_FLAT_EXTRAS.CK_CMP_CD "
'                    tempSQL = tempSQL & "AND DISPLAY_COVS.TCH_POL_ID = DISPLAY_FLAT_EXTRAS.TCH_POL_ID "
'                    tempSQL = tempSQL & "AND DISPLAY_COVS.COV_PHA_NBR = DISPLAY_FLAT_EXTRAS.COV_PHA_NBR "
'                    tempSQL = tempSQL & "AND (DISPLAY_FLAT_EXTRAS.SST_XTR_TYP_CD ='2' Or DISPLAY_FLAT_EXTRAS.SST_XTR_TYP_CD ='4') "
'
'                'Renwal Rates (used to get rateclass).  If rateclasses are specifed, use inner join to return only those
'                'records with the specified rateclass.  If rateclass is not specified, use outer join simply to display rateclass for results
'                tempSQL = tempSQL & " LEFT OUTER JOIN DB2TAB.LH_COV_INS_RNL_RT DISPLAY_COVS_RENEWALS  "
'                tempSQL = tempSQL & "ON DISPLAY_COVS.CK_SYS_CD = DISPLAY_COVS_RENEWALS.CK_SYS_CD "
'                    tempSQL = tempSQL & "AND DISPLAY_COVS.CK_CMP_CD = DISPLAY_COVS_RENEWALS.CK_CMP_CD "
'                    tempSQL = tempSQL & "AND DISPLAY_COVS.TCH_POL_ID = DISPLAY_COVS_RENEWALS.TCH_POL_ID "
'                    tempSQL = tempSQL & "AND DISPLAY_COVS.COV_PHA_NBR = DISPLAY_COVS_RENEWALS.COV_PHA_NBR "
'                    'Set PRM_TYP_CD to 'C' so you only get one record from this table per cov phase
'                    tempSQL = tempSQL & "AND DISPLAY_COVS_RENEWALS.PRM_RT_TYP_CD = 'C' "
'
'        tempSQL = tempSQL & ") "
'
'        dctWith.Add tempSQL, "DISPLAY"
'        tempSQL = ""




'Build WITH clause


End Function

Private Function BlnQueryNewBusinessTable() As Boolean
Dim tempBln As Boolean
tempBln = False
If TextBox_LowLastChangeDate.value <> "" Or TextBox_HighLastChangeDate.value <> "" Then
    tempBln = True
End If
BlnQueryNewBusinessTable = tempBln
End Function


Private Function BuildSQLString()
Dim sqlstring As String
Dim tempSQL As String
Dim dct As Dictionary   'dct is used many times to facilitate building query string.  Use in particular with multi-select listboxes
Set dct = New Dictionary
Dim i As Integer
Dim AttainedAgeCalc As String
Dim DurationCalc As String

DurationCalc = "TRUNCATE(MONTHS_BETWEEN('" & Format(Now(), "yyyy-mm-dd") & "',COVERAGE1.ISSUE_DT)/12,0)"
AttainedAgeCalc = "COVERAGE1.INS_ISS_AGE + " & DurationCalc



If OptionButton_ShowAllCoverages Then
    mMainTbl = "COVSALL"
Else
    mMainTbl = "COVERAGE1"
End If

sqlstring = BuildWithClause

sqlstring = sqlstring & "SELECT DISTINCT "
    sqlstring = sqlstring & " CURRENT_DATE RunDate "
    sqlstring = sqlstring & ",POLICY1.CK_POLICY_NBR PolicyNumber "
    If CheckBox_ShowTCH_POL_ID Then sqlstring = sqlstring & ",POLICY1.TCH_POL_ID TCH_POL_ID "
    If CheckBox_ShowProductLineCode Then sqlstring = sqlstring & ",COVERAGE1.PRD_LIN_TYP_CD "
    sqlstring = sqlstring & ",POLICY1.CK_CMP_CD CompanyCode "
    sqlstring = sqlstring & ",POLICY1.PRM_PAY_STA_REA_CD StatusCode "
    
    
    
    
    If CheckBox_ShowCurrentDuration Or TextBox_LowCurrentPolicyYear <> "" Or TextBox_HighCurrentPolicyYear <> "" Or CheckBox_SpecifyWithinConversionPeriod Or CheckBox_ShowIfWithinConversionPeriod Then
        sqlstring = sqlstring & "," & DurationCalc & " AS Duration "
    End If
    
    If CheckBox_ShowCurrentAttainedAge Or TextBox_LowCurrentAge <> "" Or TextBox_HighCurrentAge <> "" Or CheckBox_ShowConversionCreditInfo Or CheckBox_SpecifyWithinConversionPeriod Or CheckBox_ShowIfWithinConversionPeriod Then
        sqlstring = sqlstring & "," & AttainedAgeCalc & " AS AttainedAge "
    End If
    
    
    sqlstring = sqlstring & ",POLICY1.SUS_CD SuspenseCode "
    sqlstring = sqlstring & ",SUBSTR(POLICY1.SVC_AGC_NBR,1,1) AgentCode "
    
    'Convert state number to two letter abbreviation
    sqlstring = sqlstring & ",(CASE "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '01' THEN 'AL' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '02' THEN 'AZ' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '03' THEN 'AR' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '04' THEN 'CA' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '05' THEN 'CO' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '06' THEN 'CT' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '07' THEN 'DE' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '08' THEN 'DC' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '09' THEN 'FL' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '10' THEN 'GA' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '11' THEN 'ID' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '12' THEN 'IL' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '13' THEN 'IN' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '14' THEN 'IA' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '15' THEN 'KS' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '16' THEN 'KY' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '17' THEN 'LA' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '18' THEN 'ME' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '19' THEN 'MD' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '20' THEN 'MA' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '21' THEN 'MI' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '22' THEN 'MN' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '23' THEN 'MS' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '24' THEN 'MO' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '25' THEN 'MT' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '26' THEN 'NE' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '27' THEN 'NV' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '28' THEN 'NH' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '29' THEN 'NJ' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '30' THEN 'NM' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '31' THEN 'NY' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '32' THEN 'NC' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '33' THEN 'ND' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '34' THEN 'OH' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '35' THEN 'OK' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '36' THEN 'OR' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '37' THEN 'PA' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '38' THEN 'RI' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '39' THEN 'SC' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '40' THEN 'SD' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '41' THEN 'TN' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '42' THEN 'TX' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '43' THEN 'UT' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '44' THEN 'VT' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '45' THEN 'VA' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '46' THEN 'WA' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '47' THEN 'WV' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '48' THEN 'WI' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '49' THEN 'WY' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '50' THEN 'AK' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '51' THEN 'HI' "
        sqlstring = sqlstring & "WHEN POLICY1.POL_ISS_ST_CD  = '52' THEN 'PR' "
        sqlstring = sqlstring & "ELSE POLICY1.POL_ISS_ST_CD "
    sqlstring = sqlstring & "END) IssueState "
    
    sqlstring = sqlstring & "," & mMainTbl & ".PLN_DES_SER_CD Plancode "
    sqlstring = sqlstring & "," & mMainTbl & ".POL_FRM_NBR FormNumber "
    sqlstring = sqlstring & "," & mMainTbl & ".ISSUE_DT IssueDt "
    sqlstring = sqlstring & "," & mMainTbl & ".INS_ISS_AGE IssueAge "
    
    sqlstring = sqlstring & "," & "USERDEF_52G.FUZGREIN_IND PARTNER "
      

    If CheckBox_MarketOrgCode Then
         sqlstring = sqlstring & ", SUBSTR(POLICY1.SVC_AGC_NBR,1,1) MarkOrg "
    End If
    
    If CheckBox_SpecifyCashValueRateGTzeroOnBaseCov Or CheckBox_DisplayTradCVCov1 Then
        sqlstring = sqlstring & ",(CASE WHEN COVERAGE1.LOW_DUR_1_CSV_AMT IS NULL THEN '0' ELSE COVERAGE1.LOW_DUR_1_CSV_AMT END) BCVR_COV1 "
        sqlstring = sqlstring & ",(CASE WHEN COVERAGE1.LOW_DUR_2_CSV_AMT IS NULL THEN '0' ELSE COVERAGE1.LOW_DUR_2_CSV_AMT END) ECVR_COV1 "
        sqlstring = sqlstring & ",INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN "
        sqlstring = sqlstring & ",INTERPOLATION_MONTHS.MONTHS_YTD "
        sqlstring = sqlstring & ",(CASE WHEN COVERAGE1.LOW_DUR_1_CSV_AMT IS NULL THEN '0' ELSE COVERAGE1.LOW_DUR_1_CSV_AMT END)*COVERAGE1.COV_UNT_QTY*INTERPOLATION_MONTHS.MONTHS_TO_NEXT_ANN + (CASE WHEN COVERAGE1.LOW_DUR_2_CSV_AMT IS NULL THEN '0' ELSE COVERAGE1.LOW_DUR_2_CSV_AMT END)*COVERAGE1.COV_UNT_QTY*INTERPOLATION_MONTHS.MONTHS_YTD CV_COV1 "
    End If

    If CheckBox_DisplayAccountValue_02_75 Then
        sqlstring = sqlstring & ",MVVAL.CSV_AMT "
        sqlstring = sqlstring & ",TRAD_CV.INTERP_NSP "
        sqlstring = sqlstring & ",TRAD_CV.INTERP_CV "
        sqlstring = sqlstring & ",COVERAGE1.ADV_PRD_IND "
        sqlstring = sqlstring & ",COVERAGE1.LOW_DUR_CSV_AMT "
        sqlstring = sqlstring & ",COVERAGE1.LOW_DUR_1_CSV_AMT "
        sqlstring = sqlstring & ",COVERAGE1.LOW_DUR_NSP_AMT "
        sqlstring = sqlstring & ",COVERAGE1.LOW_DUR_1_NSP_AMT "
'        sqlstring = sqlstring & "(CASE WHEN  = '1' THEN MVVAL.CSV_AMT "
'        sqlstring = sqlstring & "WHEN SUBSTR(POLICY1.PRM_PAY_STA_REA_CD,1,1)  = '4' THEN TRAD_CV.INTERP_NSP "
'        sqlstring = sqlstring & "ELSE TRAD_CV.INTERP_CV "
'        sqlstring = sqlstring & "END) CSV "
    End If
    
    If CheckBox_ShowSexAndRateclass Then
        sqlstring = sqlstring & ",COV1_RENEWALS.RT_CLS_CD RenewalClass "
        sqlstring = sqlstring & ",COV1_RENEWALS.RT_SEX_CD RenewalSex "
    End If
    If CheckBox_ShowSex02 Then
        sqlstring = sqlstring & ",COVERAGE1.INS_SEX_CD SEX_CD "
    End If
    
    
    If CheckBox_ShowSubstandard Then sqlstring = sqlstring & ",(CASE WHEN TABLE_RATING1.SST_XTR_RT_TBL_CD IS NULL THEN ' ' ELSE TABLE_RATING1.SST_XTR_RT_TBL_CD END) TableRating "              '
    If CheckBox_ShowSubstandard Then sqlstring = sqlstring & ",(CASE WHEN FLAT_EXTRA1.SST_XTR_UNT_AMT IS NULL THEN '0' ELSE FLAT_EXTRA1.SST_XTR_UNT_AMT END) Flat "

    If CheckBox_RPUOriginalAmt Then sqlstring = sqlstring & ",CHANGE_TYPE9.TOTALORIGUNITS "
    
    If CheckBox_ISWL_GCVGTCurrCV Or CheckBox_ISWL_GCVLTCurrCV Then
    sqlstring = sqlstring & ",ISWL_INTERPOLATED_GCV.ISWL_GCV "
    End If
        
    If CheckBox_MulitpleBaseCoverages Or CheckBox_ULInCorridor Or CheckBox_ShowSpecifiedAmount Or TextBox_CurrentSAGreaterThan <> "" Or TextBox_CurrentSALessThan <> "" Then
        sqlstring = sqlstring & ",COVSUMMARY.TOTAL_SA TotalFace "
        sqlstring = sqlstring & ",COVSUMMARY.TOTAL_ORIGINAL_SA TotalOriginalFace "
    End If
    
    If CheckBox_DisplayNextChange Then
        sqlstring = sqlstring & ",COVERAGE1.NXT_CHG_TYP_CD NextChangeType "
        sqlstring = sqlstring & ",COVERAGE1.NXT_CHG_DT NextChangeDt "
    End If
               
    If TextBox_AVGreaterThan <> "" Or TextBox_AVLessThan <> "" Or CheckBox_ULInCorridor Or CheckBox_AccumulationValueGTPremiumPaid Or CheckBox_ISWL_GCVGTCurrCV Or CheckBox_ISWL_GCVLTCurrCV Or CheckBox_ShowAccumulationValue Or CheckBox_ShowPremiumPTD Then
        sqlstring = sqlstring & ",MVVAL.LASTMVDT LastMonthliverary "
        sqlstring = sqlstring & ",MVVAL.CSV_AMT CurrCV "
        sqlstring = sqlstring & ",MVVAL.TOTALPREM "
    End If
    
    
    If CheckBox_ShowDBOption Then
        sqlstring = sqlstring & ",NONTRAD.DTH_BNF_PLN_OPT_CD DBOpt "
    End If
    
    If CheckBox_ULInCorridor Or CheckBox_AccumulationValueGTPremiumPaid Then
        sqlstring = sqlstring & ",MVVAL.DB DB "
        sqlstring = sqlstring & ",MVVAL.CORRPCT CorrPct "
        sqlstring = sqlstring & ",MVVAL.OPTDB "
        sqlstring = sqlstring & ",ROUND(MVVAL.DB  - COVSUMMARY.TOTAL_SA,2) CORRAMT "
    End If
    
    If CheckBox_GLPIsNegative Then sqlstring = sqlstring & ",GLP.GLP_VALUE "
    If CheckBox_LastAccountDate Then sqlstring = sqlstring & ",POLICY1.LST_ACT_TRS_DT LST_ACC_DT "
    If CheckBox_LastFinancialDate Then sqlstring = sqlstring & ",POLICY1.LST_FIN_DT "
    If CheckBox_ShowBillToDate Then sqlstring = sqlstring & ",POLICY1.PRM_BILL_TO_DT BILL_TO_DT "
    If CheckBox_ShowPaidToDate Then sqlstring = sqlstring & ",POLICY1.PRM_PAID_TO_DT PAID_TO_DT "
    
    If CheckBox_ShowBillablePremium Or TextBox_LowBillingPrem.value <> "" Or TextBox_HighBillingPrem.value <> "" Then
        sqlstring = sqlstring & ",IFNULL(POLICY1.POL_PRM_AMT,0) BILL_PREM "
    End If
           
    If CheckBox_ShowBillingMode Then
        sqlstring = sqlstring & ",(CASE BILLMODE_POOL.PMT_FQY_PER "
            sqlstring = sqlstring & "WHEN 1 THEN "
                    sqlstring = sqlstring & "(CASE BILLMODE_POOL.NSD_MD_CD "
                    sqlstring = sqlstring & "WHEN '2' THEN 'BiWeekly' "
                    sqlstring = sqlstring & "WHEN 'S' THEN 'SemiMonthly' "
                    sqlstring = sqlstring & "WHEN '9' THEN '9thly' "
                    sqlstring = sqlstring & "WHEN 'A' THEN '10thly' "
                    sqlstring = sqlstring & "ELSE 'Monthly' "
                sqlstring = sqlstring & "End) "
            sqlstring = sqlstring & "WHEN 3 THEN 'Quarterly' "
            sqlstring = sqlstring & "WHEN 6 THEN 'SemiAnnually' "
            sqlstring = sqlstring & "WHEN 12 THEN 'Annually' "
            sqlstring = sqlstring & "ELSE ' ' "
        sqlstring = sqlstring & "End) BILL_MODE "

'3/2/2026 - RJH - This code below was causing issues when formating the data to an array.  I couldnt figure out exactly what the problem was so ive just commented it out for now

'        sqlstring = sqlstring & ",(CASE BILLMODE_POOL.PMT_FQY_PER "
'            sqlstring = sqlstring & "WHEN 1 THEN "
'                    sqlstring = sqlstring & "(CASE BILLMODE_POOL.NSD_MD_CD "
'                    sqlstring = sqlstring & "WHEN '2' THEN 26 "
'                    sqlstring = sqlstring & "WHEN 'S' THEN 24 "
'                    sqlstring = sqlstring & "WHEN '9' THEN 9 "
'                    sqlstring = sqlstring & "WHEN 'A' THEN 10 "
'                    sqlstring = sqlstring & "ELSE 12 "
'                sqlstring = sqlstring & "End) "
'            sqlstring = sqlstring & "WHEN 3 THEN 4 "
'            sqlstring = sqlstring & "WHEN 6 THEN 2 "
'            sqlstring = sqlstring & "WHEN 12 THEN 1 "
'            sqlstring = sqlstring & "ELSE ' ' "
'        sqlstring = sqlstring & "End) BILL_FREQ "
'
'        sqlstring = sqlstring & ",IFNULL(POLICY1.POL_PRM_AMT,0) * (CASE BILLMODE_POOL.PMT_FQY_PER "
'            sqlstring = sqlstring & "WHEN 1 THEN "
'                    sqlstring = sqlstring & "(CASE BILLMODE_POOL.NSD_MD_CD "
'                    sqlstring = sqlstring & "WHEN '2' THEN 26 "
'                    sqlstring = sqlstring & "WHEN 'S' THEN 24 "
'                    sqlstring = sqlstring & "WHEN '9' THEN 9 "
'                    sqlstring = sqlstring & "WHEN 'A' THEN 10 "
'                    sqlstring = sqlstring & "ELSE 12 "
'                sqlstring = sqlstring & "End) "
'            sqlstring = sqlstring & "WHEN 3 THEN 4 "
'            sqlstring = sqlstring & "WHEN 6 THEN 2 "
'            sqlstring = sqlstring & "WHEN 12 THEN 1 "
'            sqlstring = sqlstring & "ELSE ' ' "
'        sqlstring = sqlstring & "End) ANN_PREM "
    End If
    
    If CheckBox_ShowBillingForm Or CheckBox_SpecifyBillingForm Then sqlstring = sqlstring & ",POLICY1.BIL_FRM_CD BillForm "
    If CheckBox_ShowSLRBillingForm Or CheckBox_SpecifySLRBillingForm Then sqlstring = sqlstring & ",SLR_BILL_CONTROL.BIL_FRM_CD SLRBillForm "
  
    If CheckBox_ShowBillingControlNumber Then sqlstring = sqlstring & ",BILL_CONTROL.BIL_CTL_NBR BillControl "
    
    If CheckBox_ShowGSP Then sqlstring = sqlstring & ",GSP.GSP_VALUE "
    If CheckBox_ShowGLP Then sqlstring = sqlstring & ",GLP.GLP_VALUE "
    If CheckBox_ShowTAMRA Then sqlstring = sqlstring & ",TAMRA.SVPY_LVL_PRM_AMT TAMRA7PAY "
    If CheckBox_ShowCostBasis Then sqlstring = sqlstring & ",POLICY_TOTALS.POL_CST_BSS_AMT COSTBASIS "
    
    If CheckBox_ShowGPEDate Then sqlstring = sqlstring & ",GRACE_TABLE.GRA_PER_EXP_DT GPE_DT "
    If CheckBox_ShowCTP Then sqlstring = sqlstring & ",COMMTARGET.TAR_PRM_AMT CTP "
    If CheckBox_ShowMonthlyMTP Then sqlstring = sqlstring & ",MTP.TAR_PRM_AMT MonthlyMTP "
    If CheckBox_ShowAccumMonthlyMTP Then sqlstring = sqlstring & ",ACCUMMTP.TAR_PRM_AMT ACCUMMTP "
    If CheckBox_ShowAccumGLP Then sqlstring = sqlstring & ",ACCUMGLP.TAR_PRM_AMT ACCUMGLP "
    If CheckBox_ShowShadowAV Then sqlstring = sqlstring & ",SHADOWAV.TAR_PRM_AMT ShadowAV "
        
    If CheckBox_ShowPolicyDebt Or CheckBox_HasLoan Then
        sqlstring = sqlstring & ",POLICYDEBT.LOAN_PRINCIPLE  "
        sqlstring = sqlstring & ",POLICYDEBT.LOAN_ACCRUED "
        sqlstring = sqlstring & ",(CASE "
                sqlstring = sqlstring & "WHEN POLICY1.LN_TYP_CD  = '0' THEN 'FIX' "
                sqlstring = sqlstring & "WHEN POLICY1.LN_TYP_CD  = '1' THEN 'FIX' "
                sqlstring = sqlstring & "WHEN POLICY1.LN_TYP_CD  = '6' THEN 'VAR' "
                sqlstring = sqlstring & "WHEN POLICY1.LN_TYP_CD  = '7' THEN 'VAR' "
                sqlstring = sqlstring & "WHEN POLICY1.LN_TYP_CD  = '9' THEN 'NA' "
                sqlstring = sqlstring & "ELSE POLICY1.LN_TYP_CD "
        sqlstring = sqlstring & "END) LOAN_TYPE "
        sqlstring = sqlstring & ",(CASE "
                sqlstring = sqlstring & "WHEN POLICY1.LN_TYP_CD  = '0' THEN 'ADVANCE' "
                sqlstring = sqlstring & "WHEN POLICY1.LN_TYP_CD  = '1' THEN 'ARREARS' "
                sqlstring = sqlstring & "WHEN POLICY1.LN_TYP_CD  = '6' THEN 'ADVANCE' "
                sqlstring = sqlstring & "WHEN POLICY1.LN_TYP_CD  = '7' THEN 'ARREARS' "
                sqlstring = sqlstring & "WHEN POLICY1.LN_TYP_CD  = '9' THEN 'NA' "
                sqlstring = sqlstring & "ELSE POLICY1.LN_TYP_CD "
        sqlstring = sqlstring & "END) LOAN_TIMING "
    End If
    
    If CheckBox_ShowAccumWithdrawals Then sqlstring = sqlstring & ",POLICY_TOTALS.TOT_WTD_AMT "
    
    If CheckBox_ShowPremiumPaidYTD Then sqlstring = sqlstring & ",LH_POL_YR_TOT_at_MaxDuration.YTD_TOT_PMT_AMT "
    'SQLString = SQLString & ",LH_POL_YR_TOT_at_MaxDuration.YTD_TOT_PMT_AMT "
    
    If CheckBox_ShowTradOverloanInd Or CheckBox_OverloanIndicator Then sqlstring = sqlstring & ",POLICY1_MOD.OVERLOAN_IND "
    
    If CheckBox_ShowShortPayFields Then
        sqlstring = sqlstring & ",SHORTPAY_PRM.TAR_PRM_AMT SHORTPAY_AMT "
        sqlstring = sqlstring & ",SHORTPAY_PRM.TAR_DT SHORTPAY_CEASEDT "
        sqlstring = sqlstring & ",USERDEF_52G.INITIAL_PAY_DUR SHORTPAY_DUR "
        sqlstring = sqlstring & ",USERDEF_52G.INITIAL_MODE SHORTPAY_MODE "
        sqlstring = sqlstring & ",USERDEF_52G.DIAL_TO_PREM_AGE SHORTPAY_DBAGE "
    End If
    
    If CheckBox_ReinsuranceCode Or CheckBox_ShowReinsuredCode Then
        sqlstring = sqlstring & ",POLICY1.REINSURED_CD REINSURED_CD "
    End If
    
    If TextBox_LowAppDate <> "" Or TextBox_HighAppDate <> "" Then
        sqlstring = sqlstring & ",POLICY1.APP_WRT_DT APP_DT "
    End If
    
    If CheckBox_ShowLastEntryCode Or CheckBox_SpecifyLastEntryCode Or TextBox_LowLastFinancialDate <> "" Or TextBox_HighLastFinancialDate <> "" Then
        sqlstring = sqlstring & ",POLICY1.LST_ETR_CD LAST_CD "
        sqlstring = sqlstring & ",POLICY1.LST_FIN_DT LAST_DT "
    End If
    
    If CheckBox_ShowOriginalEntryCode Then
        sqlstring = sqlstring & ",POLICY1.OGN_ETR_CD ORIG_CD "
    End If
    
    
    If CheckBox_ShowMECStatus Then
        sqlstring = sqlstring & ",(CASE "
        sqlstring = sqlstring & "WHEN POLICY1.MEC_STATUS_CD = '0' THEN '0 - NO' "
        sqlstring = sqlstring & "WHEN POLICY1.MEC_STATUS_CD = '1' THEN '1 - YES' "
        sqlstring = sqlstring & "WHEN POLICY1.MEC_STATUS_CD = '2' THEN '2 - NO' "
        sqlstring = sqlstring & "ELSE POLICY1.MEC_STATUS_CD "
        sqlstring = sqlstring & "END) MEC_INDICATOR_01 "
    End If
    
    If CheckBox_Show_UL_DefinitionOfLifeInsurance Then
        sqlstring = sqlstring & ",(CASE "
        sqlstring = sqlstring & "WHEN NONTRAD.TFDF_CD = '1' THEN '1 - GPT TEFRA' "
        sqlstring = sqlstring & "WHEN NONTRAD.TFDF_CD = '2' THEN '2 - GPT DEFRA' "
        sqlstring = sqlstring & "WHEN NONTRAD.TFDF_CD = '3' THEN '3 - CVAT DEFRA' "
        sqlstring = sqlstring & "WHEN NONTRAD.TFDF_CD = '4' THEN '4 - GPT Selected' "
        sqlstring = sqlstring & "WHEN NONTRAD.TFDF_CD = '5' THEN '5 - CVAT Selected' "
        sqlstring = sqlstring & "ELSE NONTRAD.TFDF_CD "
        sqlstring = sqlstring & "END) DefOfLifeIns "
    End If
    
    If CheckBox_SpecifyHasConvertedPolicyNumber Or CheckBox_ShowConvertedPolicyNumber Then
        sqlstring = sqlstring & ",USERDEF_52G.EXCH_POL_NUMBER EXCHANGE_POL "
        sqlstring = sqlstring & ",USERDEF_52G.EXCHANGE EXCHANGE_CD "
        sqlstring = sqlstring & ",USERDEF_52G.SOURCE_COV_PHASE CONV_COV "
        sqlstring = sqlstring & ",USERDEF_52G.SOURCE_ISSUE_DATE CONV_ISSDT "
        sqlstring = sqlstring & ",USERDEF_52G. SOURCE_PLAN_CODE CONV_PLAN "
        sqlstring = sqlstring & ",USERDEF_52G. SOURCE_FACE_AMT CONV_FACE "
    End If
    
    If Me.CheckBox_SpecifyIsAReplacement Or Me.CheckBox_ShowReplacementPolicy Or Me.CheckBox_HasReplacementPolicyNumber Then
        sqlstring = sqlstring & ",USERDEF_52R.REPLACED_POLICY REPLACED_POL "
    End If
    
    
    If CheckBox_ShowNSP Then
         sqlstring = sqlstring & ",NSPTARGET.TAR_PRM_AMT NSP "
    End If
    
    
    If CheckBox_ShowNextScheduledNotificationDate Then
        sqlstring = sqlstring & ",POLICY1.NXT_SCH_NOT_DT NextNotifyDt "
    End If
    If CheckBox_ShowNextYearEndDate Then
        sqlstring = sqlstring & ",POLICY1.NXT_YR_END_PRC_DT NextYearEndDt "
    End If
    If CheckBox_ShowApplicationDate Then
        sqlstring = sqlstring & ",POLICY1.APP_WRT_DT AppDt "
    End If
    If Me.CheckBox_ShowNextMonthliversaryDate Then
        sqlstring = sqlstring & ",POLICY1.NXT_MVRY_PRC_DT NextMVDt "
    End If
    If CheckBox_ShowNextScheduledStatementDate Then
        sqlstring = sqlstring & ",POLICY1.NXT_SCH_STT_DT NextStatementDt "
    End If
    If CheckBox_ShowMDOIndicator Or CheckBox_IsMDO Then
    sqlstring = sqlstring & ",SUBSTR(POLICY1.USR_RES_CD,1,1) MDO "
    End If
    
    If TextBox_LowLastChangeDate.value <> "" Or TextBox_HighLastChangeDate.value <> "" Then
        sqlstring = sqlstring & ",NEWBUS.LST_CHG_DT "
    End If
    
    If TextBox_LowBillCommenceDate.value <> "" Or TextBox_LowBillCommenceDate.value <> "" Or CheckBox_BillingSuspended Then
        sqlstring = sqlstring & ",NONTRAD.BIL_STA_CD "
        sqlstring = sqlstring & ",NONTRAD.BIL_COMMENCE_DT "
    End If
    
    If CheckBox_ShowCIRFKey Then
        sqlstring = sqlstring & ",FFC.CUR_ITS_RT_SER_NBR CIRF_Key "
    End If
    
    If TextBox_FundIDs <> "" Then
        sqlstring = sqlstring & ",FUND_VALUES.FUNDAMT " & TextBox_FundIDs & "_AMT "
    End If
    
    If TextBox_TerminationLowDate <> "" Or TextBox_TerminationHighDate <> "" Or CheckBox_ShowTerminationDate_from_69 Then
         sqlstring = sqlstring & ",TERMINATION_DATES.TERM_ENTRY_DT "
    End If

    If CheckBox_ShowInitialTermPeriod Or CheckBox_SpecifyInitialTermPeriod Then
        sqlstring = sqlstring & ",COVERAGE1.INT_RNL_PER "
        sqlstring = sqlstring & ",COVERAGE1.SBQ_RNL_STR_DUR "
        sqlstring = sqlstring & ",COVERAGE1.SBQ_RNL_PER "
    End If

    If CheckBox_ShowConversionPeriodInfo Or CheckBox_SpecifyWithinConversionPeriod Then
        sqlstring = sqlstring & ",UPDF.CONVERSION_PERIOD CN_PERIOD "
        sqlstring = sqlstring & ",UPDF.CONVERSION_AGE CN_AGE "
        sqlstring = sqlstring & ",UPDF.CONV_TO_TRM_PERIOD CN_TO_TERM_PERIOD "
    End If
    
    If CheckBox_SpecifyWithinConversionPeriod Or CheckBox_ShowIfWithinConversionPeriod Then
        sqlstring = sqlstring & ",(CASE "
        sqlstring = sqlstring & "WHEN "
        sqlstring = sqlstring & "(UPDF.CONVERSION_PERIOD = 0 AND COVERAGE1.INS_ISS_AGE + TRUNCATE(MONTHS_BETWEEN(DATE('2025-06-08'), COVERAGE1.ISSUE_DT) / 12, 0) < UPDF.CONVERSION_AGE) "
        sqlstring = sqlstring & "OR "
        sqlstring = sqlstring & "(UPDF.CONVERSION_PERIOD > 0 AND TRUNCATE(MONTHS_BETWEEN(DATE('2025-06-08'), COVERAGE1.ISSUE_DT) / 12, 0) < UPDF.CONVERSION_PERIOD AND COVERAGE1.INS_ISS_AGE + TRUNCATE(MONTHS_BETWEEN(DATE('2025-06-08'), COVERAGE1.ISSUE_DT) / 12, 0) < UPDF.CONVERSION_AGE) "
        sqlstring = sqlstring & "THEN 'TRUE' "
        sqlstring = sqlstring & "ELSE 'FALSE' "
        sqlstring = sqlstring & "END "
        sqlstring = sqlstring & ") AS WITHIN_CONV_PERIOD "
    End If
    
    If CheckBox_ShowConversionCreditInfo Then
        sqlstring = sqlstring & ",UPDF.CONV_CREDIT_IND CN_CRED_IND "
        sqlstring = sqlstring & ",UPDF.CONV_CREDIT_RULE CN_CRED_RULE "
        sqlstring = sqlstring & ",UPDF.CONV_CREDIT_PERIOD CN_CRED_PERIOD "
    End If

    If CheckBox_ShowSubseries Then
       sqlstring = sqlstring & ",COVERAGE1.LIF_PLN_SUB_SRE_CD SUBSERIES "
    End If
    
    
    If CheckBox_ShowPremCalcRules Then
        sqlstring = sqlstring & ",FIXPREM.MD_PRM_MUL_ORD_CD "
        sqlstring = sqlstring & ",FIXPREM.RT_FCT_ORD_CD "
        sqlstring = sqlstring & ",FIXPREM.ROU_RLE_CD "
    End If
    
    
'-----------------------------------------------------------------------------------------------------------------------------------------
'-----------------------------------------------------------------------------------------------------------------------------------------
'START FROM CLAUSE
'-----------------------------------------------------------------------------------------------------------------------------------------
'-----------------------------------------------------------------------------------------------------------------------------------------

sqlstring = sqlstring & "FROM DB2TAB.LH_BAS_POL POLICY1 "

    'CRITERIA FOR ANY COVERAGE
    '-----------------------------------------------------------------------------------------------------------------------------------------
    Dim blnIncludeAll As Boolean
    blnIncludeAll = OptionButton_ShowAllCoverages Or _
                    ListBox_MultiplePlancodes.ListCount > 0 Or _
                    CheckBox_GIO_Indicator Or _
                    CheckBox_COLA_Indicator Or _
                    TextBox_PlancodeAllCovs <> "" Or _
                    TextBox_FormNumberLikeAllCovs <> "" Or _
                    CheckBox_SpecifyProductLineCodeAllCovs Or _
                    CheckBox_SpecifyProductIndicatorAllCovs

    If blnIncludeAll Then
        sqlstring = sqlstring & "INNER JOIN DB2TAB.LH_COV_PHA COVSALL  "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = COVSALL.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = COVSALL.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = COVSALL.TCH_POL_ID "
            If ListBox_MultiplePlancodes.ListCount > 0 Or TextBox_PlancodeAllCovs <> "" Then
                dct.RemoveAll
                For i = 0 To ListBox_MultiplePlancodes.ListCount - 1
                   dct.Add "COVSALL.PLN_DES_SER_CD" & " ='" & ListBox_MultiplePlancodes.Column(0, i) & "'", ""
                Next i
                
                '9/23/2019 - added a look for a wildcard in the plancode text box.  For DB2 the wild card symbol is %
                If TextBox_PlancodeAllCovs <> "" Then
                        If InStr(1, TextBox_PlancodeAllCovs, "%") > 0 Then
                            dct.Add "COVSALL.PLN_DES_SER_CD" & " Like '" & TextBox_PlancodeAllCovs.value & "'", ""
                        Else
                            dct.Add "COVSALL.PLN_DES_SER_CD" & " ='" & TextBox_PlancodeAllCovs.value & "'", ""
                        End If
                End If
                        
                        
                If dct.Count > 0 Then sqlstring = sqlstring & "AND (" & Join(dct.Keys, " OR ") & ") "
            End If
            If Me.CheckBox_SpecifyProductLineCodeAllCovs Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_ProductLineCodeAllCovs, "COVSALL.PRD_LIN_TYP_CD", 1
            
        'Modified fields on the 02 segment
        If CheckBox_SpecifyProductIndicatorAllCovs Or CheckBox_GIO_Indicator Or CheckBox_COLA_Indicator Then
        sqlstring = sqlstring & "INNER JOIN DB2TAB.TH_COV_PHA MODCOVSALL  "
            sqlstring = sqlstring & "ON MODCOVSALL.CK_SYS_CD = COVSALL.CK_SYS_CD "
            sqlstring = sqlstring & "AND MODCOVSALL.CK_CMP_CD = COVSALL.CK_CMP_CD "
            sqlstring = sqlstring & "AND MODCOVSALL.TCH_POL_ID = COVSALL.TCH_POL_ID "
            sqlstring = sqlstring & "AND MODCOVSALL.COV_PHA_NBR = COVSALL.COV_PHA_NBR "
            If Me.CheckBox_SpecifyProductIndicatorAllCovs Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_ProductIndicatorAllCovs, "MODCOVSALL.AN_PRD_ID", 1
            If Me.CheckBox_GIO_Indicator Then sqlstring = sqlstring & "AND (MODCOVSALL.OPT_EXER_IND = 'Y') "
            If Me.CheckBox_COLA_Indicator Then sqlstring = sqlstring & "AND (MODCOVSALL.COLA_INCR_IND = '1') "
        
        End If
    End If
   
   'LH_NEW_BUS_POL (00 segment)
   '-----------------------------------------------------------------------------------------------------------------------------------------
    'This table should only be added if you are querying Pending policies (CK_SYS_CD = "P")
    If BlnQueryNewBusinessTable Then
        sqlstring = sqlstring & "INNER JOIN DB2TAB.LH_NEW_BUS_POL NEWBUS "
          sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = NEWBUS.CK_SYS_CD "
          sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = NEWBUS.CK_CMP_CD "
          sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = NEWBUS.TCH_POL_ID "
    End If
           
       
       
    'LH_FXD_PRM_POL - premium rules for fixed premium products
    If CheckBox_ShowPremCalcRules Then
        sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_FXD_PRM_POL FIXPREM "
          sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = FIXPREM.CK_SYS_CD "
          sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = FIXPREM.CK_CMP_CD "
          sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = FIXPREM.TCH_POL_ID "
    End If
    
       
       
   'TH_BAS_POL (01 segment) - ANICO MODS FOR 01 Segment
   '-----------------------------------------------------------------------------------------------------------------------------------------
   If Me.CheckBox_ShowTradOverloanInd Then
    sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.TH_BAS_POL POLICY1_MOD "
          sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = POLICY1_MOD.CK_SYS_CD "
          sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = POLICY1_MOD.CK_CMP_CD "
          sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = POLICY1_MOD.TCH_POL_ID "
   End If
   
   

    'CRITERIA FOR BASE COVERAGE (COV = 1)
    '-----------------------------------------------------------------------------------------------------------------------------------------

    sqlstring = sqlstring & "INNER JOIN COVERAGE1  "
        sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = COVERAGE1.CK_SYS_CD "
        sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = COVERAGE1.CK_CMP_CD "
        sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = COVERAGE1.TCH_POL_ID "

        If TextBox_ValuationClass <> "" Then sqlstring = sqlstring & "AND (COVERAGE1.INS_CLS_CD = '" & TextBox_ValuationClass & "') "
        If TextBox_ValuationBase <> "" Then sqlstring = sqlstring & "AND (COVERAGE1.PLN_BSE_SRE_CD = '" & TextBox_ValuationBase & "') "
        If TextBox_ValuationSubseries <> "" Then sqlstring = sqlstring & "AND (COVERAGE1.LIF_PLN_SUB_SRE_CD = '" & TextBox_ValuationSubseries & "') "
        If CheckBox_ValuationClassNotPlanDescriptionClass Then sqlstring = sqlstring & "AND (COVERAGE1.INS_CLS_CD <> SUBSTR(COVERAGE1.PLN_DES_SER_CD,3,1)) "
        If TextBox_ValuationMortalityTable <> "" Then sqlstring = sqlstring & "AND COVERAGE1.MTL_FCT_TBL_CD  = '" & TextBox_ValuationMortalityTable & "' "
        If TextBox_ETIMortalityTable <> "" Then sqlstring = sqlstring & "AND COVERAGE1.NSP_EI_TBL_CD  = '" & TextBox_ETIMortalityTable & "' "
        If TextBox_NFOInterestRate <> "" Then sqlstring = sqlstring & "AND COVERAGE1.NSP_ITS_RT  = " & CDbl(TextBox_NFOInterestRate) & " "
        If TextBox_RPUMortalityTable <> "" Then sqlstring = sqlstring & "AND COVERAGE1.NSP_RPU_TBL_CD  = '" & TextBox_RPUMortalityTable & "' "
        If ComboBox_Cov1ProductLineCode <> "" Then sqlstring = sqlstring & "AND COVERAGE1.PRD_LIN_TYP_CD  = '" & ComboBox_Cov1ProductLineCode.value & "' "
        If TextBox_Cov1Plancode <> "" Then sqlstring = sqlstring & "AND COVERAGE1.PLN_DES_SER_CD  = '" & TextBox_Cov1Plancode.value & "' "
        If CheckBox_SpecifyCov1SexcodeFrom02 Then AddListBoxEntriesToSQL sqlstring, ListBox_Cov1SexCodeFrom02, "COVERAGE1.INS_SEX_CD", 1
        
            
        If CheckBox_SpecifyInitialTermPeriod Then AddListBoxEntriesToSQL sqlstring, ListBox_InitialTermPeriod, "COVERAGE1.INT_RNL_PER ", 3
        
      
        'For the current cash value to be greater than 0 either the last year CVR should be greater than zero or next year or both
        If CheckBox_SpecifyCashValueRateGTzeroOnBaseCov Then sqlstring = sqlstring & "AND (COVERAGE1.LOW_DUR_1_CSV_AMT > 0 or COVERAGE1.LOW_DUR_2_CSV_AMT > 0) "
        
        If TextBox_LowIssueAge.value <> "" Then sqlstring = sqlstring & "AND (COVERAGE1.INS_ISS_AGE >=  " & TextBox_LowIssueAge.value & ") "
        If TextBox_HighIssueAge.value <> "" Then sqlstring = sqlstring & "AND (COVERAGE1.INS_ISS_AGE <= " & TextBox_HighIssueAge.value & ") "

        If TextBox_IssuedAfter.value <> "" Then sqlstring = sqlstring & "AND COVERAGE1.ISSUE_DT >=  '" & Format(TextBox_IssuedAfter.value, "yyyy-mm-dd") & "' "
        If TextBox_IssuedBefore.value <> "" Then sqlstring = sqlstring & "AND COVERAGE1.ISSUE_DT <= '" & Format(TextBox_IssuedBefore.value, "yyyy-mm-dd") & "' "

        If Me.TextBox_LowIssueMonth.value <> "" Then sqlstring = sqlstring & "AND MONTH(COVERAGE1.ISSUE_DT) >=  " & Me.TextBox_LowIssueMonth.value & " "
        If Me.TextBox_HighIssueMonth.value <> "" Then sqlstring = sqlstring & "AND MONTH(COVERAGE1.ISSUE_DT) <= " & TextBox_HighIssueMonth.value & " "

        If Me.TextBox_LowIssueDay.value <> "" Then sqlstring = sqlstring & "AND DAY(COVERAGE1.ISSUE_DT) >= " & TextBox_LowIssueDay.value & " "
        If Me.TextBox_HighIssueDay.value <> "" Then sqlstring = sqlstring & "AND DAY(COVERAGE1.ISSUE_DT) <= " & TextBox_HighIssueDay.value & " "

        'Modified fields on the 02 segment
        If ComboBox_Cov1ProductIndicator <> "" Or CheckBox_ShowProductLineCode Then
            If CheckBox_ShowProductLineCode Then
               sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.TH_COV_PHA MODCOV1 "
            Else
               sqlstring = sqlstring & "INNER JOIN DB2TAB.TH_COV_PHA MODCOV1 "
            End If
            sqlstring = sqlstring & "ON COVERAGE1.CK_SYS_CD = MODCOV1.CK_SYS_CD "
            sqlstring = sqlstring & "AND COVERAGE1.CK_CMP_CD = MODCOV1.CK_CMP_CD "
            sqlstring = sqlstring & "AND COVERAGE1.TCH_POL_ID = MODCOV1.TCH_POL_ID "
            sqlstring = sqlstring & "AND COVERAGE1.COV_PHA_NBR = MODCOV1.COV_PHA_NBR "
            If ComboBox_Cov1ProductIndicator <> "" Then sqlstring = sqlstring & "AND (MODCOV1.AN_PRD_ID = '" & left(ComboBox_Cov1ProductIndicator.value, 1) & "') "
        End If

        'Table Rating.  LH_SST_XTR_CRG
        If CheckBox_TableRating Or CheckBox_ShowSubstandard Then
            If CheckBox_TableRating Then
                sqlstring = sqlstring & "INNER JOIN DB2TAB.LH_SST_XTR_CRG TABLE_RATING1  "
            Else
                sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_SST_XTR_CRG TABLE_RATING1  "
            End If
            sqlstring = sqlstring & "ON COVERAGE1.CK_SYS_CD = TABLE_RATING1.CK_SYS_CD "
            sqlstring = sqlstring & "AND COVERAGE1.CK_CMP_CD = TABLE_RATING1.CK_CMP_CD "
            sqlstring = sqlstring & "AND COVERAGE1.TCH_POL_ID = TABLE_RATING1.TCH_POL_ID "
            sqlstring = sqlstring & "AND COVERAGE1.COV_PHA_NBR = TABLE_RATING1.COV_PHA_NBR "
            sqlstring = sqlstring & "AND (TABLE_RATING1.SST_XTR_TYP_CD ='0' Or TABLE_RATING1.SST_XTR_TYP_CD ='1' Or TABLE_RATING1.SST_XTR_TYP_CD ='3') "
        End If

        'Flat Extra.  LH_SST_XTR_CRG
        If CheckBox_FlatExtra Or CheckBox_ShowSubstandard Then
            If CheckBox_FlatExtra Then
                sqlstring = sqlstring & "INNER JOIN DB2TAB.LH_SST_XTR_CRG FLAT_EXTRA1  "
            Else
                sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_SST_XTR_CRG FLAT_EXTRA1  "
            End If
            sqlstring = sqlstring & "ON COVERAGE1.CK_SYS_CD = FLAT_EXTRA1.CK_SYS_CD "
            sqlstring = sqlstring & "AND COVERAGE1.CK_CMP_CD = FLAT_EXTRA1.CK_CMP_CD "
            sqlstring = sqlstring & "AND COVERAGE1.TCH_POL_ID = FLAT_EXTRA1.TCH_POL_ID "
            sqlstring = sqlstring & "AND COVERAGE1.COV_PHA_NBR = FLAT_EXTRA1.COV_PHA_NBR "
            sqlstring = sqlstring & "AND (FLAT_EXTRA1.SST_XTR_TYP_CD ='2' Or FLAT_EXTRA1.SST_XTR_TYP_CD ='4') "
        End If
        
        'RATE CLASS FOR COVERAGE1
        '---------------------------------------------------------------------------------------------------------
        If CheckBox_SpecifyCov1Rateclass Or CheckBox_SpecifyCov1Sexcode Or CheckBox_ShowSexAndRateclass Then
            If CheckBox_SpecifyCov1Rateclass Or CheckBox_SpecifyCov1Sexcode Then
                sqlstring = sqlstring & "INNER JOIN DB2TAB.LH_COV_INS_RNL_RT COV1_RENEWALS  "
            Else
                sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_COV_INS_RNL_RT COV1_RENEWALS  "
            End If
            sqlstring = sqlstring & "ON COVERAGE1.CK_SYS_CD = COV1_RENEWALS.CK_SYS_CD "
            sqlstring = sqlstring & "AND COVERAGE1.CK_CMP_CD = COV1_RENEWALS.CK_CMP_CD "
            sqlstring = sqlstring & "AND COVERAGE1.TCH_POL_ID = COV1_RENEWALS.TCH_POL_ID "
            sqlstring = sqlstring & "AND COVERAGE1.COV_PHA_NBR = COV1_RENEWALS.COV_PHA_NBR "
            'Set PRM_TYP_CD to 'C' so you only get one record from this table per cov phase
            sqlstring = sqlstring & "AND COV1_RENEWALS.PRM_RT_TYP_CD = 'C' "
            If CheckBox_SpecifyCov1Rateclass Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_Cov1Rateclass, "COV1_RENEWALS.RT_CLS_CD", 1
            If CheckBox_SpecifyCov1Sexcode Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_Cov1SexCode, "COV1_RENEWALS.RT_SEX_CD", 1
        End If

    'CRITERIA FOR RIDERS
    'Everything needed for riders is found in BuildRiderTable
    sqlstring = sqlstring & BuildRiderTable

    
    'TRAD CV
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_DisplayAccountValue_02_75 Then
        sqlstring = sqlstring & "LEFT OUTER JOIN TRAD_CV "
            sqlstring = sqlstring & "ON COVERAGE1.CK_SYS_CD = TRAD_CV.CK_SYS_CD "
            sqlstring = sqlstring & "AND COVERAGE1.CK_CMP_CD = TRAD_CV.CK_CMP_CD "
            sqlstring = sqlstring & "AND COVERAGE1.TCH_POL_ID = TRAD_CV.TCH_POL_ID "
    End If
    
    'CRITERIA FOR BENEFITS (No restriction on COV_PHA_NBR)
    '-----------------------------------------------------------------------------------------------------------------------------------------
    'Benefit1
    blnQueryBenefit1 = ComboBox_Benefit1 <> "" Or TextBox_Benefit1SubType <> "" Or CheckBox_Benefit1PostIssue Or TextBox_Benefit1LowCeaseDate <> "" Or TextBox_Benefit1HighCeaseDate <> "" Or ComboBox_Benefit1CeaseDateStatus <> ""
    If blnQueryBenefit1 Then
    sqlstring = sqlstring & "INNER JOIN DB2TAB.LH_SPM_BNF BEN1  "
        sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = BEN1.CK_SYS_CD "
        sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = BEN1.CK_CMP_CD "
        sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = BEN1.TCH_POL_ID "
        If ComboBox_Benefit1 <> "" Then sqlstring = sqlstring & "AND (BEN1.SPM_BNF_TYP_CD = '" & left(Me.ComboBox_Benefit1.value, 1) & "') "
        If TextBox_Benefit1SubType <> "" Then sqlstring = sqlstring & "AND (BEN1.SPM_BNF_SBY_CD = '" & TextBox_Benefit1SubType.value & "') "
        If CheckBox_Benefit1PostIssue Then sqlstring = sqlstring & "AND (BEN1.BNF_ISS_DT > COVERAGE1.ISSUE_DT) "
    
        If TextBox_Benefit1LowCeaseDate <> "" Then sqlstring = sqlstring & "AND (BEN1.BNF_CEA_DT >= '" & Format(TextBox_Benefit1LowCeaseDate, "yyyy-mm-dd") & "') "
        If TextBox_Benefit1HighCeaseDate <> "" Then sqlstring = sqlstring & "AND (BEN1.BNF_CEA_DT <= '" & Format(TextBox_Benefit1HighCeaseDate, "yyyy-mm-dd") & "') "
              
        If left(ComboBox_Benefit1CeaseDateStatus, 1) = "1" Then sqlstring = sqlstring & "AND (BEN1.BNF_CEA_DT = BEN1.BNF_OGN_CEA_DT) "
        If left(ComboBox_Benefit1CeaseDateStatus, 1) = "2" Then sqlstring = sqlstring & "AND (BEN1.BNF_CEA_DT < BEN1.BNF_OGN_CEA_DT) "
        If left(ComboBox_Benefit1CeaseDateStatus, 1) = "3" Then sqlstring = sqlstring & "AND (BEN1.BNF_CEA_DT > BEN1.BNF_OGN_CEA_DT) "
        
    End If
    
    'Benefit2
    blnQueryBenefit2 = ComboBox_Benefit2 <> "" Or TextBox_Benefit2SubType <> "" Or CheckBox_Benefit2PostIssue
    If blnQueryBenefit2 Then
    sqlstring = sqlstring & "INNER JOIN DB2TAB.LH_SPM_BNF BEN2  "
        sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = BEN2.CK_SYS_CD "
        sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = BEN2.CK_CMP_CD "
        sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = BEN2.TCH_POL_ID "
        If ComboBox_Benefit2 <> "" Then sqlstring = sqlstring & "AND (BEN2.SPM_BNF_TYP_CD = '" & left(Me.ComboBox_Benefit2.value, 1) & "') "
        If TextBox_Benefit2SubType <> "" Then sqlstring = sqlstring & "AND (BEN2.SPM_BNF_SBY_CD = '" & TextBox_Benefit2SubType.value & "') "
        If CheckBox_Benefit2PostIssue Then sqlstring = sqlstring & "AND (BEN2.BNF_ISS_DT > COV1.ISSUE_DT) "
    End If

    'Benefit3
    blnQueryBenefit3 = ComboBox_Benefit3 <> "" Or TextBox_Benefit3SubType <> "" Or CheckBox_Benefit3PostIssue
    If blnQueryBenefit3 Then
    sqlstring = sqlstring & "INNER JOIN DB2TAB.LH_SPM_BNF BEN3  "
        sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = BEN3.CK_SYS_CD "
        sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = BEN3.CK_CMP_CD "
        sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = BEN3.TCH_POL_ID "
        If ComboBox_Benefit3 <> "" Then sqlstring = sqlstring & "AND (BEN3.SPM_BNF_TYP_CD = '" & left(Me.ComboBox_Benefit3.value, 1) & "') "
        If TextBox_Benefit3SubType <> "" Then sqlstring = sqlstring & "AND (BEN3.SPM_BNF_SBY_CD = '" & TextBox_Benefit3SubType.value & "') "
        If CheckBox_Benefit3PostIssue Then sqlstring = sqlstring & "AND (BEN3.BNF_ISS_DT > COV1.ISSUE_DT) "
    End If


    'UL Related. LH_COV_FXD_FND_CTL (Fixed Fund Control 55 segment)
    If CheckBox_ShowCIRFKey Then
    sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_COV_FXD_FND_CTL FFC "
        sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = FFC.CK_SYS_CD "
        sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = FFC.CK_CMP_CD "
        sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = FFC.TCH_POL_ID "
        'sqlstring = sqlstring & "AND FFC.FND_ID_CD IN ('U1','I1', 'A1', 'F1', 'SW', 'GF') "
        
    End If
    
            

    
    
    'UL Related. LH_POL_FND_VAL_TOT (FUND_VALUES) (65 segemnt)
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If TextBox_FundIDs <> "" Then
    sqlstring = sqlstring & "INNER JOIN FUND_VALUES "
        sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = FUND_VALUES.CK_SYS_CD "
        sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = FUND_VALUES.CK_CMP_CD "
        sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = FUND_VALUES.TCH_POL_ID "
        sqlstring = sqlstring & "AND FUND_VALUES.FND_ID_CD = '" & TextBox_FundIDs.value & "' "
        If TextBox_FundIDGreaterThan.value <> "" Then sqlstring = sqlstring & "AND FUND_VALUES.FUNDAMT >= " & TextBox_FundIDGreaterThan.value & " "
        If TextBox_FundIDLessThan.value <> "" Then sqlstring = sqlstring & "AND FUND_VALUES.FUNDAMT <= " & TextBox_FundIDLessThan.value & " "
    End If

    'UL related.  LH_NON_TRD_POL (66 segment)
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_Show_UL_DefinitionOfLifeInsurance Or CheckBox_ShowDBOption Or Me.CheckBox_SpecifyDBOption Or Me.CheckBox_SpecifyDefinitionOfLifeInsurance Or _
        CheckBox_FailedTAMRAorGP Or CheckBox_GracePeriodRuleCode Or CheckBox_BillingSuspended Or TextBox_LowBillCommenceDate <> "" Or TextBox_HighBillCommenceDate <> "" Then
    
        If Me.CheckBox_SpecifyDBOption Or Me.CheckBox_SpecifyDefinitionOfLifeInsurance Or CheckBox_FailedTAMRAorGP Or CheckBox_GracePeriodRuleCode Then
                sqlstring = sqlstring & "INNER JOIN DB2TAB.LH_NON_TRD_POL NONTRAD "
        Else
            sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_NON_TRD_POL NONTRAD "
        End If
        sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = NONTRAD.CK_SYS_CD "
        sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = NONTRAD.CK_CMP_CD "
        sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = NONTRAD.TCH_POL_ID "

        'Add DB Option codes
        If CheckBox_SpecifyDBOption Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_DBOption, "NONTRAD.DTH_BNF_PLN_OPT_CD", 1

        'Add DB Option codes
        If CheckBox_SpecifyDefinitionOfLifeInsurance Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_DefinitionOfLifeInsurance, "NONTRAD.TFDF_CD", 1

        'Grace Thershold Rule
        If CheckBox_GracePeriodRuleCode Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_GracePeriodRuleCode, "NONTRAD.GRA_THD_RLE_CD", 1
        
        'TAMRA or GP Failed indicator
        If CheckBox_FailedTAMRAorGP Then sqlstring = sqlstring & "AND (NONTRAD.PR_LIMIT_EXC_ONL = '1') "
        
        'Billing suspended
        If CheckBox_BillingSuspended Then sqlstring = sqlstring & "AND (NONTRAD.BIL_STA_CD = '1') "
        
    
        
    End If
   
   'Premium Allocation Funds
   '-----------------------------------------------------------------------------------------------------------------------------------------
   If CheckBox_PremiumAllocationFunds And SelectedCount(ListBox_PremiumAllocationFunds) > 0 Then
        sqlstring = sqlstring & "INNER JOIN ALLOCATION_FUNDS "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = ALLOCATION_FUNDS.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = ALLOCATION_FUNDS.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = ALLOCATION_FUNDS.TCH_POL_ID "
   End If
   
   'Premium Allocation Count (Type = P).  LH_FND_ALC (57 Segment)
   If TextBox_TypePCountGreaterThan <> "" Or TextBox_TypePCountLessThan <> "" Then
    sqlstring = sqlstring & "INNER JOIN DB2TAB.LH_FND_TRS_ALC_SET ALLOCATION_P_COUNT "
          sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = ALLOCATION_P_COUNT.CK_SYS_CD "
          sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = ALLOCATION_P_COUNT.CK_CMP_CD "
          sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = ALLOCATION_P_COUNT.TCH_POL_ID "
          sqlstring = sqlstring & "AND ALLOCATION_P_COUNT.FND_TRS_TYP_CD = 'P' "
          If TextBox_TypePCountGreaterThan <> "" Then sqlstring = sqlstring & "AND ALLOCATION_P_COUNT.FND_ALC_SEQ_NBR >= " & TextBox_TypePCountGreaterThan & " "
          If TextBox_TypePCountLessThan <> "" Then sqlstring = sqlstring & "AND ALLOCATION_P_COUNT.FND_ALC_SEQ_NBR <= " & TextBox_TypePCountLessThan & " "
   End If
   
   'Skipped Coverage Reinstatement.  LH_COV_SKIPPED_PER (09 segment)
   '-----------------------------------------------------------------------------------------------------------------------------------------
   If Me.CheckBox_SkippedCoverageReinstatement Then
    sqlstring = sqlstring & "INNER JOIN DB2TAB.LH_COV_SKIPPED_PER REINSTATEMENT "
          sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = REINSTATEMENT.CK_SYS_CD "
          sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = REINSTATEMENT.CK_CMP_CD "
          sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = REINSTATEMENT.TCH_POL_ID "
   End If
 
   'Standard Loan Repament (SLR) Billing Control.  LH_LN_RPY_TRM  (20 segment)
   '-----------------------------------------------------------------------------------------------------------------------------------------
   If Me.CheckBox_SpecifySLRBillingForm Then
    sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_LN_RPY_TRM SLR_BILL_CONTROL "
          sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = SLR_BILL_CONTROL.CK_SYS_CD "
          sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = SLR_BILL_CONTROL.CK_CMP_CD "
          sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = SLR_BILL_CONTROL.TCH_POL_ID "
   End If


   'Billing Control.  LH_BIL_FRM_CTL (33 segment)
   '-----------------------------------------------------------------------------------------------------------------------------------------
   If Me.CheckBox_ShowBillingControlNumber Then
    sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_BIL_FRM_CTL BILL_CONTROL "
          sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = BILL_CONTROL.CK_SYS_CD "
          sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = BILL_CONTROL.CK_CMP_CD "
          sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = BILL_CONTROL.TCH_POL_ID "
   End If

   '========================================================================================================================================================================
   'USER MODIFICATION SEGMENTS (52)
   '========================================================================================================================================================================
   
   'TH_USER_GENERIC (52-G segment)
   '-----------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_SpecifyHasConvertedPolicyNumber Or CheckBox_IsRGA Then
        sqlstring = sqlstring & "INNER JOIN DB2TAB.TH_USER_GENERIC USERDEF_52G "
    Else
        sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.TH_USER_GENERIC USERDEF_52G "
    End If
    sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = USERDEF_52G.CK_SYS_CD "
    sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = USERDEF_52G.CK_CMP_CD "
    sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = USERDEF_52G.TCH_POL_ID "
    If CheckBox_SpecifyHasConvertedPolicyNumber Then
          sqlstring = sqlstring & "AND USERDEF_52G.EXCH_POL_NUMBER IS NOT NULL "
    End If


   'TH_USER_PDF (52-1)
   '-----------------------------------------------------------------------------------------------------------------------------------------

        sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.TH_USER_PDF UPDF "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = UPDF.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = UPDF.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = UPDF.TCH_POL_ID "
            sqlstring = sqlstring & "AND UPDF.TYPE_SEQUENCE = 1 "
   
   
   'TH_USER_REPLACEMENT (52-R segment)
   '-----------------------------------------------------------------------------------------------------------------------------------------
   If Me.CheckBox_SpecifyIsAReplacement Or Me.CheckBox_ShowReplacementPolicy Or CheckBox_HasReplacementPolicyNumber Then
    If CheckBox_SpecifyIsAReplacement Or CheckBox_HasReplacementPolicyNumber Then
        sqlstring = sqlstring & "INNER JOIN DB2TAB.TH_USER_REPLACEMENT USERDEF_52R "
    Else
        sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.TH_USER_REPLACEMENT USERDEF_52R "
    End If
          sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = USERDEF_52R.CK_SYS_CD "
          sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = USERDEF_52R.CK_CMP_CD "
          sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = USERDEF_52R.TCH_POL_ID "
          If CheckBox_HasReplacementPolicyNumber Then
                sqlstring = sqlstring & "AND USERDEF_52R.REPLACED_POLICY IS NOT NULL "
          End If
          
   End If


   'Premium Allocation Count (Type = V).  LH_FND_ALC (57 Segment)
   If TextBox_TypeVCountGreaterThan <> "" Or TextBox_TypeVCountLessThan <> "" Then
    sqlstring = sqlstring & "INNER JOIN DB2TAB.LH_FND_TRS_ALC_SET ALLOCATION_V_COUNT "
          sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = ALLOCATION_V_COUNT.CK_SYS_CD "
          sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = ALLOCATION_V_COUNT.CK_CMP_CD "
          sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = ALLOCATION_V_COUNT.TCH_POL_ID "
          sqlstring = sqlstring & "AND ALLOCATION_V_COUNT.FND_TRS_TYP_CD = 'V' "
          If TextBox_TypeVCountGreaterThan <> "" Then sqlstring = sqlstring & "AND ALLOCATION_V_COUNT.FND_ALC_SEQ_NBR >= " & TextBox_TypeVCountGreaterThan & " "
          If TextBox_TypeVCountLessThan <> "" Then sqlstring = sqlstring & "AND ALLOCATION_V_COUNT.FND_ALC_SEQ_NBR <= " & TextBox_TypeVCountLessThan & " "
   End If

    'TAMRA. Table LH_TAMRA_7_PY_PER (59 Segment)
    '-----------------------------------------------------------------------------------------------------------------------------------------
    sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_TAMRA_7_PY_PER TAMRA  "
        sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = TAMRA.CK_SYS_CD "
        sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = TAMRA.CK_CMP_CD "
        sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = TAMRA.TCH_POL_ID "

      
    'Policy Totals. Table LH_POL_TOTALS (60 Segment)
    '-----------------------------------------------------------------------------------------------------------------------------------------
    sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_POL_TOTALS POLICY_TOTALS "
        sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = POLICY_TOTALS.CK_SYS_CD "
        sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = POLICY_TOTALS.CK_CMP_CD "
        sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = POLICY_TOTALS.TCH_POL_ID "

    
    'Policy Totals - Year To Date. Table LH_POL_YR_TOT (63 Segment)
'    '-----------------------------------------------------------------------------------------------------------------------------------------
    sqlstring = sqlstring & "LEFT OUTER JOIN LH_POL_YR_TOT_at_MaxDuration "
        sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = LH_POL_YR_TOT_at_MaxDuration.CK_SYS_CD "
        sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = LH_POL_YR_TOT_at_MaxDuration.CK_CMP_CD "
        sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = LH_POL_YR_TOT_at_MaxDuration.TCH_POL_ID "


    
    

    
    '=========================================================================================================================================
    'TARGET TABLES  (58 Segment):  LH_POL_TARGET, LH_COV_TARGET, LH_COM_TARTET
    '=========================================================================================================================================
    
    'Policy Target LH_COMM_TARGET
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_ShowCTP Then
        sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_COM_TARGET COMMTARGET "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = COMMTARGET.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = COMMTARGET.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = COMMTARGET.TCH_POL_ID "
            sqlstring = sqlstring & "AND COMMTARGET.TAR_TYP_CD = 'CT' "
    End If
    
    'Policy Target LH_POL_TARGET
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_ShowMonthlyMTP Then
        sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_POL_TARGET MTP "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = MTP.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = MTP.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = MTP.TCH_POL_ID "
            sqlstring = sqlstring & "AND MTP.TAR_TYP_CD = 'MT' "

    End If
    If CheckBox_ShowAccumMonthlyMTP Then
        sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_POL_TARGET ACCUMMTP "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = ACCUMMTP.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = ACCUMMTP.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = ACCUMMTP.TCH_POL_ID "
            sqlstring = sqlstring & "AND ACCUMMTP.TAR_TYP_CD = 'MA' "
    End If
    If CheckBox_ShowAccumGLP Then
        sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_POL_TARGET ACCUMGLP "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = ACCUMGLP.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = ACCUMGLP.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = ACCUMGLP.TCH_POL_ID "
            sqlstring = sqlstring & "AND ACCUMGLP.TAR_TYP_CD = 'TA' "
    End If
    If CheckBox_ShowShortPayFields Then
        sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_POL_TARGET SHORTPAY_PRM "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = SHORTPAY_PRM.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = SHORTPAY_PRM.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = SHORTPAY_PRM.TCH_POL_ID "
            sqlstring = sqlstring & "AND SHORTPAY_PRM.TAR_TYP_CD = 'VS' "
    End If
      
      
    'Policy Target LH_COV_TARGET
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_ShowShadowAV Or TextBox_ShadowAVGreaterThan <> "" Or TextBox_ShadowAVLessThan <> "" Then
        sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_COV_TARGET SHADOWAV "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = SHADOWAV.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = SHADOWAV.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = SHADOWAV.TCH_POL_ID "
            'SQLString = SQLString & "AND SHADOWAV.COV_PHA_NBR = '1' "
            sqlstring = sqlstring & "AND SHADOWAV.TAR_TYP_CD = 'XP' "
    End If
      
        
    'Policy Net Single Premium on LH_POL_TARGET 58 seg for CVAT MDBR
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_ShowNSP Then
        sqlstring = sqlstring & "LEFT OUTER JOIN DB2TAB.LH_POL_TARGET NSPTARGET "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = NSPTARGET.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = NSPTARGET.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = NSPTARGET.TCH_POL_ID "
            sqlstring = sqlstring & "AND NSPTARGET.TAR_TYP_CD = 'NS' "
    End If
    
      
'Complex queries (queries using tables created with the WITH clause above)
'-----------------------------------------------------------------------------------------------------------------------------------------
    
    'FH_FIXED table (69 Segment) - Termination Dates are found from the FH_FIXED table (69 Segment).  The entry date of the termation transaction is used
    If TextBox_TerminationLowDate <> "" Or TextBox_TerminationHighDate <> "" Or CheckBox_ShowTerminationDate_from_69 Then
        'If specifying a date range then inner join so that only poilcies with termiatnion dates show.
        'Otherwise, if just specifying to show termiantion date, do a Left outer join to include policies that may not be termianted
        If TextBox_TerminationLowDate <> "" Or TextBox_TerminationHighDate <> "" Then
            sqlstring = sqlstring & "INNER JOIN TERMINATION_DATES AS TD "
        Else
            sqlstring = sqlstring & "LEFT OUTER JOIN TERMINATION_DATES AS TD "
        End If
        sqlstring = sqlstring & "ON POLICY1.CK_CMP_CD = TD.CK_CMP_CD "
        sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = TD.TCH_POL_ID "
    End If
    
    
    If Me.CheckBox_HasChangeSegment Then
        sqlstring = sqlstring & "INNER JOIN CHANGE_SEGMENT  "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = CHANGE_SEGMENT.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = CHANGE_SEGMENT.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = CHANGE_SEGMENT.TCH_POL_ID "
    End If
    
    
    'Loans.  ALL_LOANS created from LH_CSH_VAL_LOAN (Trad) and LH_FND_VAL_LOAN (Advanced).  77 & 79 Segments.
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_HasLoan Or TextBox_LoanPrincipleGreaterThan <> "" Or TextBox_LoanPrincipleLessThan <> "" Or TextBox_LoanAccruedIntGreaterThan <> "" Or TextBox_LoanAccruedIntLessThan <> "" Then
        sqlstring = sqlstring & "INNER JOIN ALL_LOANS  "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = ALL_LOANS.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = ALL_LOANS.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = ALL_LOANS.TCH_POL_ID "
            
            If Me.CheckBox_HasPreferredLoan Then sqlstring = sqlstring & "AND (ALL_LOANS.PRF_LN_IND = '1') "
    
    End If


    If CheckBox_ShowPolicyDebt Or blnHas77Segment Then
            
            'If the query requires that policies have a 77 segment then the policies must exist in the POLICYDEBT table.
            'However, if the query is only trying to display the policy debt if any exists, then we need to use the LEFT OUTER Join
            If blnHas77Segment Then
                sqlstring = sqlstring & "INNER JOIN POLICYDEBT  "
            Else
                sqlstring = sqlstring & "LEFT OUTER JOIN POLICYDEBT  "
            End If
            
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = POLICYDEBT.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = POLICYDEBT.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = POLICYDEBT.TCH_POL_ID "
            
            
            If TextBox_LoanPrincipleGreaterThan <> "" Then sqlstring = sqlstring & "AND POLICYDEBT.LOAN_PRINCIPLE >= " & TextBox_LoanPrincipleGreaterThan.value & " "
            If TextBox_LoanPrincipleLessThan <> "" Then sqlstring = sqlstring & "AND POLICYDEBT.LOAN_PRINCIPLE <= " & TextBox_LoanPrincipleLessThan.value & " "

            If TextBox_LoanAccruedIntGreaterThan <> "" Then sqlstring = sqlstring & "AND POLICYDEBT.LOAN_ACCRUED >= " & TextBox_LoanAccruedIntGreaterThan.value & " "
            If TextBox_LoanAccruedIntLessThan <> "" Then sqlstring = sqlstring & "AND POLICYDEBT.LOAN_ACCRUED <= " & TextBox_LoanAccruedIntLessThan.value & " "
    
    
    End If

    'UL Values and total UL specified amount.  MVVAL created from LH_POL_MVRY_VAL (75 Segment) & LH_NON_TRD_POL (66 segment)
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_DisplayAccountValue_02_75 Or _
        Me.CheckBox_ULInCorridor Or _
        CheckBox_AccumulationValueGTPremiumPaid Or _
        CheckBox_ISWL_GCVGTCurrCV Or _
        CheckBox_ISWL_GCVLTCurrCV Or _
        CheckBox_ShowAccumulationValue Or _
        CheckBox_ShowPremiumPTD Or _
        TextBox_AVGreaterThan <> "" Or _
        TextBox_AVLessThan <> "" Then
        sqlstring = sqlstring & "LEFT OUTER JOIN MVVAL  "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = MVVAL.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = MVVAL.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = MVVAL.TCH_POL_ID "

    End If

    'Mulitple Base Coverages.  COVSUMMARY created from ALL_BASE_COVS which is created from two instances of LH_COV_PHA
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_MulitpleBaseCoverages Or CheckBox_CurrentSALTOriginalSA Or CheckBox_CurrentSAGTOriginalSA Or CheckBox_ShowSpecifiedAmount Or TextBox_CurrentSAGreaterThan <> "" Or TextBox_CurrentSALessThan <> "" Or _
        Me.CheckBox_ULInCorridor Or CheckBox_AccumulationValueGTPremiumPaid Or CheckBox_ISWL_GCVGTCurrCV Or CheckBox_ISWL_GCVLTCurrCV Then
        sqlstring = sqlstring & "INNER JOIN COVSUMMARY "
            sqlstring = sqlstring & "ON COVSUMMARY.TCH_POL_ID = POLICY1.TCH_POL_ID "
            sqlstring = sqlstring & "AND COVSUMMARY.CK_CMP_CD = POLICY1.CK_CMP_CD "
            sqlstring = sqlstring & "AND COVSUMMARY.CK_SYS_CD = POLICY1.CK_SYS_CD "
            If CheckBox_MulitpleBaseCoverages Then sqlstring = sqlstring & "AND (COVSUMMARY.BASECOVCOUNT > 1) "
            If TextBox_CurrentSAGreaterThan <> "" Then sqlstring = sqlstring & "AND (COVSUMMARY.TOTAL_SA >= " & TextBox_CurrentSAGreaterThan & " ) "
            If TextBox_CurrentSALessThan <> "" Then sqlstring = sqlstring & "AND (COVSUMMARY.TOTAL_SA <= " & TextBox_CurrentSALessThan & " ) "
    End If
   
    'Billing modes. BILLMODE_POOL created from two instances of LH_BAS_POL
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If Me.CheckBox_SpecifyBillingModes Or CheckBox_ShowBillingMode Then
        sqlstring = sqlstring & "INNER JOIN BILLMODE_POOL  "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = BILLMODE_POOL.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = BILLMODE_POOL.CK_CMP_CD "
             sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = BILLMODE_POOL.TCH_POL_ID "
    End If
        
    'Grace Period Ending Date. GRACE_TABLE created from LH_NON_TRD_POL and LH_TRD_POL
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If TextBox_LowGPEDate.value <> "" Or TextBox_HighGPEDate.value <> "" Or Me.CheckBox_GraceIndicator Or CheckBox_ShowGPEDate Then
        sqlstring = sqlstring & "INNER JOIN GRACE_TABLE  "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = GRACE_TABLE.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = GRACE_TABLE.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = GRACE_TABLE.TCH_POL_ID "
            If TextBox_LowGPEDate.value <> "" Then sqlstring = sqlstring & "AND (GRACE_TABLE.GRA_PER_EXP_DT >= '" & Format(TextBox_LowGPEDate.value, "yyyy-mm-dd") & "') "
            If TextBox_HighGPEDate.value <> "" Then sqlstring = sqlstring & "AND (GRACE_TABLE.GRA_PER_EXP_DT <= '" & Format(TextBox_HighGPEDate.value, "yyyy-mm-dd") & "') "
            
    End If
            
    'Add GLP
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_GLPIsNegative Or CheckBox_ShowGLP Then
        sqlstring = sqlstring & "INNER JOIN GLP "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = GLP.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = GLP.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = GLP.TCH_POL_ID "
    End If
   
    'Add GSP
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_ShowGSP Then
        sqlstring = sqlstring & "LEFT OUTER JOIN GSP "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = GSP.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = GSP.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = GSP.TCH_POL_ID "
    End If
   
   
    'Guarnateed Cash Value for ISWL
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_ISWL_GCVGTCurrCV Or CheckBox_ISWL_GCVLTCurrCV Then
        sqlstring = sqlstring & "INNER JOIN ISWL_INTERPOLATED_GCV "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = ISWL_INTERPOLATED_GCV.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = ISWL_INTERPOLATED_GCV.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = ISWL_INTERPOLATED_GCV.TCH_POL_ID "
    End If
   
    'Add Interpolated Months
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_DisplayTradCVCov1 Then
        sqlstring = sqlstring & "LEFT OUTER JOIN INTERPOLATION_MONTHS "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = INTERPOLATION_MONTHS.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = INTERPOLATION_MONTHS.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = INTERPOLATION_MONTHS.TCH_POL_ID "
    End If
    
    
    'Original face amount for policies on RPU
    '-----------------------------------------------------------------------------------------------------------------------------------------
    If CheckBox_RPUOriginalAmt Then
           sqlstring = sqlstring & "LEFT OUTER JOIN CHANGE_TYPE9 "
            sqlstring = sqlstring & "ON POLICY1.CK_SYS_CD = CHANGE_TYPE9.CK_SYS_CD "
            sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD = CHANGE_TYPE9.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = CHANGE_TYPE9.TCH_POL_ID "
    End If
  
    'Transactions. FH_FIXED tables (69 segment)
    '-----------------------------------------------------------------------------------------------------------------------------------------
    blnTransaction1 = ComboBox_Transaction1 <> "" Or TextBox_Transaction1LowEntryDate <> "" Or TextBox_Transaction1HighEntryDate <> "" Or TextBox_Transaction1LowEffectiveDate <> "" Or TextBox_Transaction1HighEffectiveDate <> "" Or TextBox_Origin_of_Trans <> ""
    If blnTransaction1 Then
        sqlstring = sqlstring & "INNER JOIN DB2TAB.FH_FIXED TR1 "
            sqlstring = sqlstring & "ON POLICY1.CK_CMP_CD = TR1.CK_CMP_CD "
            sqlstring = sqlstring & "AND POLICY1.TCH_POL_ID = TR1.TCH_POL_ID "
            If ComboBox_Transaction1 <> "" Then sqlstring = sqlstring & "AND (TR1.TRANS = '" & left(ComboBox_Transaction1, 2) & "') "
            If TextBox_Transaction1LowEntryDate <> "" Then sqlstring = sqlstring & "AND TR1.ENTRY_DT >= '" & Format(TextBox_Transaction1LowEntryDate, "yyyy-mm-dd") & "' "
            If TextBox_Transaction1HighEntryDate <> "" Then sqlstring = sqlstring & "AND TR1.ENTRY_DT <= '" & Format(TextBox_Transaction1HighEntryDate, "yyyy-mm-dd") & "' "
            If TextBox_Transaction1LowEffectiveDate <> "" Then sqlstring = sqlstring & "AND TR1.ASOF_DT >= '" & Format(TextBox_Transaction1LowEffectiveDate, "yyyy-mm-dd") & "' "
            If TextBox_Transaction1HighEffectiveDate <> "" Then sqlstring = sqlstring & "AND TR1.ASOF_DT <= '" & Format(TextBox_Transaction1HighEffectiveDate, "yyyy-mm-dd") & "' "
            If CheckBox_Transaction1OnIssueDay Then sqlstring = sqlstring & "AND DAY(TR1.ASOF_DT) = DAY(COVERAGE1.ISSUE_DT) "
            If CheckBox_Transaction1OnIssueMonth Then sqlstring = sqlstring & "AND MONTH(TR1.ASOF_DT) = MONTH(COVERAGE1.ISSUE_DT) "
            
            If TextBox_Transaction1EffMonthLow <> "" Then sqlstring = sqlstring & "AND MONTH(TR1.ASOF_DT) >= " & TextBox_Transaction1EffMonthLow & " "
            If TextBox_Transaction1EffMonthHigh <> "" Then sqlstring = sqlstring & "AND MONTH(TR1.ASOF_DT) <= " & TextBox_Transaction1EffMonthHigh & " "
            
            If TextBox_Transaction1EffDayLow <> "" Then sqlstring = sqlstring & "AND DAY(TR1.ASOF_DT) >= " & TextBox_Transaction1EffDayLow & " "
            If TextBox_Transaction1EffDayHigh <> "" Then sqlstring = sqlstring & "AND DAY(TR1.ASOF_DT) <= " & TextBox_Transaction1EffDayHigh & " "
            
            If TextBox_Transaction1GrossAmtLow <> "" Then sqlstring = sqlstring & "AND TR1.GROSS_AMT >= " & TextBox_Transaction1GrossAmtLow & " "
            If TextBox_Transaction1GrossAmtHigh <> "" Then sqlstring = sqlstring & "AND TR1.GROSS_AMT <= " & TextBox_Transaction1GrossAmtHigh & " "
            
            If TextBox_Origin_of_Trans <> "" Then sqlstring = sqlstring & "AND TR1.ORIGIN_OF_TRANS ='" & TextBox_Origin_of_Trans.value & "'" & " "
            
            If TextBox_FundIDList <> "" Then sqlstring = sqlstring & "AND TR1.FUND_ID IN(" & ListOfStringValuesSQL(TextBox_FundIDList.value) & ")" & " "

            
    End If


'WHERE clause
'-----------------------------------------------------------------------------------------------------------------------------------------
sqlstring = sqlstring & "WHERE 1 = 1 "

    If ComboBox_SystemCode <> "" Then sqlstring = sqlstring & " AND POLICY1.CK_SYS_CD='" & ComboBox_SystemCode & "' "
    
  
    'If Company is not specified but MarketOrg is, then find the valid companies for the Market Org.
    'For example if MarketOrg = "CSSD", then the only valid company to search with is "ANICO"
    If Me.ComboBox_MarketOrg.value <> ANY_SELECTION And ComboBox_Company.value = ANY_SELECTION Then
        Dim sqlCompanyString As String
        Select Case Me.ComboBox_MarketOrg
            Case "CSSD": sqlCompanyString = " POLICY1.CK_CMP_CD ='01' "
            Case "IMG": sqlCompanyString = " POLICY1.CK_CMP_CD ='01' OR POLICY1.CK_CMP_CD ='26' "
            Case "MLM": sqlCompanyString = " POLICY1.CK_CMP_CD ='01' OR POLICY1.CK_CMP_CD ='26' "
            Case "DIRECT": sqlCompanyString = " POLICY1.CK_CMP_CD ='01' OR POLICY1.CK_CMP_CD ='26' "
            Case "GSL": sqlCompanyString = " POLICY1.CK_CMP_CD ='08' "
            Case "ANTEX": sqlCompanyString = " POLICY1.CK_CMP_CD ='04' "
            Case "SLAICO": sqlCompanyString = " POLICY1.CK_CMP_CD ='06' "
        End Select
        sqlstring = sqlstring & "AND (" & sqlCompanyString & ") "
    Else
        'Translate Company code
        
        Dim CompanyCode As String
        CompanyCode = IIf(ComboBox_Company.value = ANY_SELECTION, ANY_SELECTION, CompanyDictionary(ComboBox_Company.value))
        If CompanyCode <> ANY_SELECTION Then sqlstring = sqlstring & "AND POLICY1.CK_CMP_CD ='" & CompanyCode & "' "
    End If
    
    'Translate Market Org
    Dim MarketOrg As String
    MarketOrg = DetermineMarketOrgCode(Me.ComboBox_MarketOrg)
    If ComboBox_MarketOrg <> ANY_SELECTION Then sqlstring = sqlstring & "AND SUBSTR(POLICY1.SVC_AGC_NBR,1,1)='" & MarketOrg & "' "
    If TextBox_BranchNumber <> "" Then sqlstring = sqlstring & "AND SUBSTR(POLICY1.SVC_AGC_NBR,2,3)='" & TextBox_BranchNumber.value & "' "
    
    
    If TextBox_LoanChargeRate.value <> "" Then sqlstring = sqlstring & "AND POLICY1.LN_PLN_ITS_RT = " & TextBox_LoanChargeRate.value & " "

    'TAMRA (59 segment)
    If Me.CheckBox_MEC Then sqlstring = sqlstring & "AND TAMRA.MEC_STA_CD = '1' "
    If Me.CheckBox_1035Amount Then sqlstring = sqlstring & "AND TAMRA.XCG_1035_PMT_QTY > 0 "
    If Me.TextBox_7PayGreaterThan <> "" Then sqlstring = sqlstring & "AND TAMRA.SVPY_LVL_PRM_AMT >= " & TextBox_7PayGreaterThan & " "
    If Me.TextBox_7PayLessThan <> "" Then sqlstring = sqlstring & "AND TAMRA.SVPY_LVL_PRM_AMT <= " & TextBox_7PayLessThan & " "
    
    If Me.TextBox_7PayAVGreaterThan <> "" Then sqlstring = sqlstring & "AND TAMRA.SVPY_BEG_CSV_AMT >= " & TextBox_7PayAVGreaterThan & " "
    If Me.TextBox_7PayAVLessThan <> "" Then sqlstring = sqlstring & "AND TAMRA.SVPY_BEG_CSV_AMT <= " & TextBox_7PayAVLessThan & " "
    
    
    'Policy Totals
    If Me.TextBox_AccumWDGreaterThan <> "" Then sqlstring = sqlstring & "AND POLICY_TOTALS.TOT_WTD_AMT >= " & TextBox_AccumWDGreaterThan & " "
    If Me.TextBox_AccumWDLessThan <> "" Then sqlstring = sqlstring & "AND POLICY_TOTALS.TOT_WTD_AMT <= " & TextBox_AccumWDLessThan & " "
    
    If Me.TextBox_PremYTDGreaterThan <> "" Then sqlstring = sqlstring & "AND POLICY_TOTALS_YTD.YTD_TOT_PMT_AMT >= " & TextBox_PremYTDGreaterThan & " "
    If Me.TextBox_PremYTDLessThan <> "" Then sqlstring = sqlstring & "AND POLICY_TOTALS_YTD.YTD_TOT_PMT_AMT <= " & TextBox_PremYTDLessThan & " "
    
    If TextBox_AdditionalPremGreaterThan <> "" Then sqlstring = sqlstring & "AND POLICY_TOTALS.TOT_ADD_PRM_AMT >= " & CDbl(TextBox_AdditionalPremGreaterThan) & " "
    If TextBox_AdditionalPremLessThan <> "" Then sqlstring = sqlstring & "AND POLICY_TOTALS.TOT_ADD_PRM_AMT <= " & CDbl(TextBox_AdditionalPremLessThan) & " "
    
    If TextBox_TotalPremGreaterThan <> "" Then sqlstring = sqlstring & "AND (POLICY_TOTALS.TOT_ADD_PRM_AMT + POLICY_TOTALS.TOT_REG_PRM_AMT) >= " & CDbl(TextBox_AdditionalPremGreaterThan) & " "
    If TextBox_TotalPremLessThan <> "" Then sqlstring = sqlstring & "AND (POLICY_TOTALS.TOT_ADD_PRM_AMT + POLICY_TOTALS.TOT_REG_PRM_AMT) <= " & CDbl(TextBox_AdditionalPremGreaterThan) & " "

    If TextBox_LowPaidToDate.value <> "" Then sqlstring = sqlstring & "AND POLICY1.PRM_PAID_TO_DT >=  '" & Format(TextBox_LowPaidToDate.value, "yyyy-mm-dd") & "' "
    If TextBox_HighPaidToDate.value <> "" Then sqlstring = sqlstring & "AND POLICY1.PRM_PAID_TO_DT <= '" & Format(TextBox_HighPaidToDate.value, "yyyy-mm-dd") & "' "
       
    If TextBox_LowLastFinancialDate.value <> "" Then sqlstring = sqlstring & "AND POLICY1.LST_FIN_DT >=  '" & Format(TextBox_LowLastFinancialDate.value, "yyyy-mm-dd") & "' "
    If TextBox_HighLastFinancialDate.value <> "" Then sqlstring = sqlstring & "AND POLICY1.LST_FIN_DT <= '" & Format(TextBox_HighLastFinancialDate.value, "yyyy-mm-dd") & "' "

    If TextBox_LowAppDate.value <> "" Then sqlstring = sqlstring & "AND POLICY1.APP_WRT_DT >=  '" & Format(TextBox_LowAppDate.value, "yyyy-mm-dd") & "' "
    If TextBox_HighAppDate.value <> "" Then sqlstring = sqlstring & "AND POLICY1.APP_WRT_DT <= '" & Format(TextBox_HighAppDate.value, "yyyy-mm-dd") & "' "

    
    'Add SQL logic to restrict by attained age input.  Since there is no AttainedAge field in COVERAGE1, logic is used to determine the
    'corresponding issue ages that meet the criteria
    If TextBox_LowCurrentAge <> "" Then sqlstring = sqlstring & "AND COVERAGE1.INS_ISS_AGE >= (" & CInt(TextBox_LowCurrentAge) & " - TRUNCATE(MONTHS_BETWEEN('" & Format(Now(), "yyyy-mm-dd") & "',COVERAGE1.ISSUE_DT)/12,0)) "
    If TextBox_HighCurrentAge <> "" Then sqlstring = sqlstring & "AND COVERAGE1.INS_ISS_AGE <= (" & CInt(TextBox_HighCurrentAge) & "  - TRUNCATE(MONTHS_BETWEEN('" & Format(Now(), "yyyy-mm-dd") & "',COVERAGE1.ISSUE_DT)/12,0)) "
      
      
    If TextBox_LowCurrentPolicyYear <> "" Then sqlstring = sqlstring & "AND (TRUNCATE(MONTHS_BETWEEN('" & Format(Now(), "yyyy-mm-dd") & "',COVERAGE1.ISSUE_DT)/12,0) +1) >= " & CInt(TextBox_LowCurrentPolicyYear) & " "
    If TextBox_HighCurrentPolicyYear <> "" Then sqlstring = sqlstring & "AND (TRUNCATE(MONTHS_BETWEEN('" & Format(Now(), "yyyy-mm-dd") & "',COVERAGE1.ISSUE_DT)/12,0) +1) <= " & CInt(TextBox_HighCurrentPolicyYear) & " "
      
    If TextBox_LowLastChangeDate.value <> "" Then sqlstring = sqlstring & "AND NEWBUS.LST_CHG_DT >=  '" & Format(TextBox_LowLastChangeDate.value, "yyyy-mm-dd") & "' "
    If TextBox_HighLastChangeDate.value <> "" Then sqlstring = sqlstring & "AND NEWBUS.LST_CHG_DT <=  '" & Format(TextBox_HighLastChangeDate.value, "yyyy-mm-dd") & "' "

    If TextBox_LowBillCommenceDate.value <> "" Then sqlstring = sqlstring & "AND NONTRAD.BIL_COMMENCE_DT >=  '" & Format(TextBox_LowBillCommenceDate.value, "yyyy-mm-dd") & "' "
    If TextBox_HighBillCommenceDate.value <> "" Then sqlstring = sqlstring & "AND NONTRAD.BIL_COMMENCE_DT <=  '" & Format(TextBox_HighBillCommenceDate.value, "yyyy-mm-dd") & "' "
        
    If TextBox_PolicyNumberContains.value <> "" Then
        Select Case left(ComboBox_PolicynumberCriteria.value, 1)
            '1 = Starts with, 2 = Ends with, 3 = Contains
            Case 1: sqlstring = sqlstring & "AND (TRIM(TRAILING FROM POLICY1.CK_POLICY_NBR) Like  '" & TextBox_PolicyNumberContains.value & "%') "
            Case 2: sqlstring = sqlstring & "AND (TRIM(TRAILING FROM POLICY1.CK_POLICY_NBR) Like  '%" & TextBox_PolicyNumberContains.value & "') "
            Case 3: sqlstring = sqlstring & "AND (TRIM(TRAILING FROM POLICY1.CK_POLICY_NBR) Like  '%" & TextBox_PolicyNumberContains.value & "%') "
            Case Else
        End Select
    End If
    
    
    If TextBox_FormNumberLikeAllCovs.value <> "" Then sqlstring = sqlstring & "AND (COVERAGE1.POL_FRM_NBR Like  '" & TextBox_FormNumberLikeAllCovs.value & "%') "
   
    If TextBox_LowBillingPrem.value <> "" Then sqlstring = sqlstring & "AND POLICY1.POL_PRM_AMT >= " & CDbl(TextBox_LowBillingPrem.value) & " "
    If TextBox_HighBillingPrem.value <> "" Then sqlstring = sqlstring & "AND POLICY1.POL_PRM_AMT <= " & CDbl(TextBox_HighBillingPrem.value) & " "
    

   
    'Add state codes.
    'Can't use AddListBoxEntriesToSQL because the Cyberlife state code is not part of the what is displayed in the list box
    dct.RemoveAll
    If Me.CheckBox_SpecifyState Then
        For i = 0 To ListBox_State.ListCount - 1
            If ListBox_State.Selected(i) = True Then dct.Add "POLICY1.POL_ISS_ST_CD = '" & Format(StateDictionary(ListBox_State.List(i)), "00") & "'", ""
        Next i
        If dct.Count > 0 Then sqlstring = sqlstring & "AND (" & Join(dct.Keys, " OR ") & ") "
        dct.RemoveAll
    End If

    'If Me.CheckBox_SpecifyStatusCodes Then AddListBoxEntriesToSQL SQLString, Me.ListBox_SuspenseCode, "POLICY1.SUS_CD", 1
    If Me.CheckBox_SpecifyBillingForm Then AddListBoxEntriesToSQL sqlstring, ListBox_BillingForm, "POLICY1.BIL_FRM_CD", 1
    If Me.CheckBox_SpecifySLRBillingForm Then AddListBoxEntriesToSQL sqlstring, ListBox_SLRBillingForm, "SLR_BILL_CONTROL.BIL_FRM_CD", 1
    
    If Me.CheckBox_SpecifyNFO Then AddListBoxEntriesToSQL sqlstring, ListBox_NFO, "POLICY1.NFO_OPT_TYP_CD", 1
    If Me.CheckBox_SpecifyLoanType Then AddListBoxEntriesToSQL sqlstring, ListBox_LoanType, "POLICY1.LN_TYP_CD", 1
    If Me.CheckBox_SpecifyPrimaryDivOpt Then AddListBoxEntriesToSQL sqlstring, ListBox_PrimaryDivOption, "POLICY1.PRI_DIV_OPT_CD", 1
    If Me.CheckBox_SpecifyStatusCodes Then AddListBoxEntriesToSQL sqlstring, ListBox_StatusCode, "POLICY1.PRM_PAY_STA_REA_CD", 2
    If CheckBox_GraceIndicator Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_GraceIndicator, "SUBSTR(GRACE_TABLE.IN_GRA_PER_IND,1,1)", 1
    If CheckBox_OverloanIndicator Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_OverloanIndicator, "POLICY1_MOD.OVERLOAN_IND", 1
    If CheckBox_SuspenseCode Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_SuspenseCode, "POLICY1.SUS_CD", 1
    If CheckBox_ReinsuranceCode Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_ReinsuranceCode, "POLICY1.REINSURED_CD", 1
    If CheckBox_NonTradIndicator Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_NonTradIndicator, "POLICY1.NON_TRD_POL_IND", 1
    If CheckBox_SpecifyLastEntryCode Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_LastEntryCodes, "POLICY1.LST_ETR_CD", 1
    If CheckBox_SpecifyOrigEntryCode Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_OrigEntryCode, "POLICY1.OGN_ETR_CD", 1
    
    If CheckBox_ULInCorridor Then sqlstring = sqlstring & "AND (MVVAL.DB > COVSUMMARY.TOTAL_SA + MVVAL.OPTDB) "
    If CheckBox_AccumulationValueGTPremiumPaid Then sqlstring = sqlstring & "AND (MVVAL.CSV_AMT >= MVVAL.TOTALPREM) "
    If CheckBox_GLPIsNegative Then sqlstring = sqlstring & "AND (GLP.GLP_VALUE < 0) "
    If CheckBox_CurrentSALTOriginalSA Then sqlstring = sqlstring & "AND (COVSUMMARY.TOTAL_SA <= COVSUMMARY.TOTAL_ORIGINAL_SA) "
    If CheckBox_CurrentSAGTOriginalSA Then sqlstring = sqlstring & "AND (COVSUMMARY.TOTAL_SA >= COVSUMMARY.TOTAL_ORIGINAL_SA) "
    If CheckBox_ISWL_GCVGTCurrCV Then sqlstring = sqlstring & "AND (ISWL_INTERPOLATED_GCV.ISWL_GCV >= MVVAL.CSV_AMT) "
    If CheckBox_ISWL_GCVLTCurrCV Then sqlstring = sqlstring & "AND (ISWL_INTERPOLATED_GCV.ISWL_GCV <= MVVAL.CSV_AMT) "
    If TextBox_AVGreaterThan <> "" Then sqlstring = sqlstring & "AND (MVVAL.CSV_AMT > " & CDbl(TextBox_AVGreaterThan.value) & " ) "
    If TextBox_AVLessThan <> "" Then sqlstring = sqlstring & "AND (MVVAL.CSV_AMT < " & CDbl(TextBox_AVLessThan.value) & " ) "
    
    If TextBox_ShadowAVGreaterThan <> "" Then sqlstring = sqlstring & "AND (SHADOWAV.TAR_PRM_AMT >= " & CDbl(TextBox_ShadowAVGreaterThan.value) & " ) "
    If TextBox_ShadowAVLessThan <> "" Then sqlstring = sqlstring & "AND (SHADOWAV.TAR_PRM_AMT <= " & CDbl(TextBox_ShadowAVLessThan.value) & " ) "
    
    If TextBox_AccumMTPGreaterThan <> "" Then sqlstring = sqlstring & "AND (ACCUMMTP.TAR_PRM_AMT >= " & CDbl(TextBox_AccumMTPGreaterThan.value) & " ) "
    If TextBox_AccumMTPLessThan <> "" Then sqlstring = sqlstring & "AND (ACCUMMTP.TAR_PRM_AMT <= " & CDbl(TextBox_AccumMTPLessThan.value) & " ) "
    
    If TextBox_AccumGLPGreaterThan <> "" Then sqlstring = sqlstring & "AND (ACCUMGLP.TAR_PRM_AMT >= " & CDbl(TextBox_AccumGLPGreaterThan.value) & " ) "
    If TextBox_AccumGLPLessThan <> "" Then sqlstring = sqlstring & "AND (ACCUMGLP.TAR_PRM_AMT <= " & CDbl(TextBox_AccumGLPLessThan.value) & " ) "
    
    If CheckBox_IsMDO Then sqlstring = sqlstring & "AND SUBSTR(POLICY1.USR_RES_CD,1,1) = 'Y' "
    
    If CheckBox_IsRGA Then sqlstring = sqlstring & "AND USERDEF_52G.FUZGREIN_IND = 'R' "
    
    If CheckBox_HasChangeSegment Then AddListBoxEntriesToSQL sqlstring, Me.ListBox_68SegmentChangeCodes, "CHANGE_SEGMENT.CHG_TYP_CD", 1

    'This checks to see if policy is still in the conversion period
    If CheckBox_SpecifyWithinConversionPeriod Then
    'checks if duration is less than Conversion Period OR if policy attained age is less than Conversion-to-Age.
        'sqlstring = sqlstring & "AND (CASE WHEN (" & DurationCalc & " < 1 * UPDF.CONVERSION_PERIOD) OR (" & AttainedAgeCalc & " < 1 * UPDF.CONVERSION_AGE) THEN 'TRUE' ELSE 'FALSE' END) = 'TRUE' "
        sqlstring = sqlstring & "AND (CASE "
        sqlstring = sqlstring & "WHEN "
        sqlstring = sqlstring & "(UPDF.CONVERSION_PERIOD = 0 AND COVERAGE1.INS_ISS_AGE + TRUNCATE(MONTHS_BETWEEN(DATE('2025-06-08'), COVERAGE1.ISSUE_DT) / 12, 0) < UPDF.CONVERSION_AGE) "
        sqlstring = sqlstring & "OR "
        sqlstring = sqlstring & "(UPDF.CONVERSION_PERIOD > 0 AND TRUNCATE(MONTHS_BETWEEN(DATE('2025-06-08'), COVERAGE1.ISSUE_DT) / 12, 0) < UPDF.CONVERSION_PERIOD AND COVERAGE1.INS_ISS_AGE + TRUNCATE(MONTHS_BETWEEN(DATE('2025-06-08'), COVERAGE1.ISSUE_DT) / 12, 0) < UPDF.CONVERSION_AGE) "
        sqlstring = sqlstring & "THEN 'TRUE' "
        sqlstring = sqlstring & "ELSE 'FALSE' "
        sqlstring = sqlstring & "END "
        sqlstring = sqlstring & ") = 'TRUE' "
    End If
    
    'GROUP BY
    If Not (ToggleButton_GetAll) Then sqlstring = sqlstring & "FETCH FIRST " & TextBox_MaxCount.value & " ROWS ONLY;"

sqlstring = SQLStringForRegion(sqlstring, ComboBox_Region.value)

Debug.Print sqlstring

BuildSQLString = sqlstring


Set dct = Nothing


End Function

Private Sub AddListBoxEntriesToSQL_Unrestricted(ByRef strSQL As String, lb As MSForms.Listbox, strTableAndFieldName)
'This procedure reads the selected entries in a List box and assignes the values to the giving field name.
'This can only be used if the listbox entry begins with the code to be assinged.  inLeftLength determines how many
'characters to pull from the listbox entry text
Dim dct As Dictionary
Set dct = New Dictionary
     Dim i As Integer
     For i = 0 To lb.ListCount - 1
       dct.Add strTableAndFieldName & " ='" & lb.Column(0, i) & "'", ""
     Next i
     If dct.Count > 0 Then strSQL = strSQL & "AND (" & Join(dct.Keys, " OR ") & ") "
Set dct = Nothing
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
Property Get IsPopulated()
 'This property allows a test to see if PopulateForm has already been executed.  PopulateForm will clear all current settings and should not occur after the form is initially openned
 IsPopulated = blnIsPopulated
End Property


Private Function BuildSQLStringToFindBase() As String
Dim sqlstring As String

sqlstring = sqlstring & "SELECT RIDERS.PLN_DES_SER_CD "
sqlstring = sqlstring & ",RIDERS.POL_FRM_NBR "
sqlstring = sqlstring & ",POL_ISSUE.PLN_DES_SER_CD "
sqlstring = sqlstring & ",POL_ISSUE.POL_FRM_NBR "
sqlstring = sqlstring & IIf(CheckBox_BaseSearchShowPolicies, ", SUBSTR(RIDERS.TCH_POL_ID,1,10) ", ", COUNT(RIDERS.PLN_DES_SER_CD) ")

sqlstring = sqlstring & "FROM DB2TAB.LH_COV_PHA RIDERS "

sqlstring = sqlstring & "INNER JOIN DB2TAB.LH_COV_PHA POL_ISSUE  "
         sqlstring = sqlstring & "ON (RIDERS.CK_SYS_CD = POL_ISSUE.CK_SYS_CD) "
         sqlstring = sqlstring & "AND (RIDERS.CK_CMP_CD = POL_ISSUE.CK_CMP_CD) "
         sqlstring = sqlstring & "AND (RIDERS.TCH_POL_ID = POL_ISSUE.TCH_POL_ID) "
         sqlstring = sqlstring & "AND (POL_ISSUE.COV_PHA_NBR = 1) "

sqlstring = sqlstring & "WHERE    (RIDERS.PLN_DES_SER_CD = '" & Trim(TextBox_RiderPlancodeForBaseSearch.value) & "') "
    sqlstring = sqlstring & " AND  RIDERS.COV_PHA_NBR > 1 "
    

If Me.CheckBox_BaseSearchShowPolicies Then
  sqlstring = sqlstring & ""
Else
  sqlstring = sqlstring & "GROUP BY RIDERS.PLN_DES_SER_CD, RIDERS.POL_FRM_NBR, POL_ISSUE.PLN_DES_SER_CD, POL_ISSUE.POL_FRM_NBR;    "
End If

BuildSQLStringToFindBase = sqlstring

'Debug.Print SQLString

End Function

Private Function BuildSQLStringToFindRiders()
Dim sqlstring As String

sqlstring = sqlstring & "SELECT POL_ISSUE.PLN_DES_SER_CD "
sqlstring = sqlstring & ", POL_ISSUE.POL_FRM_NBR "
sqlstring = sqlstring & ", RIDERS.PLN_DES_SER_CD "
sqlstring = sqlstring & ", RIDERS.POL_FRM_NBR "
sqlstring = sqlstring & IIf(CheckBox_BaseSearchShowPolicies, ", SUBSTR(RIDERS.TCH_POL_ID,1,10) ", ", COUNT(RIDERS.PLN_DES_SER_CD) ")

sqlstring = sqlstring & "FROM DB2TAB.LH_COV_PHA RIDERS "

sqlstring = sqlstring & " INNER JOIN DB2TAB.LH_COV_PHA POL_ISSUE "
         sqlstring = sqlstring & "ON (RIDERS.CK_SYS_CD = POL_ISSUE.CK_SYS_CD) "
         sqlstring = sqlstring & "AND (RIDERS.CK_CMP_CD = POL_ISSUE.CK_CMP_CD) "
         sqlstring = sqlstring & "AND (RIDERS.TCH_POL_ID = POL_ISSUE.TCH_POL_ID) "
         sqlstring = sqlstring & "AND (POL_ISSUE.COV_PHA_NBR = 1) "
         sqlstring = sqlstring & "AND (POL_ISSUE.PLN_DES_SER_CD  = '" & Trim(TextBox_BasePlancodeForRiderSearch.value) & "') "

sqlstring = sqlstring & "WHERE    (RIDERS.PLN_DES_SER_CD <> '" & Trim(TextBox_BasePlancodeForRiderSearch.value) & "' "
    sqlstring = sqlstring & " AND  RIDERS.COV_PHA_NBR > 1) "
    
If Me.CheckBox_RiderSearchShowPolicies Then
  sqlstring = sqlstring & ""
Else
   sqlstring = sqlstring & "GROUP BY POL_ISSUE.PLN_DES_SER_CD,  POL_ISSUE.POL_FRM_NBR, RIDERS.PLN_DES_SER_CD, RIDERS.POL_FRM_NBR;    "
End If

BuildSQLStringToFindRiders = sqlstring

'Debug.Print SQLString

End Function

Private Function BuildSQLStringToFindValues()
Dim sqlstring As String
Dim Tablename As String, Fieldname As String, DB2Name As String

Tablename = Trim(TextBox_TableNameForValueSearch.value)
Fieldname = Trim(TextBox_FieldNameForValueSearch.value)
DB2Name = Tablename & "." & Fieldname

sqlstring = sqlstring & "SELECT VALUES_TBL." & Fieldname & ", COUNT(VALUES_TBL.TCH_POL_ID) "
sqlstring = sqlstring & "FROM " & "DB2TAB." & Tablename & " VALUES_TBL "
sqlstring = sqlstring & "GROUP BY VALUES_TBL." & Fieldname & "; "

BuildSQLStringToFindValues = sqlstring

End Function

Private Sub CommandButton_PlancodePicker_Click()
    If Not frmPlancodeSelection.IsActive Then frmPlancodeSelection.classInitialize Me
    frmPlancodeSelection.Show vbModeless

End Sub
Private Sub Label_RemoveAllPlancodes_Click()
    Me.ListBox_MultiplePlancodes.Clear
End Sub

Private Sub Label_RemoveSelectedPlancodes_Click()
    With ListBox_MultiplePlancodes
    Dim X As Integer
    X = .ListCount - 1
    Do Until X < 0
       If .Selected(X) Then .RemoveItem (X)
       X = X - 1
    Loop
    End With
End Sub

Private Function SelectedCount(lb As MSForms.Listbox) As Integer
Dim tempFundCount As Integer
Dim i As Integer
For i = 0 To lb.ListCount - 1
    If lb.Selected(i) Then tempFundCount = tempFundCount + 1
Next
SelectedCount = tempFundCount
End Function


Private Sub TextBox_ETIMortalityTable_Change()
TextBox_ETIMortalityTable = UCase(TextBox_ETIMortalityTable)
End Sub

Private Sub TextBox_RPUMortalityTable_Change()
TextBox_RPUMortalityTable = UCase(TextBox_RPUMortalityTable)
End Sub

Private Sub TextBox_ValuationMortalityTable_Change()
  TextBox_ValuationMortalityTable.value = UCase(TextBox_ValuationMortalityTable.value)
  
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



Private Sub VDisplay_ListBoxDoubleClick(lbx As MSForms.Listbox)
    On Error GoTo ErrHandler
    Dim PolicyNumber As String
    Dim CompanyCode As String

    PolicyNumber = lbx.Column(1, lbx.ListIndex)
    CompanyCode = lbx.Column(2, lbx.ListIndex)
    CreatePolicyForm GetPolicy(PolicyNumber, ComboBox_Region.value, "I", CompanyCode)
    Exit Sub

ErrHandler:
    MsgBox "Error in ListBoxDoubleClick: " & Err.Description
End Sub



