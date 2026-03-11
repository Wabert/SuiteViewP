' Module: mdl_HideWorkbook.bas
' Type: Standard Module
' Stream Path: VBA/mdl_HideWorkbook
' =========================================================

Attribute VB_Name = "mdl_HideWorkbook"
Option Explicit

Sub HideExcelWindow()
Dim win As Window
    
    If Application.Workbooks.Count = 1 Then
        Application.Visible = False
    Else
        For Each win In Application.Windows
            If win.caption = ThisWorkbook.name Then
                win.Visible = False
                Exit For
            End If
        Next win
    End If
End Sub

Sub ShowExcelWindow()
Dim win As Window
    If Application.Workbooks.Count = 1 Then
        Application.Visible = True
        Windows(ThisWorkbook.name).Visible = True
    Else
        For Each win In Application.Windows
            If win.caption = ThisWorkbook.name Then
                win.Visible = True
                Exit For
            End If
        Next win
    End If
End Sub


