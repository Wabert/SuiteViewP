VERSION 5.00
Begin {C62A69F0-16DC-11CE-9E98-00AA00574A4F} ProgressBar 
   Caption         =   "Please Wait..."
   ClientHeight    =   1200
   ClientLeft      =   45
   ClientTop       =   330
   ClientWidth     =   5760
   OleObjectBlob   =   "ProgressBar.frx":0000
   StartUpPosition =   1  'CenterOwner
End
Attribute VB_Name = "ProgressBar"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Dim Plancode As String
Dim Version As String
Dim EffDate As String
Dim First As Integer
Dim Last As Integer
Dim IAR_Use As Integer
Dim Pay_Age As Integer
Dim Pay_Age_Use As Integer
Dim ME_Age As Integer
Dim ME_Age_Use As Integer
Dim Val_Per_Unit As Double
Dim Prod_Cred_AMT As Double
Dim Prod_Cred_Use As Integer
Dim MDRT As String
Dim DEF As Integer
Dim Spec_Benefits As String
Dim R As String
Dim LV As String
Dim Dur As String

Dim ADV_Prod_Control As Boolean
Dim ADV_Prod_INIT_Prem_MIN As String
Dim ADV_Prod_INIT_Prem_MAX As String
Dim ADV_Prod_INIT_Prem_Rule As String
Dim ADV_Prod_Per_Prem_MIN As String
Dim ADV_Prod_Per_Prem_MAX As String
Dim ADV_FY_Prem_MAX As String
Dim ADV_Corr_Rule As String
Dim ADV_Corr_PCT As String
Dim ADV_Corr_AMT As String
Dim ADV_MAP_Period As String
Dim Rate_Type As String
Dim Rate_Start As String
Dim Rate_Stop As String

Dim Rate_IDENT_Duration As Integer
Dim Rate_IDENT_Gender As String
Dim Rate_IDENT_Rate_Class As String
Dim Rate_IDENT_Band As String
Dim Rate_IDENT_Plan_Option As String
Dim Rate_Value As Double

Dim ProductArray() As String
Dim AdvProductArray() As String
Dim AddAssocProductArray() As String
Dim RateArray() As String

Private Sub UserForm_activate()
    Call Main
End Sub

Private Function LineCount(FileName As String) As Long

    Open FileName For Input As #1
        Do While Not EOF(1)
            i = i + 1
            Line Input #1, D
        Loop
    Close #1
    LineCount = i
End Function

Private Function RemoveWhiteSpace(key As String) As String

Do While ((Len(key) <> 0) And (Right$(key, 1) = " "))
     If Right$(key, 1) = " " Then key = Left$(key, Len(key) - 1)
Loop
Do While ((Len(key) <> 0) And (Left$(key, 1) = " "))
     If Left$(key, 1) = " " Then key = Right$(key, Len(key) - 1)
Loop

If Len(key) = 0 Then
    key = " "
End If

RemoveWhiteSpace = key

End Function

Sub Analyze(Line As String)

    'Determines if the line needs to be skipped
    If Left(Line, 5) = "0DATE" Then
        Exit Sub
    End If
    If Left(Line, 51) = "1                                                  " Then
            Exit Sub
    End If
    If Mid(Line, 51, 32) = "PRINT ISSUE AGE DESCRIPTION FILE" Then
        Exit Sub
    End If
    If Line = "                                                                                                                                     " Then
        Exit Sub
    End If
    If Line = "   PLAN CODE  V  EFFDATE FST LST USE PAY-AGE USE  ME-AGE USE  VAL PER UNIT  PROD CRED AMT USE MDRT DEF SPEC BENEFITS  R LV DUR       " Then
        Exit Sub
    End If
    
    ' Will determine if this is a key field and store values into global variables
    If Mid(Line, 2, 1) = " " And Mid(Line, 3, 1) <> " " Then
        Plancode = RemoveWhiteSpace(Mid(Line, 3, 10))
        Version = RemoveWhiteSpace(Mid(Line, 14, 3))
        EffDate = Mid(Line, 17, 2) & "/" & Mid(Line, 19, 2) & "/" & Mid(Line, 21, 4)
        First = RemoveWhiteSpace(Mid(Line, 26, 3))
        Last = RemoveWhiteSpace(Mid(Line, 30, 3))
        IAR_Use = RemoveWhiteSpace(Mid(Line, 35, 1))
        Pay_Age = RemoveWhiteSpace(Mid(Line, 42, 3))
        Pay_Age_Use = RemoveWhiteSpace(Mid(Line, 47, 1))
        ME_Age = RemoveWhiteSpace(Mid(Line, 54, 3))
        ME_Age_Use = RemoveWhiteSpace(Mid(Line, 59, 1))
        Val_Per_Unit = RemoveWhiteSpace(Mid(Line, 61, 14))
        Prod_Cred_AMT = RemoveWhiteSpace(Mid(Line, 76, 14))
        Prod_Cred_Use = RemoveWhiteSpace(Mid(Line, 92, 1))
        MDRT = RemoveWhiteSpace(Mid(Line, 94, 4))
        DEF = RemoveWhiteSpace(Mid(Line, 101, 1))
        Spec_Benefits = RemoveWhiteSpace(Mid(Line, 103, 15))
        R = RemoveWhiteSpace(Mid(Line, 119, 1))
        LV = RemoveWhiteSpace(Mid(Line, 121, 2))
        Dur = RemoveWhiteSpace(Mid(Line, 124, 10))
        Exit Sub
    End If
    
    'Determines if the following line contains Advance Product Control Keys
    If Mid(Line, 2, 130) = "*** ADV PROD. CTL.  INIT PREM (MIN) - (MAX)    RULE   PER PREM (MIN) - (MAX)     F/Y PREM  CORR RULE    PCNT       AMT  MAP PERIOD" Then
        ADV_Prod_Control = True
        Exit Sub
    End If
    If ADV_Prod_Control Then
    
        If (Mid(Line, 2, 1) = "*") Then ' Sometimes an advanced column header appears errorously when on the page break; this if statement should help correct it
            ADV_Prod_Control = False
            Exit Sub
        End If
        ADV_Prod_INIT_Prem_MIN = RemoveWhiteSpace(Mid(Line, 29, 9))
        ADV_Prod_INIT_Prem_MAX = RemoveWhiteSpace(Mid(Line, 40, 9))
        ADV_Prod_INIT_Prem_Rule = RemoveWhiteSpace(Mid(Line, 50, 1))
        ADV_Prod_Per_Prem_MIN = RemoveWhiteSpace(Mid(Line, 62, 9))
        ADV_Prod_Per_Prem_MAX = RemoveWhiteSpace(Mid(Line, 73, 9))
        ADV_FY_Prem_MAX = RemoveWhiteSpace(Mid(Line, 83, 10))
        ADV_Corr_Rule = RemoveWhiteSpace(Mid(Line, 97, 1))
        ADV_Corr_PCT = RemoveWhiteSpace(Mid(Line, 103, 8))
        ADV_Corr_AMT = RemoveWhiteSpace(Mid(Line, 112, 10))
        ADV_MAP_Period = RemoveWhiteSpace(Mid(Line, 127, 4))
        
        ADV_Prod_Control = False
        Exit Sub
    End If
    
    If (Mid(Line, 1, 19) = "                   " And Mid(Line, 20, 1) <> " ") Then
        Rate_Type = Mid(Line, 20, 1)
        Rate_Start = Mid(Line, 24, 2) & "/" & Mid(Line, 26, 2) & "/" & Mid(Line, 28, 4)
        If (Mid(Line, 34, 2) <> "  ") Then  ' Determines if an end date is entered
            Rate_Stop = Mid(Line, 34, 2) & "/" & Mid(Line, 36, 2) & "/" & Mid(Line, 38, 4)
        End If
        If (Mid(Line, 34, 2) = "  ") Then ' Codes 12/31/9999 if no end date is specified entered
            Rate_Stop = "12/31/9999"
        End If
    End If
    
    If (Mid(Line, 1, 19) = "                   ") Then
        
        If Mid(Line, 44, 1) <> " " Then
            Rate_IDENT_Duration = RemoveWhiteSpace(Mid(Line, 44, 2))
            Rate_IDENT_Gender = RemoveWhiteSpace(Mid(Line, 46, 1))
            Rate_IDENT_Rate_Class = RemoveWhiteSpace(Mid(Line, 47, 1))
            Rate_IDENT_Band = RemoveWhiteSpace(Mid(Line, 48, 1))
            Rate_IDENT_Plan_Option = RemoveWhiteSpace(Mid(Line, 49, 2))
            Rate_Value = RemoveWhiteSpace(Mid(Line, 52, 12))
            storeRate
        End If
        If Mid(Line, 66, 1) <> " " Then
            Rate_IDENT_Duration = RemoveWhiteSpace(Mid(Line, 66, 2))
            Rate_IDENT_Gender = RemoveWhiteSpace(Mid(Line, 68, 1))
            Rate_IDENT_Rate_Class = RemoveWhiteSpace(Mid(Line, 69, 1))
            Rate_IDENT_Band = RemoveWhiteSpace(Mid(Line, 70, 1))
            Rate_IDENT_Plan_Option = RemoveWhiteSpace(Mid(Line, 71, 2))
            Rate_Value = RemoveWhiteSpace(Mid(Line, 74, 12))
            storeRate
        End If
        If Mid(Line, 88, 1) <> " " Then
            Rate_IDENT_Duration = RemoveWhiteSpace(Mid(Line, 88, 2))
            Rate_IDENT_Gender = RemoveWhiteSpace(Mid(Line, 90, 1))
            Rate_IDENT_Rate_Class = RemoveWhiteSpace(Mid(Line, 91, 1))
            Rate_IDENT_Band = RemoveWhiteSpace(Mid(Line, 92, 1))
            Rate_IDENT_Plan_Option = RemoveWhiteSpace(Mid(Line, 93, 2))
            Rate_Value = RemoveWhiteSpace(Mid(Line, 96, 12))
            storeRate
        End If
        If Mid(Line, 110, 1) <> " " Then
            Rate_IDENT_Duration = RemoveWhiteSpace(Mid(Line, 110, 2))
            Rate_IDENT_Gender = RemoveWhiteSpace(Mid(Line, 112, 1))
            Rate_IDENT_Rate_Class = RemoveWhiteSpace(Mid(Line, 113, 1))
            Rate_IDENT_Band = RemoveWhiteSpace(Mid(Line, 114, 1))
            Rate_IDENT_Plan_Option = RemoveWhiteSpace(Mid(Line, 115, 2))
            Rate_Value = RemoveWhiteSpace(Mid(Line, 118, 12))
            storeRate
        End If
    End If

End Sub

Sub storeRate()
    Dim j As Integer
    Dim Break_loop As Boolean

    ' Product Loop

    j = 0
    Break_loop = False
      
    l = UBound(ProductArray)
    
    Do While (j <= UBound(ProductArray, 2) And Not Break_loop)
        If ((ProductArray(0, j) = CStr(j)) And _
        (ProductArray(1, j) = CStr(Plancode)) And _
        (ProductArray(2, j) = CStr(Version)) And _
        (ProductArray(3, j) = CStr(EffDate)) And _
        (ProductArray(4, j) = CStr(Age)) And _
        (ProductArray(5, j) = CStr(IAR_Use)) And _
        (ProductArray(6, j) = CStr(Pay_Age)) And _
        (ProductArray(7, j) = CStr(Pay_Age_Use)) And _
        (ProductArray(8, j) = CStr(ME_Age)) And _
        (ProductArray(9, j) = CStr(ME_Age_Use)) And _
        (ProductArray(10, j) = CStr(Val_Per_Unit)) And _
        (ProductArray(11, j) = CStr(Prod_Cred_AMT)) And _
        (ProductArray(12, j) = CStr(Prod_Cred_Use)) And _
        (ProductArray(13, j) = CStr(MDRT)) And _
        (ProductArray(14, j) = CStr(DEF)) And _
        (ProductArray(15, j) = CStr(Spec_Benefit)) And _
        (ProductArray(16, j) = CStr(R)) And _
        (ProductArray(17, j) = CStr(LV)) And _
        (ProductArray(18, j) = CStr(Dur))) Then
                Break_loop = True
        End If
        j = j + 1
        If (j > UBound(ProductArray, 2) And Not Break_loop) Then
                ReDim Preserve ProductArray(18, j)
                ProductArray(0, j) = j
                ProductArray(1, j) = Plancode
                ProductArray(2, j) = Version
                ProductArray(3, j) = EffDate
                ProductArray(4, j) = Age
                ProductArray(5, j) = IAR_Use
                ProductArray(6, j) = Pay_Age
                ProductArray(7, j) = Pay_Age_Use
                ProductArray(8, j) = ME_Age
                ProductArray(9, j) = ME_Age_Use
                ProductArray(10, j) = Val_Per_Unit
                ProductArray(11, j) = Prod_Cred_AMT
                ProductArray(12, j) = Prod_Cred_Use
                ProductArray(13, j) = MDRT
                ProductArray(14, j) = DEF
                ProductArray(15, j) = Spec_Benefit
                ProductArray(16, j) = R
                ProductArray(17, j) = LV
                ProductArray(18, j) = Dur
        End If
            
    Loop
    
    'Advanced Product Loop
    
    j = j - 1
    Break_loop = False
    Dim k
    
    k = 0
    
    If (Len(ADV_Prod_INIT_Prem_MIN) = 0 And _
        Len(ADV_Prod_INIT_Prem_MAX) = 0 And _
        Len(ADV_Prod_INIT_Prem_Rule) = 0 And _
        Len(ADV_Prod_Per_Prem_MIN) = 0 And _
        Len(ADV_Prod_Per_Prem_MAX) = 0 And _
        Len(ADV_FY_Prem_MAX) = 0 And _
        Len(ADV_Corr_Rule) = 0 And _
        Len(ADV_Corr_PCT) = 0 And _
        Len(ADV_Corr_AMT) = 0 And _
        Len(ADV_MAP_Period) = 0) Then
            Break_loop = True
        Else
            Break_loop = False
        End If
        Do While (k <= UBound(AdvProductArray, 2) And Not Break_loop)
            If ((AdvProductArray(0, k) = CStr(j)) And _
            (AdvProductArray(1, k) = CStr(First)) And _
            (AdvProductArray(2, k) = CStr(ADV_Prod_INIT_Prem_MIN)) And _
            (AdvProductArray(3, k) = CStr(ADV_Prod_INIT_Prem_MAX)) And _
            (AdvProductArray(4, k) = CStr(ADV_Prod_INIT_Prem_Rule)) And _
            (AdvProductArray(5, k) = CStr(ADV_Prod_Per_Prem_MIN)) And _
            (AdvProductArray(6, k) = CStr(ADV_Prod_Per_Prem_MAX)) And _
            (AdvProductArray(7, k) = CStr(ADV_FY_Prem_MAX)) And _
            (AdvProductArray(8, k) = CStr(ADV_Corr_Rule)) And _
            (AdvProductArray(9, k) = CStr(ADV_Corr_PCT)) And _
            (AdvProductArray(10, k) = CStr(ADV_Corr_AMT)) And _
            (AdvProductArray(11, k) = CStr(ADV_MAP_Period))) Then
                Break_loop = True
            End If
            k = k + 1
            If (k > UBound(AdvProductArray, 2) And Not Break_loop) Then
                ReDim Preserve AdvProductArray(11, k)
                AdvProductArray(0, k) = CStr(j)
                AdvProductArray(1, k) = CStr(First)
                AdvProductArray(2, k) = CStr(ADV_Prod_INIT_Prem_MIN)
                AdvProductArray(3, k) = CStr(ADV_Prod_INIT_Prem_MAX)
                AdvProductArray(4, k) = CStr(ADV_Prod_INIT_Prem_Rule)
                AdvProductArray(5, k) = CStr(ADV_Prod_Per_Prem_MIN)
                AdvProductArray(6, k) = CStr(ADV_Prod_Per_Prem_MAX)
                AdvProductArray(7, k) = CStr(ADV_FY_Prem_MAX)
                AdvProductArray(8, k) = CStr(ADV_Corr_Rule)
                AdvProductArray(9, k) = CStr(ADV_Corr_PCT)
                AdvProductArray(10, k) = CStr(ADV_Corr_AMT)
                AdvProductArray(11, k) = CStr(ADV_MAP_Period)
            End If
            
        Loop
    
    
        Break_loop = False
        k = UBound(RateArray, 2) + 1
        
                ReDim Preserve RateArray(11, k)
                RateArray(0, k) = CStr(j)
                RateArray(1, k) = CStr(Rate_Type)
                RateArray(2, k) = CStr(Rate_Start)
                RateArray(3, k) = CStr(Rate_Stop)
                RateArray(4, k) = CStr(First)
                RateArray(5, k) = CStr(Rate_IDENT_Duration)
                RateArray(6, k) = CStr(First - CInt(Rate_IDENT_Duration))
                RateArray(7, k) = CStr(Rate_IDENT_Gender)
                RateArray(8, k) = CStr(Rate_IDENT_Rate_Class)
                RateArray(9, k) = CStr(Rate_IDENT_Band)
                RateArray(10, k) = CStr(Rate_IDENT_Plan_Option)
                RateArray(11, k) = CStr(Rate_Value)

End Sub

Sub ProduceTextFile()
    
    Dim Directory As String
    Dim FileName As String
    Dim j As Integer
    Dim FilePath As String
    Dim fso As New FileSystemObject
    Dim stream As TextStream  ' Declare a TextStream.
    Dim ArrayBound
    
    MsgBox ("Select Text File Directory")

    With Application.FileDialog(msoFileDialogFolderPicker)
        .Show
        Directory = .SelectedItems(1)
    End With
    
    
    
    j = 1
    
    Do While (j <= UBound(ProductArray, 2))
    FileName = ProductArray(1, j) & " - " & _
                ProductArray(2, j) & " - " & _
                "Plan Rates.txt"
     
    FilePath = Directory & "\" & FileName ' create a .txt

    Set stream = fso.CreateTextFile(FilePath, True) ' Create a TextStream.
    
    ArrayBound = UBound(RateArray, 2)

    k = 0
    
                stream.WriteLine (ProductArray(1, k) & "," & _
                            ProductArray(2, k) & "," & _
                            ProductArray(3, k) & "," & _
                            RateArray(1, k) & "," & _
                            RateArray(2, k) & "," & _
                            RateArray(3, k) & "," & _
                            RateArray(4, k) & "," & _
                            RateArray(5, k) & "," & _
                            RateArray(6, k) & "," & _
                            RateArray(7, k) & "," & _
                            RateArray(8, k) & "," & _
                            RateArray(9, k) & "," & _
                            RateArray(10, k) & "," & _
                            RateArray(11, k))
    
    k = 1
     'loop round adding lines
    Do While k <= ArrayBound
         ' write your code here
         If (RateArray(0, k) = j Or RateArray(0, k) = 0) Then
         
            stream.WriteLine (ProductArray(1, j) & "," & _
                            ProductArray(2, j) & "," & _
                            ProductArray(3, j) & "," & _
                            RateArray(1, k) & "," & _
                            RateArray(2, k) & "," & _
                            RateArray(3, k) & "," & _
                            RateArray(4, k) & "," & _
                            RateArray(5, k) & "," & _
                            RateArray(6, k) & "," & _
                            RateArray(7, k) & "," & _
                            RateArray(8, k) & "," & _
                            RateArray(9, k) & "," & _
                            RateArray(10, k) & "," & _
                            RateArray(11, k))
            End If
        k = k + 1
    Loop
     
    stream.Close
    
    If UBound(AdvProductArray, 2) > 1 Then
    
        FileName = ProductArray(1, j) & " - " & _
                ProductArray(2, j) & " - " & _
                "Advanced Product Rates.txt"
     
        FilePath = Directory & "\" & FileName ' create a .txt file

        Set stream = fso.CreateTextFile(FilePath, True) ' Create a TextStream.
    
        ArrayBound = UBound(AdvProductArray, 2)

        k = 0
        
        stream.WriteLine (ProductArray(1, k) & "," & _
                            ProductArray(2, k) & "," & _
                            ProductArray(3, k) & "," & _
                            AdvProductArray(1, k) & "," & _
                            AdvProductArray(2, k) & "," & _
                            AdvProductArray(3, k) & "," & _
                            AdvProductArray(4, k) & "," & _
                            AdvProductArray(5, k) & "," & _
                            AdvProductArray(6, k) & "," & _
                            AdvProductArray(7, k) & "," & _
                            AdvProductArray(8, k) & "," & _
                            AdvProductArray(9, k) & "," & _
                            AdvProductArray(10, k) & "," & _
                            AdvProductArray(11, k))


        k = 1
        
        Do While k <= ArrayBound
                If (AdvProductArray(0, k) = j Or AdvProductArray(0, k) = 0) Then
         
                        stream.WriteLine (ProductArray(1, j) & "," & _
                            ProductArray(2, j) & "," & _
                            ProductArray(3, j) & "," & _
                            AdvProductArray(1, k) & "," & _
                            AdvProductArray(2, k) & "," & _
                            AdvProductArray(3, k) & "," & _
                            AdvProductArray(4, k) & "," & _
                            AdvProductArray(5, k) & "," & _
                            AdvProductArray(6, k) & "," & _
                            AdvProductArray(7, k) & "," & _
                            AdvProductArray(8, k) & "," & _
                            AdvProductArray(9, k) & "," & _
                            AdvProductArray(10, k) & "," & _
                            AdvProductArray(11, k))
                End If
            k = k + 1
        Loop
     
        stream.Close
    End If
    
    j = j + 1
    Loop

End Sub
Sub CPDReady()

    Dim i, j, k, m, w, x, y, datx, daty As Integer
    Dim KeySheetName As String
    Dim RateTitleName As String
    
    i = 0
    j = 0
    k = 0
    m = 1
    x = 1
    y = 1
    datx = 0
    daty = 0
    Dim LowAge, HighAge As Integer
    Workbooks.Add
    
    Do While Worksheets.Count > 1
        Application.DisplayAlerts = False
        Worksheets(2).Delete
    Loop

    Application.DisplayAlerts = True
    w = Worksheets.Count
    
    'Builds product information tab
    
    Worksheets(w).Name = "Product Information"
    
        Worksheets(w).Cells(1, 1) = "RATE INTRODUCTION"
        Worksheets(w).Cells(2, 1) = "Plancode"
        Worksheets(w).Cells(2, 2) = ProductArray(1, m)
        Worksheets(w).Cells(3, 1) = "Rate Set Version Code"
        Worksheets(w).Cells(3, 2) = ProductArray(2, m)
        Worksheets(w).Cells(4, 1) = "Rate Set Effective Date"
        Worksheets(w).Cells(4, 2) = ProductArray(3, m)
        If (UBound(AdvProductArray, 2) > 1) Then
            Worksheets(w).Cells(5, 1) = "Product Line Code"
            Worksheets(w).Cells(5, 2) = "U"
        End If
    
        Worksheets(w).Cells(7, 1) = "ISSUE LIMITS AND RESTRICTIONS"
        Worksheets(w).Cells(8, 1) = "Low Age"
        
        i = 1
        LowAge = 999
        Do While i <= UBound(RateArray, 2)
            If LowAge > CInt(RateArray(4, i)) Then
                LowAge = CInt(RateArray(4, i))
            End If
            i = i + 1
        Loop
        Worksheets(w).Cells(8, 2) = LowAge
        Worksheets(w).Cells(9, 1) = "High Age"
        HighAge = 0
        i = 1
        Do While i <= UBound(RateArray, 2)
            If HighAge < CInt(RateArray(4, i)) Then
                HighAge = CInt(RateArray(4, i))
            End If
            i = i + 1
        Loop
        Worksheets(w).Cells(9, 2) = HighAge
        Worksheets(w).Cells(10, 1) = "Issue Age Use Code"
        Worksheets(w).Cells(10, 2) = ProductArray(5, m)
        If (ProductArray(7, m) = "0") Then
            Worksheets(w).Cells(11, 1) = "Premium Years Number"
        End If
        If (ProductArray(7, m) = "1") Then
            Worksheets(w).Cells(11, 1) = "Premium Cease Age"
        End If
        Worksheets(w).Cells(11, 2) = ProductArray(6, m)
        Worksheets(w).Cells(12, 1) = "Premium Cease Duration or Age Indicator"
        Worksheets(w).Cells(12, 2) = ProductArray(7, m)
        If (ProductArray(9, m) = "0") Then
            Worksheets(w).Cells(13, 1) = "Benefit Period Policy Duration"
        End If
        If (ProductArray(9, m) = "1") Then
            Worksheets(w).Cells(13, 1) = "Benefit Period Attained Age"
        End If
        Worksheets(w).Cells(13, 2) = ProductArray(8, m)
        Worksheets(w).Cells(14, 1) = "Benefit Period Duration or Age Indicator"
        Worksheets(w).Cells(14, 2) = ProductArray(9, m)
        Worksheets(w).Cells(15, 1) = "Value Per Unit Amount"
        Worksheets(w).Cells(15, 2) = ProductArray(10, m)
        Worksheets(w).Cells(16, 1) = "Deficient Reserves Code"
        Worksheets(w).Cells(16, 2) = ProductArray(14, m)
        Worksheets(w).Cells(17, 1) = "Special Rate Designation Code"
        Worksheets(w).Cells(17, 2) = ProductArray(15, m)
        
        Worksheets(w).Cells(19, 1) = "AGENT PRODUCTION"
        If (ProductArray(12, m) = "1") Then
            Worksheets(w).Cells(20, 1) = "Production Credit per Unit Amount"
        End If
        If (ProductArray(12, m) = "2") Then
            Worksheets(w).Cells(20, 1) = "Production Credit Percent"
        End If
        If (ProductArray(12, m) = "3") Then
            Worksheets(w).Cells(20, 1) = "Production Credit Flat Amount"
        End If
        Worksheets(w).Cells(20, 2) = ProductArray(11, m)
        Worksheets(w).Cells(21, 1) = "Production Credit Use Code"
        Worksheets(w).Cells(21, 2) = ProductArray(12, m)
        Worksheets(w).Cells(22, 1) = "Million Dollar Round Table Code"
        Worksheets(w).Cells(22, 2) = ProductArray(13, m)
        
        
    i = 0
    j = 0
    k = 0
    x = 1
    y = 1
    datx = 0
    daty = 0

    ' Builds GROUPS Premium Limits and Restraints tabe if the text file is contains an advanced product

    If (UBound(AdvProductArray, 2) > 1) Then
        w = w + 1
        Worksheets.Add(After:=Worksheets(Worksheets.Count)).Name = "GROUPS Prem Lmts And Restrs"
        
        Worksheets(w).Cells(1, 1) = "PREMUM RESTRICTIONS"
        Worksheets(w).Cells(2, 1) = "Minimum Initial Premium Rule Code"
        i = 1
        Do While (i < UBound(AdvProductArray, 1))
            If m = AdvProductArray(0, i) Then
                Worksheets(w).Cells(2, 2) = AdvProductArray(4, i)
                i = UBound(AdvProductArray, 2)
            End If
            i = i + 1
        Loop
        i = 1
        Worksheets(w).Cells(3, 1) = "Corridor Rule Code"
        Do While (i < UBound(AdvProductArray, 1))
            If m = AdvProductArray(0, i) Then
                Worksheets(w).Cells(3, 2) = AdvProductArray(8, i)
                i = UBound(AdvProductArray, 2)
            End If
            i = i + 1
        Loop
        
        Worksheets(w).Cells(5, 1) = "PREMUM LIMITS"
        
        i = 0
        x = 1
        y = 6
        Do While i <= UBound(AdvProductArray, 2)
            Do While j <= UBound(AdvProductArray, 1)
                If j <> 4 And j <> 8 Then
                    Worksheets(w).Cells(y, x) = AdvProductArray(j, i)
                    x = x + 1
                End If
                j = j + 1
            Loop
            x = 2
            j = 1
            i = i + 1
            y = y + 1
        Loop
        
    End If
    
    k = 1

    'Produces Rates in Tabs
    
    Do While (k <= UBound(RateArray, 2))
    
        KeySheetName = RateArray(10, k)
        If (Left(RateArray(10, k), 1) = "*") Then
            KeySheetName = Right(RateArray(10, k), 1)
        End If
        If (Right(RateArray(10, k), 1) = "*") Then
            If Len(KeySheetName) = 1 Then
                KeySheetName = ""
            Else
                KeySheetName = Left(KeySheetName, 1)
            End If
        End If
        
        If RateArray(5, k) = "0" Then
            KeySheetName = RateArray(1, k) & " - " & Left(RateArray(2, k), 2) & "-" & Mid(RateArray(2, k), 4, 2) & "-" & Right(RateArray(2, k), 4) & " " & KeySheetName
        Else
            KeySheetName = RateArray(1, k) & " - " & Left(RateArray(2, k), 2) & "-" & Mid(RateArray(2, k), 4, 2) & "-" & Right(RateArray(2, k), 4) & " " & KeySheetName & " Select"
        End If
  
        
        w = 1
        Do While ((w <= Worksheets.Count) And (Not (Worksheets(w).Name = KeySheetName)))
            
            If (w = Worksheets.Count And (Not (Worksheets(w).Name = KeySheetName))) Then
                Worksheets.Add(After:=Worksheets(Worksheets.Count)).Name = KeySheetName
                w = 0
            End If
            w = w + 1
        Loop
        
        ' Find the place to put the attained age rates
        If RateArray(5, k) = "0" Then
            datx = 1
            daty = 1
            RateTitleName = RateArray(7, k) & " " & RateArray(8, k) & " " & RateArray(9, k)
            
            Do While (Not (Worksheets(w).Cells(daty, datx) = RateTitleName))
                If Len(Worksheets(w).Cells(daty, datx)) = 0 Then
                    Worksheets(w).Cells(daty, datx) = RateTitleName
                    datx = datx - 3
                End If
                datx = datx + 3
            Loop
                
            Do While (Len(Worksheets(w).Cells(daty, datx)) > 0)
                 daty = daty + 1
            Loop
            Worksheets(w).Cells(daty, datx) = RateArray(4, k)
            Worksheets(w).Cells(daty, datx + 1) = RateArray(11, k)
        
        End If
        
        If (Not (RateArray(5, k) = "0")) Then
            datx = 1
            daty = 1
            RateTitleName = RateArray(7, k) & " " & RateArray(8, k) & " " & RateArray(9, k)
            
            Do While (Not (Worksheets(w).Cells(daty, datx) = RateTitleName))
                If Len(Worksheets(w).Cells(daty, datx)) = 0 Then
                    Worksheets(w).Cells(daty, datx) = RateTitleName
                    daty = daty - 122
                End If
                daty = daty + 122
            Loop
                
            Do While (Not (Worksheets(w).Cells(daty, datx) = RateArray(5, k)))
                 If (Len(Worksheets(w).Cells(daty, datx)) = 0) Then
                    Worksheets(w).Cells(daty, datx) = RateArray(5, k)
                    datx = datx - 1
                 End If
                 datx = datx + 1
            Loop
            
            daty = daty + 1
            Do While (Not (Worksheets(w).Cells(daty, 1) = RateArray(4, k)))
                 If (Len(Worksheets(w).Cells(daty, 1)) = 0) Then
                    Worksheets(w).Cells(daty, 1) = RateArray(4, k)
                    daty = daty - 1
                 End If
                 daty = daty + 1
            Loop
            
            Worksheets(w).Cells(daty, datx) = RateArray(11, k)
        
        End If
        k = k + 1
    Loop

    q = 1

End Sub
Sub Main()

    Dim R As Integer
    Dim PctDone As Single
    Dim LastPctDone As Single
    
    If TypeName(ActiveSheet) <> "Worksheet" Then Exit Sub
    Application.ScreenUpdating = False
    
    Dim sFileName As String
    Dim iFileNum As Integer
    Dim sBuf As String
    
    With ProgressBar
        ReDim ProductArray(18, 0) As String
    
            ProductArray(0, 0) = "0"
            ProductArray(1, 0) = "Plancode"
            ProductArray(2, 0) = "Plancode Version"
            ProductArray(3, 0) = "Plancode V Effective Date"
            ProductArray(4, 0) = "Age"
            ProductArray(5, 0) = "Age Use Code"
            ProductArray(6, 0) = "Pay Age"
            ProductArray(7, 0) = "Pay Age Use Code"
            ProductArray(8, 0) = "ME-Age"
            ProductArray(9, 0) = "ME-Age Use Code"
            ProductArray(10, 0) = "Value Per Unit"
            ProductArray(11, 0) = "Production Credit"
            ProductArray(12, 0) = "Production Credit Use Code"
            ProductArray(13, 0) = "Million Dollar Round Table (MRDT)"
            ProductArray(14, 0) = "Deficient"
            ProductArray(15, 0) = "Special Benefit Class"
            ProductArray(16, 0) = "R"
            ProductArray(17, 0) = "LV"
            ProductArray(18, 0) = "Duration"
   
        ReDim AdvProductArray(11, 0) As String
        
            AdvProductArray(0, 0) = "0"
            AdvProductArray(1, 0) = "Issue Age"
            AdvProductArray(2, 0) = "Initial Minimum"
            AdvProductArray(3, 0) = "Initial Maximum"
            AdvProductArray(4, 0) = "Rule Code"
            AdvProductArray(5, 0) = "Periodic Premium Minimum"
            AdvProductArray(6, 0) = "Periodic Premium Maximum"
            AdvProductArray(7, 0) = "Required First Year Premium"
            AdvProductArray(8, 0) = "Corridor Rule Code"
            AdvProductArray(9, 0) = "Corridor Percentage"
            AdvProductArray(10, 0) = "Corridor Amount"
            AdvProductArray(11, 0) = "MAP Period"
        
        ReDim AddAssocProductArray(3, 0) As String
        
            AddAssocProductArray(0, 0) = "0"
            AddAssocProductArray(1, 0) = "Associated Product Plancode"
            AddAssocProductArray(2, 0) = "Associated Rate Set Version Code"
            AddAssocProductArray(3, 0) = "Associated Rate Set Effective Date"
        
        ReDim RateArray(11, 0) As String
            
            RateArray(0, 0) = "0"
            RateArray(1, 0) = "Rate Type"
            RateArray(2, 0) = "Scale Start"
            RateArray(3, 0) = "Scale Stop"
            RateArray(4, 0) = "Attained Age"
            RateArray(5, 0) = "Duration"
            RateArray(6, 0) = "Issue Age"
            RateArray(7, 0) = "Gender"
            RateArray(8, 0) = "Rate Class"
            RateArray(9, 0) = "Band"
            RateArray(10, 0) = "Plan Option"
            RateArray(11, 0) = "Rate"

    End With
    
    ' Get the file name:
    sFileName = Range("sFile").Value

    ' Test if the file exists
    If Len(Dir$(sFileName)) = 0 Then
        j = MsgBox("Text File Not Found")
        Unload ProgressBar
        Exit Sub
    End If
    
    With ProgressBar
        .FrameProgress.Caption = "Analyzing file size"
        DoEvents
    End With
    
    total_lines = LineCount(sFileName)
    
    Open sFileName For Input As #1
    
    For i = 1 To total_lines
        Line Input #1, sBuf
        Analyze (sBuf)
        PctDone = i / (total_lines)
        If (PctDone - LastPctDone) > 0.01 Then
            With ProgressBar
                .FrameProgress.Caption = Format(PctDone, "0%")
                .LabelProgress.Width = PctDone * (.FrameProgress.Width - 10)
            End With
            LastPctDone = PctDone
        End If
        
        'The DoEvents statement is responsible for the Progress Bar form updating
        DoEvents
    Next i
    If (Range("sTextFileOption").Value) Then
        ProduceTextFile
    End If
    If (Range("sCPDReadyOption").Value) Then
        CPDReady
    End If
    Close #1
    Unload ProgressBar
End Sub



