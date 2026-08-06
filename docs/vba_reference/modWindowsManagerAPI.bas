' Module: modWindowsManagerAPI.bas
' Type: Standard Module
' Stream Path: VBA/modWindowsManagerAPI
' =========================================================

Attribute VB_Name = "modWindowsManagerAPI"
'====================================================================
'  modWindowManagerEnum – 64-/32-bit safe Windows API wrapper module
'  » All public-facing routines are unchanged. Only the private API
'    declarations and pointer-sized data types were updated.
'  » VBA7 is assumed.  Use LongPtr / PtrSafe everywhere.
'  » GetWindowLongPtr is conditionally aliased because the 32-bit
'    version of user32.dll only exposes GetWindowLong[AW] names.
'====================================================================
Option Explicit

#If VBA7 Then
    '====================  Windows-API declarations  ====================
    '––  enumeration & window text ––––––––––––––––––––––––––––––––––––––
    Private Declare PtrSafe Function EnumWindows Lib "user32" (ByVal lpEnumFunc As LongPtr, ByVal lParam As LongPtr) As Long
    Private Declare PtrSafe Function GetWindowTextLengthW Lib "user32" (ByVal hWnd As LongPtr) As Long
    Private Declare PtrSafe Function GetWindowTextW Lib "user32" (ByVal hWnd As LongPtr, ByVal lpString As LongPtr, ByVal cch As Long) As Long

    '––  visibility & show/hide –––––––––––––––––––––––––––––––––––––––––
    Private Declare PtrSafe Function IsWindowVisible Lib "user32" (ByVal hWnd As LongPtr) As Long
    Private Declare PtrSafe Function ShowWindow Lib "user32" (ByVal hWnd As LongPtr, ByVal nCmdShow As Long) As Long

    '––  misc. style/rect/process info ––––––––––––––––––––––––––––––––––
    #If Win64 Then
        Private Declare PtrSafe Function GetWindowLongPtr Lib "user32" Alias "GetWindowLongPtrW" (ByVal hWnd As LongPtr, ByVal nIndex As Long) As LongPtr
    #Else
        '32-bit user32 exports GetWindowLongW; alias accordingly so we can
        'still call it using the GetWindowLongPtr name.
        Private Declare PtrSafe Function GetWindowLongPtr Lib "user32" Alias "GetWindowLongW" (ByVal hWnd As LongPtr, ByVal nIndex As Long) As LongPtr
    #End If

    Private Declare PtrSafe Function GetWindow Lib "user32" (ByVal hWnd As LongPtr, ByVal uCmd As Long) As LongPtr
    Private Declare PtrSafe Function GetWindowRect Lib "user32" (ByVal hWnd As LongPtr, lpRect As RECT) As Long
    Private Declare PtrSafe Function GetWindowThreadProcessId Lib "user32" (ByVal hWnd As LongPtr, lpdwProcessId As Long) As Long
    Private Declare PtrSafe Function OpenProcess Lib "kernel32" (ByVal dwDesiredAccess As Long, ByVal bInheritHandle As Long, ByVal dwProcessId As Long) As LongPtr
    Private Declare PtrSafe Function QueryFullProcessImageNameW Lib "kernel32" (ByVal hProcess As LongPtr, ByVal dwFlags As Long, ByVal lpExeName As LongPtr, ByRef lpdwSize As Long) As Long
    Private Declare PtrSafe Function CloseHandle Lib "kernel32" (ByVal hObject As LongPtr) As Long
    Private Declare PtrSafe Function GetClassNameW Lib "user32" (ByVal hWnd As LongPtr, ByVal lpClassName As LongPtr, ByVal nMaxCount As Long) As Long

    '====================  ALWAYS-ON-TOP helpers  =======================
    Private Declare PtrSafe Function SetWindowPos Lib "user32" (ByVal hWnd As LongPtr, ByVal hWndInsertAfter As LongPtr, ByVal X As Long, ByVal Y As Long, ByVal cx As Long, ByVal cy As Long, ByVal wFlags As Long) As Long


    '====================  WinEvent hook  ==============================
    Private Declare PtrSafe Function SetWinEventHook Lib "user32" (ByVal eventMin As Long, ByVal eventMax As Long, ByVal hMod As LongPtr, ByVal pfn As LongPtr, ByVal idProcess As Long, ByVal idThread As Long, ByVal dwFlags As Long) As LongPtr
    Private Declare PtrSafe Function UnhookWinEvent Lib "user32" (ByVal hWinEventHook As LongPtr) As Long

    '====================  simple UI-refresh timer  ====================
    Private Declare PtrSafe Function SetTimer Lib "user32" (ByVal hWnd As LongPtr, ByVal nIDEvent As LongPtr, ByVal uElapse As Long, ByVal lpTimerFunc As LongPtr) As LongPtr
    Private Declare PtrSafe Function KillTimer Lib "user32" (ByVal hWnd As LongPtr, ByVal nIDEvent As LongPtr) As Long
#End If    'VBA7

'====================  Public constants (exported)  =================
Public Const SW_HIDE    As Long = 0
Public Const SW_SHOW    As Long = 5      'or SW_SHOWNORMAL (=1)
Public Const SW_RESTORE As Long = 9

Private Const GW_OWNER         As Long = 4&


'====================  Enumerate open top-level windows  =============
Private mTitles  As Collection
Private mHandles As Collection
Private mDisplayNames As Collection
Public gSkipHwnd As LongPtr          'available if the form wants to tag itself

Private frmCaption As String        'caption of the calling form

Private Type RECT
    left   As Long
    top    As Long
    Right  As Long
    Bottom As Long
End Type

'––––––––––––  ALWAYS-ON-TOP helpers  ––––––––––––––––––––––––
Public Const HWND_TOPMOST   As LongPtr = -1
Public Const HWND_NOTOPMOST As LongPtr = -2

Private Const SWP_NOACTIVATE As Long = &H10

'–––––––––––  WinEvent hook to catch window create/destroy –––––––––––
Private Const EVENT_OBJECT_CREATE  As Long = &H8000    'new window
Private Const EVENT_OBJECT_DESTROY As Long = &H8001    'closed window
Private Const OBJID_WINDOW         As Long = 0
Private Const WINEVENT_OUTOFCONTEXT   As Long = &H0
Private Const WINEVENT_SKIPOWNPROCESS As Long = &H2
Private Const EVENT_OBJECT_SHOW    As Long = &H8002
Private Const EVENT_OBJECT_HIDE    As Long = &H8003
Private Const EVENT_SYSTEM_FOREGROUND As Long = &H3

'––––––––––––––––––––––  module level variables ––––––––––––––––––––––
Private hHookCreateDestroy As LongPtr
Private hHookForeground    As LongPtr
Private mMgrEvt   As clsWindowDisplayManager   'object we’ll tell to Refresh
Private fCaption  As String             'Parent form caption

Private mTimerID  As LongPtr
Private mMgrRef   As clsWindowDisplayManager
Private mCurrentWindows()
Private mblnTimerOn As Boolean


'eCount shoudl be updated to equal the number of items in eWinArray (not include ecount)
Public Enum eWinArray
    eTitle = 1
    eHwnd = 2
    eListOrder = 3
    eIsSelected = 4
    eDisplayname = 5
    eCount = 5
End Enum

Global mTB_HWnd As LongPtr



Public Property Let MyTaskbar_Handle(hWnd As LongPtr)
    mTB_HWnd = hWnd
End Property
Public Property Get MyTaskbar_Handle() As LongPtr
   MyTaskbar_Handle = mTB_HWnd
End Property

'====================  Thin wrappers exposed to forms  ==============
'Return True if the window is currently visible
Public Function Window_IsVisible(ByVal hWnd As LongPtr) As Boolean
    Window_IsVisible = (IsWindowVisible(hWnd) <> 0)
End Function

'Show, hide or restore a window (nCmdShow = SW_HIDE / SW_SHOW / SW_RESTORE) Window_Show
Public Sub Window_Show(ByVal hWnd As LongPtr, ByVal nCmdShow As Long)
    ShowWindow hWnd, nCmdShow
End Sub


'-----------  PUBLIC ENTRY POINT  -----------------------------------
Public Function GetOpenWindows(ByVal callerCaption As String) As Variant
    fCaption = callerCaption

    Set mTitles = New Collection
    Set mHandles = New Collection
    Set mDisplayNames = New Collection
    EnumWindows AddressOf EnumProc, 0&           'kick-off enumeration

    Dim n As Long: n = mTitles.Count
    If n = 0 Then Exit Function

    Dim arr() As Variant, i As Long
    ReDim arr(1 To n, 1 To eCount)
    For i = 1 To n
        arr(i, eTitle) = mTitles(i)
        arr(i, eHwnd) = mHandles(i)
        arr(i, eListOrder) = 0                      'This will be used later to order the controls
        arr(i, eIsSelected) = False                 'IsSelected
        arr(i, eDisplayname) = mDisplayNames(i)     'Name displayed in the windows form
        'Debug.Print "   " & arr(i, 1); " | " & arr(i, 2) & " | " & arr(i, 3) & " | " & arr(i, 4)
    Next i

    'update current array
    mCurrentWindows = arr
    GetOpenWindows = arr
End Function

'-----------  CALLBACK FOR EnumWindows  ------------------------------
Private Function EnumProc(ByVal hWnd As LongPtr, ByVal lParam As LongPtr) As LongPtr
    '0) Ignore invisible windows unless they were made invisible by user
    Dim r As Long
    Dim blnKeep As Boolean
    
    'Debug.Print "EnumProc Call"
    
    
    If ArrayHasData(mCurrentWindows) Then
        For r = LBound(mCurrentWindows, 1) To UBound(mCurrentWindows, 1)

            
            If mCurrentWindows(r, 2) = hWnd Then
                blnKeep = True
                'Debug.Print "   " & mCurrentWindows(r, 1); " | " & mCurrentWindows(r, 2) & " | " & mCurrentWindows(r, 3) & " | " & blnKeep
                Exit For
            End If
        Next
    End If
        
    
    'If the window is invisible and its not been flagged to keep, then it can be removed
    If IsWindowVisible(hWnd) = 0 And Not blnKeep Then EnumProc = 1: Exit Function

    '1) Window caption
    Dim nLen As Long: nLen = GetWindowTextLengthW(hWnd)
    If nLen = 0 Then EnumProc = 1: Exit Function  'blank title

    Dim buff As String: buff = Space$(nLen + 1)
    GetWindowTextW hWnd, StrPtr(buff), nLen + 1
    buff = Trim$(buff)
    
    Dim title As String
    title = CleanCaption(buff)
    
    'Test for some app/window names that are not relevant to the user and we dont want to display
    'This wont catch everything but we do what we can here
    Dim testtitle As String
    testtitle = LCase$(title)
    If testtitle Like "*windows input*" _
       Or testtitle = "program manager" _
       Or testtitle = "task manager" _
        Or testtitle = "settings" _
       Or testtitle = Trim$(LCase$(fCaption)) Then
          EnumProc = 1
          Exit Function
    End If

    Debug.Print "Title of window: " & title

    '2) Skip tool-windows
    Dim style As LongPtr
    style = GetWindowLongPtr(hWnd, GWL_EXSTYLE)
    If (style And WS_EX_TOOLWINDOW) <> 0 Then EnumProc = 1: Exit Function

    '3) Store
    mTitles.Add title
    mDisplayNames.Add FormatCaption(title)
    mHandles.Add hWnd

    EnumProc = 1                                    'continue enumeration
End Function


'========================================================================================================================
' Helpers for re-formatting window captions
'========================================================================================================================

'-- 1) Convert full application name ? short label
Private Function ShortAppName(ByVal appTitle As String) As String
    Select Case LCase$(Trim$(appTitle))
        Case "google chrome":     ShortAppName = "Chrome"
        Case "microsoft edge":    ShortAppName = "Edge"
        Case "mozilla firefox":   ShortAppName = "Firefox"
        Case "file explorer":     ShortAppName = "File Explorer"
        Case Else:                ShortAppName = appTitle          'leave as-is
    End Select
End Function

'-- 2) Optional: shorten well-known “detail” phrases
Private Function ShortDetails(ByVal detail As String) As String
    If InStr(1, LCase$(detail), "chatgpt", vbTextCompare) > 0 Then
        ShortDetails = "GPT"
    Else
        ShortDetails = detail
    End If
End Function

'-- 3) Main formatter:  App  –  Details
Private Function FormatCaption(ByVal fullTitle As String) As String
    Dim title As String: title = Replace$(fullTitle, ChrW$(160), " ")   'non-breaking space ? normal

    'find the *last* dash-style delimiter – covers " - " and " – "
    Dim delimPos As Long
    delimPos = InStrRev(title, " - ")
    If delimPos = 0 Then delimPos = InStrRev(title, " – ")

    'If we didn’t find “app – detail”, just return what we got
    If delimPos = 0 Then
        FormatCaption = title
        Exit Function
    End If

    Dim details As String, appPart As String, shorten As String
    details = Trim$(left$(title, delimPos - 1))
    appPart = Trim$(Mid$(title, delimPos + 3))        '3 = Len(" - ")
    shorten = ShortAppName(appPart)

    'swap + shorten
    FormatCaption = shorten & " - " & details
End Function

Function ArrayHasData(ByRef arr As Variant) As Boolean
    Dim lb As Long, ub As Long

    On Error Resume Next        '—if the array is unallocated,
    lb = LBound(arr, 1)         '  LBound/UBound raise error 9
    ub = UBound(arr, 1)
    If Err.Number = 0 Then
        ArrayHasData = (ub >= lb)
    End If
    On Error GoTo 0
End Function


