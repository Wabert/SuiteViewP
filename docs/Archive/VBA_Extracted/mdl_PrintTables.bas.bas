' Module: mdl_PrintTables.bas
' Type: Standard Module
' Stream Path: VBA/mdl_PrintTables
' =========================================================

Attribute VB_Name = "mdl_PrintTables"


Sub PrintDB2TablesByPolicy(strPolicyNumber As String, TableList As Range)
'Prints each DB2 table from the TableList for the policynumber provided.
'If there is more than on table they are printed below the last table

Application.Calculate

Dim xRow As Long, xCol As Long
Dim Tablename As String
Dim TableRange As Range
Dim ary As Variant, aryT() As Variant
Dim mPolDB2 As cls_PolicyData
Dim mPolicy As cls_PolicyInformation
Set mPolicy = New cls_PolicyInformation
mPolicy.classInitialize strPolicyNumber
Set mPolDB2 = mPolicy.DB2Data


xRow = 1
xCol = 4

'Clear existing data first
Cells(xRow, xCol).Select
Range(Selection, ActiveCell.SpecialCells(xlLastCell)).Select
Selection.Clear


For X = 1 To TableList.rows.Count
    Tablename = TableList.Cells(X, 1)
    Cells(xRow, xCol) = Tablename
    If Tablename <> "" Then
        xRow = xRow + 1
        ary = mPolDB2.GetTable(Tablename)
        
        If IsEmpty(ary) Then
            Cells(xRow, xCol) = "No Entries in " & Tablename & " for policy " & strPolicyNumber
        Else
            aryT = Transpose2DArray_to_2DArray(ary)
            aryrows = UBound(aryT, 1) + 1
            arycols = UBound(aryT, 2) + 1
               
            Set TableRange = Range(Cells(xRow, xCol).Address).Resize(aryrows, arycols)
            TableRange.value = aryT
            AddBorderToRange TableRange
        End If
        xRow = xRow + aryrows + 1
    End If
Next


End Sub


Sub AddBorderToRange(rn As Range)
   
    rn.Select
    Selection.Borders(xlDiagonalDown).LineStyle = xlNone
    Selection.Borders(xlDiagonalUp).LineStyle = xlNone
    With Selection.Borders(xlEdgeLeft)
        .LineStyle = xlContinuous
        .ColorIndex = 0
        .TintAndShade = 0
        .Weight = xlThin
    End With
    With Selection.Borders(xlEdgeTop)
        .LineStyle = xlContinuous
        .ColorIndex = 0
        .TintAndShade = 0
        .Weight = xlThin
    End With
    With Selection.Borders(xlEdgeBottom)
        .LineStyle = xlContinuous
        .ColorIndex = 0
        .TintAndShade = 0
        .Weight = xlThin
    End With
    With Selection.Borders(xlEdgeRight)
        .LineStyle = xlContinuous
        .ColorIndex = 0
        .TintAndShade = 0
        .Weight = xlThin
    End With
    Selection.Borders(xlInsideVertical).LineStyle = xlNone
    Selection.Borders(xlInsideHorizontal).LineStyle = xlNone

    

End Sub
