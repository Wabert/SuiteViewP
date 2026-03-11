' Module: cls_FilterHeading.cls
' Type: Class Module
' Stream Path: VBA/cls_FilterHeading
' =========================================================

Attribute VB_Name = "cls_FilterHeading"
Attribute VB_Base = "0{FCFB3D2A-A0FA-1068-A738-08002B3371B5}"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Attribute VB_TemplateDerived = False
Attribute VB_Customizable = False
Private WithEvents mButton As MSForms.Label 'Header button.  Clicking this will display the DropDown listbox of all the values in the column
Attribute mButton.VB_VarHelpID = -1
Private WithEvents mDropDown As MSForms.Listbox 'Lists all the unique values in the filter column.  Clicking these values will apply more filters to the data
Attribute mDropDown.VB_VarHelpID = -1
Private mFB As cls_FilterBox
Private mCol As Integer


Public Sub classInitialize(FB As cls_FilterBox, oButtonLbl As MSForms.Label, oDropDownLbl As MSForms.Listbox, ColumnNumber As Integer)
    Set mFB = FB
    Set mButton = oButtonLbl
    Set mDropDown = oDropDownLbl
    
    With mDropDown
    .IntegralHeight = True
    .Visible = False
    .Backcolor = mButton.Backcolor
    .SpecialEffect = fmSpecialEffectEtched
    .ColumnCount = 1
    .ColumnWidths = "1"
    .MultiSelect = 1
    End With
    mCol = ColumnNumber
End Sub
Public Property Let height(sngHeight As Single)
    mButton.height = sngHeight
End Property
Public Property Get height() As Single
    height = mButton.height
End Property
Public Property Let width(sngWidth As Single)
    mButton.width = sngWidth
    mDropDown.width = sngWidth + 10
End Property
Public Property Get width() As Single
    width = mButton.width
End Property
Public Property Let left(sngLeft As Single)
    mButton.left = sngLeft
    mDropDown.left = sngLeft
End Property
Public Property Get left() As Single
    left = mButton.left
End Property
Public Property Let top(sngTop As Single)
    mButton.top = sngTop
    mDropDown.top = sngTop + mButton.height + 2
End Property
Public Property Get top() As Single
    left = mButton.top
End Property
Public Property Let caption(strCaption As String)
    mButton.caption = strCaption
End Property
Public Property Let SpecialEffect(SpecialEffect As fmSpecialEffect)
    mButton.SpecialEffect = SpecialEffect
End Property
Public Property Let TextAlign(TextAlign As fmTextAlign)
    mButton.TextAlign = TextAlign
End Property
Public Property Get ColumnIndex()
    ColumnIndex = mCol
End Property
Private Sub mDropDown_Change()
    mFB.UpdateFilterDropDowns mDropDown, mCol
    Dim X As Integer
    If mFB.Listbox.ListCount > 0 Then
        For X = 0 To mFB.Listbox.ListCount - 1
            mFB.Listbox.Selected(X) = False
        Next
    End If
End Sub
Private Sub mButton_Click()
    mFB.ButtonUpdate mButton, mDropDown, mCol
End Sub

