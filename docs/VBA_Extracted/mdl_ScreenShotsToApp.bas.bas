' Module: mdl_ScreenShotsToApp.bas
' Type: Standard Module
' Stream Path: VBA/mdl_ScreenShotsToApp
' =========================================================

Attribute VB_Name = "mdl_ScreenShotsToApp"
Option Explicit

'=============================================
'  CaptureDesktopToWord_APPEND
'=============================================

'----------- 1. 64-/32-bit API declares (same as before) -----------

  Private Declare PtrSafe Function GetDC Lib "user32" (ByVal hWnd As LongPtr) As LongPtr
  Private Declare PtrSafe Function ReleaseDC Lib "user32" (ByVal hWnd As LongPtr, ByVal hDC As LongPtr) As Long
  Private Declare PtrSafe Function CreateCompatibleDC Lib "gdi32" (ByVal hDC As LongPtr) As LongPtr
  Private Declare PtrSafe Function CreateCompatibleBitmap Lib "gdi32" (ByVal hDC As LongPtr, ByVal nWidth As Long, ByVal nHeight As Long) As LongPtr
  Private Declare PtrSafe Function SelectObject Lib "gdi32" (ByVal hDC As LongPtr, ByVal hObject As LongPtr) As LongPtr
  Private Declare PtrSafe Function DeleteDC Lib "gdi32" (ByVal hDC As LongPtr) As Long
  Private Declare PtrSafe Function DeleteObject Lib "gdi32" (ByVal hObj As LongPtr) As Long
  Private Declare PtrSafe Function BitBlt Lib "gdi32" _
      (ByVal hDestDC As LongPtr, ByVal X As Long, ByVal Y As Long, _
       ByVal nWidth As Long, ByVal nHeight As Long, _
       ByVal hSrcDC As LongPtr, ByVal xSrc As Long, ByVal ySrc As Long, _
       ByVal dwRop As Long) As Long
  Private Declare PtrSafe Function GetSystemMetrics Lib "user32" (ByVal nIndex As Long) As Long
  Private Declare PtrSafe Function OpenClipboard Lib "user32" (ByVal hWnd As LongPtr) As Long
  Private Declare PtrSafe Function EmptyClipboard Lib "user32" () As Long
  Private Declare PtrSafe Function SetClipboardData Lib "user32" (ByVal wFormat As Long, ByVal hMem As LongPtr) As LongPtr
  Private Declare PtrSafe Function CloseClipboard Lib "user32" () As Long


'----------- 2. constants -----------
Private Const SM_XVIRTUALSCREEN As Long = 76
Private Const SM_YVIRTUALSCREEN As Long = 77
Private Const SM_CXVIRTUALSCREEN As Long = 78
Private Const SM_CYVIRTUALSCREEN As Long = 79
Private Const SM_CXSCREEN As Long = 0
Private Const SM_CYSCREEN As Long = 1
Private Const SRCCOPY As Long = &HCC0020
Private Const CAPTUREBLT As Long = &H40000000
Private Const CF_BITMAP As Long = 2
Private Const wdPasteBitmap As Long = 4

'----------- 3. keep Word running across clicks -----------
Private g_wdApp As Object   'Word.Application
Private g_wdDoc As Object   'Word.Document

'--- Outlook globals (persist between clicks) ---
Private g_olApp  As Object          'Outlook.Application
Private g_olMail As Object          'currently-open MailItem

Public Sub CaptureDesktopToOutlook_APPEND()
    On Error GoTo ErrorHandler

    '--- Get screen dimensions ---
    Dim X As Long, Y As Long, w As Long, h As Long
    X = 0: Y = 0
    w = GetSystemMetrics(SM_CXSCREEN)
    h = GetSystemMetrics(SM_CYSCREEN)

    '--- Capture screen ---
    Dim hDeskDC As LongPtr, hMemDC As LongPtr, hBmp As LongPtr, hOld As LongPtr
    hDeskDC = GetDC(0)
    hMemDC = CreateCompatibleDC(hDeskDC)
    hBmp = CreateCompatibleBitmap(hDeskDC, w, h)
    hOld = SelectObject(hMemDC, hBmp)

    BitBlt hMemDC, 0, 0, w, h, hDeskDC, X, Y, SRCCOPY Or CAPTUREBLT

    SelectObject hMemDC, hOld
    DeleteDC hMemDC
    ReleaseDC 0, hDeskDC

    '--- Clipboard ---
    If OpenClipboard(0&) Then
        EmptyClipboard
        If SetClipboardData(CF_BITMAP, hBmp) = 0 Then
            DeleteObject hBmp
            MsgBox "Failed to set clipboard data.", vbExclamation
            CloseClipboard
            Exit Sub
        End If
        CloseClipboard
    Else
        DeleteObject hBmp
        MsgBox "Unable to access clipboard.", vbExclamation
        Exit Sub
    End If

    '--- Outlook setup ---
    On Error Resume Next
    If g_olApp Is Nothing Then
        Set g_olApp = GetObject(, "Outlook.Application")
        If g_olApp Is Nothing Then Set g_olApp = CreateObject("Outlook.Application")
    End If
    On Error GoTo 0

    On Error GoTo ErrorHandler
    If g_olMail Is Nothing Then
        Set g_olMail = g_olApp.CreateItem(0)
        g_olMail.BodyFormat = 2
    Else
        
        Debug.Print "g_olMail.Sent: " & g_olMail.Sent
        Debug.Print "g_olMail.Saved: " & g_olMail.Saved
        If g_olMail.Sent Or g_olMail.Saved Then
            Set g_olMail = g_olApp.CreateItem(0)
            g_olMail.BodyFormat = 2
        End If
    End If
        
    On Error GoTo 0
    
    g_olMail.Display

    '--- Paste into WordEditor ---
    Dim wdDoc As Object
    Set wdDoc = g_olMail.GetInspector.WordEditor

    With wdDoc
        .Range(.Content.End - 1).Select
    End With

    '--- Insert timestamp ---
    Dim ts As String
    ts = Format(Now, "yyyy-mm-dd hh:nn:ss")
    Dim startPos As Long
    startPos = wdDoc.Application.Selection.Start
    
    With wdDoc.Application.Selection
        .TypeText Text:="Screenshot taken at: " & ts
        .TypeParagraph
        .PasteSpecial DataType:=wdPasteBitmap
        .TypeParagraph
        .TypeParagraph
    End With
    
    Dim endPos As Long
    endPos = wdDoc.Application.Selection.Start
    
    Dim pastedRange As Object
    Set pastedRange = wdDoc.Range(Start:=startPos, End:=endPos)

    
    If pastedRange.InlineShapes.Count > 0 Then
        With pastedRange.InlineShapes(1)
            .ScaleHeight = 50
            .ScaleWidth = 50
        End With
    Else
        MsgBox "No inline shape found in pasted range."
    End If


    '--- Optional: release Outlook objects if done ---
    'Set g_olMail = Nothing
    'Set g_olApp = Nothing

    Exit Sub

ErrorHandler:
    MsgBox "An error occurred when sending a screen shot to your outlook.   Error: " & Err.Description, vbCritical
    If hMemDC <> 0 Then DeleteDC hMemDC
    If hDeskDC <> 0 Then ReleaseDC 0, hDeskDC
    If hBmp <> 0 Then DeleteObject hBmp
    On Error GoTo 0
End Sub


Public Sub ScreenShotCleanup()
    Set g_olMail = Nothing
    Set g_olApp = Nothing
    
    Set g_wdDoc = Nothing
    Set g_wdApp = Nothing
   
End Sub

Private Sub test()
'CaptureDesktopToWord_APPEND
CaptureDesktopToOutlook_APPEND
End Sub


Public Sub CaptureDesktopToWord_APPEND()
    
    '---- A. grab desktop to clipboard (same code as before) ----
    Dim X As Long, Y As Long, w As Long, h As Long
    
    '---------------- all screens ---------------------
    'x = GetSystemMetrics(SM_XVIRTUALSCREEN)
    'y = GetSystemMetrics(SM_YVIRTUALSCREEN)
    'w = GetSystemMetrics(SM_CXVIRTUALSCREEN)
    'h = GetSystemMetrics(SM_CYVIRTUALSCREEN)
    
    '---------------- primary screen only ---------------------
    X = 0
    Y = 0
    w = GetSystemMetrics(0)  ' SM_CXSCREEN
    h = GetSystemMetrics(1)  ' SM_CYSCREEN

    
    
    Dim hDeskDC As LongPtr, hMemDC As LongPtr, hBmp As LongPtr, hOld As LongPtr
    hDeskDC = GetDC(0)
    hMemDC = CreateCompatibleDC(hDeskDC)
    hBmp = CreateCompatibleBitmap(hDeskDC, w, h)
    hOld = SelectObject(hMemDC, hBmp)
    
    BitBlt hMemDC, 0, 0, w, h, hDeskDC, X, Y, SRCCOPY Or CAPTUREBLT
    
    SelectObject hMemDC, hOld
    DeleteDC hMemDC
    ReleaseDC 0, hDeskDC
    
    OpenClipboard 0&
    EmptyClipboard
    SetClipboardData CF_BITMAP, hBmp     'clipboard now owns the bitmap
    CloseClipboard

    '---- B. Get or create a dedicated Word instance and document ----
    
    Dim docStillOpen As Boolean
    docStillOpen = False
    
    On Error Resume Next
    
    ' Check if g_wdApp is still valid
    If g_wdApp Is Nothing Then
        Set g_wdApp = CreateObject("Word.Application")
        g_wdApp.Visible = True
    Else
        ' Try accessing a property to test if it's still alive
        Dim testCount As Long
        testCount = g_wdApp.Documents.Count
        If Err.Number <> 0 Then
            Set g_wdApp = CreateObject("Word.Application")
            g_wdApp.Visible = True
            Set g_wdDoc = Nothing
            Err.Clear
        End If
    End If
    
    On Error GoTo 0
    
    
    On Error GoTo ErrorHandler
    ' Check if the document is still open
    If Not g_wdDoc Is Nothing Then
        Dim doc As Object
        For Each doc In g_wdApp.Documents
            If doc Is g_wdDoc Then
                docStillOpen = True
                Exit For
            End If
        Next doc
    End If
    
    ' If the document is not open, create a new one
    If Not docStillOpen Then
        Set g_wdDoc = g_wdApp.Documents.Add
    
        ' Set narrow margins
        With g_wdDoc.PageSetup
            .topMargin = g_wdApp.InchesToPoints(0.25)
            .BottomMargin = g_wdApp.InchesToPoints(0.25)
            .leftMargin = g_wdApp.InchesToPoints(0.25)
            .RightMargin = g_wdApp.InchesToPoints(0.25)
        End With
    End If


    '---- C. move to end, paste, add a blank line ----
    Dim rng As Object
    
    Set rng = g_wdDoc.Range
    rng.Collapse Direction:=0   ' Collapse to end of document
    rng.PasteSpecial DataType:=wdPasteBitmap
    rng.InsertParagraphAfter
    rng.InsertParagraphAfter

    Exit Sub

ErrorHandler:
        MsgBox "An error occurred when sending a screen shot to your outlook.   Error: " & Err.Description, vbCritical

End Sub

''=============================================================
''  CaptureDesktopToOutlook_APPEND
''     – grabs the desktop, puts it on the Clipboard,
''       opens (or re-uses) ONE compose window,
''       and pastes each new shot underneath the previous one.
''=============================================================
'Public Sub CaptureDesktopToOutlook_APPEND()
'
'    '----------- A.  grab the desktop to the Clipboard --------
'    Dim x As Long, y As Long, w As Long, h As Long
'
'    '---------------- all screens -----------------------------
'    x = GetSystemMetrics(SM_XVIRTUALSCREEN)
'    y = GetSystemMetrics(SM_YVIRTUALSCREEN)
'    w = GetSystemMetrics(SM_CXVIRTUALSCREEN)
'    h = GetSystemMetrics(SM_CYVIRTUALSCREEN)
'
'    '---------------- primary screen only ---------------------
'    x = 0
'    y = 0
'    w = GetSystemMetrics(0)  ' SM_CXSCREEN
'    h = GetSystemMetrics(1)  ' SM_CYSCREEN
'
'
'    Dim hDeskDC As LongPtr, hMemDC As LongPtr, hBmp As LongPtr, hOld As LongPtr
'    hDeskDC = GetDC(0)
'    hMemDC = CreateCompatibleDC(hDeskDC)
'    hBmp = CreateCompatibleBitmap(hDeskDC, w, h)
'    hOld = SelectObject(hMemDC, hBmp)
'
'    BitBlt hMemDC, 0, 0, w, h, hDeskDC, x, y, SRCCOPY Or CAPTUREBLT
'
'    SelectObject hMemDC, hOld
'    DeleteDC hMemDC
'    ReleaseDC 0, hDeskDC
'
'    OpenClipboard 0&
'    EmptyClipboard
'    SetClipboardData CF_BITMAP, hBmp          'clipboard now owns bitmap
'    CloseClipboard
'
'    '----------- B.  spin-up Outlook + one compose window -----------
'    On Error Resume Next
'    If g_olApp Is Nothing Then
'        Set g_olApp = GetObject(, "Outlook.Application")
'        If g_olApp Is Nothing Then _
'               Set g_olApp = CreateObject("Outlook.Application")
'    End If
'    On Error GoTo 0
'
'    If g_olMail Is Nothing Then
'        Set g_olMail = g_olApp.CreateItem(0)   '0 = olMailItem
'        g_olMail.BodyFormat = 2                '2 = olFormatHTML
'        g_olMail.Display                       'show the inspector
'    End If
'
'    '----------- C.  paste at end of e-mail body -----------
'    Dim wdDoc As Object                       'Word document behind the mail
'    Set wdDoc = g_olMail.GetInspector.WordEditor
'
'    With wdDoc
'        .Range(.Content.End - 1).Select       'move cursor to end
'    End With
'
'    wdDoc.Application.Selection.PasteSpecial DataType:=wdPasteBitmap
'    wdDoc.Application.Selection.TypeParagraph       'blank line after shot
'    wdDoc.Application.Selection.TypeParagraph
'End Sub






