' Module: mdlForecast.bas
' Type: Standard Module
' Stream Path: VBA/mdlForecast
' =========================================================

Attribute VB_Name = "mdlForecast"
Public Sub UpdateControlsForChangeInValue(dct As Dictionary, ctrlNameThatChanged As String)
Dim ctrl As MSForms.Control
Select Case ctrlNameThatChanged
    Case "ToAge":
        If dct("FromAge").value <> "" And dct("ToAge").value <> "" Then
                l = dct("FromAge").value
                dct("Years").value = Val(dct("ToAge").value) - Val(dct("FromAge").value)
                l = dct("Years").value
        End If
    
    Case "Years":
        If dct("FromAge").value <> "" And dct("Years").value <> "" Then
            dct("ToAge").value = Val(dct("FromAge").value) + Val(dct("Years").value)
        End If

    Case "FromAge":
        If dct("FromAge").value <> "" And dct("ToAge").value <> "" Then
                dct("Years").value = Val(dct("ToAge").value) - Val(dct("FromAge").value)
        End If
End Select


End Sub

Public Function RowComplete(dct As Dictionary) As Boolean
Dim tempboolean
tempboolean = True

tempboolean = tempboolean And dct("Amount") <> ""
tempboolean = tempboolean And dct("FromAge") <> ""
tempboolean = tempboolean And dct("Years") <> ""
tempboolean = tempboolean And dct("ToAge") <> ""
tempboolean = tempboolean And dct("Mode") <> ""
RowComplete = tempboolean
End Function

Public Function FindFromAge(StartDate As Variant, IssueAge As Integer, IssueDate As Date) As Variant
        If StartDate = "" Then
            FindFromAge = ""
        Else
           FindFromAge = IssueAge + DateDiff("YYYY", IssueDate, CDate(StartDate))
        End If
End Function
Public Function FindToAge(StopDate As Variant, IssueAge As Integer, IssueDate As Date) As Variant
        If StopDate = "" Then
            FindToAge = ""
        Else
            FindToAge = IssueAge + DateDiff("YYYY", IssueDate, CDate(StopDate))
        End If
End Function
Public Function FindYearCount(FromAge As Variant, ToAge As Variant) As Variant
If FromAge = "" Or ToAge = "" Then
    FindYearCount = ""
Else
    FindYearCount = ToAge - FromAge
End If
End Function
Public Function FindStartDate(FromAge As Variant, AttainedAge As Integer, IssueAge As Integer, ValuationDate As Date, IssueDate As Date) As Variant
    If FromAge = "" Then
        FindStartDate = ""
    Else
        Dim StartDate As Date
        StartDate = DateAdd("YYYY", CInt(FromAge) - AttainedAge, IssueDate)
        FindStartDate = CDate(fmax(StartDate, ValuationDate))
    End If
End Function
Public Function FindStopDate(ToAge As Variant, AttainedAge As Integer, IssueAge As Integer, ValuationDate As Date, IssueDate As Date) As Variant
    If ToAge = "" Then
        FindStopDate = ""
    Else
        FindStopDate = DateAdd("YYYY", CInt(ToAge) - IssueAge, IssueDate)
    End If
End Function

