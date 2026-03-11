Attribute VB_Name = "ReadIn"

Sub ReadIn()


    ProgressBar.LabelProgress.Width = 0
    ProgressBar.Show


End Sub

Sub CPDReady()

    Workbooks.Add
    
    Do While Worksheets.Count > 1
        Worksheets(2).Delete
    Loop

    Worksheets(1).Name = "Premium Limits"

End Sub
