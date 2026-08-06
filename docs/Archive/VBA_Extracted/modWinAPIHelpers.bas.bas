' Module: modWinAPIHelpers.bas
' Type: Standard Module
' Stream Path: VBA/modWinAPIHelpers
' =========================================================

Attribute VB_Name = "modWinAPIHelpers"
Option Explicit
Option Private Module      ' Keeps the helper API names out of Intellisense for other modules
'====================================================================
'  Windows API Helpers – VBA7-compliant, 32/64-bit safe
'  Last updated: 26-May-2025
'--------------------------------------------------------------------
'  Public surface      :   • WAPI_FormResizeMove
'                           • WAPI_SetWindowTopMost
'                           • WAPI_MakeFormResizable
'                           • WAPI_Sleep   (wrapper – use sparingly!)
'                           • WAPI_RemoveTitleBar
'                           • WAPI_GetWorkingArea
'                           • WAPI_ClickHoldDraggable
'                           • PrimeDragDropSystem  (safe no-op unless explicitly enabled)
'
'  Drag-&-drop support :   • SetupDragDropSafe   (installs subclass)
'                           • TeardownDragDropSafe (uninstalls – ALWAYS call!)
'====================================================================

#If VBA7 Then
    Private Const VBA7_OR_LATER As Long = 1
#Else
    Private Const VBA7_OR_LATER As Long = 0
#End If

'========  Common typedefs =====================================================
#If Win64 Then
    Private Type RECT_PTR
        left   As Long
        top    As Long
        Right  As Long
        Bottom As Long
    End Type

    Private Type MONITORINFO_PTR
        cbSize    As Long
        rcMonitor As RECT_PTR
        rcWork    As RECT_PTR
        dwFlags   As Long
    End Type
#Else
    Private Type RECT_PTR
        left   As Long
        top    As Long
        Right  As Long
        Bottom As Long
    End Type

    Private Type MONITORINFO_PTR
        cbSize    As Long
        rcMonitor As RECT_PTR
        rcWork    As RECT_PTR
        dwFlags   As Long
    End Type
#End If

'========  Conditional API declarations =======================================

#If Win64 Then   '===========================[ 64-bit Office ]==================
    '--- shell32 ---
    Private Declare PtrSafe Function DragAcceptFiles Lib "shell32.dll" (ByVal hWnd As LongPtr, ByVal fAccept As Long) As Long
    Private Declare PtrSafe Function DragQueryFile Lib "shell32.dll" Alias "DragQueryFileW" (ByVal hDrop As LongPtr, ByVal iFile As Long, ByVal lpszFile As LongPtr, ByVal cch As Long) As Long
    Private Declare PtrSafe Function DragFinish Lib "shell32.dll" (ByVal hDrop As LongPtr) As Long

    '--- user32  ---
    Private Declare PtrSafe Function SetWindowLongPtr Lib "user32" Alias "SetWindowLongPtrW" (ByVal hWnd As LongPtr, ByVal nIndex As Long, ByVal dwNewLong As LongPtr) As LongPtr
    Private Declare PtrSafe Function CallWindowProc Lib "user32" Alias "CallWindowProcW" (ByVal lpPrevWndFunc As LongPtr, ByVal hWnd As LongPtr, ByVal msg As Long, ByVal wParam As LongPtr, ByVal lParam As LongPtr) As LongPtr
    Private Declare PtrSafe Function FindWindow Lib "user32" Alias "FindWindowA" (ByVal lpClassName As String, ByVal lpWindowName As String) As LongPtr
    Private Declare PtrSafe Function GetWindowLongPtr Lib "user32" Alias "GetWindowLongPtrA" (ByVal hWnd As LongPtr, ByVal nIndex As Long) As LongPtr
    Private Declare PtrSafe Function DrawMenuBar Lib "user32" (ByVal hWnd As LongPtr) As Long
    Private Declare PtrSafe Function MonitorFromWindow Lib "user32" (ByVal hWnd As LongPtr, ByVal dwFlags As Long) As LongPtr
    Private Declare PtrSafe Function GetMonitorInfo Lib "user32" Alias "GetMonitorInfoA" (ByVal hMonitor As LongPtr, ByRef lpmi As MONITORINFO_PTR) As Long
    Private Declare PtrSafe Function EnumWindows Lib "user32" (ByVal lpEnumFunc As LongPtr, ByVal lParam As LongPtr) As Long
    Private Declare PtrSafe Function GetWindowTextLength Lib "user32" Alias "GetWindowTextLengthA" (ByVal hWnd As LongPtr) As Long
    Private Declare PtrSafe Function GetWindowText Lib "user32" Alias "GetWindowTextA" (ByVal hWnd As LongPtr, ByVal lpString As String, ByVal cch As Long) As Long
    Private Declare PtrSafe Function IsWindowVisible Lib "user32" (ByVal hWnd As LongPtr) As Long
    Private Declare PtrSafe Function SetWindowPos Lib "user32" (ByVal hWnd As LongPtr, ByVal hWndInsertAfter As LongPtr, ByVal X As Long, ByVal Y As Long, ByVal cx As Long, ByVal cy As Long, ByVal uFlags As Long) As Long
    Private Declare PtrSafe Function GetDC Lib "user32" (ByVal hWnd As LongPtr) As LongPtr
    Private Declare PtrSafe Function ReleaseDC Lib "user32" (ByVal hWnd As LongPtr, ByVal hDC As LongPtr) As Long
    Private Declare PtrSafe Function ReleaseCapture Lib "user32" () As Long
    Private Declare PtrSafe Function SendMessage Lib "user32" Alias "SendMessageA" (ByVal hWnd As LongPtr, ByVal wMsg As Long, ByVal wParam As LongPtr, ByVal lParam As LongPtr) As LongPtr
    Private Declare PtrSafe Function FindWindowW Lib "user32" (ByVal lpClassName As LongPtr, ByVal lpWindowName As LongPtr) As LongPtr
    Private Declare PtrSafe Function GetClassName Lib "user32" Alias "GetClassNameW" (ByVal hWnd As LongPtr, ByVal lpClass As LongPtr, ByVal nMaxCount As Long) As Long


    '--- gdi32  ---
    Private Declare PtrSafe Function GetDeviceCaps Lib "gdi32" (ByVal hDC As LongPtr, ByVal nIndex As Long) As Long
    
    '--- kernel32 ---
    Private Declare PtrSafe Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As Long)
   
       Private Declare PtrSafe Function SetProcessDpiAwarenessContext Lib "user32" _
            (ByVal value As LongPtr) As Boolean
    Private Declare PtrSafe Function GetAncestor Lib "user32" _
            (ByVal hWnd As LongPtr, ByVal gaFlags As Long) As LongPtr
   
    
#Else            '===========================[ 32-bit Office ]==================
    Private Declare PtrSafe Function DragAcceptFiles Lib "shell32.dll" (ByVal hWnd As Long, ByVal fAccept As Long) As Long
    Private Declare PtrSafe Function DragQueryFile Lib "shell32.dll" Alias "DragQueryFileW" (ByVal hDrop As Long, ByVal iFile As Long, ByVal lpszFile As Long, ByVal cch As Long) As Long
    Private Declare PtrSafe Function DragFinish Lib "shell32.dll" (ByVal hDrop As Long) As Long
    Private Declare PtrSafe Function SetWindowLongPtr Lib "user32" Alias "SetWindowLongW" (ByVal hWnd As Long, ByVal nIndex As Long, ByVal dwNewLong As Long) As Long
    Private Declare PtrSafe Function CallWindowProc Lib "user32" Alias "CallWindowProcW" (ByVal lpPrevWndFunc As Long, ByVal hWnd As Long, ByVal msg As Long, ByVal wParam As Long, ByVal lParam As Long) As Long
    Private Declare PtrSafe Function FindWindow Lib "user32" Alias "FindWindowA" (ByVal lpClassName As String, ByVal lpWindowName As String) As Long
    Private Declare PtrSafe Function GetWindowLongPtr Lib "user32" Alias "GetWindowLongA" (ByVal hWnd As Long, ByVal nIndex As Long) As Long
    Private Declare PtrSafe Function DrawMenuBar Lib "user32" (ByVal hWnd As Long) As Long
    Private Declare PtrSafe Function MonitorFromWindow Lib "user32" (ByVal hWnd As Long, ByVal dwFlags As Long) As Long
    Private Declare PtrSafe Function GetMonitorInfo Lib "user32" Alias "GetMonitorInfoA" (ByVal hMonitor As Long, ByRef lpmi As MONITORINFO_PTR) As Long
    Private Declare PtrSafe Function EnumWindows Lib "user32" (ByVal lpEnumFunc As Long, ByVal lParam As Long) As Long
    Private Declare PtrSafe Function GetWindowTextLength Lib "user32" Alias "GetWindowTextLengthA" (ByVal hWnd As Long) As Long
    Private Declare PtrSafe Function GetWindowText Lib "user32" Alias "GetWindowTextA" (ByVal hWnd As Long, ByVal lpString As String, ByVal cch As Long) As Long
    Private Declare PtrSafe Function IsWindowVisible Lib "user32" (ByVal hWnd As Long) As Long
    Private Declare PtrSafe Function SetWindowPos Lib "user32" (ByVal hWnd As Long, ByVal hWndInsertAfter As Long, ByVal X As Long, ByVal Y As Long, ByVal cx As Long, ByVal cy As Long, ByVal uFlags As Long) As Long
    Private Declare PtrSafe Function GetDC Lib "user32" (ByVal hWnd As Long) As Long
    Private Declare PtrSafe Function ReleaseDC Lib "user32" (ByVal hWnd As Long, ByVal hDC As Long) As Long
    Private Declare PtrSafe Function ReleaseCapture Lib "user32" () As Long
    Private Declare PtrSafe Function SendMessage Lib "user32" Alias "SendMessageA" (ByVal hWnd As Long, ByVal wMsg As Long, ByVal wParam As Long, ByVal lParam As Long) As Long
    Private Declare PtrSafe Function GetDeviceCaps Lib "gdi32" (ByVal hDC As Long, ByVal nIndex As Long) As Long
    Private Declare PtrSafe Sub Sleep Lib "kernel32" (ByVal dwMilliseconds As Long)
    Private Declare PtrSafe Function FindWindowW Lib "user32" (ByVal lpClassName As Long, ByVal lpWindowName As Long) As Long

    Private Declare PtrSafe Function GetClassName Lib "user32" Alias "GetClassNameW" (ByVal hWnd As Long, ByVal lpClass As Long, ByVal nMaxCount As Long) As Long


#End If


'=====  API for Timer  (PtrSafe for 32/64-bit)  =========================
Private Declare PtrSafe Function GetTickCount Lib "kernel32" () As Long


Private Declare PtrSafe Function SystemParametersInfo Lib "user32" Alias "SystemParametersInfoA" (ByVal uAction As Long, ByVal uParam As Long, pvParam As Any, ByVal fWinIni As Long) As Long


'PtrSafe tells the compiler the declare is 64-bit ready.
'LongPtr automatically becomes:
'   • 8-bytes on 64-bit Office
'   • 4-bytes on 32-bit Office
Private Declare PtrSafe Function ShellExecute Lib "shell32.dll" Alias "ShellExecuteA" (ByVal hWnd As LongPtr, ByVal lpOperation As String, ByVal lpFile As String, ByVal lpParams As String, ByVal lpDir As String, ByVal nShowCmd As Long) As LongPtr

'For URL testing
Private Declare PtrSafe Function UrlIs Lib "shlwapi.dll" Alias "UrlIsW" (ByVal pszUrl As LongPtr, ByVal dwFlags As Long) As Long

'========  Constants ===========================================================
Private Const GWL_STYLE          As Long = -16
Private Const WS_CAPTION         As Long = &HC00000
Private Const WS_THICKFRAME      As Long = &H40000

Private Const WM_NCLBUTTONDOWN   As Long = &HA1
Private Const HTCAPTION          As Long = 2
Private Const WM_DROPFILES       As Long = &H233
Private Const GWL_WNDPROC        As Long = -4

Private Const LOGPIXELSX         As Long = 88
Private Const LOGPIXELSY         As Long = 90

Private Const MONITOR_DEFAULTTONEAREST As Long = &H2

Private Const HWND_TOPMOST       As LongPtr = -1


Private Const SWP_NOACTIVATE     As Long = &H10
Private Const SWP_NOZORDER       As Long = &H4

Private Const LOG_FILE_NAME      As String = "DragDropLog.txt"

'========  Module-level state ==================================================
Private mPrevWndProc   As LongPtr
Private mFormWnd       As LongPtr
Private mDragForm      As Object        ' The actual UserForm implementing AddLinkLabel
Private mIsHandling    As Boolean

Private mWindowDict    As Object        ' Late-bound Scripting.Dictionary
Private mLogFilePath   As String
'======  Testing if URL is good  ==============================================
Private Const URLIS_URL As Long = 0      'just “is this a URL?”


'----------------------- Create app as additional taskbar ---------------------------------------

' ====== API ======
#If VBA7 Then
    Private Declare PtrSafe Function SHAppBarMessage Lib "shell32.dll" _
            (ByVal dwMessage As Long, pData As APPBARDATA) As LongPtr

    Private Declare PtrSafe Function GetSystemMetrics Lib "user32" _
            (ByVal nIndex As Long) As Long

    Private Declare PtrSafe Function RegisterWindowMessage Lib "user32" _
            Alias "RegisterWindowMessageA" (ByVal lpString As String) As Long
            
            
    Private Declare PtrSafe Function GetDpiForWindow Lib "user32" (ByVal hWnd As LongPtr) As Long
#End If

' ====== types ======
Private Type RECT
    left   As Long: top As Long: Right  As Long: Bottom As Long
End Type

Private Type APPBARDATA
    cbSize           As Long
    hWnd             As LongPtr
    uCallbackMessage As Long
    uEdge            As Long
    rc               As RECT
    lParam           As LongPtr
End Type

' ====== constants ======
Private Const ABM_NEW     As Long = &H0&
Private Const ABM_REMOVE  As Long = &H1&
Private Const ABM_QUERYPOS As Long = &H2&
Private Const ABM_SETPOS   As Long = &H3&
Private Const ABM_GETTASKBARPOS As Long = &H5
Private Const ABE_LEFT  As Long = 0
Private Const ABE_TOP   As Long = 1
Private Const ABE_RIGHT As Long = 2
Private Const ABE_BOTTOM As Long = 3
Private Const SPI_GETWORKAREA As Long = &H30
Private Const SWP_SHOWWINDOW As Long = &H40&


Public Const SWP_NOMOVE       As Long = &H2
Public Const SWP_NOSIZE       As Long = &H1
Public Const SWP_FRAMECHANGED As Long = &H20
Public Const HWND_TOP         As LongPtr = 0


Public Const GWL_EXSTYLE    As Long = -20
Public Const WS_EX_TOOLWINDOW As Long = &H80     'hide from Alt+Tab & taskbar
Public Const WS_EX_APPWINDOW As Long = &H40000   'put in Alt+Tab & taskbar



'===== declarations (put in the same module you keep the other API code) =========
#If VBA7 Then
    
    Private Declare PtrSafe Function GetDesktopWindow Lib "user32" () As LongPtr
#End If

Private Const GA_ROOT = 2

Private Const GWLP_HWNDPARENT As Long = -8
#If VBA7 Then
Private Declare PtrSafe Function GetProcessDpiAwareness Lib "shcore" _
        (ByVal hProcess As LongPtr, awareness As Long) As Long
Private Declare PtrSafe Function GetCurrentProcess Lib "kernel32" () As LongPtr
#End If

Enum DPI_AWARE
    PROCESS_DPI_UNAWARE = 0          'virtualised – needs conversion
    PROCESS_SYSTEM_DPI_AWARE = 1     'virtualised
    PROCESS_PER_MONITOR_DPI_AWARE = 2 'true pixels
End Enum


' ====== public helpers ======
Public Sub CreateCustomTaskbarSpace(frm As Object, heightLogical As Long, ByRef Taskbar_pixel_width As Single, ByRef Taskbar_pixel_height As Single, ByRef Taskbar_pixel_top As Single, ByRef Taskbar_pixel_left As Single)
    'A.  Get the top-level window handle straight from the form
    Dim hWnd As LongPtr: hWnd = WAPI_WindowHandleFromCaption(frm.caption)
    If hWnd = 0 Then Exit Sub

    'B.  Work within *the monitor that owns this window*
    Dim hMon As LongPtr: hMon = MonitorFromWindow(hWnd, MONITOR_DEFAULTTONEAREST)
    Dim mi As MONITORINFO_PTR
    mi.cbSize = LenB(mi)
    If GetMonitorInfo(hMon, mi) = 0 Then Exit Sub

    Dim monLeft&, monTop&, monRight&, monBottom&
    monLeft = mi.rcMonitor.left:   monTop = mi.rcMonitor.top
    monRight = mi.rcMonitor.Right: monBottom = mi.rcMonitor.Bottom

    'C.  Convert the logical height you want into physical px for this monitor
    
'    Dim dpiY As Long
'    Dim hPx As Long
'    dpiY = GetDpiForWindow(hwnd)
'    If dpiY = 96 Then
'        'Process is SYSTEM_DPI_AWARE -> convert with Points to pixels
'        hPx = PointsToPixelsY(heightLogical) - PointsToPixelsY(0)
'    Else
'        'Per-monitor aware -> straight dpi maths
'        If dpiY = 0 Then dpiY = 96
'        hPx = heightLogical * dpiY \ 96
'    End If


    '----------------  Build the APPBARDATA ------------------------------------------
    Dim abd As APPBARDATA
    With abd
        .cbSize = LenB(abd)
        .hWnd = hWnd
        .uCallbackMessage = RegisterWindowMessage("MY_APPBAR")
        .uEdge = ABE_BOTTOM
        .rc.left = monLeft
        .rc.top = monBottom - heightLogical
        .rc.Right = monRight
        .rc.Bottom = monBottom
    End With
    
    '----------------  Register and negotiate the space with the shell ----------------
    If SHAppBarMessage(ABM_NEW, abd) = 0 Then Exit Sub
    SHAppBarMessage ABM_QUERYPOS, abd
    SHAppBarMessage ABM_SETPOS, abd

    '----------------  Move the window into the approved rectangle --------------------
    SetWindowPos abd.hWnd, 0, _
                 abd.rc.left, abd.rc.top, _
                 abd.rc.Right - abd.rc.left, _
                 abd.rc.Bottom - abd.rc.top, _
                 SWP_NOZORDER Or SWP_NOACTIVATE Or SWP_SHOWWINDOW


    '----------------- Save dimensions of rectange for later update -------------------
    Taskbar_pixel_width = abd.rc.Right - abd.rc.left
    Taskbar_pixel_height = abd.rc.Bottom - abd.rc.top
    Taskbar_pixel_top = abd.rc.top
    Taskbar_pixel_left = abd.rc.left

End Sub

'Return the class name for a window handle
Public Function WindowClassName(ByVal hWnd As LongPtr) As String
    Const BUFSZ As Long = 256
    Dim buf As String * BUFSZ, lngRet As Long

    lngRet = GetClassName(hWnd, StrPtr(buf), BUFSZ)
    If lngRet > 0 Then
        WindowClassName = left$(buf, lngRet)
    End If
End Function
'===== call this once, right after you show the UserForm ========================
Public Sub MakeFormTopLevel(frm As Object)
    Dim hFrm As LongPtr
    hFrm = WAPI_WindowHandleFromCaption(frm.caption)    'your helper that finds the handle
    If hFrm = 0 Then Exit Sub

    'Set owner = desktop (0)  ?  now the form is top-level, not owned by Excel
    SetWindowLongPtr hFrm, GWLP_HWNDPARENT, GetDesktopWindow()
End Sub


Public Sub NewTaskbarAsToolApp(frm As Object)
    Dim hWnd As LongPtr: hWnd = WAPI_WindowHandleFromCaption(frm.caption)
    If hWnd = 0 Then Exit Sub


    'read, tweak, write the extended style
    Dim ex As LongPtr
    ex = GetWindowLongPtr(hWnd, GWL_EXSTYLE)
    ex = (ex Or WS_EX_TOOLWINDOW) And Not WS_EX_APPWINDOW
    SetWindowLongPtr hWnd, GWL_EXSTYLE, ex

    'tell Windows the style changed
    SetWindowPos hWnd, HWND_TOP, 0, 0, 0, 0, _
                 SWP_NOMOVE Or SWP_NOSIZE Or SWP_FRAMECHANGED
End Sub



'==================================================
'Returns the visible thickness of the Windows task-bar (in pixels)
'If the bar is on the side we return its *width*; if on top/bottom we
'return its *height*.
Public Function GetSystemTaskbarThickness() As Long
    Dim abd As APPBARDATA
    abd.cbSize = LenB(abd)

    If SHAppBarMessage(ABM_GETTASKBARPOS, abd) <> 0 Then   'TRUE ==> success
        Select Case abd.uEdge
            Case ABE_TOP, ABE_BOTTOM
                GetSystemTaskbarThickness = abd.rc.Bottom - abd.rc.top
            Case ABE_LEFT, ABE_RIGHT
                GetSystemTaskbarThickness = abd.rc.Right - abd.rc.left
        End Select
    End If
End Function

'-----------------------------  Dock a form as a custom task-bar  -----------------------------
'Public Sub CreateCustomTaskbarSpace(frm As Object, Optional heightPixels As Long = 100)
'    Dim hwnd As LongPtr: hwnd = WAPI_WindowHandleFromCaption(frm.caption)
'
'    Debug.Print hwnd
'
'    If hwnd = 0 Then Exit Sub
'
'    '--- 1. declare working vars --------------------------------------------------------------
'    Dim abd As APPBARDATA          'structure passed to / returned from SHAppBarMessage
'    Dim cx  As Long, cy As Long    'full-screen pixel dimensions (primary monitor)
'
'    '--- 2. get screen size ------------------------------------------------------------------
'    cx = GetSystemMetrics(0)       'SM_CXSCREEN  ? screen width  in px
'    cy = GetSystemMetrics(1)       'SM_CYSCREEN  ? screen height in px
'
'
'    '--- 3. fill in APPBARDATA asking for a strip at the bottom ------------------------------
'    With abd
'        .cbSize = LenB(abd)                    'size of the structure
'        .hwnd = hwnd                           'window handle of the form
'        .uCallbackMessage = RegisterWindowMessage("MY_APPBAR")
'        .uEdge = ABE_BOTTOM                    'dock to bottom edge
'        'desired rectangle: full width, “heightPixels” tall, hugging screen bottom
'        .rc.left = 0
'        .rc.top = cy - heightPixels
'        .rc.Right = cx
'        .rc.Bottom = cy
'    End With
'
'
'    '--- 3a. make the window a "tool window" so it vanishes from Alt+Tab/taskbar
'    Dim ex As LongPtr
'     ex = GetWindowLongPtr(abd.hwnd, GWL_EXSTYLE)
'    ex = (ex Or WS_EX_TOOLWINDOW) And Not WS_EX_APPWINDOW
'    SetWindowLongPtr abd.hwnd, GWL_EXSTYLE, ex
'
'    'flush the style change (optional but tidy)
'    SetWindowPos abd.hwnd, 0, 0, 0, 0, 0, _
'                 SWP_NOMOVE Or SWP_NOSIZE Or SWP_NOZORDER Or SWP_FRAMECHANGED
'
'
'    '--- 4. register as a new app-bar ---------------------------------------------------------
'    If SHAppBarMessage(ABM_NEW, abd) = 0 Then Exit Sub   'exit if registration failed
'
'    '--- 5. let the shell adjust the rectangle (other bars may share the edge) ---------------
'    SHAppBarMessage ABM_QUERYPOS, abd    'shell suggests allowed rectangle
'    SHAppBarMessage ABM_SETPOS, abd      'shell locks that rectangle in place
'
'    '--- 6. move/resize the actual window into the approved rectangle ------------------------
'    SetWindowPos abd.hwnd, 0, _
'                 abd.rc.left, abd.rc.top, _
'                 abd.rc.Right - abd.rc.left, _
'                 abd.rc.Bottom - abd.rc.top, _
'                 SWP_NOZORDER Or SWP_NOACTIVATE Or SWP_SHOWWINDOW
'
'    '--- 7. stash the final size/position in public variables --------------------------------
'    Taskbar_width = abd.rc.Right - abd.rc.left
'    Taskbar_height = abd.rc.Bottom - abd.rc.top
'    Taskbar_top = abd.rc.top
'    Taskbar_left = abd.rc.left
'End Sub

Public Sub RemoveAppBar(frm As Object)
    Dim hWnd As LongPtr: hWnd = WAPI_WindowHandleFromCaption(frm.caption)
    If hWnd = 0 Then Exit Sub
    
    Dim abd As APPBARDATA
    abd.cbSize = LenB(abd)
    abd.hWnd = hWnd
    SHAppBarMessage ABM_REMOVE, abd
End Sub


Public Function GetTimePunch() As Currency
    GetTimePunch = GetTickCount
End Function

Public Function IsValidUrl(ByVal s As String) As Boolean
    'UrlIs returns 1 (=True) if it recognises the string
    If Len(s) = 0 Then Exit Function
    IsValidUrl = CBool(UrlIs(StrPtr(s), URLIS_URL))
End Function

Public Sub OpenLink(ByVal target As String, Optional ByVal hWnd As LongPtr = 0)
    'target can be "https://example.com", "C:\Docs\report.pdf", "C:\Data\", etc.
    'hwnd is the handle for the window that you can have be the owner of whatever opens.  So if that app closes what ever it openned will close
    
    Const SW_SHOWNORMAL As Long = 1        'show window if there is one
    Const ERROR_SUCCESS As Long = 32       'ShellExecute returns >31 on success

    If LenB(target) = 0 Then Exit Sub      'nothing to open
    If ShellExecute(hWnd, "open", target, vbNullString, vbNullString, SW_SHOWNORMAL) < ERROR_SUCCESS Then
        MsgBox "Unable to open: " & target, vbExclamation, "Open failed"
    End If
End Sub

Public Sub WAPI_FormResizeMove(ByVal frm As Object, _
                                ByVal PointsOrPixels As String, _
                                ByVal newwidth As Single, _
                                ByVal newheight As Single, _
                                ByVal newtop As Single, _
                                ByVal newleft As Single)
    Dim hWnd As LongPtr: hWnd = WAPI_WindowHandleFromCaption(frm.caption)
    If hWnd = 0 Then Exit Sub
        
    Select Case PointsOrPixels
       Case "Points":
                    Call SetWindowPos(hWnd, 0, _
                          PointsToPixelsX(newleft), _
                          PointsToPixelsY(newtop), _
                          PointsToPixelsX(newwidth), _
                          PointsToPixelsY(newheight), _
                          SWP_NOZORDER)
        Case "Pixels":
                    Call SetWindowPos(hWnd, 0, newleft, newtop, newwidth, newheight, SWP_NOZORDER)
        
        Case Else:  MsgBox "Must specify either 'Points' or 'Pixels'"
    End Select
        
End Sub
'wrapper – call once to pin, call again with False to release
Public Sub WAPI_SetWindowTopMost(ByVal frm As Object, Optional ByVal stayOnTop As Boolean = True)
    Dim hWnd As LongPtr: hWnd = WAPI_WindowHandleFromCaption(frm.caption)
    If hWnd = 0 Then Exit Sub
    
    Dim afterH As LongPtr
    afterH = IIf(stayOnTop, HWND_TOPMOST, HWND_NOTOPMOST)

    SetWindowPos hWnd, afterH, 0, 0, 0, 0, _
                 SWP_NOMOVE Or SWP_NOSIZE Or SWP_NOACTIVATE
End Sub

'Public Sub WAPI_BringToTop(ByVal frm As Object)
'    Dim hWnd As LongPtr
'    hWnd = WAPI_WindowHandleFromCaption(frm.caption)
'    If hWnd <> 0 Then _
'        SetWindowPos hWnd, HWND_TOPMOST, 0, 0, 0, 0, _
'                     SWP_NOMOVE Or SWP_NOSIZE Or SWP_NOACTIVATE
'End Sub

Public Sub WAPI_MakeFormResizable(ByVal frm As Object)
    Dim hWnd As LongPtr: hWnd = WAPI_WindowHandleFromCaption(frm.caption)
    If hWnd = 0 Then Exit Sub
    
#If Win64 Then
        Dim style As LongPtr: style = GetWindowLongPtr(hWnd, GWL_STYLE)
        style = style Or WS_THICKFRAME
        SetWindowLongPtr hWnd, GWL_STYLE, style
#Else
        Dim style As Long:     style = GetWindowLongPtr(hWnd, GWL_STYLE)
        style = style Or WS_THICKFRAME
        SetWindowLongPtr hWnd, GWL_STYLE, style
#End If
    DrawMenuBar hWnd
End Sub

' Sleep – wrapper. Consider using Application.Wait instead.
Public Sub WAPI_Sleep(ByVal ms As Long)
    Sleep CLng(ms)
End Sub

Public Sub WAPI_RemoveTitleBar(ByVal frm As Object)
    Dim hWnd As LongPtr: hWnd = WAPI_WindowHandleFromCaption(frm.caption)
    If hWnd = 0 Then Exit Sub
    
#If Win64 Then
        Dim style As LongPtr: style = GetWindowLongPtr(hWnd, GWL_STYLE)
        style = style And Not WS_CAPTION
        SetWindowLongPtr hWnd, GWL_STYLE, style
#Else
        Dim style As Long:     style = GetWindowLongPtr(hWnd, GWL_STYLE)
        style = style And Not WS_CAPTION
        SetWindowLongPtr hWnd, GWL_STYLE, style
#End If
    DrawMenuBar hWnd
End Sub

Public Sub WAPI_GetWorkingArea(ByVal frm As Object, _
                               ByRef outWidth As Single, _
                               ByRef outHeight As Single, _
                               ByRef outLeft As Single, _
                               ByRef outTop As Single, _
                               Optional blnPoints As Boolean = True)
                               
    Dim hWnd As LongPtr: hWnd = WAPI_WindowHandleFromCaption(frm.caption)
    If hWnd = 0 Then Exit Sub
    
    Dim hMon As LongPtr: hMon = MonitorFromWindow(hWnd, MONITOR_DEFAULTTONEAREST)
    
    Dim mi As MONITORINFO_PTR: mi.cbSize = LenB(mi)
    If GetMonitorInfo(hMon, mi) <> 0 Then
        outWidth = (mi.rcWork.Right - mi.rcWork.left)
        outHeight = (mi.rcWork.Bottom - mi.rcWork.top)
        outLeft = (mi.rcWork.left)
        outTop = (mi.rcWork.top)
        If blnPoints Then
            outWidth = PixelsToPointsX(outWidth)
            outHeight = PixelsToPointsY(outHeight)
            outLeft = PixelsToPointsX(outLeft)
            outTop = PixelsToPointsY(outTop)
        End If
    Else
        'Default size is in points
        outWidth = 800
        outHeight = 600
        outLeft = 0
        outTop = 0
        
        If Not blnPoints Then
            outWidth = PointsToPixelsX(outWidth)
            outHeight = PointsToPixelsY(outHeight)
            outLeft = 0
            outTop = 0
        End If
        
    End If
End Sub

' Click-and-drag anywhere on the form to move it
Public Sub WAPI_ClickHoldDraggable(ByVal frm As Object)
    Dim hWnd As LongPtr: hWnd = WAPI_WindowHandleFromCaption(frm.caption)
    If hWnd = 0 Then Exit Sub
    
    ReleaseCapture
    SendMessage hWnd, WM_NCLBUTTONDOWN, HTCAPTION, 0
End Sub

'====================================================================
'  ––– Safe Drag-and-Drop priming (no subclass left behind) –––
'====================================================================
Public Sub PrimeDragDropSystem(ByVal frm As Object)
    SetupDragDropSafe frm, False     ' install subclass
    TeardownDragDropSafe             ' and immediately remove it
End Sub

'  Enable drag-&-drop (install subclass). Call once in UserForm_Activate.
Public Sub SetupDragDropSafe(ByVal frm As Object, Optional ByVal enableRealHandling As Boolean = True)
    If mPrevWndProc <> 0 Then Exit Sub   ' already installed
    
    mFormWnd = WAPI_WindowHandleFromCaption(frm.caption, "ThunderDFrame")
    If mFormWnd = 0 Then Exit Sub
    
    DragAcceptFiles mFormWnd, Abs(enableRealHandling)
    Set mDragForm = frm
    
    mPrevWndProc = SetWindowLongPtr(mFormWnd, GWL_WNDPROC, AddressOf SubClassWndProc)
End Sub

'  ALWAYS call from UserForm_Terminate (or Workbook_BeforeClose) to avoid crashes!
Public Sub TeardownDragDropSafe()
On Error Resume Next
    If mPrevWndProc <> 0 And mFormWnd <> 0 Then _
        SetWindowLongPtr mFormWnd, GWL_WNDPROC, mPrevWndProc
    mPrevWndProc = 0: mFormWnd = 0
    Set mDragForm = Nothing
    mIsHandling = False
End Sub

'====================================================================
'  ––– Private helpers –––
'====================================================================

' Window-proc – STRICTLY minimal, no DoEvents!
Private Function SubClassWndProc(ByVal hWnd As LongPtr, ByVal uMsg As Long, _
                                 ByVal wParam As LongPtr, ByVal lParam As LongPtr) As LongPtr
    If uMsg = WM_DROPFILES Then
        HandleDropSafe wParam
        SubClassWndProc = 0
    Else
        SubClassWndProc = CallWindowProc(mPrevWndProc, hWnd, uMsg, wParam, lParam)
    End If
End Function

Private Sub HandleDropSafe(ByVal hDrop As LongPtr)
    If mIsHandling Or mDragForm Is Nothing Then Exit Sub
    mIsHandling = True
    On Error GoTo EH
    
    Dim files As Long: files = DragQueryFile(hDrop, &HFFFFFFFF, 0, 0)
    Dim i As Long
    
    For i = 0 To files - 1
        Dim nChars As Long: nChars = DragQueryFile(hDrop, i, 0, 0) + 1
        Dim buf As String:  buf = String$(nChars, vbNullChar)
        DragQueryFile hDrop, i, StrPtr(buf), nChars
        buf = left$(buf, InStr(buf, vbNullChar) - 1)
        mDragForm.AddLinkLabel buf          ' <<– UserForm method
    Next i
    
EH:
    DragFinish hDrop
    mIsHandling = False
End Sub

'--------------------------------------------------------------------
'  Pixel / point conversion – DPI aware
'--------------------------------------------------------------------
Public Function PixelsToPointsX(ByVal px As Long) As Single
    PixelsToPointsX = CSng(px) * 72 / GetDpiX
End Function
Public Function PixelsToPointsY(ByVal py As Long) As Single
    PixelsToPointsY = CSng(py) * 72 / GetDpiY
End Function
Public Function PointsToPixelsX(ByVal pt As Single) As Long
    PointsToPixelsX = CLng(pt * GetDpiX / 72)
End Function
Public Function PointsToPixelsY(ByVal pt As Single) As Long
    PointsToPixelsY = CLng(pt * GetDpiY / 72)
End Function

Private Function ScreenDPI(Optional ByVal useY As Boolean = False) As Long
    Dim hDC As LongPtr
    hDC = GetDC(0)
    ScreenDPI = GetDeviceCaps(hDC, IIf(useY, LOGPIXELSY, LOGPIXELSX))
    ReleaseDC 0, hDC
End Function


Public Function GetDpiX() As Long
    Static dpiX As Long
    If dpiX = 0 Then dpiX = GetDeviceCaps(GetDC(0), LOGPIXELSX): ReleaseDC 0, GetDC(0)
    GetDpiX = dpiX
End Function
Public Function GetDpiY() As Long
    Static dpiY As Long
    If dpiY = 0 Then dpiY = GetDeviceCaps(GetDC(0), LOGPIXELSY): ReleaseDC 0, GetDC(0)
    GetDpiY = dpiY
End Function

'--------------------------------------------------------------------
'  Misc helpers
'--------------------------------------------------------------------
'  Robustly locate the top-level window for a UserForm
Public Function WAPI_WindowHandleFromCaption(ByVal caption As String, _
                                      Optional ByVal classHint As String = vbNullString) As LongPtr
    Dim hWnd As LongPtr
    If LenB(classHint) = 0 Then classHint = "ThunderDFrame"
    
    hWnd = FindWindow(classHint, caption)
    If hWnd = 0 Then hWnd = FindWindow(vbNullString, caption)   ' last resort
    
    WAPI_WindowHandleFromCaption = hWnd
End Function

'  Ensure dictionary exists
Private Sub EnsureWindowDictReady()
    If mWindowDict Is Nothing Then Set mWindowDict = CreateObject("Scripting.Dictionary")
End Sub

'--------------------------------------------------------------------
'  Logging (optional – silent in production)
'--------------------------------------------------------------------
Public Sub InitLogFilePath()
    If mLogFilePath <> "" Then Exit Sub
    
    mLogFilePath = ThisWorkbook.path & "\" & LOG_FILE_NAME
    Dim fso As Object: Set fso = CreateObject("Scripting.FileSystemObject")
    If fso.FileExists(mLogFilePath) Then fso.DeleteFile mLogFilePath
    Dim f As Object:  Set f = fso.CreateTextFile(mLogFilePath, True)
    f.WriteLine "Log created " & Now
    f.Close
End Sub

Private Sub LogMsg(ByVal s As String)
    Const DEBUG_MODE As Boolean = False
    If Not DEBUG_MODE Then Exit Sub
    
    InitLogFilePath
    Dim fp As Integer: fp = FreeFile
    Open mLogFilePath For Append As #fp
    Print #fp, Format$(Now, "yyyy-mm-dd hh:nn:ss") & "  " & s
    Close #fp
End Sub

'====================================================================
'  ––– Workbook-level cleanup (call from ThisWorkbook.BEFORECLOSE) –––
'====================================================================
Public Sub WAPI_CleanupAll()
    TeardownDragDropSafe
    If Not mWindowDict Is Nothing Then
        mWindowDict.RemoveAll
        Set mWindowDict = Nothing
    End If
End Sub


