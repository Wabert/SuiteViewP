' Module: clsHiResTimer.cls
' Type: Standard Module
' Stream Path: VBA/clsHiResTimer
' =========================================================

Attribute VB_Name = "clsHiResTimer"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Option Explicit

Private Declare PtrSafe Function QueryFrequency Lib "kernel32" Alias "QueryPerformanceFrequency" (ByRef Frequency As Currency) As Long
Private Declare PtrSafe Function QueryCounter Lib "kernel32" Alias "QueryPerformanceCounter" (ByRef PerformanceCount As Currency) As Long
    
Dim Frequency As Currency
Dim Overhead As Currency
Dim Started As Currency
Dim Stopped As Currency

Private Sub Class_Initialize()
    Dim Count1 As Currency
    Dim Count2 As Currency
    
    Call QueryFrequency(Frequency)
    Call QueryCounter(Count1)
    Call QueryCounter(Count2)
    Overhead = Count2 - Count1
End Sub

Public Sub StartTimer()
    QueryCounter Started
End Sub

Public Sub StopTimer()
    QueryCounter Stopped
End Sub

Public Property Get Elapsed() As Double
    Dim Timer As Currency
    
    If Stopped = 0 Then
        QueryCounter Timer
    Else
        Timer = Stopped
    End If
    
    If Frequency > 0 Then
        Elapsed = (Timer - Started - Overhead) / Frequency
    End If
End Property



