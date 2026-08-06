' Module: cls_ListBoxEvents.cls
' Type: Class Module
' Stream Path: VBA/cls_ListBoxEvents
' =========================================================

Attribute VB_Name = "cls_ListBoxEvents"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Option Explicit

' Raise events for other classes to handle
Public Event OnDoubleClick()
Public Event OnClick()

' Single WithEvents reference to the ListBox we're monitoring
Private WithEvents mListbox As MSForms.Listbox
Attribute mListbox.VB_VarHelpID = -1

' Property to set the ListBox we want to monitor
Public Property Set Listbox(lb As MSForms.Listbox)
    Set mListbox = lb
End Property

' Event handler for DblClick
Private Sub mListbox_DblClick(ByVal Cancel As MSForms.ReturnBoolean)
    RaiseEvent OnDoubleClick
End Sub

' Event handler for Click
Private Sub mListbox_Click()
    RaiseEvent OnClick
End Sub

Private Sub Class_Terminate()
    Set mListbox = Nothing
End Sub
