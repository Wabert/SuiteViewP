Attribute VB_Name = "Module2"


Public Sub calc()
age = ThisWorkbook.Sheets("Calc").Cells(2, 2)
Class = ThisWorkbook.Sheets("Calc").Cells(4, 2)
Sex = ThisWorkbook.Sheets("Calc").Cells(3, 2)
k = Sex & Class
With Sheets("2008 VBT").Range("A1:A400")
        Set rng1 = .Find(what:=k, after:=.Cells(.Cells.Count), LookIn:=xlValues, LookAt:=xlWhole, searchOrder:=xlByRows, SearchDirection:=xlNext)
        Application.Goto rng1, True
End With
    rownum = ActiveCell.Row + 1
    
    colnum = ActiveCell.Column + 1
    Range(Cells(rownum, colnum), Cells(rownum, colnum + 100)).Select
    With Sheets("2008 VBT").Range(Cells(rownum, colnum), Cells(rownum, colnum + 100))
        Set rng2 = .Find(what:=age, after:=.Cells(.Cells.Count), LookIn:=xlValues, LookAt:=xlWhole, searchOrder:=xlByColumns, SearchDirection:=xlNext)
        Application.Goto rng2, True
    End With
    rownum = ActiveCell.Row + 1
    colnum = ActiveCell.Column
    Range(Cells(rownum, colnum), Cells(rownum + 121, colnum)).Select
    Selection.Copy
    Sheets("calc").Select
    Cells(8, 3).Select
    Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
        :=False, Transpose:=False
End Sub


Public Sub flat()
Sheets("calc").Cells(1, 8) = 0
k = Sheets("calc").Cells(6, 15)
Range("B6").GoalSeek Goal:=k, ChangingCell:=Range("H2")
End Sub
Public Sub table()
Sheets("calc").Cells(2, 8) = 0
k = Sheets("calc").Cells(6, 15)
Range("B6").GoalSeek Goal:=k, ChangingCell:=Range("H1")
End Sub


Public Sub get_rates()
n = Cells(3, 4)
If Cells(3, 4) = "C" Then

age = ThisWorkbook.Sheets("Calc.monthly").Cells(1, 2)
Class = ThisWorkbook.Sheets("Calc.monthly").Cells(3, 2)
Sex = ThisWorkbook.Sheets("Calc.monthly").Cells(2, 2)
k = Sex & Class
With Sheets("2008 VBT").Range("A1:A400")
        Set rng1 = .Find(what:=k, after:=.Cells(.Cells.Count), LookIn:=xlValues, LookAt:=xlWhole, searchOrder:=xlByRows, SearchDirection:=xlNext)
        Application.Goto rng1, True
End With
    rownum = ActiveCell.Row + 1
    
    colnum = ActiveCell.Column + 1
    Range(Cells(rownum, colnum), Cells(rownum, colnum + 100)).Select
    With Sheets("2008 VBT").Range(Cells(rownum, colnum), Cells(rownum, colnum + 100))
        Set rng2 = .Find(what:=age, after:=.Cells(.Cells.Count), LookIn:=xlValues, LookAt:=xlWhole, searchOrder:=xlByColumns, SearchDirection:=xlNext)
        Application.Goto rng2, True
    End With
    rownum = ActiveCell.Row + 1
    colnum = ActiveCell.Column
    Range(Cells(rownum, colnum), Cells(rownum + 121, colnum)).Select
    Selection.Copy
    Sheets("calc.monthly").Select
    Cells(6, 2).Select
    Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
        :=False, Transpose:=False
        Sheets("Inputs").Select
Else
Sheets("calc.monthly").Select
Range(Cells(6, 15), Cells(127, 15)).Select
Selection.Copy
Cells(6, 2).Select
    Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
        :=False, Transpose:=False
        Sheets("Inputs").Select
End If

End Sub


        
        
    
    
    
End Sub

