Attribute VB_Name = "GuideLines"
Public Sub LaunchGuidelineSolver()
    GuidelineSolver.Show
End Sub


Public Sub GuidelineRecal(aStartYear As Integer, aStopYear As Integer, aTEFRATest As Boolean, aTAMRATest As Boolean, aDebugPrint As Boolean)

    Dim EvaluateYear As Integer
    
    Dim pCoverage_1_Spec_Amt, Coverage_1_Spec_Amt As Double
    Dim pCoverage_2_Spec_Amt, Coverage_2_Spec_Amt As Double
    Dim pCoverage_3_Spec_Amt, Coverage_3_Spec_Amt As Double
    Dim pDBO, DBO As String
    
    Dim RecalcNeeded As Boolean
    
    'Validate Start Date and Stop Date Inputs
    If aStartYear - 1 > 0 Then
        EvaluateYear = 1
    Else
        EvaluateYear = aStartYear - 1
    End If
    
    If aStopYear < 1 Then
        aStopYear = 1
    Else
        If aStopYear > 121 Then
            aStopYear = 121
        End If
    End If
    
    RecalcNeeded = True
    
    'Loop to process each year between the starting year and ending year
    Do While EvaluateYear <= aStopYear
        
        'Spreadsheet should recalculate depending on Guideline Changes
        If RecalcNeeded Then
            Application.Calculate
            RecalcNeeded = False
        End If
    
        
        
        EvaluateYear = EvaluateYear + 1
    Loop


End Sub
