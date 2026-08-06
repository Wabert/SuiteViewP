' Module: mdlTableTransformationTools.bas
' Type: Standard Module
' Stream Path: VBA/mdlTableTransformationTools
' =========================================================

Attribute VB_Name = "mdlTableTransformationTools"
Public Sub TT_FlattenTable()
Dim ary()
Dim rowCount As Long, ColumnCount As Long, X As Long, Y As Long

ReDim ary(Selection.rows.Count * Selection.Columns.Count, 0 To 2)

'Assume first row contains header data
ary(0, 0) = Selection(1, 1)
ary(0, 1) = "Header"
ary(0, 2) = "Data"

For X = 2 To Selection.rows.Count
    For Y = 2 To Selection.Columns.Count
        rowCount = rowCount + 1
        ary(rowCount, 0) = Selection(X, 1)
        ary(rowCount, 1) = Selection(1, Y)
        ary(rowCount, 2) = Selection(X, Y)
    Next
Next

DumpArrayValuesIntoExcel ary


End Sub
Sub TT_IA2IADur()
Dim rng As Range
Dim MaxAge

Sheets("TT_IA2IADur").Select

MaxAge = Range("sTT_IA2IADur_MaxAge")
RateDur = Range("sTT_IA2IADur_MaturityAge")

Set rng = Selection

Dim ary()
j = rng.Columns.Count + 1
ReDim ary(1000000, 1 To j)

'Find IssueAge column
Dim colIA
Dim colDur
For X = 1 To rng.Columns.Count
    If rng(1, X) = "IssueAge" Then colIA = X
    If rng(1, X) = "Rate" Then colRT = X
Next


If colIA = 0 Then
    MsgBox "Cannot find an 'IssueAge' column."
    Exit Sub
End If
If colRT = 0 Then
    MsgBox "Cannot find a 'Rate' column."
    Exit Sub
End If



For X = 1 To rng.Columns.Count - 1
    ary(0, X) = rng(1, X)
Next
ary(0, rng.Columns.Count) = "Duration"
ary(0, rng.Columns.Count + 1) = "Rate"

aryCount = 1
For rCount = 2 To rng.rows.Count
    IA = rng(rCount, colIA)
    MaxDur = MaxAge - IA
    For Dur = 1 To MaxDur
    
        For X = 1 To rng.Columns.Count - 1
            ary(aryCount, X) = rng(rCount, X)
        Next
        ary(aryCount, rng.Columns.Count) = Dur
        If Dur > RateDur Then
            ary(aryCount, rng.Columns.Count + 1) = 0
        Else
            ary(aryCount, rng.Columns.Count + 1) = rng(rCount, colRT)
        End If
        aryCount = aryCount + 1
    Next
Next
Dim ary2()
ary2 = Transpose2DArray_to_2DArray(ary)
ReDim Preserve ary2(LBound(ary, 2) To UBound(ary, 2), aryCount - 1)
ary = Transpose2DArray_to_2DArray(ary2)
DumpArrayValuesIntoExcel ary
    
End Sub


Sub TT_IADur2IADur()
Dim rng As Range
Dim MaxAge

Sheets("TT_IADur2IADur").Select

MaxAge = Range("sTT_IADur2IADur_MaturityAge")
RateDur = Range("sTT_IADur2IADur_Duration")

Set rng = Selection

Dim ary()
j = rng.Columns.Count + 1
ReDim ary(1000000, 1 To j)

'Find IssueAge column
Dim colIA
Dim colRT
Dim colDR
For X = 1 To rng.Columns.Count
    If rng(1, X) = "IssueAge" Then colIA = X
    If rng(1, X) = "Duration" Then colDR = X
    If rng(1, X) = "Rate" Then colRT = X
Next


If colIA = 0 Then
    MsgBox "Cannot find an 'IssueAge' column."
    Exit Sub
End If
If colRT = 0 Then
    MsgBox "Cannot find a 'Rate' column."
    Exit Sub
End If
If colDR = 0 Then
    MsgBox "Cannot find an 'Duration' column."
    Exit Sub
End If


For X = 1 To rng.Columns.Count
    ary(0, X) = rng(1, X)
Next

aryCount = 1
rCount = 2
Do While rCount <= rng.rows.Count
    IA = rng(rCount, colIA)
    MaxDur = MaxAge - IA
    
    
    For Dur = 1 To MaxDur
        
        If Dur <= RateDur Then
            For X = 1 To rng.Columns.Count
                ary(aryCount, X) = rng(rCount, X)
            Next
            rCount = rCount + 1
            aryCount = aryCount + 1
        Else
            For X = 1 To rng.Columns.Count
                ary(aryCount, X) = rng(rCount - 1, X)
            Next
            ary(aryCount, colRT) = 0
            ary(aryCount, colDR) = Dur
            aryCount = aryCount + 1
        End If
        
    Next
Loop
Dim ary2()
ary2 = Transpose2DArray_to_2DArray(ary)
ReDim Preserve ary2(LBound(ary, 2) To UBound(ary, 2), aryCount - 1)
ary = Transpose2DArray_to_2DArray(ary2)
DumpArrayValuesIntoExcel ary
    
End Sub


Sub TT_AA2IADur()
Dim rng As Range
Dim MaxAge

Sheets("TT_AA2IADur").Select

MaxAge = Range("sTT_AA2IADur_MinIssueAge")
RateDur = Range("sTT_AA2IADur_MaxIssueAge")

Set rng = Selection

'Find AttainedAge column
Dim colAA
Dim colRT
For X = 1 To rng.Columns.Count
    If rng(1, X) = "AttainedAge" Then colAA = X
    If rng(1, X) = "Rate" Then colRT = X
Next


If colAA = 0 Then
    MsgBox "Cannot find an 'AttainedAge' column."
    Exit Sub
End If
If colRT = 0 Then
    MsgBox "Cannot find a 'Rate' column."
    Exit Sub
End If
If colRT <> rng.Columns.Count Then
    MsgBox "'Rate' column must be the last column."
    Exit Sub
End If


'Add all rates to a dictionary and find max attained age
Dim dctRate As Dictionary
Set dctRate = New Dictionary
Dim MaxAA As Integer
For X = 2 To rng.rows.Count
    key = rng(X, 1)
    For Y = 2 To rng.Columns.Count - 1
        key = key & "." & rng(X, Y)
    Next
    dctRate(key) = rng(X, rng.Columns.Count)
    If MaxAA < rng(X, colAA) Then MaxAA = rng(X, colAA)
Next




j = rng.Columns.Count + 1
Dim ary()
ReDim ary(1000000, 1 To j)

'Convert from Attained Age to Issue Age and Duration.  The Attained Age column will now store the IssueAge and a Duration column will be added

'Add headers
For X = 1 To rng.Columns.Count - 1
    ary(0, X) = rng(1, X)
    If X = colAA Then ary(0, X) = "IssueAge"
Next
ary(0, rng.Columns.Count) = "Duration"
ary(0, rng.Columns.Count + 1) = "Rate"
aryCount = 1
Dim IA As Integer
Dim Dur As Integer
For rCount = 2 To rng.rows.Count
    IA = rng(rCount, colAA)
    For Dur = 1 To MaxAA - IA + 1
        'Copy the whole row except for the rate and Attained Age (attained age will be added to the key later)
        'Also create the lookup key
        For X = 1 To rng.Columns.Count - 1
            If X <> colAA Then
                ary(aryCount, X) = rng(rCount, X)
                If X = 1 Then
                    key = ary(aryCount, X)
                Else
                    key = key & "." & ary(aryCount, X)
                End If
            End If
        Next
        'Store the Issue Age were the Attained age used to be
        ary(aryCount, colAA) = IA
        
        'Add Duration
        ary(aryCount, rng.Columns.Count) = Dur
        
        'Add attained age to the lookup key
        key = key & "." & IA + Dur - 1
        
        'Lookup the rate in the dictionary
        ary(aryCount, rng.Columns.Count + 1) = dctRate(key)
        
        aryCount = aryCount + 1
    Next
Next
Dim ary2()
ary2 = Transpose2DArray_to_2DArray(ary)
ReDim Preserve ary2(LBound(ary, 2) To UBound(ary, 2), 0 To aryCount)
ary = Transpose2DArray_to_2DArray(ary2)
DumpArrayValuesIntoExcel ary
    
End Sub

