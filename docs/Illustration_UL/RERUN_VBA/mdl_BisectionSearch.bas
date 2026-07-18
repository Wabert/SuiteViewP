Attribute VB_Name = "mdl_BisectionSearch"
Option Explicit
Dim mTimeElapsed As Date
Dim mIterationCount As Integer
Const SECONDS_PER_DAY = 86400

Sub BisectionSearch()
    Dim InverseOrDirect As String
    Dim LB As Double, UB As Double
    Dim SearchType As String
    SearchType = Range("sSearch_Type")
    
    'Get handle to the range of the cell for the SearchWith value (aka independent variable)
    Dim IndRangeName As String
    Dim IndRangeIndex As Long
    Dim IndRange As Range
    IndRangeName = Range("sSearch_Independent_Range")
    IndRangeIndex = Range("sSearch_Independent_Index")
    Set IndRange = Range(IndRangeName).Rows(IndRangeIndex)
    
    'Get handle to the range of the cell for the dependent value
    Dim DepRangeName As String
    Dim DepRange As Range
    Set DepRange = Range("sSearch_Dependent_Value")
    DepRangeName = Range("sSearch_Dependent_Range").Value
    
    'Set some search criteria that depends if you are searching with Premium, Face or Loans
    Select Case SearchType
        Case "Premium":
                        Application.Calculate
                        UB = Range("sGSP_Issue")
                        LB = 0
                        
                        'Default relationship
                        InverseOrDirect = "Direct"
                        
                       

        Case "Face":    UB = 5000000
                        LB = 25000
    
                        'Default relationship
                        InverseOrDirect = "Inverse"
                        Select Case DepRangeName
                             Case "vGLP", "vGSP", "v7PayPrem", "sGSP_Issue", "sGLP_Issue", "s7Pay_Issue"
                             InverseOrDirect = "Direct"
                        End Select
    
    
        Case "Loan":

                        'Set upper and lower bounds.  These are just a guess and there is room for improving performance by setting better bounds
                        UB = 1000000
                        LB = 0
                     
                        'Default relationship
                        InverseOrDirect = "Inverse"
    
    End Select
    
    Dim SearchResult As Variant
    SearchResult = getBisSearch(IndRange, DepRange, Range("sSearch_Dependent_GoalValue").Value, InverseOrDirect, LB, UB, Range("sSearch_Independent_Tolerance").Value, Range("sSearch_MaxIteration").Value)
       
    Range("BiS_Result") = SearchResult
    Range("BiS_Timer") = mTimeElapsed
    Range("BiS_Iteration") = mIterationCount

End Sub

Function getBisSearch(IndRange As Range, DepRange As Range, GoalValue As Double, InverseOrDirect As String, StartingLB As Double, StartingUB As Double, Tolerance As Double, MaxIterations As Integer) As Variant
'This function performs the basic Bisection search routine and returns the resulting value

Dim IterationCount As Integer
Dim UB As Double, LB As Double
Dim DependentValue As Double, NextIndValue As Double
Dim StartTime As Double

    'The Started time of the marco starts
    mTimeElapsed = 0
    StartTime = Timer
    
    'Begin Search loop
    LB = StartingLB
    UB = StartingUB
    IterationCount = 0
    Do While IterationCount <= MaxIterations
        IterationCount = IterationCount + 1
        
        'If new value is within tolerance then exit
        IndRange.Value = (LB + UB) / 2
        
        'Calculate spreadsheet formulas and pull the resulting target value
        Calculate
        DependentValue = DepRange.Value
        
        'Adjust the upper and lower bounds according to the results and the relationship of the TargetValueType to SearchWithValueType
        If InverseOrDirect = "Inverse" Then
            If GoalValue >= DependentValue Then
                UB = IndRange.Value
            Else
                LB = IndRange.Value
            End If
        Else
            If GoalValue <= DependentValue Then
                UB = IndRange.Value
            Else
                LB = IndRange.Value
            End If
        End If
        
        
        NextIndValue = (LB + UB) / 2
        If Abs(IndRange.Value - NextIndValue) < Tolerance Then
            Exit Do
        End If

    Loop
    
    
    'Time Elapsed for the Marco
    mTimeElapsed = (Timer - StartTime) / SECONDS_PER_DAY
    mIterationCount = IterationCount

    getBisSearch = IndRange.Value
End Function
