' Module: mdlUtilities_for_Policies.bas
' Type: Standard Module
' Stream Path: VBA/mdlUtilities_for_Policies
' =========================================================

Attribute VB_Name = "mdlUtilities_for_Policies"


Private Function ObjectStateString(ObjectState As ADODB.ObjectStateEnum) As String
'Code from http://stackoverflow.com/questions/632385/how-can-i-best-use-vba-in-access-or-excel-to-test-an-odbc-connection

Select Case ObjectState
    Case ADODB.ObjectStateEnum.adStateClosed:    ObjectStateString = "Closed"
    Case ADODB.ObjectStateEnum.adStateConnecting:    ObjectStateString = "Connecting"
    Case ADODB.ObjectStateEnum.adStateExecuting:    ObjectStateString = "Executing"
    Case ADODB.ObjectStateEnum.adStateFetching:    ObjectStateString = "Fetching"
    Case ADODB.ObjectStateEnum.adStateOpen:    ObjectStateString = "Open"
    Case Else:    ObjectStateString = "State " & CLng(ObjectState) & ": unknown state number"
End Select

End Function

Public Function IsModalMonth(MonthOfYear As Integer, ModeNumber As Integer) As Boolean
'Give the MonthOfYear (a value from 1 to 12) and the the number of months between payments (1, 3, 6, 12) this function returns true if the month is a modal month
    Dim ModResult As Integer
   
    ModResult = ((ModeNumber - 1) Mod MonthOfYear + 1)
    
    If ModResult = 1 Then
        IsModalMonth = True
    Else
        IsModalMonth = False
    End If

End Function

Public Function IsMonthliversary(dt, PolicyIssueDate As Date) As Boolean
 EndOfMonthDate = DateSerial(Year(dt), Month(dt) + 1, 0)
 EndOfMonthDay = Day(EndOfMonthDate)
 IsMonthliversary = (Day(dt) = fmin(EndOfMonthDay, Day(PolicyIssueDate)))
End Function

Public Function MonthOfYear2(IssueDate As Date, ValuationDate As Date) As Integer
'This function finds the month of year for any valuation date.  This function returns a value from 1 to 12
Dim IssueDay As Integer, ValuationDay As Integer
IssueDay = Day(IssueDate)
ValuationDay = Day(ValuationDate)

If ValuationDay >= IssueDay Then
    MonthOfYear_OffMonthliversary = MonthOfYear(Month(IssueDate), Month(ValuationDate))
Else
    If ValuationDay < IssueDay Then
        'If ValuationDay is less than the IssueDay but its the last day of that month, then
        'its a monthliversary.  For example if policy is issued on 1/30/2013 and the valuation date
        'is 2/28/2013, then the valuation date is a monthliversary
        
        'End of Month for the valuatoin month
        EOM_Valuation = Day(DateSerial(Year(ValuationDate), Month(ValuationDate) + 1, 0))
        If ValuationDay = EOM_Valuation Then
            MonthOfYear_OffMonthliversary = MonthOfYear(Month(IssueDate), Month(ValuationDate))
        Else
            MonthOfYear_OffMonthliversary = MonthOfYear(Month(IssueDate), Month(ValuationDate) - 1)
        End If
    End If
End If
    

End Function

Public Function MonthOfYear(IssueMonth As Integer, ValuationMonth As Integer)
'This function finds the month of year for the valuation date, but the valuation date mush be a monthliversary  This function returns a value from 1 to 12
Dim mth As Integer
  mth = Abs(IssueMonth - ValuationMonth)
  If IssueMonth > ValuationMonth Then mth = 12 - mth
  mth = mth + 1
  MonthOfYear = mth
End Function
Public Function NullZ(arg1, substituteValue)
 NullZ = IIf(IsNull(arg1), substituteValue, arg1)
End Function
Public Function CompletedDateParts(difftype As String, argDate1, argDate2) As Long
'This function is used to calculate number of completed months and years.  I copied
'it from the internet http://www.ozgrid.com/forum/showthread.php?t=37711
    Dim EarlyDate, LateDate As Date
    Dim tempDate, Date1, Date2 As Date
    Dim k As Long
        
    Date1 = CDate(argDate1)
    Date2 = CDate(argDate2)
    
    If Date1 <= Date2 Then
        EarlyDate = Date1
        LateDate = Date2
    Else
        EarlyDate = Date2
        LateDate = Date1
    End If
     
    tempDate = EarlyDate
    k = 0
    Do While tempDate <= LateDate
        k = k + 1
        tempDate = DateAdd(difftype, k, EarlyDate)
     Loop
    CompletedDateParts = k - 1
End Function
Public Function InsteadOfNull()
Dim vntTemp As Variant

Select Case mParent.Fields(mFieldName).Type
 Case DataTypeEnum.adChar: vntTemp = ""
 Case DataTypeEnum.adDate: vntTemp = #1/1/1900#
 Case DataTypeEnum.adDouble: vntTemp = 0
 Case DataTypeEnum.adSmallInt: vntTemp = 0
 Case DataTypeEnum.adInteger: vntTemp = 0
 Case DataTypeEnum.adNumeric: vntTemp = 0
 Case DataTypeEnum.adDBDate: vntTemp = #1/1/1900#
 Case Else:     Stop
End Select
InsteadOfNull = vntTemp
End Function
